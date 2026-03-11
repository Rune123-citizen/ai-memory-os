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
            duration_seconds INTEGER DEFAULT 0,
            is_processed INTEGER DEFAULT 0
        )
    ''')

    # Failsafe: Add column to existing DB if upgrading
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN is_processed INTEGER DEFAULT 0")
    except:
        pass

    conn.commit()
    conn.close()
    print(f"SQlite Database initialized at {DB_PATH}")

def insert_event(timestamp: str, process: str, window_title: str, event_type: str, duration_seconds: int = 0) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO events (timestamp, process, window_title, event_type, duration_seconds, is_processed)
        VALUES (?, ?, ?, ?, ?, 0)
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

def get_unprocessed_events():
    """Fetches raw logs that haven't been grouped into sessions yet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # We are selecting 6 columns: id (0), timestamp (1), process (2), window_title (3), event_type (4), duration_seconds (5)
    cursor.execute("SELECT id, timestamp, process, window_title, event_type, duration_seconds FROM events WHERE is_processed = 0 ORDER BY timestamp ASC")

    rows = cursor.fetchall()
    conn.close()
    
    # FIX: Correctly mapping duration_seconds to r[5] instead of r[4]
    return [{"id": r[0], "timestamp": r[1], "process": r[2], "window_title": r[3], "duration_seconds": r[5]} for r in rows]

def mark_events_processed(event_ids: list):
    """Marks raw logs as processed so they aren't batched again"""
    if not event_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE events SET is_processed = 1 WHERE id IN ({','.join('?' * len(event_ids))})", event_ids)
    conn.commit()
    conn.close()

init_db()