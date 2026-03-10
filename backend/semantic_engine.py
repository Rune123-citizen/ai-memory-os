import re
from backend.database import get_unprocessed_events, mark_events_processed
from backend.rag_engine import store_in_vector_db

def classify_activity(process: str, title: str):
    """Step 4 - Activity Classification"""
    process = process.lower()
    title = title.lower()
    
    if "code" in process or "idea" in process or "pycharm" in process:
        parts = title.split(" - ")
        project = parts[1] if len(parts) > 1 else parts[0]
        return "Coding", project.strip(), 0.9
    
    elif "chrome" in process or "edge" in process or "firefox" in process:
        if "github" in title or "stackoverflow" in title or "docs" in title:
            return "Research", "Documentation/Code", 0.7
        
        elif "youtube" in title or "netflix" in title:
            return "Entertainment", "Media", 0.2
        
        else:
            return "Browsing", "Web", 0.4
        
    elif "teams" in process or "slack" in process or "discord" in process:
        return "Communication", "Team Sync", 0.8
    
    elif "terminal" in process or "powershell" in process or "cmd" in process:
        return "Debugging", "Terminal", 0.85
    
    else:
        return "General", process, 0.3

def build_sessions():
    """Step 5 & 6 - Session Builder and Importance Scoring"""
    events = get_unprocessed_events()
    
    # Wait until we have a batch of at least 5 events to form meaningful sessions
    if len(events) < 5: 
        return 
        
    sessions = {} 
    processed_ids = []
    
    for e in events:
        processed_ids.append(e['id'])
        act, proj, weight = classify_activity(e['process'], e['window_title'])
        
        # Group by Activity and Project
        key = f"{act}_{proj}"
        if key not in sessions:
            sessions[key] = {
                'activity': act,
                'project': proj,
                'weight': weight,
                'duration': 0,
                'start_time': e['timestamp'],
                'end_time': e['timestamp'],
                'frequency': 0,
                'keywords': set()
            }
        
        s = sessions[key]

        try:
            duration_val = int(e.get('duration_seconds', 0))
        
        except (ValueError, TypeError):
            duration_val = 0
        
        # --- FIX: Explicitly convert duration to an integer before adding ---
        s['duration'] += duration_val
        
        s['end_time'] = e['timestamp']
        s['frequency'] += 1
        
        # Extract keywords for scoring
        words = [w for w in re.split(r'\W+', e['window_title'].lower()) if len(w) > 3]
        s['keywords'].update(words)

    for s in sessions.values():
        # Step 6 - Memory Importance Scoring Algorithm
        dur_score = min(s['duration'] / 3600.0, 1.0) # 1 hour maxes duration score
        freq_score = min(s['frequency'] / 20.0, 1.0) # 20 switches maxes frequency
        kw_score = min(len(s['keywords']) / 10.0, 1.0) # 10 unique words maxes keywords
        
        importance = (0.4 * dur_score) + (0.3 * s['weight']) + (0.2 * kw_score) + (0.1 * freq_score)
        importance = round(min(importance, 1.0), 3) 
        
        session_text = f"Activity: {s['activity']} | Project: {s['project']} | Duration: {s['duration']}s | Time: {s['start_time']} to {s['end_time']}"
        
        # Store the aggregated session, not the individual clicks!
        store_in_vector_db(
            sqlite_id=0,
            timestamp=s['end_time'],
            process=s['activity'], 
            window_title=s['project'],
            duration=s['duration'],
            importance=importance,
            text_override=session_text
        )
        
    mark_events_processed(processed_ids)