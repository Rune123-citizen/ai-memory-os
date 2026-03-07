#This file contains the core logic for interacting with the SQLite database. It includes functions for initializing the database, inserting new events, and fetching events from the last 24 hours.
import sqlite3
import os

#define the path for the sqlite database
DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

def init_db():
    """Initilaise the database and create the necessary tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    #create the table for storing os events
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            process TEXT NOT NULL,
            window_title TEXT NOT NULL,
            event_type TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    print(f"SQlite Database initialized at {DB_PATH}")

def insert_event(timestamp: str, process: str, window_title: str, event_type: str) -> int:
    """Insert a new event into the database and return its ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO events (timestamp, process, window_title, event_type)
        VALUES (?, ?, ?, ?)
    ''', (timestamp, process, window_title, event_type))

    event_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return event_id

from datetime import datetime, timedelta

def get_todays_events():
    """Fetches all raw events from the last 24 hours directly from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calculate exactly 24 hours ago
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    
    cursor.execute('''
        SELECT timestamp, process, window_title 
        FROM events 
        WHERE timestamp >= ?
    ''', (yesterday,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{"timestamp": r[0], "process": r[1], "window_title": r[2]} for r in rows]


#Run intialization when this file is imported
init_db()