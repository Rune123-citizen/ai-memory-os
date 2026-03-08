from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import sqlite3
from collections import Counter
from backend.database import insert_event, DB_PATH, get_todays_events
from backend.rag_engine import store_in_vector_db, search_vector_db, generate_answer, qdrant, COLLECTION_NAME, extract_query_metadata

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
        event_id = insert_event(
            timestamp=event.timestamp,
            process=event.process,
            window_title=event.window_title,
            event_type=event.event_type,
            duration_seconds=event.duration_seconds
        )

        background_tasks.add_task(
            store_in_vector_db,
            sqlite_id=event_id,
            timestamp=event.timestamp,
            process=event.process,
            window_title=event.window_title,
            duration=event.duration_seconds
        )

        return {"status": "Success","message": "Event stored and embedding queued."}
    except Exception as e:
        print(f"[API ERROR] Failed to store event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest event: {str(e)}")
    
class QueryPayload(BaseModel):
    question: str

@app.post("/query")
def query_memory(payload: QueryPayload):
    try:
        # Step 1: Route and clean the query
        metadata = extract_query_metadata(payload.question)
        clean_keywords = metadata.get("keywords", payload.question)
        
        # --- SAFETY CHECK: Squash lists into a string ---
        if isinstance(clean_keywords, list):
            clean_keywords = " ".join(clean_keywords)
        elif not isinstance(clean_keywords, str):
            clean_keywords = str(clean_keywords)
            
        # --- AGGRESSIVE ALIAS MAPPING ---
        target_app = metadata.get("app_name")
        
        app_aliases = {
            "vs code": "Code.exe",
            "vscode": "Code.exe",
            "visual studio code": "Code.exe",
            "code": "Code.exe",
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "powershell": "WindowsTerminal.exe",
            "terminal": "WindowsTerminal.exe",
            "windows terminal": "WindowsTerminal.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "windows explorer": "explorer.exe"
        }

        # FIX 1: If the AI missed the app name, fish it out of the keywords
        if not target_app:
            lower_keywords = clean_keywords.lower()
            for alias in app_aliases.keys():
                if alias in lower_keywords:
                    target_app = alias
                    print(f"[ROUTER] Fished app name '{alias}' out of keywords.")
                    break

        # FIX 2: Normalize the string and strip hallucinated '.exe' tags
        if target_app and isinstance(target_app, str):
            clean_target = target_app.lower().strip()
            
            # If the AI added '.exe' to human slang (e.g., "vs code.exe"), strip it
            if clean_target.endswith(".exe") and clean_target not in app_aliases.values():
                clean_target = clean_target[:-4].strip()
            
            # Map to the exact OS process name
            if clean_target in app_aliases:
                final_target = app_aliases[clean_target]
                print(f"[ROUTER] Alias mapped '{target_app}' -> '{final_target}'")
                target_app = final_target
            elif clean_target in [val.lower() for val in app_aliases.values()]:
                # If it already extracted exactly "code.exe", keep it!
                pass 
        # -----------------------------------------------------------

        # Step 2: Retrieve relevant context from Qdrant using Hybrid Search & Filters
        context = search_vector_db(clean_keywords, target_process=target_app)

        if not context:
            return {
                "question": payload.question,
                "answer": "No records found for this query.",
                "context_used": []
            }
        
        # Step 3: Generate the answer using phi3
        answer = generate_answer(payload.question, context)

        return {
            "question": payload.question,
            "extracted_metadata": metadata,
            "answer": answer.strip(),
            "context_used": context.split("\n") 
        }
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

@app.get("/query/today")
def query_today():
    try:
        events = get_todays_events()
        if not events:
            return {"answer": "No activity recorded in the last 24 hours."}
        
        summary_counts = Counter()
        for e in events:
            key = f"{e['process']} - '{e['window_title']}'"
            summary_counts[key] += e['duration_seconds']

        context_lines = [f"Used {item} for {count} seconds" for item, count in summary_counts.items()]
        context_text = "\n".join(context_lines)

        print(f"[API] compressed {len(events)} raw events into {len(context_lines)} unique activities for the AI")

        prompt = "Summarize my computer activity for today based on these aggregate logs. Group your answer by application or project and mention time spent."
        answer = generate_answer(prompt, context_text)

        return {"answer": answer, "raw_events_processed": len(events)}
    except Exception as e:
        print(f"[API] Error in query/today: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
@app.post("/consolidate")
def consolidate_memory():
    try:
        events = get_todays_events()
        if not events:
            return {"message": "Nothing to consolidate today."}
            
        context_lines = [f"Used {e['process']} on '{e['window_title']}' for {e['duration_seconds']}s" for e in events]
        context_text = "\n".join(context_lines)
        
        summary_prompt = "Write a dense, 2-paragraph summary of what the user accomplished based on this activity log. Focus on the main themes and projects."
        daily_summary = generate_answer(summary_prompt, context_text)
        
        store_in_vector_db(
            sqlite_id=0,
            timestamp=datetime.now().isoformat(),
            process="System",
            window_title="Daily Consolidation",
            duration=0
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