"""
Agent 1: Event Collector

Ingests webhook events from Redis queue (webhook trigger) OR polls
GitHub API (cron trigger). Normalizes raw events into structured records.

Uses GPT-4o-mini (research role) + GitHub MCP tools.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff, build_skip_output
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a GitHub event analyst. You have access to GitHub tools.

CRITICAL RULES:
- For cron-triggered runs, you MUST use the get_repo, list_pull_requests, and get_issues tools
  to poll the repository for recent activity.
- NEVER say "I can't access GitHub" — you have tools that CAN.
- If a tool returns an error or is unavailable, report the error and continue with available data.

Process and normalize GitHub events into structured records for downstream analysis.

For each event, extract:
- event_type, timestamp, actor, repo
- Key details (PR title, branch, review status, alert severity, etc.)
- Classification: security | productivity | deployment | other

Return a structured summary: total events, breakdown by type, key highlights."""


@register_node("event_collector")
def create_event_collector(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def event_collector_node(state: dict[str, Any]) -> dict[str, Any]:
        trigger = state.get("trigger", "cron")
        repo = state.get("repo", "")

        llm = build_chat_llm(model_config)

        try:
            if trigger == "webhook":
                events = [state.get("normalized_event", {})]
            else:
                events = []

            result = await retry_with_backoff(
                _process_events,
                llm, events, repo, tools,
                max_retries=params.get("retry", 3),
                node_name="event_collector",
            )
            return result

        except Exception as exc:
            return {
                "normalized_events": [],
                "event_summary": build_skip_output("event_collector", str(exc)),
            }

    return event_collector_node


async def _process_events(
    llm: Any, events: list[dict], repo: str, tools: list,
) -> dict[str, Any]:
    if not events and not tools:
        return {
            "normalized_events": [],
            "event_summary": {"total": 0, "repo": repo},
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Process GitHub events for {repo}.\nExisting events: {events}"},
    ]

    response = await run_tool_agent(llm, tools, messages)

    return {
        "normalized_events": events,
        "event_summary": {
            "total": len(events),
            "repo": repo,
            "analysis": response.content,
        },
    }
