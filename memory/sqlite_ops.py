from __future__ import annotations

"""
SQLite operations layer — lightweight local persistence.

Replaces Redis for:
  - Tool result caching (with TTL expiry)
  - Cost tracking (atomic counters)
  - Webhook event queue
  - Metrics storage
  - Audit logs

Single database file at ~/.nester/ops.db — zero external services.
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_db_path: str | None = None
_local = threading.local()

SCHEMA_SQL = """
-- Tool result cache with TTL
CREATE TABLE IF NOT EXISTS tool_cache (
    cache_key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_cache_expires ON tool_cache(expires_at);

-- Webhook event queue
CREATE TABLE IF NOT EXISTS webhook_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_webhook_status ON webhook_queue(status);

-- Cost tracking
CREATE TABLE IF NOT EXISTS cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    amount REAL NOT NULL,
    model TEXT DEFAULT '',
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cost_scope ON cost_tracking(scope, scope_key);

-- Metrics
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_metrics_flow ON metrics(flow_name, metric_name);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT NOT NULL,
    resource TEXT,
    outcome TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at);

-- Session state (short-lived, replaces Redis session state)
CREATE TABLE IF NOT EXISTS session_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_expires ON session_state(expires_at);

-- OAuth tokens for integration connectors (Google, GitHub, Slack, etc.)
-- NOTE: Single-user only — one token per provider. Multi-user requires adding a user_id column.
CREATE TABLE IF NOT EXISTS oauth_tokens (
    provider TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT DEFAULT 'Bearer',
    scopes TEXT DEFAULT '',
    expires_at TEXT,
    provider_user_id TEXT DEFAULT '',
    provider_user_name TEXT DEFAULT '',
    connected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Pipeline run history
CREATE TABLE IF NOT EXISTS run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    flow_name TEXT NOT NULL,
    flow_version TEXT DEFAULT '',
    user_id TEXT DEFAULT 'anonymous',
    status TEXT NOT NULL,
    input_data TEXT DEFAULT '{}',
    output_data TEXT DEFAULT '{}',
    node_timings TEXT DEFAULT '{}',
    duration_ms INTEGER DEFAULT 0,
    error TEXT,
    prospect_name TEXT DEFAULT '',
    company_name TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_history_flow ON run_history(flow_name, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_status ON run_history(status);

-- Manual credentials for non-OAuth integrations (SMTP, API keys)
CREATE TABLE IF NOT EXISTS integration_credentials (
    integration_name TEXT PRIMARY KEY,
    credentials TEXT NOT NULL,
    connected_at TEXT NOT NULL,
    last_tested TEXT,
    test_result TEXT DEFAULT 'untested'
);

-- API keys (user-set via Settings UI, override .env values)
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Company knowledge chunks from Google Drive docs (with embeddings for similarity search)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(file_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_file ON knowledge_chunks(file_id);

-- Drive file sync state (tracks what has been indexed)
CREATE TABLE IF NOT EXISTS knowledge_files (
    file_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    modified_time TEXT NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    indexed_at TEXT NOT NULL
);

-- Company master profile (LLM-generated summary of all company docs)
CREATE TABLE IF NOT EXISTS company_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    profile_text TEXT NOT NULL,
    doc_count INTEGER DEFAULT 0,
    generated_at TEXT NOT NULL,
    folder_id TEXT DEFAULT ''
);

-- SOW Generator: sessions
CREATE TABLE IF NOT EXISTS sow_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Untitled SOW',
    status TEXT NOT NULL DEFAULT 'draft',
    sow_markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- SOW Generator: uploaded documents (templates global, proposals per-session)
CREATE TABLE IF NOT EXISTS sow_documents (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    doc_type TEXT NOT NULL,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    raw_bytes BLOB NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sow_docs_session ON sow_documents(session_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_sow_docs_type ON sow_documents(doc_type);

-- SOW Generator: chat messages per session
CREATE TABLE IF NOT EXISTS sow_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sow_chat_session ON sow_chat_messages(session_id, id);
"""


def init_sqlite_ops(db_path: str = "~/.nester/ops.db") -> None:
    """Initialize the SQLite operations database. Creates tables if needed."""
    global _db_path

    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    _db_path = str(path)

    conn = sqlite3.connect(_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_SQL)
    conn.close()

    # Restrict permissions — tokens and credentials stored here
    path.chmod(0o600)

    logger.info("[SQLite] Initialized at %s", _db_path)


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if _db_path is None:
        raise RuntimeError("SQLite not initialized — call init_sqlite_ops() at startup")

    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(_db_path)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


@contextmanager
def _transaction() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for atomic transactions."""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def is_sqlite_ready() -> bool:
    """Return True if SQLite is initialized."""
    return _db_path is not None


def _now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


# ── Tool Cache ───────────────────────────────────────────────────────────────


def cache_get(cache_key: str) -> Any | None:
    """Get a cached value if it exists and hasn't expired."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM tool_cache WHERE cache_key = ? AND expires_at > ?",
        (cache_key, _now_iso()),
    ).fetchone()

    if row is None:
        return None
    return json.loads(row["value"])


def cache_set(cache_key: str, value: Any, ttl_seconds: int) -> None:
    """Set a cache value with TTL."""
    # timedelta imported at module level

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    ).isoformat()

    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tool_cache (cache_key, value, expires_at) VALUES (?, ?, ?)",
            (cache_key, json.dumps(value, default=str), expires_at),
        )


def cache_invalidate(pattern: str | None = None) -> int:
    """Invalidate cached entries. Pattern uses SQL LIKE syntax."""
    with _transaction() as conn:
        if pattern:
            cursor = conn.execute(
                "DELETE FROM tool_cache WHERE cache_key LIKE ?",
                (pattern,),
            )
        else:
            cursor = conn.execute("DELETE FROM tool_cache")
        count = cursor.rowcount
        logger.info("[SQLite] Invalidated %d cache entries", count)
        return count


def cache_cleanup() -> int:
    """Remove expired cache entries."""
    with _transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM tool_cache WHERE expires_at <= ?",
            (_now_iso(),),
        )
        return cursor.rowcount


# ── Cost Tracking ────────────────────────────────────────────────────────────


def record_cost(
    scope: str,
    scope_key: str,
    amount: float,
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Record an LLM cost entry."""
    with _transaction() as conn:
        conn.execute(
            "INSERT INTO cost_tracking (scope, scope_key, amount, model, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scope, scope_key, amount, model, tokens_in, tokens_out),
        )


def get_cost_total(scope: str, scope_key: str, since: str | None = None) -> float:
    """Get total cost for a scope/key, optionally since a date."""
    conn = _get_conn()
    if since:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total "
            "FROM cost_tracking WHERE scope = ? AND scope_key = ? AND created_at >= ?",
            (scope, scope_key, since),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total "
            "FROM cost_tracking WHERE scope = ? AND scope_key = ?",
            (scope, scope_key),
        ).fetchone()
    return float(row["total"])


# ── Webhook Queue ────────────────────────────────────────────────────────────


def push_webhook(source: str, event_type: str, payload: dict[str, Any]) -> int:
    """Push an event to the webhook queue. Returns the row ID."""
    with _transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO webhook_queue (source, event_type, payload) VALUES (?, ?, ?)",
            (source, event_type, json.dumps(payload, default=str)),
        )
        return cursor.lastrowid or 0


def pop_webhooks(limit: int = 100) -> list[dict[str, Any]]:
    """Pop pending webhooks from the queue (marks them as processing)."""
    with _transaction() as conn:
        rows = conn.execute(
            "SELECT id, source, event_type, payload, created_at "
            "FROM webhook_queue WHERE status = 'pending' "
            "ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()

        if not rows:
            return []

        ids = [r["id"] for r in rows]
        # Placeholders are purely "?" characters — no user data in the SQL string
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE webhook_queue SET status = 'processing' WHERE id IN ({placeholders})",
            tuple(ids),
        )

        return [
            {
                "id": r["id"],
                "source": r["source"],
                "event_type": r["event_type"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


def ack_webhook(webhook_id: int) -> None:
    """Mark a webhook as processed."""
    with _transaction() as conn:
        conn.execute(
            "UPDATE webhook_queue SET status = 'done', processed_at = ? WHERE id = ?",
            (_now_iso(), webhook_id),
        )


# ── Metrics ──────────────────────────────────────────────────────────────────


def record_metric(
    flow_name: str,
    run_id: str,
    metric_name: str,
    metric_value: float,
) -> None:
    """Record a metric for a flow run."""
    with _transaction() as conn:
        conn.execute(
            "INSERT INTO metrics (flow_name, run_id, metric_name, metric_value) "
            "VALUES (?, ?, ?, ?)",
            (flow_name, run_id, metric_name, metric_value),
        )


def query_metrics(
    flow_name: str,
    metric_name: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query metrics for a flow."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT run_id, metric_value, created_at FROM metrics "
        "WHERE flow_name = ? AND metric_name = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (flow_name, metric_name, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Audit Log ────────────────────────────────────────────────────────────────


def audit_log(
    action: str,
    resource: str = "",
    actor: str = "",
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write an audit log entry."""
    with _transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log (actor, action, resource, outcome, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (actor, action, resource, outcome, json.dumps(metadata or {}, default=str)),
        )


# ── Session State ────────────────────────────────────────────────────────────


def session_set(key: str, value: Any, ttl_seconds: int = 3600) -> None:
    """Store a session state value with TTL."""
    # timedelta imported at module level

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    ).isoformat()

    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO session_state (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), expires_at),
        )


def session_get(key: str) -> Any | None:
    """Get a session state value if not expired."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM session_state WHERE key = ? AND expires_at > ?",
        (key, _now_iso()),
    ).fetchone()

    if row is None:
        return None
    return json.loads(row["value"])


def session_delete(key: str) -> None:
    """Delete a session state value."""
    with _transaction() as conn:
        conn.execute("DELETE FROM session_state WHERE key = ?", (key,))


def cleanup_expired() -> int:
    """Remove all expired entries across cache and session tables."""
    now = _now_iso()
    total = 0
    with _transaction() as conn:
        total += conn.execute(
            "DELETE FROM tool_cache WHERE expires_at <= ?", (now,)
        ).rowcount
        total += conn.execute(
            "DELETE FROM session_state WHERE expires_at <= ?", (now,)
        ).rowcount
    if total:
        logger.debug("[SQLite] Cleaned up %d expired entries", total)
    return total


# ── Integration Credentials ──────────────────────────────────────────────────


def save_credentials(
    integration_name: str,
    credentials: dict[str, Any],
    test_result: str = "untested",
) -> None:
    """Save credentials for an integration (upsert)."""
    now = _now_iso()
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO integration_credentials "
            "(integration_name, credentials, connected_at, last_tested, test_result) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                integration_name,
                json.dumps(credentials),
                now,
                now if test_result != "untested" else None,
                test_result,
            ),
        )
    logger.info("[SQLite] Saved credentials for %s", integration_name)


def get_credentials(integration_name: str) -> dict[str, Any] | None:
    """Get saved credentials for an integration. Returns None if not configured."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT credentials, connected_at, last_tested, test_result "
        "FROM integration_credentials WHERE integration_name = ?",
        (integration_name,),
    ).fetchone()

    if row is None:
        return None

    return {
        "credentials": json.loads(row["credentials"]),
        "connected_at": row["connected_at"],
        "last_tested": row["last_tested"],
        "test_result": row["test_result"],
    }


def delete_credentials(integration_name: str) -> bool:
    """Delete credentials for an integration. Returns True if a row was deleted."""
    with _transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM integration_credentials WHERE integration_name = ?",
            (integration_name,),
        )
        deleted = cursor.rowcount > 0
    if deleted:
        logger.info("[SQLite] Deleted credentials for %s", integration_name)
    return deleted


def list_connected_integrations() -> list[dict[str, Any]]:
    """Return all integrations that have saved credentials."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT integration_name, connected_at, last_tested, test_result "
        "FROM integration_credentials ORDER BY connected_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def update_test_result(integration_name: str, test_result: str) -> None:
    """Update the test result for an integration's credentials."""
    now = _now_iso()
    with _transaction() as conn:
        conn.execute(
            "UPDATE integration_credentials SET last_tested = ?, test_result = ? "
            "WHERE integration_name = ?",
            (now, test_result, integration_name),
        )


# ── OAuth Tokens ─────────────────────────────────────────────────────────────


def save_oauth_token(
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    token_type: str = "Bearer",
    scopes: str = "",
    expires_at: str | None = None,
    provider_user_id: str = "",
    provider_user_name: str = "",
) -> None:
    """Save or update OAuth tokens for a provider (upsert)."""
    now = _now_iso()
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens "
            "(provider, access_token, refresh_token, token_type, scopes, "
            "expires_at, provider_user_id, provider_user_name, connected_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
            "COALESCE((SELECT connected_at FROM oauth_tokens WHERE provider = ?), ?), ?)",
            (
                provider, access_token, refresh_token, token_type, scopes,
                expires_at, provider_user_id, provider_user_name,
                provider, now, now,
            ),
        )
    logger.info("[SQLite] Saved OAuth token for %s (%s)", provider, provider_user_name or "unknown")


def get_oauth_token(provider: str) -> dict[str, Any] | None:
    """Get stored OAuth token for a provider. Returns None if not connected."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT access_token, refresh_token, token_type, scopes, expires_at, "
        "provider_user_id, provider_user_name, connected_at, updated_at "
        "FROM oauth_tokens WHERE provider = ?",
        (provider,),
    ).fetchone()

    if row is None:
        return None

    return {
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"],
        "token_type": row["token_type"],
        "scopes": row["scopes"],
        "expires_at": row["expires_at"],
        "provider_user_id": row["provider_user_id"],
        "provider_user_name": row["provider_user_name"],
        "connected_at": row["connected_at"],
        "updated_at": row["updated_at"],
    }


def delete_oauth_token(provider: str) -> bool:
    """Delete OAuth tokens for a provider. Returns True if a row was removed."""
    with _transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM oauth_tokens WHERE provider = ?",
            (provider,),
        )
        deleted = cursor.rowcount > 0
    if deleted:
        logger.info("[SQLite] Deleted OAuth token for %s", provider)
    return deleted


def list_oauth_connections() -> list[dict[str, Any]]:
    """Return all connected OAuth providers (no tokens — just metadata)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT provider, scopes, provider_user_id, provider_user_name, "
        "connected_at, updated_at "
        "FROM oauth_tokens ORDER BY connected_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def update_oauth_access_token(
    provider: str,
    access_token: str,
    expires_at: str | None = None,
) -> bool:
    """Update just the access token after a refresh (preserves refresh_token).

    Returns True if a row was updated, False if provider not found.
    """
    now = _now_iso()
    with _transaction() as conn:
        cursor = conn.execute(
            "UPDATE oauth_tokens SET access_token = ?, expires_at = ?, updated_at = ? "
            "WHERE provider = ?",
            (access_token, expires_at, now, provider),
        )
        return cursor.rowcount > 0


# ── Run History ─────────────────────────────────────────────────────────────


def save_run(
    run_id: str,
    flow_name: str,
    status: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    node_timings: dict[str, Any],
    duration_ms: int,
    started_at: str,
    completed_at: str,
    flow_version: str = "",
    user_id: str = "anonymous",
    error: str | None = None,
    prospect_name: str = "",
    company_name: str = "",
) -> None:
    """Persist a completed pipeline run."""
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO run_history "
            "(run_id, flow_name, flow_version, user_id, status, input_data, output_data, "
            "node_timings, duration_ms, error, prospect_name, company_name, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, flow_name, flow_version, user_id, status,
                json.dumps(input_data, default=str),
                json.dumps(output_data, default=str),
                json.dumps(node_timings, default=str),
                duration_ms, error, prospect_name, company_name,
                started_at, completed_at,
            ),
        )
    logger.info("[SQLite] Saved run %s (%s) — %s", run_id[:8], flow_name, status)


