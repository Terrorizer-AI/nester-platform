"""
Mem0 memory layer — persistent agent memory with semantic search.

Replaces Supabase + pgvector for long-term knowledge storage.
Runs fully local: Qdrant embedded (in-process, no server) + SQLite history.

Capabilities:
  - Store facts extracted from agent pipeline outputs
  - Semantic search across prospect/company/flow memories
  - Automatic deduplication and conflict resolution
  - Namespace isolation via user_id prefixes

Data lives under ~/.nester/mem0/ — zero external services.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_mem0_client = None
_initialized = False


def _ensure_dirs(data_dir: str) -> Path:
    """Create the data directory tree if it doesn't exist."""
    path = Path(data_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_mem0(
    data_dir: str = "~/.nester/mem0",
    llm_model: str = "gpt-4o-mini",
    embedding_model: str = "text-embedding-3-small",
) -> Any:
    """
    Initialize the Mem0 client singleton.

    Uses Qdrant embedded (in-process Rust core, no server) and SQLite
    for history tracking. Only external dependency is OpenAI API for
    LLM fact extraction and embeddings.
    """
    global _mem0_client, _initialized

    if _initialized and _mem0_client is not None:
        return _mem0_client

    base = _ensure_dirs(data_dir)
    qdrant_path = str(base / "qdrant")
    history_db = str(base / "history.db")

    # Ensure qdrant subdirectory exists
    Path(qdrant_path).mkdir(parents=True, exist_ok=True)

    from mem0 import Memory

    config = {
        "llm": {
            "provider": "openai",
            "config": {
                "model": llm_model,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": embedding_model,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "nester_memories",
                "path": qdrant_path,
                "on_disk": True,
            },
        },
        "history_db_path": history_db,
        "version": "v1.1",
    }

    _mem0_client = Memory.from_config(config)
    _initialized = True

    logger.info(
        "[Mem0] Initialized — qdrant=%s, history=%s", qdrant_path, history_db
    )
    return _mem0_client


def get_mem0() -> Any:
    """Get the Mem0 client singleton. Raises if not initialized."""
    if _mem0_client is None:
        raise RuntimeError("Mem0 not initialized — call init_mem0() at startup")
    return _mem0_client


def is_mem0_ready() -> bool:
    """Return True if Mem0 is initialized and accessible."""
    return _initialized and _mem0_client is not None


# ── High-level memory operations ─────────────────────────────────────────────


def store_memory(
    content: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Store a fact or insight in Mem0.

    Mem0 internally:
      1. Extracts discrete facts from the content via LLM
      2. Embeds each fact and checks for duplicates
      3. Resolves conflicts (ADD/UPDATE/DELETE/NONE)

    Args:
        content: The text to extract facts from.
        user_id: Namespace key (e.g. "prospect_kunal_shrivastava").
        metadata: Optional metadata dict (flow name, run_id, agent, etc.).

    Returns:
        List of memory operation results from Mem0.
    """
    mem = get_mem0()
    messages = [{"role": "assistant", "content": content}]

    try:
        result = mem.add(
            messages=messages,
            user_id=user_id,
            metadata=metadata or {},
        )
        logger.debug("[Mem0] Stored memory for %s: %d operations", user_id, len(result.get("results", [])))
        return result.get("results", [])
    except Exception as exc:
        logger.error("[Mem0] Failed to store memory for %s: %s", user_id, exc)
        return []


def search_memory(
    query: str,
    user_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Semantic search across memories for a given user_id namespace.

    Args:
        query: Natural language search query.
        user_id: Namespace key to search within.
        limit: Maximum number of results.

    Returns:
        Ranked list of memory dicts with 'memory', 'score', 'metadata'.
    """
    mem = get_mem0()

    try:
        results = mem.search(query=query, user_id=user_id, limit=limit)
        logger.debug("[Mem0] Search '%s' for %s: %d results", query[:50], user_id, len(results.get("results", [])))
        return results.get("results", [])
    except Exception as exc:
        logger.error("[Mem0] Search failed for %s: %s", user_id, exc)
        return []


def get_all_memories(
    user_id: str,
) -> list[dict[str, Any]]:
    """
    Retrieve all memories for a given user_id namespace.

    Useful for dumping the full knowledge base for a prospect/company.
    """
    mem = get_mem0()

    try:
        results = mem.get_all(user_id=user_id)
        return results.get("results", [])
    except Exception as exc:
        logger.error("[Mem0] get_all failed for %s: %s", user_id, exc)
        return []


def delete_memory(memory_id: str) -> bool:
    """Delete a specific memory by its ID."""
    mem = get_mem0()

    try:
        mem.delete(memory_id=memory_id)
        logger.debug("[Mem0] Deleted memory %s", memory_id)
        return True
    except Exception as exc:
        logger.error("[Mem0] Delete failed for %s: %s", memory_id, exc)
        return False


def delete_all_memories(user_id: str) -> bool:
    """Delete all memories for a given user_id namespace."""
    mem = get_mem0()

    try:
        mem.delete_all(user_id=user_id)
        logger.info("[Mem0] Deleted all memories for %s", user_id)
        return True
    except Exception as exc:
        logger.error("[Mem0] delete_all failed for %s: %s", user_id, exc)
        return False


# ── Convenience helpers for Nester flows ─────────────────────────────────────


def prospect_user_id(name: str) -> str:
    """Generate a consistent user_id for a prospect."""
    return f"prospect_{name.lower().strip().replace(' ', '_')}"


def company_user_id(name: str) -> str:
    """Generate a consistent user_id for a company."""
    return f"company_{name.lower().strip().replace(' ', '_')}"


def flow_user_id(flow_name: str) -> str:
    """Generate a user_id for flow-level shared knowledge."""
    return f"flow_{flow_name}"


def store_agent_output(
    agent_name: str,
    raw_response: str,
    prospect_name: str = "",
    company_name: str = "",
    max_chars: int = 3000,
) -> None:
    """
    Store an agent's raw LLM output in Mem0 under both prospect and company namespaces.

    Called after each agent finishes. Mem0 automatically:
      - Extracts discrete facts from the text
      - Deduplicates against existing memories
      - Merges/updates conflicting facts

    This means every pipeline run accumulates knowledge — if we research the
    same company twice, Mem0 keeps one clean version, not duplicates.
    """
    if not is_mem0_ready():
        return
    if not raw_response or len(raw_response) < 20:
        return

    content = raw_response[:max_chars]
    meta = {"agent": agent_name, "flow": "sales_outreach"}

    try:
        # Store under prospect namespace
        if prospect_name:
            pid = prospect_user_id(prospect_name)
            store_memory(
                content=f"[{agent_name}] {content}",
                user_id=pid,
                metadata=meta,
            )
            logger.info("[Mem0] Stored %s output for prospect %s (%d chars)", agent_name, prospect_name, len(content))

        # Store under company namespace
        if company_name:
            cid = company_user_id(company_name)
            store_memory(
                content=f"[{agent_name}] {content}",
                user_id=cid,
                metadata=meta,
            )
            logger.info("[Mem0] Stored %s output for company %s (%d chars)", agent_name, company_name, len(content))
    except Exception as exc:
        logger.debug("[Mem0] store_agent_output failed for %s: %s", agent_name, exc)
