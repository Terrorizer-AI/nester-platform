"""
Settings API — manage user-configurable API keys.

Endpoints:
  GET  /settings/keys        — list all keys (masked values)
  POST /settings/keys        — save one or more keys
  DELETE /settings/keys/{key} — remove a key (falls back to .env)
"""

from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Keys grouped by the agent/flow that uses them
MANAGED_KEYS: list[dict[str, str]] = [
    # ── Sales Outreach Agent ──────────────────────────────────────────────────
    {
        "key": "DEEPSEEK_API_KEY",
        "label": "DeepSeek API Key",
        "description": "Powers all LLM agents — research, persona building, email writing (DeepSeek)",
        "placeholder": "sk-...",
        "link": "https://platform.deepseek.com/api_keys",
        "group": "Sales Outreach",
        "required": "true",
    },
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API Key",
        "description": "Used for embeddings (knowledge base, memory) — required even with DeepSeek",
        "placeholder": "sk-proj-...",
        "link": "https://platform.openai.com/api-keys",
        "group": "Sales Outreach",
        "required": "true",
    },
    {
        "key": "TAVILY_API_KEY",
        "label": "Tavily API Key",
        "description": "Web search for company research, funding rounds, and news",
        "placeholder": "tvly-...",
        "link": "https://app.tavily.com",
        "group": "Sales Outreach",
        "required": "true",
    },
    {
        "key": "FIRECRAWL_API_KEY",
        "label": "Firecrawl API Key",
        "description": "Scrapes company websites to extract products, team, and pricing",
        "placeholder": "fc-...",
        "link": "https://www.firecrawl.dev",
        "group": "Sales Outreach",
        "required": "true",
    },
    {
        "key": "CALENDLY_SCHEDULING_URL",
        "label": "Calendly Scheduling Link",
        "description": "Inserted as the CTA link at the bottom of every outreach email",
        "placeholder": "https://calendly.com/yourname/30min",
        "link": "https://calendly.com",
        "group": "Sales Outreach",
        "required": "false",
    },
    {
        "key": "SMTP_USER",
        "label": "SMTP Email Address",
        "description": "Gmail address used for email validation and sending",
        "placeholder": "you@gmail.com",
        "link": "https://support.google.com/mail/answer/185833",
        "group": "Sales Outreach",
        "required": "false",
    },
    {
        "key": "SMTP_PASSWORD",
        "label": "SMTP App Password",
        "description": "Gmail App Password (16-char, not your Google account password)",
        "placeholder": "xxxx xxxx xxxx xxxx",
        "link": "https://support.google.com/accounts/answer/185833",
        "group": "Sales Outreach",
        "required": "false",
    },
    # ── GitHub Monitor Agent ──────────────────────────────────────────────────
    {
        "key": "GITHUB_TOKEN",
        "label": "GitHub Personal Access Token",
        "description": "Reads repos, PRs, issues, and security alerts for monitoring",
        "placeholder": "ghp_...",
        "link": "https://github.com/settings/tokens",
        "group": "GitHub Monitor",
        "required": "true",
    },
    {
        "key": "GITHUB_WEBHOOK_SECRET",
        "label": "GitHub Webhook Secret",
        "description": "Validates HMAC signatures on incoming GitHub webhook events",
        "placeholder": "any-random-secret",
        "link": "https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries",
        "group": "GitHub Monitor",
        "required": "false",
    },
    {
        "key": "SLACK_BOT_TOKEN",
        "label": "Slack Bot Token",
        "description": "Sends security alerts and weekly reports to Slack channels",
        "placeholder": "xoxb-...",
        "link": "https://api.slack.com/apps",
        "group": "GitHub Monitor",
        "required": "true",
    },
    {
        "key": "SLACK_SIGNING_SECRET",
        "label": "Slack Signing Secret",
        "description": "Verifies incoming Slack event and action webhook requests",
        "placeholder": "...",
        "link": "https://api.slack.com/apps",
        "group": "GitHub Monitor",
        "required": "false",
    },
    # ── Google Drive (Company Knowledge) ─────────────────────────────────────
    {
        "key": "GOOGLE_CLIENT_ID",
        "label": "Google Client ID",
        "description": "OAuth 2.0 Client ID — enables Google Drive file picker in the sidebar",
        "placeholder": "1234567890-abc.apps.googleusercontent.com",
        "link": "https://console.cloud.google.com/apis/credentials",
        "group": "Google Drive",
        "required": "true",
    },
    {
        "key": "GOOGLE_CLIENT_SECRET",
        "label": "Google Client Secret",
        "description": "OAuth 2.0 Client Secret — paired with the Client ID",
        "placeholder": "GOCSPX-...",
        "link": "https://console.cloud.google.com/apis/credentials",
        "group": "Google Drive",
        "required": "true",
    },
    # ── Observability ─────────────────────────────────────────────────────────
    {
        "key": "LANGFUSE_PUBLIC_KEY",
        "label": "Langfuse Public Key",
        "description": "Enables LLM call tracing — tracks agent steps, latency, and cost",
        "placeholder": "pk-lf-...",
        "link": "https://cloud.langfuse.com",
        "group": "Observability",
        "required": "false",
    },
    {
        "key": "LANGFUSE_SECRET_KEY",
        "label": "Langfuse Secret Key",
        "description": "Paired with Langfuse Public Key for authenticated tracing",
        "placeholder": "sk-lf-...",
        "link": "https://cloud.langfuse.com",
        "group": "Observability",
        "required": "false",
    },
]


