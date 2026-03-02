# 🧠 Personal Offline AI Memory OS

An intelligent, privacy-first system that runs locally on your computer, tracks your OS-level activity, and acts as a searchable second brain using Retrieval-Augmented Generation (RAG).

Unlike standard chatbots, this system observes your actual workflow (active windows, applications used) and allows you to query your own computer history using natural language—all completely offline.

## 🏗 Architecture

The system consists of three main isolated layers:

1. **OS Context Layer (Daemon):** A Python script using `pywin32` that monitors the active window, detects idle time, and cleans window titles.
2. **Control & Storage Layer (FastAPI + SQLite):** An API that ingests logs, saves raw chronological data to SQLite, and manages background tasks.
3. **Cognitive Layer (Qdrant + Ollama):** Converts logs into semantic embeddings (`nomic-embed-text`) stored in a Qdrant Vector DB, and uses an LLM (`phi3`) to answer user queries based on retrieved context.

## 💻 System Requirements

- **OS:** Windows 10/11 (due to `pywin32` hooks)
- **RAM:** 16GB+ recommended (to run local LLMs smoothly)
- **Dependencies:** Python 3.10+, Docker Desktop, Ollama

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone [https://github.com/YOUR_USERNAME/ai-memory-os.git](https://github.com/YOUR_USERNAME/ai-memory-os.git)
cd ai-memory-os
```

### 2.Set up the python environment

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

### 3.start background services

### You must have Qdrant and Ollama running before starting the OS.

Start Qdrant (Vector Database):

### PowerShell

docker run -p 6333:6333 -p 6334:6334 -d qdrant/qdrant

### Start Ollama & Download Models:

Ensure the Ollama app is running, then pull the required models:

### PowerShell

ollama pull phi3
ollama pull nomic-embed-text

### Running the System

You need two separate terminal windows to run the system. Ensure the .venv is active in both.

### Terminal 1: Start the Backend API

### PowerShell

uvicorn backend.main:app --reload

### Terminal 2: Start the OS Tracker Daemon

### PowerShell

python daemon/tracker.py

### Usage & API Endpoints

Once both systems are running, the tracker will passively log your window switches. You can query your memory via HTTP POST requests:

### Query your semantic memory:

### PowerShell

Invoke-RestMethod -Uri "http://localhost:8000/query" -Method Post -Headers @{"Content-Type"="application/json"} -Body '{"question": "What coding projects was I working on?"}' | ConvertTo-Json

### Get a compressed daily summary:

### PowerShell

Invoke-RestMethod -Uri "http://localhost:8000/query/today" | ConvertTo-Json

### Step 4: Push to GitHub

Now that the code is clean, ignored files are set, and documentation is written, let's push it.

1. Go to [github.com](https://github.com) and log in.
2. Click the **"+"** icon in the top right and select **"New repository"**.
3. Name it `ai-memory-os`. Leave it Public or Private (your choice), but **do not** check the boxes for "Add a README" or "Add .gitignore" (we already made them locally). Click **Create repository**.
4. Open a new PowerShell terminal in your VS Code (you don't need `.venv` for Git commands).
5. Run these commands one by one, replacing the placeholder URL with your actual new GitHub repo URL:

```powershell
# Initialize git in your folder
git init

# Stage all files (the .gitignore will automatically block the database and venv)
git add .

# Create your first commit
git commit -m "Initial commit: Completed Backend, OS Tracker, and RAG Pipeline"

# Link your local folder to GitHub (REPLACE URL WITH YOURS)
git remote add origin https://github.com/YOUR_USERNAME/ai-memory-os.git

# Rename the main branch to 'main'
git branch -M main

# Push your code to the cloud
git push -u origin main
```
