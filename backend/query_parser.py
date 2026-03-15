import json
import requests
from datetime import datetime

# The expanded alias map for normalising applications
APP_ALIASES = {
    "vs code": "Code.exe",
    "vscode": "Code.exe",
    "visual studio code": "Code.exe",
    "code": "Code.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "powershell": "WindowsTerminal.exe",
    "terminal": "WindowsTerminal.exe",
    "explorer": "explorer.exe"
}

# Map conversational activities to the likely applications
"""
ACTIVITY_MAP = {
    "coding": "Code.exe",
    "programming": "Code.exe",
    "debugging": "Code.exe",
    "research": "chrome.exe",
    "reading": "chrome.exe",
    "browsing": "chrome.exe",
    "files": "explorer.exe"
}
"""
def parse_query(query: str) -> dict:
    """
    Parses a natural language query into structured filters using Phi-3.
    """
    print(f"\n[PARSER] Analyzing query: '{query}'")
    
    prompt = f"""You are a precise query extraction engine. Analyze the user query to determine if we need to search their personal computer activity logs.

RULES FOR 'requires_database':
-Set to true if thee user asks about their own past, history,files they edited, apps they used, or their computer activity.
-Set to false if the user asks a general knowledge question, asks for a joke/poem, or needs general coding help.

EXAMPLES:
Query: "What was I coding yesterday?" -> "requires_database": true
Query: "Explain how Python lists work" -> "requires_database": false
Query: "Was I working on cricket_output today?" -> "requires_database": true
Query: "Write a haiku about a robot" -> "requires_database": false
Query: "Show me the recipes I looked at" -> "requires_database": true

Query: "{query}"

Output ONLY a valid JSON object with these exact keys:
1. "activity": The type of task (e.g., "coding", "research", "debugging"). Null if none.
2. "app": The specific software mentioned (e.g., "Chrome", "VS Code"). Null if none.
3. "time_range": Any time expression mentioned (e.g., "today", "yesterday", "last week","recently"). Null if none.
4. "keywords": A list of the most important subject words, removing filler words.
5. "requires_database": boolean (true or false based on the rules above).

JSON Output:"""

    url = "http://localhost:11434/api/generate"
    payload = {"model": "phi3:mini", "prompt": prompt, "stream": False, "format": "json"}
    
    # Default fallback structure
    parsed_data = {
        "activity": None,
        "app": None,
        "time_range": None,
        "keywords": [],
        "requires_database": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        extracted_json = json.loads(response.json()["response"])

        
        # Merge the LLM's output with our default structure
        parsed_data.update(extracted_json)
        
    except Exception as e:
        print(f"[!] LLM Parsing failed, using basic fallback. Error: {e}")
        parsed_data["keywords"] = query.split() # Fallback to splitting the raw query
        return parsed_data

    # --- Post-Processing & Normalization ---
    
    # 1. Normalize App Names
    if parsed_data["app"]:
        clean_app = parsed_data["app"].lower().strip()
        # Strip hallucinated .exe
        if clean_app.endswith(".exe") and clean_app not in APP_ALIASES.values():
            clean_app = clean_app[:-4].strip()
            
        if clean_app in APP_ALIASES:
            parsed_data["app"] = APP_ALIASES[clean_app]
            
    # 2. Infer App from Activity (if app is null but activity is known)
    """
    if not parsed_data["app"] and parsed_data["activity"]:
        clean_activity = parsed_data["activity"].lower().strip()
        if clean_activity in ACTIVITY_MAP:
            parsed_data["app"] = ACTIVITY_MAP[clean_activity]
            print(f"[PARSER] Inferred app '{parsed_data['app']}' from activity '{clean_activity}'")
    """
            
    # 3. Ensure keywords is a list
    if isinstance(parsed_data["keywords"], str):
        parsed_data["keywords"] = [k.strip() for k in parsed_data["keywords"].split(",")]

    print(f"[PARSER] Structured Output: {json.dumps(parsed_data, indent=2)}")
    return parsed_data