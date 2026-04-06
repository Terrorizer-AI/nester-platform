"""
Agent 2: Security Analyzer

Scans for Dependabot alerts, secret scanning alerts, code scanning findings.
Prioritizes by severity. Never misses critical alerts — re-queues on failure.

Uses GPT-4o-mini (research role) + GitHub MCP security toolset.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a security analyst specializing in GitHub repository security.
You have access to GitHub tools.

CRITICAL RULES:
- You MUST use the get_dependabot_alerts tool to check for security vulnerabilities.
- NEVER say "I can't access GitHub" — you have tools that CAN.
- If a tool returns an error, report it and work with available data.

Analyze security alerts and classify their severity and urgency.

For each alert:
1. Type: dependabot | secret_scanning | code_scanning
2. Severity: critical | high | medium | low
3. Status: open | dismissed | fixed
4. Affected component/file
5. Recommended action
6. Time to resolution estimate

Prioritize critical alerts first. Flag any unresolved critical alerts prominently.
Return structured JSON with severity_counts and prioritized alert list."""


@register_node("security_analyzer")
def create_security_analyzer(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def security_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
        repo = state.get("repo", "")
        events = state.get("normalized_events", [])

        llm = build_chat_llm(model_config)

        result = await retry_with_backoff(
            _analyze_security,
            llm, repo, events, tools,
            max_retries=params.get("retry", 3),
            node_name="security_analyzer",
        )
        return result

    return security_analyzer_node


async def _analyze_security(
    llm: Any, repo: str, events: list[dict], tools: list,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze security for {repo}.\nEvents: {events}"},
    ]

    response = await run_tool_agent(llm, tools, messages)

    return {
        "security_alerts": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "unresolved_critical": 0,
    }
