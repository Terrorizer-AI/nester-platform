"""
Agent 5: Service Matcher

Maps persona pain points against the seller's service catalog.
Identifies 1-3 best-fit services with a primary hook for the email.

Uses GPT-5.4-nano (synthesis role) — no tools, LLM reasoning only.
"""

import logging
from typing import Any, Callable

from config.models import get_model, build_chat_llm
from core.errors import retry_with_backoff
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a sales strategist who finds the perfect angle to connect a prospect's real problems with specific solutions.

Your job is NOT to list features. Your job is to find the ONE thing that will make this prospect think "this person gets my problem."

For each potential match:
1. Service/solution name
2. The SPECIFIC pain point it solves (not generic — tied to evidence from persona)
3. Relevance score (0.0-1.0)
4. A concrete talking point — something like "We helped [similar company] reduce X by Y%" (NOT "our platform optimizes your workflow")
5. Why this matters to THIS specific prospect (what in their data makes you think they care)

PRIMARY HOOK:
Select the single most compelling angle. This must be:
- Tied to something specific in their LinkedIn activity or career context
- Framed as a problem they're actively dealing with (not a hypothetical)
- Specific enough that it ONLY applies to this prospect (the "swap test")

Example of a GOOD hook: "[Company]'s [specific problem from their posts] — we solved exactly this for [similar company]"
Example of a BAD hook: "AI-powered solutions can help improve your workflow efficiency"
IMPORTANT: Never copy the example — generate a hook unique to THIS prospect using THEIR data.

RANKED HOOKS:
Also produce a ranked list of the best opening artifacts for the email — sorted strongest to weakest.
Each hook must reference a SPECIFIC PUBLIC ARTIFACT (a LinkedIn post, a page on their website,
a job listing, a company milestone, a product launch, a press release) — NOT a pain category.
Score by: (a) how specific/verifiable it is, (b) how recent it is, (c) how directly it connects to our services.

Hook sources in rough priority order (use judgment — a recent post beats an old press release):
- prospect_post: something the prospect personally wrote or shared on LinkedIn
- company_page: a specific page on the company website (e.g. /propel, /about, /product)
- company_post: a post from the company LinkedIn page
- career_move: a recent role change or promotion visible on LinkedIn
- job_listing: an open role that signals a strategic direction
- press_mention: a news article, funding announcement, award

