
import requests
import sys

print("Initializing connection to NeuroLayer OS...\n")

url = "http://localhost:8000/query/stream"
payload = {"question": "Find the cricket_output file for me."}

try:
    with requests.post(url, json=payload, stream=True) as response:
        response.raise_for_status()
        
        print("Response: ", end="")
        
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                sys.stdout.write(chunk)
                sys.stdout.flush()
                
    print("\n\n--- Stream Complete ---")

except Exception as e:
    print(f"[!] ERROR: {e}")