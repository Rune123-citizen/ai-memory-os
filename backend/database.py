import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            process TEXT NOT NULL,
            window_title TEXT NOT NULL,
            event_type TEXT NOT NULL,
            duration_seconds INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    print(f"SQlite Database initialized at {DB_PATH}")

def insert_event(timestamp: str, process: str, window_title: str, event_type: str, duration_seconds: int = 0) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO events (timestamp, process, window_title, event_type, duration_seconds)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, process, window_title, event_type, duration_seconds))

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id

def get_todays_events():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    
    cursor.execute('''
        SELECT timestamp, process, window_title, duration_seconds
        FROM events 
        WHERE timestamp >= ?
    ''', (yesterday,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{"timestamp": r[0], "process": r[1], "window_title": r[2], "duration_seconds": r[3]} for r in rows]

init_db()