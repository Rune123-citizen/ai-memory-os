import time
import win32gui
import win32api
import win32process
import psutil
import requests
from datetime import datetime

BACKEND_URL = "http://localhost:8000/ingest"

def get_active_window_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return {
            "process_name": process.name(),
            "window_title": window_title
        }
    except Exception:
        return None

def clean_title(title: str) -> str:
    parts = title.split(" - ")
    if len(parts) > 1:
        return parts[0].strip()
    return title.strip()

def get_idle_time():
    last_input = win32api.GetLastInputInfo()
    current_tick = win32api.GetTickCount()
    return (current_tick - last_input) / 1000.0

def run_tracker(poll_interval=5, idle_threshold=180):
    print(f"[*] Starting OS Context Tracker. Polling every {poll_interval} seconds...")
    last_window_title = ""
    last_process = ""
    start_time = time.time()

    while True:
        idle_time = get_idle_time()
        
        if idle_time > idle_threshold:
            print(f"[IDLE] User inactive for {int(idle_time)}s. Pausing tracking...")
            time.sleep(poll_interval)
            continue

        window_info = get_active_window_info()
        
        if window_info:
            raw_title = window_info["window_title"]
            cleaned_title = clean_title(raw_title)
            process_name = window_info["process_name"]
            
            if cleaned_title != last_window_title and cleaned_title != "":
                end_time = time.time()
                duration_seconds = int(end_time - start_time)
                
                if duration_seconds > 3 and last_window_title != "":
                    event_data = {
                        "timestamp": datetime.now().isoformat(),
                        "process": last_process, 
                        "window_title": last_window_title,
                        "event_type": "window_session",
                        "duration_seconds": duration_seconds
                    }
                    
                    print(f"[EVENT] {event_data['process']} -> {event_data['window_title']} ({duration_seconds}s)")
                    
                    try:
                        requests.post(BACKEND_URL, json=event_data, timeout=2.0)
                    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                        print("[!] Backend is down or busy. Event dropped.")

                start_time = time.time()
                last_window_title = cleaned_title
                last_process = process_name
                
        time.sleep(poll_interval)

if __name__ == "__main__":
    run_tracker()