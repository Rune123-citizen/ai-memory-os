import re
from datetime import datetime

def extract_duration(text: str) -> int:
    """Helper function to pull the duration integer out of the memory string."""
    match = re.search(r"Duration:\s*(\d+)s", text)
    if match:
        return int(match.group(1))
    return 0

def calculate_recency_score(timestamp_str: str) -> float:
    """Calculates how recent a memory is. 1.0 = right now, 0.0 = older than 7 days."""
    try:
        mem_time = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        hours_ago = (now - mem_time).total_seconds() / 3600.0
        
        # Decay score over 168 hours (7 days)
        return max(0.0, 1.0 - (hours_ago / 168.0))
    except Exception:
        return 0.0

def rank_memories(memories: list, top_k: int = 5) -> str:
    """
    Scores raw memories using a weighted formula, filters the top K, 
    and chronologically sorts them for the LLM context window.
    """
    if not memories:
        return ""

    ranked_memories = []
    
    for mem in memories:
        # 1. Vector Similarity Score (Weight: 60%)
        # SQLite exact keyword matches get an automatic perfect score (1.0).
        # Qdrant semantic matches use their native cosine distance score.
        sim_score = mem.get("score", 1.0) if mem.get("source") == "sqlite_exact" else mem.get("score", 0.5)

        # 2. Importance Score (Weight: 30%)
        # Based on how long you spent on the task. Caps at 15 minutes (900 seconds) = 1.0
        duration = extract_duration(mem.get("text", ""))
        importance_score = min(duration / 900.0, 1.0)

        # 3. Recency Score (Weight: 10%)
        # Rewards things you did today over things you did last week.
        recency_score = calculate_recency_score(mem.get("timestamp"))

        # --- THE MASTER SCORING FORMULA ---
        final_score = (0.6 * sim_score) + (0.3 * importance_score) + (0.1 * recency_score)

        mem["final_score"] = final_score
        ranked_memories.append(mem)

    # Step A: Rank by the mathematical score (Highest relevance first)
    ranked_memories.sort(key=lambda x: x["final_score"], reverse=True)

    # Step B: Slice the list to keep only the absolute best (e.g., top 5)
    top_memories = ranked_memories[:top_k]

    print(f"\n[RANKER] Filtered down to the top {len(top_memories)} highest-value memories.")
    for m in top_memories:
        print(f"   -> Score: {m['final_score']:.3f} | {m['text']}")

    # Step C: CRITICAL FIX - Re-sort the top 5 chronologically!
    # If we don't do this, the LLM reads time out of order and hallucinates the timeline.
    top_memories.sort(key=lambda x: x["timestamp"])

    # Extract just the text strings to feed into JARVIS
    context_lines = [m["text"] for m in top_memories]
    return "\n".join(context_lines)