import re
from datetime import datetime

def extract_duration(text: str) -> int:
    """Helper function to pull the duration integer out of the memory string."""
    match = re.search(r"Duration:\s*(\d+)s", text)
    if match:
        return int(match.group(1))
    return 0

def rank_memories(memories: list, top_k: int = 5) -> str:
    """
    Scores raw memories using a weighted formula, filters the top K, 
    and chronologically sorts them for the LLM context window.
    """
    if not memories:
        return ""

    ranked_memories = []
    
    for mem in memories:
        # 1. Vector Similarity Score
        sim_score = mem.get("score", 0.5) if mem.get("source") != "sqlite_exact" else 1.0

        # 2. Get scored importance from RAG Engine
        importance_score = mem.get("importance", 0.5)

        #3.Master formula: 70% contextual relevance + 30% RAG importance
        final_score = (0.7 * sim_score) + (0.3 * importance_score)
        
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