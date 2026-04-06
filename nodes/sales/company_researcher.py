"""
Agent 2: Company Researcher

Analyzes the prospect's company website: mission, products, target market,
tech stack, pain points, recent news, funding.

Uses GPT-4o-mini (research role) + Web Scraper + Search MCP tools.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import ErrorStrategy, retry_with_backoff, build_skip_output
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior company intelligence analyst preparing a sales briefing. You have web scraping and search tools.

MANDATORY TOOL USAGE — you MUST call ALL of these before synthesizing:
1. extract_website(company_website) — homepage content
2. extract_website(company_website + "/about") or "/about-us" — mission, team, story
3. extract_website(company_website + "/pricing") — pricing tiers, customer segments
4. company_search(company_name) — funding, news, market position
5. news_search("company_name funding OR launch OR partnership 2024 2025") — recent events

CRITICAL RULES:
- NEVER say "I can't access websites" — you have tools that CAN.
- If one URL 404s, try the homepage or another path.
- NEVER fabricate data. Only use what tools return.
- Extract EVERYTHING — do not summarize or shorten.

OUTPUT: Return a single detailed JSON object with ALL of these fields populated:
{
  "company": "name",
  "tagline": "short slogan from website",
  "mission": "full mission statement",
  "about": "full about section text, verbatim if possible",
  "industry": "industry vertical",
  "headquarters": "city, country",
  "founded": "year",
  "size": "headcount range",
  "stage": "seed/series-A/series-B/growth/public",
  "funding": "most recent round (e.g. $6.3M Seed)",
  "total_funding_raised": "cumulative total if available",
  "valuation": "valuation if public",
  "investors": ["investor name 1", "investor name 2"],
  "revenue_range": "ARR range if known",
  "products": ["detailed product/service name with 1-line description"],
  "key_features": ["feature 1", "feature 2", "feature 3"],
  "integrations": ["integration partner 1", "integration 2"],
  "tech_stack": ["inferred tech from job posts, website, or docs"],
  "target_market": "detailed ICP description",
  "customer_segments": ["segment 1 with examples", "segment 2"],
  "use_cases": ["use case 1 with detail", "use case 2"],
  "pain_points": ["pain point they solve 1", "pain point 2"],
  "competitive_advantages": ["advantage 1", "advantage 2"],
  "competitors": ["competitor 1", "competitor 2"],
  "growth_signals": [
    {"signal": "specific observable growth signal", "icon": "↑", "source": "where you found it"}
  ],
  "traction_metrics": ["1000+ customers", "500K monthly calls", "40% MoM growth"],
  "recent_news": [
    {"title": "headline", "date": "month year", "summary": "2-3 sentence detail", "url": "if available"}
  ],
  "hiring_signals": ["role they are hiring for"],
  "social_proof": ["award", "partnership", "press mention"],
  "pricing_model": "freemium / usage-based / seat-based / enterprise",
  "pricing_tiers": ["free tier description", "paid tier"],
  "confidence": 0.9
}"""


@register_node("company_researcher")
def create_company_researcher(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def company_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
        company_website = state.get("company_website", "")
        linkedin_data = state.get("linkedin_data", {})
        company_name = linkedin_data.get("company", "")

        if not company_website and not company_name:
            return {
                "company_data": build_skip_output("company_researcher", "No company info"),
            }

        llm = build_chat_llm(model_config)

        try:
            result = await retry_with_backoff(
                _research_company,
                llm, company_website, company_name, tools,
                max_retries=params.get("retry", 3),
                node_name="company_researcher",
            )
            _store_to_memory(result, company_name)
            return result
        except Exception as exc:
            strategy = ErrorStrategy(params.get("on_error", "retry_then_skip"))
            if strategy in (ErrorStrategy.RETRY_THEN_SKIP, ErrorStrategy.SKIP_IMMEDIATELY):
                return {"company_data": build_skip_output("company_researcher", str(exc))}
            raise

    return company_researcher_node


async def _research_company(
    llm: Any, website: str, company_name: str, tools: list,
) -> dict[str, Any]:
    target = website or company_name
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Research this company: {target}"},
    ]

    response = await run_tool_agent(llm, tools, messages, agent_name="company_researcher")

    return {
        "company_data": {
            "website": website,
            "company_name": company_name,
            "raw_response": response.content,
        },
    }


def _store_to_memory(result: dict[str, Any], company_name: str) -> None:
    """Store company research output in Mem0."""
    try:
        from memory.mem0_store import store_agent_output
        raw = result.get("company_data", {}).get("raw_response", "")
        store_agent_output(
            agent_name="company_researcher",
            raw_response=raw,
            company_name=company_name,
        )
    except Exception:
        pass
