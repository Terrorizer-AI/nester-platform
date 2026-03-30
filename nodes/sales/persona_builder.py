"""
Agent 4: Persona Builder

Synthesizes all upstream data (LinkedIn, Company, Activity) into a
comprehensive prospect persona with confidence scoring.

Uses GPT-5.4-nano (synthesis role) — no tools, LLM reasoning only.
Adjusts confidence based on data quality from upstream agents.

Mem0 integration:
  - RECALL: searches prior knowledge about this prospect before building
  - STORE: saves new persona insights for future runs
  Second run for same prospect = richer persona with historical context.
"""

import json
import logging
from typing import Any, Callable

from langchain_openai import ChatOpenAI

from config.models import get_model
from core.errors import ErrorStrategy, retry_with_backoff
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert sales psychologist, behavioral analyst, and prospect profiler.
Your job is to synthesize ALL available data into the most detailed, actionable prospect persona possible.

You must produce a DEEP persona — not surface-level summaries. Every claim must cite specific evidence from the data.

Build the persona with ALL of these sections:

1. IDENTITY SNAPSHOT
   - Full name, current title, company, seniority level
   - Decision-making authority (budget holder? influencer? champion? end-user?)
   - Years in current role, total career experience
   - Career trajectory (rising fast? lateral moves? specialist? generalist?)

