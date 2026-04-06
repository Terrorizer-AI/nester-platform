"""
Agent 4: Intelligence Synthesizer

Merges security alerts + productivity metrics into actionable insights.
Detects anomalies, correlates patterns, produces weekly report payload.

Uses GPT-5.4-nano (synthesis role) — no MCP tools needed.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a DevOps intelligence analyst. Synthesize security and
productivity data into actionable insights for engineering leadership.

From the combined data, produce:
1. Executive Summary: 2-3 sentence overview of repository health
2. Anomaly Detection:
   - Sudden spikes in PR cycle time (>2x baseline)
   - Unusual commit patterns (off-hours, burst commits)
   - Security alert surges
   - Review bottleneck formation
3. Correlation Analysis:
   - Security alerts vs deployment frequency
   - Review turnaround vs PR merge rate
   - Team velocity trends
4. Risk Assessment:
   - Overall risk score (0-100)
   - Top 3 risks with severity and recommended actions
5. Recommendations:
   - Prioritized action items
   - Suggested process improvements
6. Weekly Report Payload (if weekly_report flag is set):
   - Full metrics summary
   - Week-over-week trends
   - Team leaderboard

Return structured JSON with all sections."""


@register_node("intelligence_synthesizer")
def create_intelligence_synthesizer(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "synthesis"))

    async def intelligence_synthesizer_node(state: dict[str, Any]) -> dict[str, Any]:
        security_alerts = state.get("security_alerts", [])
        severity_counts = state.get("severity_counts", {})
        productivity_metrics = state.get("productivity_metrics", {})
        bottleneck_report = state.get("bottleneck_report", {})
        trends = state.get("trends", {})
        event_summary = state.get("event_summary", {})
        is_weekly = state.get("weekly_report", False)

        llm = build_chat_llm(model_config)

        combined_data = {
            "security": {
                "alerts": security_alerts,
                "severity_counts": severity_counts,
                "unresolved_critical": state.get("unresolved_critical", 0),
            },
            "productivity": {
                "metrics": productivity_metrics,
                "bottlenecks": bottleneck_report,
                "trends": trends,
            },
            "events": event_summary,
            "weekly_report_requested": is_weekly,
        }

        try:
            result = await retry_with_backoff(
                _synthesize_intelligence,
                llm, combined_data,
                max_retries=params.get("retry", 1),
                node_name="intelligence_synthesizer",
            )
            return result
        except Exception as exc:
            logger.error("[Synthesizer] Failed: %s", exc)
            return {
                "intelligence_report": {"error": str(exc)},
                "risk_score": -1,
                "action_items": [],
                "weekly_payload": {} if is_weekly else None,
            }

    return intelligence_synthesizer_node


async def _synthesize_intelligence(
    llm: Any, combined_data: dict,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Synthesize the following data:\n{combined_data}"},
    ]

    response = await llm.ainvoke(messages)

    return {
        "intelligence_report": {"analysis": response.content},
        "risk_score": 0,
        "action_items": [],
        "weekly_payload": None,
    }
