"""
Agent 8: Output Formatter

Takes the raw text responses from all 4 research agents and uses a cheap LLM
(nano model) to extract clean structured JSON for the frontend to display.

Runs AFTER email_composer. Adds ~2-3 seconds and ~$0.001 per run.
Never raises — always returns whatever it can parse, degrading gracefully.
"""

import json
import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a data extraction specialist. You receive raw research text from AI agents.
Extract structured data and return ONLY valid JSON — no markdown, no explanation, no code fences.

CRITICAL RULES:
- Extract EVERY piece of data you find — do not summarize or shorten
- For arrays (products, competitors, pain_points, growth_signals, etc.) include ALL items found, not just the first few
- For text fields (mission, about, target_market) include the FULL text verbatim
- Never truncate or omit data — completeness is the priority
- If a field has data in the raw text, it must appear in the output

Return exactly this structure (use null for missing fields, empty arrays [] for missing lists):

{
  "linkedin_parsed": {
    "name": "Full Name",
    "title": "Current Job Title",
    "company": "Current Company Name",
    "location": "City, Country",
    "connections": "500+",
    "about": "Summary text...",
    "experience": [
      {"title": "Job Title", "company": "Company", "duration": "Jan 2022 - Present", "description": "..."}
    ],
    "education": [
      {"school": "University Name", "degree": "B.Tech Computer Science", "years": "2016-2020"}
    ],
    "skills": ["skill1", "skill2"],
    "posts": [
      {"content": "Post text excerpt...", "engagement": "123 likes", "date": "2 weeks ago"}
    ],
    "contact": {"email": null, "website": null, "phone": null}
  },
  "company_parsed": {
    "name": "Company Name",
    "website": "https://...",
    "mission": "Mission statement...",
    "tagline": "Short company tagline or slogan",
    "industry": "Industry vertical",
    "headquarters": "City, Country",
    "founded": "2021",
    "size": "11-50 employees",
    "stage": "Seed / Series A / etc",
    "funding": "Bootstrapped / $2M Seed / etc",
    "total_funding_raised": "$5M",
    "valuation": "$50M or null",
    "revenue_range": "$1M-$10M ARR or null",
    "products": ["Product 1", "Product 2"],
    "tech_stack": ["React", "Python", "AWS"],
    "pain_points": ["Pain point 1", "Pain point 2"],
    "growth_signals": [
      {"signal": "Description of growth signal", "icon": "↑"}
    ],
    "target_market": "Description of ICP...",
    "competitors": ["Competitor 1", "Competitor 2"],
    "recent_news": [
      {"title": "News headline", "date": "Month Year", "summary": "Brief summary"}
    ],
    "hiring_signals": ["Hiring for X role", "Expanding Y team"],
    "social_proof": ["Award or recognition", "Partnership announcement"],
    "key_metrics": [
      {"label": "Employees", "value": "47", "trend": "up"},
      {"label": "Followers", "value": "360", "trend": "stable"}
    ]
  },
  "company_linkedin_parsed": {
    "name": "Company Name",
    "tagline": "Company tagline...",
    "employees": "11-50",
    "followers": "1,234",
    "founded": "2021",
    "specialties": ["specialty1", "specialty2"],
    "recent_posts": [
      {"content": "Post text...", "date": "1 week ago", "engagement": "45 reactions"}
    ],
    "key_people": [
      {"name": "Person Name", "title": "CEO & Co-founder"}
    ],
    "content_themes": ["AI", "Voice tech", "B2B SaaS"]
  },
  "activity_parsed": {
    "topics": ["topic1", "topic2"],
    "pain_points": [
      {"pain": "Pain description", "evidence": "Quote from post..."}
    ],
    "buying_signals": ["Signal 1", "Signal 2"],
    "communication_dna": {
      "writing_style": "Conversational and direct",
      "tone": "Inspirational",
      "post_length": "Short (< 100 words)",
      "emoji_usage": "Occasional",
      "posting_frequency": "Weekly"
    },
    "best_post_quotes": ["Quote 1", "Quote 2"]
  }
}"""


@register_node("output_formatter")
def create_output_formatter(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))

    async def output_formatter_node(state: dict[str, Any]) -> dict[str, Any]:
        linkedin_data        = state.get("linkedin_data", {})
        company_data         = state.get("company_data", {})
        company_linkedin_data = state.get("company_linkedin_data", {})
        activity_data        = state.get("activity_data", {})

        llm = build_chat_llm(model_config, temperature=0.0, max_tokens=16000)

        try:
            parsed = await _format_output(
                llm,
                linkedin_data,
                company_data,
                company_linkedin_data,
                activity_data,
            )
            _store_to_memory(parsed, state)
            return parsed
        except Exception as exc:
            logger.warning("[OutputFormatter] Failed: %s", exc)
            # Never block the pipeline — return empty parsed fields
            return {
                "linkedin_parsed": {},
                "company_parsed": {},
                "company_linkedin_parsed": {},
                "activity_parsed": {},
            }

    return output_formatter_node


def _get_raw(data: Any) -> str:
    """Extract the raw text from an agent's output dict."""
    if not data:
        return "No data available."
    if isinstance(data, dict):
        raw = data.get("raw_response", "")
        if raw and isinstance(raw, str):
            return raw[:15000]  # cap per agent to stay within context
        # If skipped
        if data.get("skipped"):
            return f"Skipped: {data.get('reason', 'no data')}"
        return json.dumps(data, default=str)[:4000]
    return str(data)[:4000]


async def _format_output(
    llm: Any,
    linkedin_data: Any,
    company_data: Any,
    company_linkedin_data: Any,
    activity_data: Any,
) -> dict[str, Any]:

    user_message = f"""Extract structured data from these 4 research outputs.
Be exhaustive — extract every product, competitor, growth signal, news item, hiring signal, and social proof item you find.
Do NOT skip or truncate any arrays.

═══ LINKEDIN PROFILE (Agent 1) ═══
{_get_raw(linkedin_data)}

═══ COMPANY RESEARCH (Agent 2a) ═══
{_get_raw(company_data)}

═══ COMPANY LINKEDIN (Agent 2b) ═══
{_get_raw(company_linkedin_data)}

═══ PROSPECT ACTIVITY (Agent 3) ═══
{_get_raw(activity_data)}

Return ONLY the JSON object. No explanation. Include ALL data found — do not truncate arrays."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    response = await llm.ainvoke(messages)
    content = response.content or ""

    # Strip any accidental markdown fences
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("[OutputFormatter] Could not parse LLM JSON response")
        parsed = {}

    return {
        "linkedin_parsed":          parsed.get("linkedin_parsed", {}),
        "company_parsed":           parsed.get("company_parsed", {}),
        "company_linkedin_parsed":  parsed.get("company_linkedin_parsed", {}),
        "activity_parsed":          parsed.get("activity_parsed", {}),
    }


def _store_to_memory(parsed: dict[str, Any], state: dict[str, Any]) -> None:
    """Store final parsed output in Mem0 — the richest structured data."""
    try:
        import json as _json
        from memory.mem0_store import store_agent_output

        li_parsed = parsed.get("linkedin_parsed", {})
        co_parsed = parsed.get("company_parsed", {})

        prospect_name = li_parsed.get("name", "") if isinstance(li_parsed, dict) else ""
        company_name = co_parsed.get("name", "") if isinstance(co_parsed, dict) else ""

        # Store the full parsed output as a structured summary
        content = _json.dumps(parsed, default=str)
        store_agent_output(
            agent_name="output_formatter",
            raw_response=content,
            prospect_name=prospect_name,
            company_name=company_name,
        )
    except Exception:
        pass
