"""
Agent 3: Productivity Analyzer

Computes PR cycle time (open→merge), review turnaround, deployment frequency,
commit velocity. Identifies review bottlenecks. Skipped on fast-path (critical events).

Uses GPT-4o-mini (research role) + GitHub MCP + custom metrics tools.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff, build_skip_output
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a DevOps productivity analyst. Compute engineering metrics
from GitHub repository data.

Compute:
- PR cycle time: median hours from open to merge
- Review turnaround: median hours from PR open to first review
- Merge rate: % of PRs merged vs closed
- Deployment frequency: deployments per week
- Commit velocity: commits per day, trend (increasing/stable/decreasing)
- Review bottlenecks: reviewers with slowest response times
- Stale PRs: PRs open > 48 hours without review

Return structured JSON with all metrics and trend indicators."""


@register_node("productivity_analyzer")
def create_productivity_analyzer(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))

    async def productivity_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
        # Skip on fast-path (critical security events)
        if state.get("fast_path", False):
            logger.info("[Productivity] Skipped — fast-path active")
            return {
                "productivity_metrics": {"skipped": True, "reason": "fast_path"},
                "bottleneck_report": {},
                "trends": {},
            }

        repo = state.get("repo", "")
        events = state.get("normalized_events", [])

        llm = build_chat_llm(model_config)

        try:
            result = await retry_with_backoff(
                _analyze_productivity,
                llm, repo, events,
                max_retries=params.get("retry", 2),
                node_name="productivity_analyzer",
            )
            return result
        except Exception as exc:
            return {
                "productivity_metrics": build_skip_output("productivity_analyzer", str(exc)),
                "bottleneck_report": {},
                "trends": {},
            }

    return productivity_analyzer_node


async def _analyze_productivity(
    llm: Any, repo: str, events: list[dict],
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Compute productivity metrics for {repo}.\nEvents: {events}"},
    ]

    response = await llm.ainvoke(messages)

    return {
        "productivity_metrics": {"analysis": response.content},
        "bottleneck_report": {},
        "trends": {},
    }
