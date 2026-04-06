"""
Agent 3: Activity Analyzer

Retrieves recent LinkedIn posts; identifies topics of interest,
pain points, buying signals, and communication style.

Uses GPT-4o-mini (research role) + LinkedIn MCP tools.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import ErrorStrategy, retry_with_backoff, build_skip_output
from core.registry import register_node
from nodes.tool_agent import run_tool_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a social media analyst specializing in B2B sales intelligence.
You have access to LinkedIn tools.

CRITICAL RULES:
- FIRST check the "EXISTING PROFILE DATA" in the user message — it likely already contains posts data.
- If existing data has posts content, analyze those posts directly WITHOUT calling any tools.
- Only call get_person_profile with sections="posts" if the existing data has NO post content at all.
- Extract the username from the LinkedIn URL: https://linkedin.com/in/USERNAME → use "USERNAME".
- NEVER call get_company_posts — that fetches company page posts, not person activity.
- NEVER say "I can't access websites" — you have tools that CAN.
- If the tool returns an error, work with the profile data already provided in the user message.
- NEVER fabricate activity data.

Analyze the prospect's recent LinkedIn posts and activity IN DEPTH.

Extract and analyze:

TOPICS OF INTEREST:
- What topics do they post about? (list each with frequency and confidence)
- What do they share/repost? (reveals what they admire or aspire to)
- What hashtags do they use?

SPECIFIC POSTS (quote actual content):
- For each significant post: topic, key quote (3-10 words), engagement count, date if available
- These quotes will be used in email personalization — accuracy is critical
- Note how RECENT each post is — stale posts (>6 months) are less useful as outreach hooks

PAIN POINTS:
- Explicit pain points mentioned in posts (quote the relevant text)
- Implicit pain points inferred from context (explain your reasoning)

BUYING SIGNALS:
- New role announcements (timing matters — recent = high intent)
- Company expansion, hiring, or product launches
- Complaints about current tools or processes
- Questions asked to network (reveals active problem-solving)

COMMUNICATION DNA:
- Writing style: formal, conversational, technical, storytelling, punchy
- Emoji usage: frequency and types
- Post length: short zingers vs long-form essays
- Tone: inspirational, analytical, humorous, direct
- Language patterns: specific phrases they repeat

ENGAGEMENT PATTERNS:
- Posting frequency (daily, weekly, monthly, rarely)
- Best performing posts (highest engagement)
- Comment style on others' posts

Return structured JSON with ALL sections above. Quote actual post content where possible."""


@register_node("activity_analyzer")
def create_activity_analyzer(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "research"))
    tools = params.get("tools", [])

    async def activity_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
        linkedin_url = state.get("linkedin_url", "")
        linkedin_data = state.get("linkedin_data", {})

        if not linkedin_url:
            return {
                "activity_data": build_skip_output("activity_analyzer", "No LinkedIn URL"),
                "communication_style": "professional",
            }

        llm = build_chat_llm(model_config)

        try:
            result = await retry_with_backoff(
                _analyze_activity,
                llm, linkedin_url, linkedin_data, tools,
                max_retries=params.get("retry", 3),
                node_name="activity_analyzer",
            )
            _store_to_memory(result, linkedin_url)
            return result
        except Exception as exc:
            strategy = ErrorStrategy(params.get("on_error", "retry_then_skip"))
            if strategy in (ErrorStrategy.RETRY_THEN_SKIP, ErrorStrategy.SKIP_IMMEDIATELY):
                return {
                    "activity_data": build_skip_output("activity_analyzer", str(exc)),
                    "communication_style": "professional",
                }
            raise

    return activity_analyzer_node


async def _analyze_activity(
    llm: Any, linkedin_url: str, linkedin_data: dict, tools: list,
) -> dict[str, Any]:
    # Extract username for the tool call
    username = linkedin_url.rstrip("/").split("/in/")[-1] if "/in/" in linkedin_url else linkedin_url

    # Pass existing profile data (already fetched by linkedin_researcher) as context.
    # The linkedin_researcher already scraped experience,education,posts — reuse it.
    existing_raw = linkedin_data.get("raw_response", "") if isinstance(linkedin_data, dict) else ""

    # Give the LLM enough data to work with — posts are often at the end of long responses
    existing_context = (
        f"\n\nEXISTING PROFILE DATA (already fetched — includes posts section):\n"
        f"{existing_raw[:12000]}"
        if existing_raw else ""
    )

    # If we already have substantial data, tell the LLM to use it instead of re-scraping
    has_existing_data = len(existing_raw) > 1000

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Analyze activity for: {linkedin_url}\n"
            f"LinkedIn username: {username}\n"
            + (
                f"The profile data below ALREADY includes posts. Analyze the posts from the existing data.\n"
                f"Only call get_person_profile if the existing data has NO post content at all."
                if has_existing_data
                else f"Call get_person_profile with username='{username}' and sections='posts'."
            )
            + f"{existing_context}"
        )},
    ]

    response = await run_tool_agent(llm, tools, messages, agent_name="activity_analyzer")

    return {
        "activity_data": {
            "url": linkedin_url,
            "raw_response": response.content,
        },
        "communication_style": "professional",
    }


def _store_to_memory(result: dict[str, Any], linkedin_url: str) -> None:
    """Store activity analysis in Mem0."""
    try:
        from memory.mem0_store import store_agent_output
        raw = result.get("activity_data", {}).get("raw_response", "")
        # Extract username as proxy for prospect name
        name = linkedin_url.rstrip("/").split("/in/")[-1] if "/in/" in linkedin_url else ""
        store_agent_output(
            agent_name="activity_analyzer",
            raw_response=raw,
            prospect_name=name,
        )
    except Exception:
        pass
