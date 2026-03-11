from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sqlite3
from collections import Counter



from backend.database import insert_event, DB_PATH, get_todays_events
from backend.rag_engine import store_in_vector_db, generate_answer, qdrant, COLLECTION_NAME

# --- NEW MODULAR PIPELINE IMPORTS ---
from backend.query_parser import parse_query
from backend.retrieval_engine import retrieve_memories
from backend.context_ranker import rank_memories
from backend.semantic_engine import build_sessions

app = FastAPI(title="NeuroLayer OS Backend")

class EventPayload(BaseModel):
    timestamp: str
    process: str
    window_title: str
    event_type: str
    duration_seconds: int = 0

@app.get("/")
def read_root():
    return {"status": "NeuroLayer OS Backend is running!"}

@app.post("/ingest")
def ingest_event(event: EventPayload, background_tasks: BackgroundTasks):
    try:
        insert_event(
            timestamp=event.timestamp,
            process=event.process,
            window_title=event.window_title,
            event_type=event.event_type,
            duration_seconds=event.duration_seconds
        )

        #trigger session builder in the background after every new event. It will batch process unprocessed events every minute or when it hits a batch of 5.
        background_tasks.add_task(build_sessions)

        return {"status": "Success","message": "Event stored and session builder queued."}
    except Exception as e:
        print(f"[API ERROR] failed to store event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest event: {str(e)}")
    
class QueryPayload(BaseModel):
    question: str

@app.post("/query/stream")
def query_memory(payload: QueryPayload):
    """
    Executes the modular Phase 1 RAG Pipeline:
    Parser -> Hybrid Retrieval -> Context Ranker -> Generation
    """
    try:
        # Step 1: Query Understanding (Extracts JSON filters & aliases)
        parsed_query = parse_query(payload.question)
        
        # Step 2: Hybrid Retrieval (Queries SQLite & Qdrant, merges results)
        raw_memories = retrieve_memories(parsed_query)
        
        # Step 3: Context Ranking (Scores by Similarity, Importance, Recency)
        # We only pass the absolute best 5 memories to the LLM to save context.
        context = rank_memories(raw_memories, top_k=5)

        if not context:
            def empty_response():
                yield "No records found for this query."
            return StreamingResponse(empty_response(), media_type="text/event-stream")
        
        # Step 4: Final AI Generation (JARVIS reads the ranked timeline)
        generator = generate_answer(payload.question, context)
        return StreamingResponse(generator, media_type="text/event-stream")

    except Exception as e:
        print(f"[API] Query Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/debug")
def debug_status():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events")
    db_count = cursor.fetchone()[0]
    conn.close()

    try:
        qdrant_info = qdrant.get_collection(COLLECTION_NAME)
        vector_count = qdrant_info.points_count
    except Exception as e:
        vector_count = f"Error: {e}"
    
    return {
        "sqlite_events": db_count,
        "qdrant_vectors": vector_count
    }

    
@app.post("/consolidate")
def consolidate_memory():
    """Long term memory & deecay system."""
    try:
        events = get_todays_events()
        if not events:
            return {"message": "Nothing to consolidate today."}
            
        context_lines = [f"Used {e['process']} on '{e['window_title']}' for {e['duration_seconds']}s" for e in events]
        context_text = "\n".join(context_lines)
        
        summary_prompt = "Write a dense, 2-paragraph summary of what the user accomplished based on this activity log. Focus on the main themes and projects, and tasks."

        #consumes the stream
        stream = generate_answer(summary_prompt, context_text)
        daily_summary = "".join([chunk for chunk in stream])
        
        summary_text = f"Daily summary ({datetime.now().strftime('%B %d')}): {daily_summary}"
        
        store_in_vector_db(
            sqlite_id=0,
            timestamp=datetime.now().isoformat(),
            process="System",
            window_title="Daily Summary",
            duration=86400,
            importance=1.0,
            text_override=summary_text
        )

        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        cursor.execute("DELETE FROM events WHERE timestamp < ?", (now_str,)) 
        conn.commit()
        conn.close()
        
        return {"status": "success", "message": "Memory consolidated and raw logs cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/debug/today")
def debug_today():
    events = get_todays_events()
    return {"total_events_today": len(events), "data": events}