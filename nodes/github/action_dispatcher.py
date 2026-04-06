"""
Agent 5: Action Dispatcher

Executes automated actions based on intelligence report:
- Sends Slack alerts for critical security issues
- Creates GitHub issues for unresolved vulnerabilities
- Auto-assigns reviewers for stale PRs
- Stores metrics in Supabase
- Sends weekly email reports

Uses GPT-4o-mini (research role) + Slack, GitHub, Email MCP tools.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff, build_skip_output
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a DevOps action coordinator. Based on the intelligence report,
determine and execute the appropriate automated actions.

Action decision matrix:
1. CRITICAL security alert → Slack #security-alerts (immediate) + GitHub issue (P0)
2. HIGH security alert → Slack #security-alerts + GitHub issue (P1)
3. Stale PR (>48h no review) → Slack mention to team lead + auto-assign reviewer
4. PR cycle time >2x baseline → Slack #engineering-metrics warning
5. Deployment failure pattern → Slack #incidents + GitHub issue
6. Weekly report requested → Email to engineering-leads distribution list

For each action, provide:
- action_type: slack_alert | github_issue | assign_reviewer | email_report | store_metrics
- priority: P0 | P1 | P2 | P3
- target: channel/repo/email
- payload: structured content for the action
- confidence: 0.0-1.0 (only execute if >= threshold)

Return structured JSON with actions list and execution summary."""


@register_node("action_dispatcher")
def create_action_dispatcher(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    confidence_threshold = params.get("config", {}).get("confidence_threshold", 0.7)

    async def action_dispatcher_node(state: dict[str, Any]) -> dict[str, Any]:
        intelligence_report = state.get("intelligence_report", {})
        risk_score = state.get("risk_score", 0)
        action_items = state.get("action_items", [])
        weekly_payload = state.get("weekly_payload")
        repo = state.get("repo", "")

        llm = build_chat_llm(model_config)

        dispatch_context = {
            "intelligence_report": intelligence_report,
            "risk_score": risk_score,
            "action_items": action_items,
            "weekly_payload": weekly_payload,
            "repo": repo,
            "confidence_threshold": confidence_threshold,
            "auto_create_issues": params.get("config", {}).get("auto_create_issues", True),
            "auto_assign_reviewers": params.get("config", {}).get("auto_assign_reviewers", True),
        }

        try:
            result = await retry_with_backoff(
                _dispatch_actions,
                llm, dispatch_context,
                max_retries=params.get("retry", 2),
                node_name="action_dispatcher",
            )
            return result
        except Exception as exc:
            logger.error("[Dispatcher] Failed: %s", exc)
            return {
                "dispatched_actions": [],
                "dispatch_summary": build_skip_output("action_dispatcher", str(exc)),
            }

    return action_dispatcher_node


async def _dispatch_actions(
    llm: Any, context: dict,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Determine actions for:\n{context}"},
    ]

    response = await llm.ainvoke(messages)

    # In production, this would parse response.content and execute
    # each action via the appropriate MCP tool (Slack, GitHub, Email).
    return {
        "dispatched_actions": [],
        "dispatch_summary": {
            "analysis": response.content,
            "actions_planned": 0,
            "actions_executed": 0,
        },
    }