def list_runs(
    flow_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List recent runs, newest first. Optionally filter by flow_name."""
    conn = _get_conn()
    if flow_name:
        rows = conn.execute(
            "SELECT run_id, flow_name, flow_version, user_id, status, "
            "duration_ms, error, prospect_name, company_name, started_at, completed_at "
            "FROM run_history WHERE flow_name = ? "
            "ORDER BY completed_at DESC LIMIT ? OFFSET ?",
            (flow_name, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT run_id, flow_name, flow_version, user_id, status, "
            "duration_ms, error, prospect_name, company_name, started_at, completed_at "
            "FROM run_history ORDER BY completed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    """Get full details for a single run including input/output data."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM run_history WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    # Parse JSON fields
    for field in ("input_data", "output_data", "node_timings"):
        if result.get(field):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def count_runs(flow_name: str | None = None) -> int:
    """Count total runs, optionally filtered by flow."""
    conn = _get_conn()
    if flow_name:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM run_history WHERE flow_name = ?",
            (flow_name,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM run_history").fetchone()
    return row["cnt"] if row else 0


# ── Company Knowledge (Drive sync + vector search) ───────────────────────────


def upsert_knowledge_chunk(
    file_id: str,
    file_name: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
) -> None:
    """Insert or replace a knowledge chunk with its embedding."""
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_chunks "
            "(file_id, file_name, chunk_index, content, embedding) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, file_name, chunk_index, content, json.dumps(embedding)),
        )


def delete_knowledge_file(file_id: str) -> int:
    """Delete all chunks for a file. Returns count of deleted chunks."""
    with _transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM knowledge_chunks WHERE file_id = ?", (file_id,)
        )
        conn.execute("DELETE FROM knowledge_files WHERE file_id = ?", (file_id,))
        return cursor.rowcount


