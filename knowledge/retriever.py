"""
Knowledge retriever — similarity search over company knowledge chunks.

Two layers returned to callers:
  1. master_profile  — full LLM-generated company summary (always included)
  2. relevant_chunks — top-k most similar chunks to the query (prospect-specific)

Used by:
  nodes/sales/service_matcher.py
  nodes/sales/email_composer.py
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
DEFAULT_TOP_K = 6


# ── Cosine similarity ─────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed_query(query: str, api_key: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(model=EMBED_MODEL, input=[query])
    return response.data[0].embedding


# ── Search ────────────────────────────────────────────────────────────────────

def search_chunks(query: str, api_key: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """
    Embed the query and return the top-k most relevant knowledge chunks.
    Returns list of {content, file_name, score}.
    """
    from memory.sqlite_ops import get_all_knowledge_chunks, is_sqlite_ready

    if not is_sqlite_ready():
        return []

    chunks = get_all_knowledge_chunks()
    if not chunks:
        return []

    try:
        query_emb = _embed_query(query, api_key)
    except Exception as e:
        logger.warning("[Retriever] Failed to embed query: %s", e)
        return []

    scored = []
    for chunk in chunks:
        score = _cosine_similarity(query_emb, chunk["embedding"])
        scored.append({
            "content": chunk["content"],
            "file_name": chunk["file_name"],
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── Master profile ────────────────────────────────────────────────────────────

def load_company_profile() -> str:
    """Return the company master profile text, or empty string if not generated yet."""
    from memory.sqlite_ops import get_company_profile, is_sqlite_ready

    if not is_sqlite_ready():
        return ""

    profile = get_company_profile()
    if not profile:
        return ""
    return profile.get("profile_text", "")


def is_knowledge_ready() -> bool:
    """Return True if knowledge base has at least one doc synced."""
    from memory.sqlite_ops import list_knowledge_files, is_sqlite_ready
    if not is_sqlite_ready():
        return False
    return len(list_knowledge_files()) > 0


# ── Main context builder ──────────────────────────────────────────────────────

def get_company_context(
    query: str,
    api_key: str,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """
    Build the full company context for LLM injection.

    Returns:
        {
            "master_profile": str,       # full company summary
            "relevant_chunks": list,     # top-k relevant chunks
            "has_knowledge": bool,       # whether any docs are synced
            "formatted": str,            # ready-to-inject text block
        }
    """
    if not is_knowledge_ready():
        return {
            "master_profile": "",
            "relevant_chunks": [],
            "has_knowledge": False,
            "formatted": "",
        }

    master_profile = load_company_profile()
    relevant_chunks = search_chunks(query, api_key, top_k=top_k)

    # Build formatted text block for LLM injection
    parts = []

    if master_profile:
        parts.append("━━━ COMPANY MASTER PROFILE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        parts.append(master_profile)

    if relevant_chunks:
        parts.append("\n━━━ MOST RELEVANT KNOWLEDGE CHUNKS (from company docs) ━━━━━━━━━")
        for i, chunk in enumerate(relevant_chunks, 1):
            parts.append(f"\n[Chunk {i} — {chunk['file_name']} | relevance: {chunk['score']:.2f}]")
            parts.append(chunk["content"])

    formatted = "\n".join(parts)

    return {
        "master_profile": master_profile,
        "relevant_chunks": relevant_chunks,
        "has_knowledge": True,
        "formatted": formatted,
    }