2. PROFESSIONAL NARRATIVE
   - Career story in 3-4 sentences (where they started → where they are → where they're heading)
   - Key career transitions and what they reveal about their priorities
   - Skills and expertise areas (from endorsements, experience descriptions)
   - Notable achievements or certifications

3. COMPANY CONTEXT
   - Company name, size, industry, stage (startup/growth/enterprise)
   - Company's recent news, funding, product launches
   - Their role within the company's org structure
   - Company challenges visible from public data

4. PSYCHOLOGICAL PROFILE
   - Motivations: what drives this person? (evidence-based, e.g., "posts about efficiency → values time savings")
   - Risk tolerance: conservative adopter or early experimenter? (cite evidence)
   - Values: what do they care about beyond work? (from interests, volunteer work, posts)
   - Decision style: data-driven, relationship-driven, intuition-driven? (cite evidence)

5. PAIN POINTS (ranked by confidence)
   For each pain point:
   - Description of the pain
   - Evidence source (which LinkedIn post, job description, company context suggests this)
   - Confidence level (high/medium/low) with reasoning
   - How it connects to potential solutions

6. COMMUNICATION DNA
   - Writing style: formal/conversational/technical/storytelling (with examples from posts)
   - Emoji usage: yes/no, frequency
   - Post length preference: short punchy vs. long-form
   - Topics they engage with most
   - Tone they respond to: data? stories? humor? directness?
   - Best communication channel: email, LinkedIn DM, phone?

7. ENGAGEMENT STRATEGY
   - Best opening angle (what specific topic/achievement to reference)
   - Topics to AVOID (sensitive areas, competitors they're loyal to)
   - Ideal time to reach out (based on posting patterns if visible)
   - Recommended approach: peer-to-peer, consultant, thought-leader, helpful stranger?
   - Specific post or achievement to reference in outreach (quote it if possible)

8. NETWORK & INFLUENCE
   - Connection count, follower count
   - Mutual connections (potential warm intros)
   - Groups and influencers they follow (signals interests)
   - Their influence level: thought leader, active participant, lurker?

Return ONLY a valid JSON object with ALL 8 sections — no markdown, no explanation, no code fences.
Each section must have specific evidence, not vague generalizations.
Include a "persona_confidence" field (0.0-1.0) and a "data_gaps" array listing what's missing.

Use this exact top-level structure:
{
  "identity_snapshot": { "name": "", "title": "", "company": "", "seniority": "", "decision_making_authority": "", "years_in_current_role": "", "total_career_experience": "", "career_trajectory": "" },
  "professional_narrative": { "career_story": "", "key_career_transitions": "", "skills_expertise": "", "notable_achievements": "" },
  "company_context": { "company_name": "", "size": "", "industry": "", "stage": "", "recent_news": "", "role_in_org": "", "visible_challenges": "" },
  "psychological_profile": { "motivations": [{"motivation": "", "evidence": "", "confidence": ""}], "risk_tolerance": {"assessment": "", "evidence": ""}, "values": [""], "decision_style": {"style": "", "evidence": ""} },
  "pain_points": [{ "description": "", "evidence_source": "", "confidence": "", "solution_connection": "" }],
  "communication_dna": { "writing_style": {"style": "", "examples": ""}, "emoji_usage": "", "post_length": {"preference": "", "evidence": ""}, "engagement_topics": [], "tone": "", "best_channel": "" },
  "engagement_strategy": { "opening_angle": "", "topics_to_avoid": [{"topic": "", "reason": "", "confidence": ""}], "ideal_timing": "", "recommended_approach": {"approach": "", "reasoning": ""}, "specific_reference": "" },
  "network_influence": { "connection_count": 0, "follower_count": 0, "mutual_connections": [], "warm_intros_strategy": {"suggestion": "", "evidence": ""}, "influence_level": {"assessment": "", "evidence": ""} },
  "persona_confidence": 0.0,
  "data_gaps": []
}"""


@register_node("persona_builder")
def create_persona_builder(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", "synthesis"))

    async def persona_builder_node(state: dict[str, Any]) -> dict[str, Any]:
        linkedin_data = state.get("linkedin_data", {})
        company_data = state.get("company_data", {})
        activity_data = state.get("activity_data", {})
        data_quality = state.get("linkedin_data_quality", "low")

        # ── Mem0 RECALL: search for prior knowledge about this prospect ────
        prior_memories = _recall_prospect_memories(linkedin_data)

        llm = ChatOpenAI(
            model=model_config.model_id,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )

        result = await retry_with_backoff(
            _build_persona,
            llm, linkedin_data, company_data, activity_data,
            data_quality, prior_memories,
            max_retries=params.get("retry", 1),
            node_name="persona_builder",
        )

        # ── Mem0 STORE: save new persona insights for future runs ──────────
        _store_prospect_persona(linkedin_data, result)

        return result

    return persona_builder_node


async def _build_persona(
    llm: Any,
    linkedin_data: dict,
    company_data: dict,
    activity_data: dict,
    data_quality: str,
    prior_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Build prior knowledge section if Mem0 returned memories
    prior_section = ""
    if prior_memories:
        memory_lines = []
        for mem in prior_memories:
            text = mem.get("memory", "")
            if text:
                memory_lines.append(f"- {text}")
        if memory_lines:
            prior_section = (
                "\n\n=== PRIOR KNOWLEDGE (from previous interactions) ===\n"
                + "\n".join(memory_lines)
                + "\n\nUse this prior knowledge to ENRICH your persona. "
                "If any prior info conflicts with fresh data, trust the fresh data "
                "but note the change."
            )

    def _extract_raw(data: dict) -> str:
        """Get the raw_response text from an agent output, or stringify the dict."""
        if not data:
            return "No data available."
        raw = data.get("raw_response", "")
        if raw and isinstance(raw, str):
            return raw[:12000]
        if data.get("skipped"):
            return f"Skipped: {data.get('reason', 'no data')}"
        return json.dumps(data, default=str)[:6000]

    context = f"""=== LINKEDIN PROFILE DATA ===
{_extract_raw(linkedin_data)}

=== COMPANY DATA ===
{_extract_raw(company_data)}

=== ACTIVITY & POSTS DATA ===
{_extract_raw(activity_data)}

=== DATA QUALITY ASSESSMENT ===
LinkedIn data quality: {data_quality}
Company data available: {bool(company_data and not company_data.get('skipped'))}
Activity data available: {bool(activity_data and not activity_data.get('skipped'))}{prior_section}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            "Build a COMPREHENSIVE prospect persona from this data.\n"
            "Be specific — cite exact quotes, post topics, job titles, company details.\n"
            "Do NOT use vague language like 'likely interested in technology'.\n"
            "Instead say 'Posts frequently about DevOps automation (3 posts in last month about CI/CD pipelines)'.\n\n"
            "CRITICAL: Return ONLY a raw JSON object. No markdown fences, no explanation text before or after.\n"
            "The first character of your response must be { and the last must be }.\n\n"
            f"{context}"
        )},
    ]

    response = await llm.ainvoke(messages)

    # Try to parse and re-serialize the JSON to ensure it's clean
    raw_content = response.content or ""
    cleaned = raw_content.strip()
    # Strip markdown fences safely
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Drop opening fence line
        lines = lines[1:]
        # Drop trailing fence line if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    # Extract JSON object if surrounded by text
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            parsed_json = json.loads(cleaned[first_brace:last_brace + 1])
            # Re-serialize clean JSON as the raw_response
            raw_content = json.dumps(parsed_json, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("[PersonaBuilder] JSON parse failed, keeping raw string: %s", exc)

    # Smarter confidence scoring based on all data sources
    confidence = 0.0
    confidence_reasons = []

    # LinkedIn data quality is the primary signal
    quality_scores = {"high": 0.45, "medium": 0.30, "low": 0.15, "failed": 0.05}
    confidence += quality_scores.get(data_quality, 0.15)
    confidence_reasons.append(f"linkedin_{data_quality}")

    # Company data adds context
    if company_data and not company_data.get("skipped"):
        confidence += 0.20
        confidence_reasons.append("company_data_present")
    else:
        confidence += 0.05
        confidence_reasons.append("company_data_missing")

    # Activity data is crucial for personalization
    if activity_data and not activity_data.get("skipped"):
        confidence += 0.25
        confidence_reasons.append("activity_data_present")
    else:
        confidence += 0.05
        confidence_reasons.append("activity_data_missing")

    # Response richness bonus (long, detailed response = better persona)
    content_len = len(raw_content)
    if content_len > 3000:
        confidence += 0.10
        confidence_reasons.append("rich_response")

    # Prior memories boost confidence
    if prior_memories:
        confidence += 0.05
        confidence_reasons.append("prior_memories_available")

    confidence = min(confidence, 1.0)

    return {
        "persona": {
            "raw_response": raw_content,
            "confidence_breakdown": confidence_reasons,
        },
        "persona_confidence": round(confidence, 2),
    }


# ── Mem0 integration helpers ─────────────────────────────────────────────────


def _extract_prospect_name(linkedin_data: dict) -> str:
    """Extract prospect name from LinkedIn data for Mem0 user_id."""
    # Try common field locations
    name = linkedin_data.get("name", "")
    if not name:
        raw = linkedin_data.get("raw_response", "")
        if isinstance(raw, str) and "name" in raw.lower():
            # Try to extract from raw text
            for line in raw.split("\n"):
                if "name" in line.lower() and ":" in line:
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
    return name


def _recall_prospect_memories(linkedin_data: dict) -> list[dict[str, Any]]:
    """Search Mem0 for prior knowledge about this prospect."""
    try:
        from memory.mem0_store import is_mem0_ready, search_memory, prospect_user_id

        if not is_mem0_ready():
            return []

        name = _extract_prospect_name(linkedin_data)
        if not name:
            return []

        uid = prospect_user_id(name)
        memories = search_memory(
            query=f"{name} persona preferences pain points communication style",
            user_id=uid,
            limit=10,
        )
        if memories:
            logger.info("[PersonaBuilder] Recalled %d prior memories for %s", len(memories), name)
        return memories
    except Exception as exc:
        logger.debug("[PersonaBuilder] Mem0 recall failed: %s", exc)
        return []


def _store_prospect_persona(linkedin_data: dict, result: dict[str, Any]) -> None:
    """Store persona insights in Mem0 for future runs."""
    try:
        from memory.mem0_store import is_mem0_ready, store_memory, prospect_user_id

        if not is_mem0_ready():
            return

        name = _extract_prospect_name(linkedin_data)
        if not name:
            return

        uid = prospect_user_id(name)
        persona_data = result.get("persona", {})
        raw = persona_data.get("raw_response", "")

        if not raw:
            return

        # Store the persona summary — Mem0 will extract discrete facts
        # and handle dedup/conflict resolution automatically
        content = f"Persona for {name}: {raw[:3000]}"
        store_memory(
            content=content,
            user_id=uid,
            metadata={
                "flow": "sales_outreach",
                "agent": "persona_builder",
                "confidence": result.get("persona_confidence", 0),
            },
        )
        logger.info("[PersonaBuilder] Stored persona memory for %s", name)
    except Exception as exc:
        logger.debug("[PersonaBuilder] Mem0 store failed: %s", exc)
