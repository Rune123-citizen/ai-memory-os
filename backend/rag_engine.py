import requests
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

#connect to local qdrant instance runnign in docker
qdrant=QdrantClient("http://localhost:6333")
COLLECTION_NAME = "memory_events"

#nomic-embed-key outputs vectors with 768 dimensions
try:
    qdrant.get_collection(COLLECTION_NAME)
except Exception:
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE)
    )
    print(f"Created Qdrant collection: {COLLECTION_NAME}")

def get_embedding(text: str) -> list[float]:
    """Asks the local ollama to convert text into a mathematical vector."""
    url = "http://localhost:11434/api/embeddings"
    payload = {
        "model": "nomic-embed-text",
        "prompt": text
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["embedding"]

def store_in_vector_db(sqlite_id: int, timestamp: str, process: str, window_title: str):
    """Converts the Os event into a sentence,embeds it and saves to qdrant."""

    #we turn raw data into a human-readable memory
    memory_text= f"At {timestamp}, the user was working in {process} on {window_title}."

    try:
        #1.get the vector from ollama(phi3)
        vector = get_embedding(memory_text)

        #2.save it to qdrant alongside the original sqlite id
        point_id =  str(uuid.uuid4())  #generate a unique id for qdrant
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "sqlite_id": sqlite_id,
                        "timestamp": timestamp,
                        "process": process,
                        "window_title": window_title,
                        "text": memory_text
                    }
                )
            ]
        )
        print(f"[VECTOR DB] saved semantic memory: '{memory_text}'")
    except Exception as e:
        print(f"[!] failed to store in vector DB: {e}")

def search_vector_db(query_text: str, limit: int = 15) -> str:
    """Embeds the users question and retreives the most relevant memories from qdrant."""
    try:
        print(f"\n[SEARCH] 1.Embedding question: '{query_text}'")
        #1.convert the question into a vector
        query_vector = get_embedding(query_text)
        
        print(f"[SEARCH] 2.Querying Qdrant database...")
        #2.search qdrant for the closest matching os events stored
        search_response = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
            with_payload=True  #we want the original text back, not just the vector
        )
        search_result= search_response.points

        print(f"[SEARCH] 3. Found {len(search_result)} relevant memories.")
        #3.extract the text payload from the results
        if not search_result:
            return ""
        
        context_lines = []
        for hit in search_result:
            if hit.payload and "text" in hit.payload:
                context_lines.append(hit.payload["text"])
        
        final_context = "\n".join(context_lines)
        print(f"[SEARCH] 4.Context successfully extracted: {len(context_lines)} lines.")
        return final_context
    
    except Exception as e:
        print(f"[!] failed to search vector DB: {e}")
        return ""

def generate_answer(question: str, context: str) -> str:
    """Sends the retrieved context and the question to local phi3."""
    
    prompt = f"""You are JARVIS, a highly analytical and precise Personal Memory OS. 
Your job is to answer the user's question based STRICTLY on the provided timeline of their computer activity.
Rules:
1. Output your response in clean, concise bullet points.
2. Be direct and highly analytical. 
3. Never apologize. If the answer is not in the context, simply state: "No records found for this query."
4. Do not invent or guess any information.

Activity Context:
{context}

User Question: {question}

Answer:"""

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "phi3",
        "prompt": prompt,
        "stream": False 
    }
    
    try:
        print("\n[AI] Thinking... (Sending data to Ollama)")
        response = requests.post(url, json=payload)
        response.raise_for_status() # This will catch if Ollama returns an error code
        return response.json()["response"]
    except Exception as e:
        print(f"[!] AI Generation failed: {e}")
        return f"Error connecting to AI: {e}"