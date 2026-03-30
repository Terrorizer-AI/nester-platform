"""
Agent 1: LinkedIn Researcher

Retrieves 48+ structured data points from a prospect's LinkedIn profile:
name, title, company, experience history, education, skills, certifications.

Uses GPT-4o-mini (research role) + LinkedIn MCP tools.
"""

import logging
from typing import Any, Callable

from langchain_openai import ChatOpenAI

from config.models import get_model
from core.errors import ErrorStrategy, retry_with_backoff, build_skip_output
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a LinkedIn research specialist. You have access to LinkedIn tools.

CRITICAL RULES:
- You MUST call the get_person_profile tool with the linkedin_username parameter.
- Extract the username from the LinkedIn URL: https://linkedin.com/in/USERNAME → use "USERNAME".
- Request ALL available sections: sections="experience,education,posts,interests,honors,languages,contact_info"
- NEVER say "I can't access websites" — you have tools that CAN.
- If the tool returns an error or is unavailable, report the error in structured format.
- NEVER generate fictional profile data. Only return data from tool results.

After receiving the tool result, parse the raw text THOROUGHLY and extract EVERY detail:

BASIC PROFILE:
- Full name, headline, current title, current company
- Industry, location (city + country), profile photo URL
- Connection count, follower count, mutual connections
- About/summary section (full text)

EXPERIENCE (every role):
- Job title, company name, company LinkedIn URL
- Employment type (full-time, contract, etc.)
- Start date → end date (or "Present"), calculated duration
- Location, description/responsibilities (full text)
- Skills used in each role

EDUCATION (every entry):
- Institution name, degree type, field of study
- Start year → end year, activities, societies
- Grade/GPA if listed

SKILLS & ENDORSEMENTS:
- All listed skills with endorsement counts
- Top 3 most-endorsed skills highlighted

CERTIFICATIONS & LICENSES:
- Certification name, issuing organization, date, credential ID

POSTS & ACTIVITY:
- Recent posts (titles, topics, engagement counts)
- Posting frequency estimate
- Content themes and tone

INTERESTS & HONORS:
- Influencers/companies/groups followed
- Awards, publications, patents, volunteer work

LANGUAGES:
- Languages spoken with proficiency levels

CONTACT INFO:
- Email, phone, website, Twitter/X handle if available

Rate data quality:
- "high": 30+ fields populated with real data
- "medium": 15-30 fields populated
- "low": fewer than 15 fields

Return structured JSON with ALL sections above. Do NOT skip any section — if data is unavailable, include the key with null or empty value."""


@register_node("linkedin_researcher")
def create_linkedin_researcher(params: dict[str, Any]) -> Callable:
    """Factory: create a LinkedIn researcher node function."""
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def linkedin_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
        linkedin_url = state.get("linkedin_url", "")
        if not linkedin_url:
            return {
                "linkedin_data": {},
                "linkedin_data_quality": "failed",
                "errors": [{"node": "linkedin_researcher", "error": "No LinkedIn URL provided"}],
            }

        llm = ChatOpenAI(
            model=model_config.model_id,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )

        try:
            result = await retry_with_backoff(
                _research_profile,
                llm, linkedin_url, tools,
                max_retries=params.get("retry", 3),
                node_name="linkedin_researcher",
            )
            # Store in memory layer
            _store_to_memory(result)
            return result
        except Exception as exc:
            strategy = ErrorStrategy(params.get("on_error", "retry_then_skip"))
            if strategy in (ErrorStrategy.RETRY_THEN_SKIP, ErrorStrategy.SKIP_IMMEDIATELY):
                logger.warning("[LinkedIn] Skipping after failure: %s", exc)
                return {
                    "linkedin_data": build_skip_output("linkedin_researcher", str(exc)),
                    "linkedin_data_quality": "failed",
                }
            raise

    return linkedin_researcher_node


async def _research_profile(llm: Any, linkedin_url: str, tools: list) -> dict[str, Any]:
    """Execute the LinkedIn research using LLM + MCP tools."""
    # Extract username for the user message so the LLM has it ready
    username = linkedin_url.rstrip("/").split("/in/")[-1] if "/in/" in linkedin_url else linkedin_url

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Research this LinkedIn profile thoroughly: {linkedin_url}\n"
            f"Username to use: {username}\n"
            f"Call get_person_profile with ALL sections: sections='experience,education,posts,interests,honors,languages,contact_info'\n"
            f"The main profile page already includes name, title, headline, about, skills.\n"
            f"The extra sections give us interests (who they follow), honors (awards/patents),\n"
            f"languages, and contact info (email/phone/website).\n"
            f"Extract EVERY available data point from the results."
        )},
    ]

    response = await run_tool_agent(llm, tools, messages, agent_name="linkedin_researcher")

    # Estimate data quality from response length
    content = response.content or ""
    if len(content) > 5000:
        quality = "high"
    elif len(content) > 2000:
        quality = "medium"
    else:
        quality = "low"

    return {
        "linkedin_data": {
            "url": linkedin_url,
            "username": username,
            "raw_response": content,
        },
        "linkedin_data_quality": quality,
    }


def _store_to_memory(result: dict[str, Any]) -> None:
    """Store LinkedIn research output in Mem0."""
    try:
        from memory.mem0_store import store_agent_output
        li_data = result.get("linkedin_data", {})
        raw = li_data.get("raw_response", "")
        # Try to extract name from the raw response
        name = ""
        if raw:
            for line in raw.split("\n")[:20]:
                if "name" in line.lower() and ":" in line:
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
        store_agent_output(
            agent_name="linkedin_researcher",
            raw_response=raw,
            prospect_name=name,
        )
    except Exception:
        pass
