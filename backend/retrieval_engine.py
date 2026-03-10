import sqlite3
from datetime import datetime, timedelta
from backend.database import DB_PATH
from backend.rag_engine import qdrant, COLLECTION_NAME, get_embedding, sparse_model
# Notice the new DatetimeRange import here:
from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, FusionQuery, Fusion, SparseVector, DatetimeRange

def parse_time_range(time_string: str):
    """
    Converts a natural language time string from the LLM into ISO start and end timestamps.
    """
    if not time_string:
        return None, None
        
    now = datetime.now()
    time_lower = time_string.lower()
    
    if "today" in time_lower:
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now
    elif "yesterday" in time_lower:
        start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time.replace(hour=23, minute=59, second=59)
    elif "week" in time_lower:
        start_time = now - timedelta(days=7)
        end_time = now
    elif "month" in time_lower:
        start_time = now - timedelta(days=30)
        end_time = now
    else:
        return None, None # Fallback if we don't recognize the exact phrase
        
    print(f"[RETRIEVAL] Time Filter Active: {start_time.isoformat()} to {end_time.isoformat()}")
    return start_time.isoformat(), end_time.isoformat()

def search_sqlite_keywords(keywords: list, target_app: str = None, start_time: str = None, end_time: str = None) -> list:
    """Searches SQLite directly for exact keyword matches within a specific timeframe."""
    if not keywords and not target_app and not start_time:
        return []
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    results = []
    
    query = "SELECT timestamp, process, window_title, duration_seconds FROM events WHERE"
    conditions = []
    params = []
    
    # 1. App Filter
    if target_app:
        conditions.append("process = ?")
        params.append(target_app)
        
    # 2. Time Filter (Temporal Logic)
    if start_time and end_time:
        conditions.append("timestamp >= ? AND timestamp <= ?")
        params.extend([start_time, end_time])
        
    # 3. Keyword Filter
    keyword_conditions = []
    for kw in keywords:
        keyword_conditions.append("window_title LIKE ?")
        params.append(f"%{kw}%")
        
    if keyword_conditions:
        conditions.append("(" + " OR ".join(keyword_conditions) + ")")
        
    if not conditions:
        return []

    final_query = f"{query} {' AND '.join(conditions)} ORDER BY timestamp DESC LIMIT 20"
    
    try:
        cursor.execute(final_query, params)
        rows = cursor.fetchall()
        for r in rows:
            memory_text = f"App: {r[1]} | Window/File: {r[2]} | Duration: {r[3]}s | Time: {r[0]}"
            results.append({
                "source": "sqlite_exact",
                "timestamp": r[0],
                "text": memory_text
            })
    except Exception as e:
        print(f"[!] SQLite Search Error: {e}")
    finally:
        conn.close()
        
    return results

def search_qdrant_vectors(query_string: str, target_app: str = None, start_time: str = None, end_time: str = None, limit: int = 15) -> list:
    """Searches Qdrant using Hybrid vectors, filtering by App and Time."""
    if not query_string:
        return []
        
    results = []
    
    try:
        query_dense = get_embedding(query_string)
        query_sparse_result = list(sparse_model.embed([query_string]))[0]
        query_sparse = SparseVector(
            indices=query_sparse_result.indices.tolist(), 
            values=query_sparse_result.values.tolist()
        )
        
        # Build strict filters
        must_conditions = []
        
        # 1. App Filter
        if target_app:
            must_conditions.append(FieldCondition(key="process", match=MatchValue(value=target_app)))
            
        # 2. Time Filter using Qdrant's DatetimeRange
        if start_time and end_time:
            must_conditions.append(FieldCondition(
                key="timestamp", 
                range=DatetimeRange(gte=start_time, lte=end_time)
            ))
            
        query_filter = Filter(must=must_conditions) if must_conditions else None

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
        
        for hit in search_response.points:
            if hit.payload and "timestamp" in hit.payload:
                results.append({
                    "source": "qdrant_vector",
                    "timestamp": hit.payload["timestamp"],
                    "text": hit.payload["text"],
                    "score": hit.score,
                    "importance": hit.payload.get("importance", 0.5)
                })
                
    except Exception as e:
        print(f"[!] Qdrant Search Error: {e}")
        
    return results

def retrieve_memories(parsed_query: dict) -> list:
    """Master retrieval function. Combines SQL and Vector searches with Temporal Bounds."""
    target_app = parsed_query.get("app")
    keywords_list = parsed_query.get("keywords", [])
    time_string = parsed_query.get("time_range")
    
    query_string = " ".join(keywords_list) if isinstance(keywords_list, list) else str(keywords_list)
    
    # Calculate the hard time bounds
    start_time, end_time = parse_time_range(time_string)
    
    print(f"\n[RETRIEVAL] Firing search - App: '{target_app}', Time: '{time_string}', Keywords: '{query_string}'")
    
    # Pass the time bounds down to the search engines
    sqlite_results = search_sqlite_keywords(keywords_list, target_app, start_time, end_time)
    qdrant_results = search_qdrant_vectors(query_string, target_app, start_time, end_time)
    
    print(f"[RETRIEVAL] Found {len(sqlite_results)} exact SQLite matches and {len(qdrant_results)} Qdrant semantic matches.")
    
    # Merge and remove duplicates using timestamps
    merged_memories = {}
    for mem in sqlite_results:
        merged_memories[mem["timestamp"]] = mem
    for mem in qdrant_results:
        merged_memories[mem["timestamp"]] = mem
        
    final_list = list(merged_memories.values())
    print(f"[RETRIEVAL] Merged into {len(final_list)} unique raw memories.")
    
    return final_list