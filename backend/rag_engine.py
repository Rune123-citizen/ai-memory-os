import requests
import uuid
import json
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct, 
    SparseVectorParams, SparseVector, 
    Prefetch, FusionQuery, Fusion,
    Filter, FieldCondition, MatchValue
)

qdrant = QdrantClient("http://localhost:6333")
COLLECTION_NAME = "neurolayer_memory_hybrid"

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
    url = "http://localhost:11434/api/embeddings"
    payload = {"model": "nomic-embed-text", "prompt": text}
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["embedding"]

def extract_query_metadata(question: str) -> dict:
    print(f"\n[ROUTER] Extracting metadata from: '{question}'")
    
    # --- UPDATED STRICT PROMPT ---
    prompt = f"""You are a query router. Extract the core search terms from this question.
Question: {question}

Output ONLY a valid JSON object with two keys:
1. 'app_name': The specific application mentioned (e.g., 'Code.exe', 'chrome.exe'). If none, output null.
2. 'keywords': The core topic they are looking for, without filler words (MUST be a single string, NOT a list).

JSON Output:"""

    url = "http://localhost:11434/api/generate"
    payload = {"model": "phi3:mini", "prompt": prompt, "stream": False, "format": "json"}
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        parsed_data = json.loads(response.json()["response"])
        print(f"[ROUTER] Extracted Data: {parsed_data}")
        return parsed_data
    except Exception as e:
        print(f"[!] Router failed, falling back to raw question. Error: {e}")
        return {"app_name": None, "keywords": question}

def store_in_vector_db(sqlite_id: int, timestamp: str, process: str, window_title: str, duration: int):
    memory_text = f"App: {process} | Window/File: {window_title} | Duration: {duration}s | Time: {timestamp}"

    try:
        dense_vector = get_embedding(memory_text)
        sparse_result = list(sparse_model.embed([memory_text]))[0]
        sparse_vector = {
            "indices": sparse_result.indices.tolist(), 
            "values": sparse_result.values.tolist()
        }

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

def search_vector_db(query_text: str, target_process: str = None, limit: int = 15) -> str:
    try:
        print(f"\n[SEARCH] 1. Embedding query for Hybrid Search: '{query_text}'")
        
        query_dense = get_embedding(query_text)
        query_sparse_result = list(sparse_model.embed([query_text]))[0]
        query_sparse = SparseVector(
            indices=query_sparse_result.indices.tolist(), 
            values=query_sparse_result.values.tolist()
        )
        
        query_filter = None
        if target_process:
            query_filter = Filter(must=[FieldCondition(key="process", match=MatchValue(value=target_process))])

        print(f"[SEARCH] 2. Querying Qdrant database using Reciprocal Rank Fusion...")
        
        search_response = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(query=query_dense, using="dense", limit=limit, filter=query_filter),
                Prefetch(query=query_sparse, using="sparse", limit=limit, filter=query_filter)
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True
        )
        
        search_result = search_response.points
        print(f"[SEARCH] 3. Found {len(search_result)} relevant memories.")

        if not search_result:
            return ""
        
        valid_hits = [hit for hit in search_result if hit.payload and "timestamp" in hit.payload]
        valid_hits.sort(key=lambda x: x.payload["timestamp"])
        
        context_lines = [hit.payload["text"] for hit in valid_hits]
        return "\n".join(context_lines)
    
    except Exception as e:
        print(f"[!] Failed to search vector DB: {e}")
        return ""

def generate_answer(question: str, context: str) -> str:
    prompt = f"""You are JARVIS, a highly analytical and precise Personal Memory OS. 
Your job is to answer the user's question based STRICTLY on the provided timeline of their computer activity.

Rules:
1. Output your response in clean, concise bullet points.
2. Be direct and highly analytical. 
3. CRITICAL: If the provided context does not explicitly contain the application, project, or information requested, YOU MUST reply: "No records found for this query." Do NOT invent, assume, or substitute information.
4. Factor in the duration of the tasks to provide better context if relevant.

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