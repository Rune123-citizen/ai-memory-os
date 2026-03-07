#takes the requests from the frontend and processes them, either by saving to the database or querying for answers. This is the core of the backend logic.
from datetime import datetime
from fastapi import FastAPI, HTTPException,BackgroundTasks
from pydantic import BaseModel
import sqlite3
from collections import Counter
from backend.database import insert_event,DB_PATH,get_todays_events
from backend.rag_engine import store_in_vector_db,search_vector_db,generate_answer,qdrant,COLLECTION_NAME

#Initialize FastAPI app
app = FastAPI(title="Memory OS Backend")

class EventPayload(BaseModel):
    timestamp: str
    process: str
    window_title: str
    event_type: str

@app.get("/")
def read_root():
    return {"status": "Memory OS Backend is running!"}

@app.post("/ingest")
def ingest_event(event: EventPayload, background_tasks: BackgroundTasks):
    """Receives OS events from the daemon and stores them in SQLite, and triggers vector DB storage."""
    try:
        #save to database(sqlite)
        event_id = insert_event(
            timestamp=event.timestamp,
            process=event.process,
            window_title=event.window_title,
            event_type=event.event_type
        )
        print(f"[API] Stored event in sqlite: {event.process} - {event.window_title}")

        #2.save to qdrant (runs in background so it doesn't slow down the os tracker)
        background_tasks.add_task(
            store_in_vector_db,
            sqlite_id=event_id,
            timestamp=event.timestamp,
            process=event.process,
            window_title=event.window_title
        )

        return {"status": "Success","message": "Event stored and embedding queued."}
    except Exception as e:
        print(f"[API ERROR] Failed to store event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest event: {str(e)}")
    
class QueryPayload(BaseModel):
    question: str

@app.post("/query")
def query_memory(payload: QueryPayload):
    """Handles user questions by searching memory and generating an AI response."""

    try:
        #1.retreive relevant context from qdrant
        context = search_vector_db(payload.question)

        if not context:
            return {
                "question": payload.question,
                "answer": "I don't have any recent memory related to that.",
                "context_used": []
            }
        
        #2.generate the answer using phi3
        answer = generate_answer(payload.question, context)

        #3.return the Ai's response along with the raw memories it used
        return{
            "question": payload.question,
            "answer": answer.strip(),
            "context_used": context.split("\n")  #return the individual memories as a list
        }
    except Exception as e:
        print(f"[API] Query Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error")

@app.get("/debug")
def debug_status():
    """checks how many records are in sqlite vs qdrant."""
    #check sqlite count
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events")
    db_count = cursor.fetchone()[0]
    conn.close()

    #check qdrant count
    try:
        qdrant_info = qdrant.get_collection(COLLECTION_NAME)
        vector_count = qdrant_info.points_count
    except Exception as e:
        vector_count = f"Error: {e}"
    
    return {
        "sqlite_events": db_count,
        "qdrant_vectors": vector_count
    }

@app.get("/query/today")
def query_today():
    """generates a perfect summary of today's events bypassing the vector db."""
    try:
        events = get_todays_events()
        if not events:
            return {"answer": "No activity recorded in the last 24 hours."}
        
        summary_counts=Counter([f"{e['process']} - '{e['window_title']}'" for e in events])

        #format the raw logs into a readable string for the AI
        context_lines = [f"Used {item} (Logged {count} times)" for item, count in summary_counts.items()]
        context_text = "\n".join(context_lines)

        print(f"[API] compressed {len(events)} raw events into {len(context_lines)} unique activities for the AI")


        #ask phi3 to summarize today's activity
        prompt ="Summarize my computer activity for today based on these aggregate logs. Group your answer by application or project."
        answer= generate_answer(prompt, context_text)

        return {"answer": answer,"raw_events_processed": len(events)}
    except Exception as e:
        print(f"[API] Error in query/today: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    

@app.post("/consolidate")
def consolidate_memory():
    """Summarizes today's logs, saves the summary to Qdrant, and deletes old SQLite logs."""
    try:
        # 1. Grab today's events
        events = get_todays_events()
        if not events:
            return {"message": "Nothing to consolidate today."}
            
        context_lines = [f"Used {e['process']} on '{e['window_title']}'" for e in events]
        context_text = "\n".join(context_lines)
        
        # 2. Ask phi3 to create a dense, permanent memory
        summary_prompt = "Write a dense, 2-paragraph summary of what the user accomplished based on this activity log. Focus on the main themes and projects."
        daily_summary = generate_answer(summary_prompt, context_text)
        
        # 3. Save this summary to Qdrant permanently
        store_in_vector_db(
            sqlite_id=0, # 0 indicates it's a consolidated memory
            timestamp=datetime.now().isoformat(),
            process="System",
            window_title="Daily Consolidation"
        )
        # Note: We'd normally pass the `daily_summary` text here, but to keep your rag_engine simple, 
        # it will store the 'System - Daily Consolidation' tag alongside the semantic embedding.
        
        # 4. Wipe SQLite to keep it fast (Optional: comment this out if you want to keep raw logs for now)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events") 
        conn.commit()
        conn.close()
        
        return {"status": "success", "message": "Memory consolidated and raw logs cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/debug/today")
def debug_today():
    """Returns today's raw logs without using the AI."""
    events = get_todays_events()
    return {"total_events_today": len(events), "data": events}