Return JSON:
{
  "matches": [{"service": "...", "pain_point": "...", "relevance": 0.9, "talking_point": "...", "evidence": "..."}],
  "primary_hook": "One specific, compelling sentence that connects their pain to our solution",
  "match_confidence": 0.85,
  "hook_reasoning": "Why this hook was chosen over others",
  "ranked_hooks": [
    {
      "source": "prospect_post | company_page | company_post | career_move | job_listing | press_mention",
      "artifact": "the specific thing — e.g. 'post titled X', 'unitypartnerslp.com/propel', 'open VP Ops role'",
      "quote": "3-10 word quote or description of the artifact",
      "confidence": 0.9,
      "recency": "2 weeks ago | 2024-Q4 | unknown"
    }
  ]
}"""


@register_node("service_matcher")
def create_service_matcher(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "synthesis"))

    async def service_matcher_node(state: dict[str, Any]) -> dict[str, Any]:
        persona = state.get("persona", {})
        service_catalog = state.get("service_catalog", [])
        targeting_brief = {
            "sender_name": state.get("sender_name", ""),
            "sender_company": state.get("sender_company", ""),
            "sender_role": state.get("sender_role", ""),
            "value_proposition": state.get("value_proposition", ""),
            "target_pain_points": state.get("target_pain_points", ""),
            "ideal_outcome": state.get("ideal_outcome", ""),
            "case_studies": state.get("case_studies", ""),
        }

        llm = build_chat_llm(model_config)

        result = await retry_with_backoff(
            _match_services,
            llm, persona, service_catalog, targeting_brief,
            max_retries=params.get("retry", 1),
            node_name="service_matcher",
        )
        _store_to_memory(result, state)
        return result

    return service_matcher_node


def _extract_pain_points_query(persona: dict) -> str:
    """Build a targeted retrieval query from the top persona pain points.

    Uses the structured pain_points array from persona JSON if available.
    Falls back to raw persona text truncated to 500 chars.
    """
    import json as _json
    raw = persona.get("raw_response", "") if isinstance(persona, dict) else ""
    if raw:
        try:
            parsed = _json.loads(raw) if isinstance(raw, str) else raw
            pain_points = parsed.get("pain_points", [])
            if isinstance(pain_points, list) and pain_points:
                descriptions = []
                for p in pain_points[:3]:
                    if isinstance(p, dict):
                        desc = p.get("description", "")
                    else:
                        desc = str(p)
                    if desc:
                        descriptions.append(desc)
                if descriptions:
                    return "case study solution for: " + "; ".join(descriptions)
        except (ValueError, TypeError, AttributeError):
            pass
    # Fallback: raw persona text
    fallback = raw[:500] if raw else str(persona)[:500]
    return f"services case studies value proposition {fallback}"


async def _match_services(
    llm: Any, persona: dict, service_catalog: list, targeting_brief: dict,
) -> dict[str, Any]:
    # ── Load company knowledge first — it's the primary source ──────────────
    import os
    knowledge_text = ""
    knowledge_catalog = ""
    try:
        from knowledge.retriever import get_company_context
        pain_query = _extract_pain_points_query(persona)
        ctx = get_company_context(
            query=pain_query,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            top_k=10,
        )
        if ctx["has_knowledge"]:
            knowledge_text = ctx["formatted"]
            knowledge_catalog = (
                "\n⚡ PRIMARY SOURCE: Use the COMPANY KNOWLEDGE section below for all "
                "service names, case studies, and value propositions."
            )
    except Exception as e:
        logger.debug("[ServiceMatcher] Knowledge retrieval skipped: %s", e)

    # ── Manual service catalog (secondary — used only if no docs) ─────────────
    if service_catalog:
        catalog_text = "\n".join(
            f"- {s.get('name', 'Unknown')}: {s.get('description', '')}"
            for s in service_catalog
        )
    elif knowledge_text:
        catalog_text = "See COMPANY KNOWLEDGE section below — extract services from there."
    else:
        catalog_text = "No service catalog — infer from persona's pain points and industry context."

    # ── Manual targeting brief (secondary — used only if no docs) ─────────────
    brief_text = ""
    if any(targeting_brief.values()):
        parts = []
        if targeting_brief.get("sender_company"):
            parts.append(f"Sender Company: {targeting_brief['sender_company']}")
        if targeting_brief.get("value_proposition"):
            parts.append(f"Value Proposition: {targeting_brief['value_proposition']}")
        if targeting_brief.get("target_pain_points"):
            parts.append(f"Pain Points We Solve: {targeting_brief['target_pain_points']}")
        if targeting_brief.get("ideal_outcome"):
            parts.append(f"Ideal Outcome: {targeting_brief['ideal_outcome']}")
        if targeting_brief.get("case_studies"):
            parts.append(f"Case Studies: {targeting_brief['case_studies']}")
        brief_text = (
            "\n\n=== TARGETING BRIEF (manual — secondary source) ===\n"
            + "\n".join(parts)
        )

    knowledge_section = (
        f"\n\n=== COMPANY KNOWLEDGE (uploaded docs — PRIMARY SOURCE) ===\n{knowledge_text}"
        if knowledge_text else ""
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            "Find the best service match for this prospect.\n\n"
            "IMPORTANT: Your primary_hook must be SPECIFIC to this person — "
            "reference their company, role, or a problem visible in their data. "
            "Generic hooks are useless.\n"
            f"{knowledge_catalog}\n\n"
            f"=== PROSPECT PERSONA ===\n{persona}\n\n"
            f"=== SERVICE CATALOG ===\n{catalog_text}"
            f"{knowledge_section}"
            f"{brief_text}"
        )},
    ]

    response = await llm.ainvoke(messages)

    # Parse structured fields from JSON response
    content = response.content or ""
    primary_hook = ""
    ranked_hooks: list[dict] = []
    top_relevance = 0.0
    try:
        import json
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            primary_hook = parsed.get("primary_hook", "")
            ranked_hooks = parsed.get("ranked_hooks", [])
            matches = parsed.get("matches", [])
            if matches and isinstance(matches, list):
                top_relevance = float(matches[0].get("relevance", 0.0))
    except (ValueError, TypeError, AttributeError):
        pass

    return {
        "service_match": {"raw_response": content},
        "primary_hook": primary_hook,
        "ranked_hooks": ranked_hooks,
        "top_service_relevance": top_relevance,
    }


def _store_to_memory(result: dict[str, Any], state: dict[str, Any]) -> None:
    """Store service match output in Mem0."""
    try:
        from memory.mem0_store import store_agent_output
        raw = result.get("service_match", {}).get("raw_response", "")
        li_data = state.get("linkedin_data", {})
        prospect = li_data.get("name", "") if isinstance(li_data, dict) else ""
        company = li_data.get("company", "") if isinstance(li_data, dict) else ""
        store_agent_output(
            agent_name="service_matcher",
            raw_response=raw,
            prospect_name=prospect,
            company_name=company,
        )
    except Exception:
        pass