def upsert_knowledge_file(
    file_id: str,
    file_name: str,
    mime_type: str,
    modified_time: str,
    chunk_count: int,
) -> None:
    """Track a synced Drive file."""
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_files "
            "(file_id, file_name, mime_type, modified_time, chunk_count, indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, file_name, mime_type, modified_time, chunk_count, _now_iso()),
        )


def get_knowledge_file(file_id: str) -> dict[str, Any] | None:
    """Get sync state for a Drive file."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM knowledge_files WHERE file_id = ?", (file_id,)
    ).fetchone()
    return dict(row) if row else None


def list_knowledge_files() -> list[dict[str, Any]]:
    """List all synced Drive files."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM knowledge_files ORDER BY indexed_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_knowledge_chunks() -> list[dict[str, Any]]:
    """Return all chunks with embeddings for similarity search."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, file_id, file_name, chunk_index, content, embedding "
        "FROM knowledge_chunks ORDER BY file_id, chunk_index"
    ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["embedding"] = json.loads(item["embedding"])
        result.append(item)
    return result


def save_company_profile(
    profile_text: str,
    doc_count: int,
    folder_id: str = "",
) -> None:
    """Save or update the LLM-generated company master profile."""
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO company_profile (id, profile_text, doc_count, generated_at, folder_id) "
            "VALUES (1, ?, ?, ?, ?)",
            (profile_text, doc_count, _now_iso(), folder_id),
        )


def get_company_profile() -> dict[str, Any] | None:
    """Get the company master profile."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone()
    return dict(row) if row else None


