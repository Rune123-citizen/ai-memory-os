import time
import win32gui
import win32api
import re
import win32process
import psutil
import requests
from datetime import datetime

BACKEND_URL = "http://localhost:8000/ingest"
def get_active_window_info():
    """Get the title and process name of the currently active window."""
    try:
        #Get the ID of the active window
        hwnd = win32gui.GetForegroundWindow()

        #Get the Title of the active window
        window_title = win32gui.GetWindowText(hwnd)

        #Get the Process ID of the active window
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        #Get the actual executable name (e.g., code.exe,chrome.exe)
        process=psutil.Process(pid)
        process_name = process.name()

        return {
            "process_name": process_name,
            "window_title": window_title
        }
    except Exception as e:
        return None

def clean_title(title: str) -> str:
    """Removes clutter from window titles (e.g., ' - Visual Studio Code')."""
    parts = title.split(" - ")
    # If the title has dashes, just keep the first part (usually the document/file name)
    if len(parts) > 1:
        return parts[0].strip()
    return title.strip()

def get_idle_time():
    """Returns the number of seconds since the user last touched the mouse or keyboard."""
    last_input = win32api.GetLastInputInfo()
    current_tick = win32api.GetTickCount()
    return (current_tick - last_input) / 1000.0

def run_tracker(poll_interval=5, idle_threshold=180):
    """Runs continuously, but pauses if the user is idle for more than 3 minutes (180s)."""
    print(f"[*] Starting OS Context Tracker. Polling every {poll_interval} seconds...")
    last_window_title = ""

    while True:
        idle_time = get_idle_time()
        
        if idle_time > idle_threshold:
            print(f"[IDLE] User inactive for {int(idle_time)}s. Pausing tracking...")
            time.sleep(poll_interval)
            continue # Skip logging until they come back

        window_info = get_active_window_info()
        
        if window_info:
            raw_title = window_info["window_title"]
            cleaned_title = clean_title(raw_title)
            
            # Only log if they switched tabs/windows AND it's not empty
            if cleaned_title != last_window_title and cleaned_title != "":
                
                event_data = {
                    "timestamp": datetime.now().isoformat(),
                    "process": window_info["process_name"],
                    "window_title": cleaned_title,
                    "event_type": "window_switch"
                }
                
                print(f"[EVENT] {event_data['process']} -> {event_data['window_title']}")
                
                try:
                    requests.post(BACKEND_URL, json=event_data)
                except requests.exceptions.ConnectionError:
                    print("[!] Backend is down. Event not sent.")

                last_window_title = cleaned_title
                
        time.sleep(poll_interval)

if __name__ == "__main__":
    run_tracker()