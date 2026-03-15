import requests
import uuid
import json
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from datetime import datetime,timedelta
from qdrant_client.models import (
    VectorParams, Distance, PointStruct, 
    SparseVectorParams
)

# Connect to local Qdrant instance
qdrant = QdrantClient("http://localhost:6333")
COLLECTION_NAME = "neurolayer_memory_hybrid"

# Load FastEmbed BM25 model for keyword search
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

try:
    qdrant.get_collection(COLLECTION_NAME)
except Exception:
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={"dense": VectorParams(size=768, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()}
    )
    print(f"Created Hybrid Qdrant collection: {COLLECTION_NAME}")

def get_embedding(text: str) -> list[float]:
    """Asks the local ollama to convert text into a dense mathematical vector."""
    url = "http://localhost:11434/api/embeddings"
    payload = {"model": "nomic-embed-text", "prompt": text}
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["embedding"]

def store_in_vector_db(sqlite_id: int, timestamp: str, process: str, window_title: str, duration: int, importance: float = 0.5, text_override: str = None):
    """Embeds memory and saves to qdrant with importance scoring"""
    memory_text = text_override if text_override else f"App: {process} | Window/File: {window_title} | Duration: {duration}s | Time: {timestamp}"

    try:
        # 1. Get Dense Vector (from Ollama)
        dense_vector = get_embedding(memory_text)

        # 2. Get Sparse Vector (from FastEmbed BM25)
        sparse_result = list(sparse_model.embed([memory_text]))[0]
        sparse_vector = {
            "indices": sparse_result.indices.tolist(), 
            "values": sparse_result.values.tolist()
        }

        # 3. Save both to Qdrant
        point_id = str(uuid.uuid4())
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector={"dense": dense_vector, "sparse": sparse_vector},
                    payload={
                        "sqlite_id": sqlite_id,
                        "timestamp": timestamp,
                        "process": process,
                        "window_title": window_title,
                        "duration_seconds": duration,
                        "importance": importance,
                        "text": memory_text
                    }
                )
            ]
        )
        print(f"[VECTOR DB] Saved hybrid memory: '{memory_text}' (Importance: {importance})")
    except Exception as e:
        print(f"[!] Failed to store in vector DB: {e}")


def generate_answer(question: str, context: str):
    """Sends the retrieved context and the question to local phi3."""
    
    # Give the AI a sense of time so it can understand "yesterday", "today", etc.
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    
    prompt = f"""You are JARVIS, an intelligent, conversational Personal Memory OS assistant.
You have access to a database of the user's recent computer activity.
current system time:{current_time}

Strict Rules:
1. Answer the user's question using ONLY the 'Activity Context' below.
2. If the context contains multiple events, list them clearly.
3. CRITICAL: You must report the EXACT 'Duration' and 'Time' numbers provided in the context. Do NOT guess, alter, mix up, or calculate new numbers. 
4. NEVER invent or hallucinate computer activity.

Activity Context:
{context}

User Question: {question}

Answer:"""

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "phi3:mini",
        "prompt": prompt, 
        "stream": True,
        "options": {
            "temperature": 0.1,
            "num_predict": 800,
            "num_ctx": 2048,
            "stop":["User Question:","\nUser Question","Activity Context:"]
        }
    }
    
    try:
        print("\n[AI] Thinking... (Sending data to Ollama)")
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status() 

        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if "response" in chunk:
                    yield chunk["response"]
    except Exception as e:
        print(f"[!] AI Generation failed: {e}")
        return f"Error connecting to AI: {e}"


def stream_general_chat(question: str):
    """Sends a general query to phi3 without the strict OS memory constraints."""
    
    prompt = f"""You are an intelligent, helpful AI assistant. Answer the user's general question naturally and accurately.

User Question: {question}

Answer:"""

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "phi3:mini",
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.6, # Slightly higher temperature for more natural, creative chatting
            "num_predict": 300,
            "num_ctx": 2048
        }
    }
    
    try:
        print("\n[AI] Thinking... (General Chat Mode)")
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status() 

        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if "response" in chunk:
                    yield chunk["response"] 
    except Exception as e:
        print(f"[!] AI Generation failed: {e}")
        yield f"Error connecting to AI: {e}"