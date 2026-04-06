"""
Agent 2b: Company LinkedIn Researcher  (runs in parallel with company_researcher)

Extracts structured data from the prospect's company LinkedIn page:
  - Company overview, mission, specialties
  - Headcount, growth signals, recent hires
  - Recent company posts and engagement
  - Key people (founders, C-suite visible on LinkedIn)
  - Funding mentions, awards, featured updates

Uses GPT-5.4-nano (research role) + LinkedIn MCP tools.
If no company_linkedin_url is provided, skips gracefully.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import ErrorStrategy, retry_with_backoff, build_skip_output
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a LinkedIn company page research specialist. You have access to LinkedIn tools.

CRITICAL RULES:
- You MUST call the get_company_profile tool with the company_username/slug parameter.
- Extract the company slug from the URL: https://linkedin.com/company/SLUG → use "SLUG".
- NEVER say "I can't access LinkedIn" — you have tools that CAN.
- NEVER fabricate company data. Only return what the tool actually returns.
- If the tool fails, report it in the structured output with skipped: true.

After receiving the tool result, extract and structure ALL available fields:

COMPANY OVERVIEW:
- Official company name, tagline, about/description
- Industry, company type (public/private/nonprofit), founded year
- Headquarters location, website URL
- Company size range and exact employee count (LinkedIn reported)
- Specialties list

GROWTH SIGNALS:
- Headcount growth % (LinkedIn provides this)
- Recent job postings count (indicator of growth areas)
- Follower count and follower growth trend

RECENT COMPANY POSTS:
- Last 5 company posts (topic, content snippet, engagement count)
- Posting frequency
- Recurring themes in content

KEY PEOPLE (visible on LinkedIn):
- Founders, CEO, key leadership with their titles
- Any recent leadership changes mentioned

COMPANY HIGHLIGHTS:
- Awards, certifications, badges
- Recent news or featured updates posted by the company
- Products/services showcased in posts

Return structured JSON. Never include invented data."""


@register_node("company_linkedin_researcher")
def create_company_linkedin_researcher(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def company_linkedin_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
        company_linkedin_url = state.get("company_linkedin_url", "")

        if not company_linkedin_url:
            return {
                "company_linkedin_data": build_skip_output(
                    "company_linkedin_researcher",
                    "No company LinkedIn URL provided",
                ),
            }

        llm = build_chat_llm(model_config)

        try:
            result = await retry_with_backoff(
                _research_company_linkedin,
                llm, company_linkedin_url, tools,
                max_retries=params.get("retry", 3),
                node_name="company_linkedin_researcher",
            )
            _store_to_memory(result, state.get("linkedin_data", {}).get("company", ""))
            return result
        except Exception as exc:
            strategy = ErrorStrategy(params.get("on_error", "retry_then_skip"))
            if strategy in (ErrorStrategy.RETRY_THEN_SKIP, ErrorStrategy.SKIP_IMMEDIATELY):
                logger.warning("[CompanyLinkedIn] Skipping after failure: %s", exc)
                return {
                    "company_linkedin_data": build_skip_output(
                        "company_linkedin_researcher", str(exc)
                    ),
                }
            raise

    return company_linkedin_researcher_node


async def _research_company_linkedin(
    llm: Any, company_linkedin_url: str, tools: list
) -> dict[str, Any]:
    slug = company_linkedin_url.rstrip("/").split("/company/")[-1].split("/")[0]
    if not slug:
        slug = company_linkedin_url

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Research this company LinkedIn page thoroughly: {company_linkedin_url}\n"
            f"Company slug: {slug}\n"
            f"Extract every available field — posts, headcount, specialties, key people."
        )},
    ]

    response = await run_tool_agent(llm, tools, messages, agent_name="company_linkedin")
    content = response.content or ""

    return {
        "company_linkedin_data": {
            "url": company_linkedin_url,
            "slug": slug,
            "raw_response": content,
        },
    }


def _store_to_memory(result: dict[str, Any], company_name: str) -> None:
    """Store company LinkedIn research output in Mem0."""
    try:
        from memory.mem0_store import store_agent_output
        raw = result.get("company_linkedin_data", {}).get("raw_response", "")
        store_agent_output(
            agent_name="company_linkedin_researcher",
            raw_response=raw,
            company_name=company_name,
        )
    except Exception:
        pass