def clear_knowledge() -> None:
    """Wipe all knowledge chunks, files, and profile (full re-sync)."""
    with _transaction() as conn:
        conn.execute("DELETE FROM knowledge_chunks")
        conn.execute("DELETE FROM knowledge_files")
        conn.execute("DELETE FROM company_profile")


# ── API Keys ──────────────────────────────────────────────────────────────────

def set_api_key(key: str, value: str) -> None:
    """Save or update a user-set API key in SQLite."""
    with _transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, _now_iso()),
        )


def get_api_key_from_db(key: str) -> str | None:
    """Get a user-set API key from SQLite. Returns None if not set."""
    try:
        conn = _get_conn()
        row = conn.execute("SELECT value FROM api_keys WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    except Exception:
        return None


def list_api_keys() -> list[dict[str, Any]]:
    """List all stored API keys (names + masked values + updated_at)."""
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT key, value, updated_at FROM api_keys ORDER BY key").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def delete_api_key(key: str) -> None:
    """Delete a user-set API key (falls back to .env value)."""
    with _transaction() as conn:
        conn.execute("DELETE FROM api_keys WHERE key = ?", (key,))


# ── SOW Generator ───────────────────────────────────────────────────────────


def create_sow_session(session_id: str, title: str = "Untitled SOW") -> None:
    """Create a new SOW session."""
    now = _now_iso()
    with _transaction() as conn:
        conn.execute(
            "INSERT INTO sow_sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )


def get_sow_session(session_id: str) -> dict[str, Any] | None:
    """Get a SOW session by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sow_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sow_sessions() -> list[dict[str, Any]]:
    """List all SOW sessions, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, title, status, created_at, updated_at FROM sow_sessions ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def update_sow_markdown(session_id: str, markdown: str) -> None:
    """Update the SOW markdown content for a session."""
    with _transaction() as conn:
        conn.execute(
            "UPDATE sow_sessions SET sow_markdown = ?, updated_at = ? WHERE id = ?",
            (markdown, _now_iso(), session_id),
        )


def update_sow_session_title(session_id: str, title: str) -> None:
    """Update a SOW session title."""
    with _transaction() as conn:
        conn.execute(
            "UPDATE sow_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now_iso(), session_id),
        )


def update_sow_session_status(session_id: str, status: str) -> None:
    """Update a SOW session status (draft/finalized)."""
    with _transaction() as conn:
        conn.execute(
            "UPDATE sow_sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), session_id),
        )


def delete_sow_session(session_id: str) -> None:
    """Delete a SOW session and its proposals + chat messages."""
    with _transaction() as conn:
        conn.execute("DELETE FROM sow_chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sow_documents WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sow_sessions WHERE id = ?", (session_id,))


# ── SOW Documents ───────────────────────────────────────────────────────────


def save_sow_document(
    doc_id: str,
    session_id: str | None,
    doc_type: str,
    file_name: str,
    mime_type: str,
    raw_bytes: bytes,
    extracted_text: str,
) -> None:
    """Save a SOW document (template or proposal)."""
    with _transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO sow_documents
               (id, session_id, doc_type, file_name, mime_type, raw_bytes, extracted_text, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, session_id, doc_type, file_name, mime_type, raw_bytes, extracted_text, _now_iso()),
        )


def list_sow_documents(
    session_id: str | None = None,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    """List SOW documents, optionally filtered by session and/or type."""
    conn = _get_conn()
    query = "SELECT id, session_id, doc_type, file_name, mime_type, length(raw_bytes) as size_bytes, uploaded_at FROM sow_documents WHERE 1=1"
    params: list[Any] = []
    if doc_type:
        query += " AND doc_type = ?"
        params.append(doc_type)
    if session_id is not None:
        query += " AND session_id = ?"
        params.append(session_id)
    elif doc_type == "template":
        query += " AND session_id IS NULL"
    query += " ORDER BY uploaded_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_sow_document(doc_id: str) -> dict[str, Any] | None:
    """Get a SOW document by ID (includes raw_bytes and extracted_text)."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sow_documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def delete_sow_document(doc_id: str) -> None:
    """Delete a SOW document."""
    with _transaction() as conn:
        conn.execute("DELETE FROM sow_documents WHERE id = ?", (doc_id,))


# ── SOW Chat Messages ──────────────────────────────────────────────────────


def save_sow_chat_message(session_id: str, role: str, content: str) -> None:
    """Save a chat message for a SOW session."""
    with _transaction() as conn:
        conn.execute(
            "INSERT INTO sow_chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now_iso()),
        )


def list_sow_chat_messages(session_id: str) -> list[dict[str, Any]]:
    """List all chat messages for a SOW session, in order."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM sow_chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]
