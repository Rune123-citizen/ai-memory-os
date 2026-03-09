import requests
import uuid
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from datetime import datetime
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

def store_in_vector_db(sqlite_id: int, timestamp: str, process: str, window_title: str, duration: int):
    """Converts the OS event into structured text, embeds (Dense+Sparse), and saves to Qdrant."""
    memory_text = f"App: {process} | Window/File: {window_title} | Duration: {duration}s | Time: {timestamp}"

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
                        "text": memory_text
                    }
                )
            ]
        )
        print(f"[VECTOR DB] Saved hybrid memory: '{memory_text}'")
    except Exception as e:
        print(f"[!] Failed to store in vector DB: {e}")

def generate_answer(question: str, context: str) -> str:
    """Sends the retrieved context and the question to local phi3."""
    
    # Give the AI a sense of time so it can understand "yesterday", "today", etc.
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    
    prompt = f"""You are JARVIS, a highly analytical and precise Personal Memory OS. 
Current System Time: {current_time}

Your job is to answer the user's question based STRICTLY on the provided timeline of their computer activity.

Rules:
1. Output your response in clean, concise bullet points.
2. Be direct and highly analytical. 
3. The context uses system process names (e.g., 'Code.exe' is VS Code, 'chrome.exe' is Google Chrome). Map these intelligently to the user's request.
4. If the provided context does not contain the requested information, reply ONLY: "No records found for this query."
5. Factor in the duration of the tasks and timestamps to provide an accurate timeline.

Activity Context:
{context}

User Question: {question}

Answer:"""

    url = "http://localhost:11434/api/generate"
    payload = {"model": "phi3:mini", "prompt": prompt, "stream": False}
    
    try:
        print("\n[AI] Thinking... (Sending data to Ollama)")
        response = requests.post(url, json=payload)
        response.raise_for_status() 
        return response.json()["response"]
    except Exception as e:
        print(f"[!] AI Generation failed: {e}")
        return f"Error connecting to AI: {e}"