def _mask(value: str) -> str:
    """Mask an API key showing only first 6 and last 4 chars."""
    if not value:
        return ""
    if len(value) <= 10:
        return "****"
    return value[:6] + "****" + value[-4:]


def _get_key_status(key: str) -> dict[str, Any]:
    """Get the current status of a key — source + masked value."""
    from memory.sqlite_ops import get_api_key_from_db
    db_val = get_api_key_from_db(key)
    env_val = os.environ.get(key, "")

    if db_val:
        return {"source": "ui", "masked": _mask(db_val), "is_set": True}
    elif env_val:
        return {"source": "env", "masked": _mask(env_val), "is_set": True}
    else:
        return {"source": "none", "masked": "", "is_set": False}


@router.get("/keys")
async def get_keys() -> dict[str, Any]:
    """Return all managed keys with their current status."""
    result = []
    for meta in MANAGED_KEYS:
        status = _get_key_status(meta["key"])
        result.append({**meta, **status})
    return {"keys": result}


class KeyUpdate(BaseModel):
    key: str
    value: str


class KeysPayload(BaseModel):
    keys: list[KeyUpdate]


@router.post("/keys")
async def save_keys(payload: KeysPayload) -> dict[str, Any]:
    """Save one or more API keys to SQLite."""
    from memory.sqlite_ops import set_api_key, is_sqlite_ready

    if not is_sqlite_ready():
        raise HTTPException(status_code=503, detail="Database not ready")

    saved = []
    for item in payload.keys:
        key = item.key.strip()
        value = item.value.strip()

        if key not in {m["key"] for m in MANAGED_KEYS}:
            raise HTTPException(status_code=400, detail=f"Unknown key: {key}")

        if not value:
            raise HTTPException(status_code=400, detail=f"Value cannot be empty for {key}")

        set_api_key(key, value)
        os.environ[key] = value
        saved.append(key)
        logger.info("[Settings] Key saved: %s", key)

    # Invalidate model registry cache so new LLM keys take effect immediately
    _LLM_KEYS = {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_RESEARCH_MODEL", "OPENAI_SYNTHESIS_MODEL", "OPENAI_EMAIL_MODEL"}
    if set(saved) & _LLM_KEYS:
        try:
            from config import models as _models
            from config.settings import get_settings
            _models._MODEL_REGISTRY.clear()
            get_settings.cache_clear()
        except Exception as e:
            logger.warning("[Settings] Could not clear model cache: %s", e)

    return {"saved": saved, "count": len(saved)}


@router.delete("/keys/{key}")
async def delete_key(key: str) -> dict[str, Any]:
    """Remove a user-set key (pipeline will fall back to .env value)."""
    from memory.sqlite_ops import delete_api_key, is_sqlite_ready

    if key not in {m["key"] for m in MANAGED_KEYS}:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key}")

    if not is_sqlite_ready():
        raise HTTPException(status_code=503, detail="Database not ready")

    delete_api_key(key)
    logger.info("[Settings] Key deleted: %s", key)

    _LLM_KEYS = {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_RESEARCH_MODEL", "OPENAI_SYNTHESIS_MODEL", "OPENAI_EMAIL_MODEL"}
    if key in _LLM_KEYS:
        try:
            from config import models as _models
            from config.settings import get_settings
            _models._MODEL_REGISTRY.clear()
            get_settings.cache_clear()
        except Exception as e:
            logger.warning("[Settings] Could not clear model cache: %s", e)

    env_val = os.environ.get(key, "")
    return {
        "deleted": key,
        "fallback": "env" if env_val else "none",
    }
