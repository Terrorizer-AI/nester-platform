"""
Agent 6: Email Composer

Generates a hyper-personalized cold email using the FULL research context from
all upstream agents:
  - LinkedIn profile (name, title, career history, headline)
  - Company research (mission, pain points, recent news, tech stack)
  - Activity analysis (recent posts, communication style, expressed concerns)
  - Persona (psychological profile, priorities, communication DNA)
  - Service match (top matched services, primary hook, relevance reasoning)

Uses gpt-4o (email role) — no tools, maximum reasoning quality.
This agent supports human-in-the-loop: the email is presented for approval.

Mem0 integration:
  - RECALL: checks if we've contacted this prospect before (avoid repeat angles)
  - STORE: saves the generated email for future reference
"""

import json
import logging
import os
from typing import Any, Callable

import httpx
from config.models import get_model, build_chat_llm, ROLE_EMAIL
from core.errors import retry_with_backoff
from core.registry import register_node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a world-class B2B sales writer. Your emails get responses because they feel
like they came from someone who genuinely understands the recipient — not from a marketing team.

## Your ONE job
Write a cold email so specific, so well-observed, and so relevant that the prospect thinks:
"This person actually knows my situation." If the prospect reads it and thinks "this could
be for anyone", you have failed.

## Voice & Tone Rules
- Write as one professional writing to another — peer-to-peer, not vendor-to-buyer
- Mirror the prospect's own communication style: if they write casually → casual; formal → formal;
  technical → technical; if they use emojis → one or two max
- NEVER use: "I hope this finds you well", "I came across your profile", "I'd love to connect",
  "reaching out", "touch base", "exciting opportunity", "synergies", "leverage", "game-changer"
- No exclamation marks except possibly in the subject line
- Short paragraphs. White space is your friend.

## SHOW DON'T TELL THE PAIN (CRITICAL)
The prospect already knows their problems. Naming their pain signals you scraped their website.
Instead: reference a SPECIFIC PUBLIC ARTIFACT — a page, a post, a job listing, a product,
an initiative — then let the reader connect it to their own situation.

WRONG: "Companies like yours tend to have lean teams and legacy workflows"
RIGHT: "The Propel platform caught my eye — not many funds build the shared tech layer this early in the hold period."

WRONG: "Based on what I understand about Unity's direction around AI-assisted automation"
RIGHT: "Saw you're investing in operational infrastructure pre-acquisition — that's a bet most funds don't make until post-close."

WRONG: "I noticed you've been focused on scaling your engineering team"
RIGHT: "Your post on async-first engineering last month resonated — shipping at that pace with a distributed team is a different problem than most consultancies solve."

The reader should think "they get it" — not "they googled me."
NEVER use phrases like "based on what I understand about your direction", "companies like yours",
"I know that [role] faces challenges with", or "given your focus on X".

## Structure (200-350 words body)

**Opening (1-2 sentences)**
Reference ONE SPECIFIC, VERIFIABLE detail — a LinkedIn post they wrote (quote 3-5 words),
a company milestone, a career transition, a technology their company recently adopted, or a pain
point they publicly expressed. This MUST prove you read their profile.
Generic phrases like "impressive background" or "noticed your work in AI" are banned.

**Context / Observation (2-3 sentences)**
Show you understand their world — their company stage, the problem they're solving, the
constraints they operate under. Reference specific facts: company size, mission statement wording,
a challenge implied by their product positioning, a recent post theme. This is where you
demonstrate depth, not just surface-level research.

**Bridge (1-2 sentences)**
Connect your observation to something you've seen or solved. Sound like you're sharing a thought,
not launching a pitch. "That got me thinking..." / "We've seen the same friction at..."
NOT "our solution can help with..."

**Value (2-3 sentences)**
Be specific and concrete. Name a comparable company. Give a result with numbers if possible.
Explain briefly HOW you solved it — one sentence on the mechanism, not just the outcome.
GOOD: "Helped Basepair cut voice agent response latency by 60% by pre-warming inference on
likely call paths. Clinics stopped dropping the AI mid-call."
BAD: "Our AI platform streamlines your operations."

**CTA (1 sentence)**
Soft. Zero pressure. One ask only. Reference the calendar link naturally — say something like
"If it's worth 30 minutes, grab a time here" or "Happy to walk through it — link below."
Do NOT paste the URL in the body — a scheduling link will be appended automatically.
GOOD: "Worth a quick 30-min call to see if the same approach fits your stack?"
GOOD: "Happy to walk through it — grab a slot whenever suits you."
BAD: "Let's schedule a 30-minute call at your convenience."

## Subject Line
- Under 55 characters
- Specific to THIS person — reference their company, a post topic, or a pain point
- Looks like a personal email, not marketing
- GOOD: "your post on [specific topic]" / "re: [Company]'s [specific challenge]"
- BAD: "Quick question" / "Partnership opportunity" / "Following up"

## SENDER IDENTITY RULES (CRITICAL)
- You are writing AS the sender (section 7). Use their name, company, and role.
- PRIMARY SOURCE for services, case studies, value proposition, and proof:
  Section 9 (COMPANY KNOWLEDGE — uploaded docs). This is real, authoritative company data.
  Quote actual product names, service names, results and client examples FROM SECTION 9 directly.
- SECONDARY SOURCE: Section 8 (Targeting Brief) — use if section 9 is empty or doesn't cover the point.
- NEVER invent or hallucinate services, products, client names, or numbers not present in sections 8 or 9.
- If section 9 has case studies with numbers → use them exactly as written. Do not soften or generalise.
- If neither section has case studies → describe the general approach without fabricated numbers.
- Sign off with the sender's actual name from section 7.

## Quality Checks (apply all before finalizing)
1. SWAP TEST: replace the prospect's name with another person's name. If the email still works perfectly → too generic → rewrite
2. SPECIFICITY TEST: can you point to exactly which data point in the research justified each sentence? If not → rewrite
3. PUSHINESS TEST: does any sentence feel like a sales pitch? → soften it
4. AUTHENTICITY TEST: would a real human send this? Or does it sound AI-generated? → rewrite any robotic phrases
5. SENDER TEST: does the email mention the sender's actual company and value prop from the brief? If not → rewrite
6. ARTIFACT TEST: does every observation reference a specific public artifact (a page URL, a post topic, a job listing, a product name, a press release)? If any sentence describes a pain CATEGORY or PATTERN instead of citing a specific thing — rewrite it to cite the artifact.

## Output Format
Return valid JSON only — an array of exactly 3 email drafts, each using a DIFFERENT opening angle:

[
  {
    "angle": "one-line label for this variant's hook (e.g. 'Company mission angle', 'Recent post angle', 'Career transition angle')",
    "subject": "subject line (under 55 chars)",
    "body": "full email body (200-350 words, no greeting like 'Hi [Name]' — start straight into the opening hook)",
    "personalization_notes": "2-3 sentences: exactly which data points from research were used and why",
    "style_match": "1 sentence: how this email mirrors the prospect's communication DNA",
    "email_quality_score": 0-100,
    "quality_notes": "honest assessment: what's strong, what's a trade-off"
  },
  { ... second variant with completely different opening and hook ... },
  { ... third variant with completely different opening and hook ... }
]

RULES FOR THE 3 VARIANTS:
- Each MUST open with a different data point (e.g. one opens on a LinkedIn post, one on a company milestone, one on a career move or pain point)
- The subject lines must all be different
- CRITICAL — DIFFERENT CASE STUDIES & SERVICES PER VARIANT:
  Each variant MUST reference a DIFFERENT case study AND a DIFFERENT service line from the company knowledge (section 8).
  For example, if variant 1 uses the Atlassian Jira case study + Cloud Foundation Nest,
  variant 2 must use a DIFFERENT case study (e.g. Smart Home, Basepair, AI-first Bank) + a DIFFERENT service (e.g. Intelligence Nest, Human Experience Nest).
  NEVER repeat the same case study or service across variants. If there are 5 case studies, pick 3 different ones.
  If only 1 case study exists, vary the SERVICE LINE and angle for each variant.
- Do NOT make one variant just a slight reword of another — they should feel like 3 distinct approaches
- All 3 must pass the SWAP TEST and SPECIFICITY TEST"""


@register_node("email_composer")
def create_email_composer(params: dict[str, Any]) -> Callable:
    model_config = get_model(params.get("model_role", ROLE_EMAIL))

    async def email_composer_node(state: dict[str, Any]) -> dict[str, Any]:
        persona = state.get("persona", {})
        service_match = state.get("service_match", {})
        primary_hook = state.get("primary_hook", "")
        communication_style = state.get("communication_style", "professional")
        linkedin_data = state.get("linkedin_data", {})
        company_data = state.get("company_data", {})
        company_linkedin_data = state.get("company_linkedin_data", {})

        # Activity fallback: if activity_data looks bad (scraper hit wrong entity),
        # use the posts already inside linkedin_data which are always correct.
        activity_data = state.get("activity_data", {})
        activity_raw = activity_data.get("raw_response", "") if isinstance(activity_data, dict) else ""
        activity_is_bad = (
            not activity_raw
            or "encountered an issue" in activity_raw.lower()
            or "unable to retrieve" in activity_raw.lower()
            or "not currently maintained" in activity_raw.lower()
        )
        if activity_is_bad:
            posts_and_activity = {}
            if isinstance(linkedin_data, dict):
                raw_li = linkedin_data.get("raw_response", "")
                if raw_li and "posts_and_activity" in raw_li:
                    posts_and_activity = {"source": "linkedin_profile", "raw_response": raw_li}
            activity_data = posts_and_activity or {"note": "No activity data available — use LinkedIn profile posts instead"}
            logger.info("[EmailComposer] Activity data invalid, falling back to LinkedIn profile posts")

        targeting_brief = {
            "sender_name": state.get("sender_name", ""),
            "sender_company": state.get("sender_company", ""),
            "sender_role": state.get("sender_role", ""),
            "value_proposition": state.get("value_proposition", ""),
            "target_pain_points": state.get("target_pain_points", ""),
            "ideal_outcome": state.get("ideal_outcome", ""),
            "email_tone": state.get("email_tone", "professional"),
            "case_studies": state.get("case_studies", ""),
            "cta_preference": state.get("cta_preference", "soft"),
        }

        # Confidence + relevance signals from upstream agents
        ranked_hooks = state.get("ranked_hooks", [])
        top_service_relevance = state.get("top_service_relevance", 0.0)
        persona_confidence = state.get("persona_confidence", 0.0)
        linkedin_data_quality = state.get("linkedin_data_quality", "unknown")

        prior_emails = _recall_prior_emails(linkedin_data)
        calendly_link = await _get_calendly_link()

        llm = build_chat_llm(model_config)

        result = await retry_with_backoff(
            _compose_email,
            llm, persona, service_match, primary_hook,
            communication_style, activity_data, linkedin_data,
            company_data, company_linkedin_data, targeting_brief, prior_emails,
            calendly_link, ranked_hooks, top_service_relevance,
            persona_confidence, linkedin_data_quality,
            max_retries=params.get("retry", 2),
            node_name="email_composer",
        )

        _store_email_memory(linkedin_data, result)
        return result

    return email_composer_node


async def _get_calendly_link() -> str:
    """Return a Calendly scheduling URL for this email.

    Priority:
      1. Create a fresh single-use link via API (max_event_count=1 — expires after one booking)
      2. Fall back to CALENDLY_SCHEDULING_URL static link if API fails
    """
    api_key = os.getenv("CALENDLY_API_KEY", "")
    event_uri = os.getenv("CALENDLY_EVENT_TYPE_URI", "")

    # Try to create a fresh single-use link
    if api_key and event_uri:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://api.calendly.com/scheduling_links",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "max_event_count": 1,
                        "owner": event_uri,
                        "owner_type": "EventType",
                    },
                )
                if r.status_code == 201:
                    url = r.json().get("resource", {}).get("booking_url", "")
                    if url:
                        logger.info("[EmailComposer] Created fresh single-use Calendly link: %s", url)
                        return url
                logger.warning(
                    "[EmailComposer] Calendly scheduling_links returned %d — falling back to static URL",
                    r.status_code,
                )
        except Exception as exc:
            logger.warning("[EmailComposer] Calendly link creation failed: %s — falling back to static URL", exc)

    # Fallback: static URL
    static = os.getenv("CALENDLY_SCHEDULING_URL", "").strip()
    if static:
        logger.info("[EmailComposer] Using static Calendly URL: %s", static)
        return static

    return ""


def _format_ranked_hooks(hooks: list[dict[str, Any]]) -> str:
    """Format ranked_hooks list into a readable numbered block for the LLM prompt."""
    if not hooks:
        return "No ranked hooks available — use strongest signals from sections 1-4."
    lines = []
    for i, h in enumerate(hooks, 1):
        confidence = h.get("confidence", 0.0)
        source = h.get("source", "unknown")
        artifact = h.get("artifact", "")
        quote = h.get("quote", "")
        recency = h.get("recency", "unknown")
        line = f"{i}. [{source} | confidence: {confidence:.0%} | {recency}] {artifact}"
        if quote:
            line += f' — "{quote}"'
        lines.append(line)
    return "\n".join(lines)


def _summarise(data: Any, max_chars: int = 800) -> str:
    """Convert any data (dict, list, str) to a readable string, truncated.

    For dicts that wrap LLM output in a 'raw_response' key (e.g. linkedin_data,
    company_linkedin_data), extract the raw_response directly so the char budget
    goes to actual content rather than the outer wrapper keys (url, slug, etc.).
    """
    if not data:
        return "Not available"
    if isinstance(data, str):
        text = data
    elif isinstance(data, dict):
        # Prefer raw_response if present — it contains the full LLM output
        raw = data.get("raw_response")
        if raw and isinstance(raw, str) and len(raw) > 50:
            text = raw
        else:
            try:
                text = json.dumps(data, indent=2)
            except Exception:
                text = str(data)
    else:
        try:
            text = json.dumps(data, indent=2)
        except Exception:
            text = str(data)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


async def _compose_email(
    llm: Any,
    persona: dict,
    service_match: dict,
    primary_hook: str,
    style: str,
    activity: dict,
    linkedin_data: dict,
    company_data: dict,
    company_linkedin_data: dict,
    targeting_brief: dict,
    prior_emails: list[dict[str, Any]] | None = None,
    calendly_link: str = "",
    ranked_hooks: list[dict[str, Any]] | None = None,
    top_service_relevance: float = 0.0,
    persona_confidence: float = 0.0,
    linkedin_data_quality: str = "unknown",
) -> dict[str, Any]:

    # ── Sender context ────────────────────────────────────────────────────────
    sender_lines = []
    for key, label in [
        ("sender_name", "Name"),
        ("sender_company", "Company"),
        ("sender_role", "Role"),
    ]:
        if targeting_brief.get(key):
            sender_lines.append(f"{label}: {targeting_brief[key]}")
    sender_text = "\n".join(sender_lines) if sender_lines else "Not provided"

    brief_lines = []
    for key, label in [
        ("value_proposition", "Value Proposition"),
        ("target_pain_points", "Pain Points We Solve"),
        ("ideal_outcome", "Ideal Outcome for Prospect"),
        ("case_studies", "Case Studies / Social Proof"),
    ]:
        if targeting_brief.get(key):
            brief_lines.append(f"{label}: {targeting_brief[key]}")
    brief_text = "\n".join(brief_lines) if brief_lines else "Not provided"

    tone = targeting_brief.get("email_tone", "professional")
    cta = targeting_brief.get("cta_preference", "soft")

    # ── Inject company knowledge from Drive docs ──────────────────────────────
    knowledge_text = ""
    try:
        import os
        from knowledge.retriever import get_company_context
        from nodes.sales.service_matcher import _extract_pain_points_query
        # Use pain-point-targeted query for more relevant chunk retrieval
        pain_query = _extract_pain_points_query(persona)
        ctx = get_company_context(
            query=pain_query,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            top_k=10,
        )
        if ctx["has_knowledge"]:
            knowledge_text = ctx["formatted"]
    except Exception as e:
        logger.debug("[EmailComposer] Knowledge retrieval skipped: %s", e)

    # ── Build rich research context ───────────────────────────────────────────
    # GPT-4o has 128K context — use generous limits so the LLM sees full details
    context = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                     FULL RESEARCH CONTEXT                           ║
╚══════════════════════════════════════════════════════════════════════╝

━━━ 1. LINKEDIN PROFILE (name, title, experience, skills, posts) ━━━━━
{_summarise(linkedin_data, 8000)}

━━━ 2. COMPANY RESEARCH (website — mission, products, tech, funding) ━
{_summarise(company_data, 6000)}

━━━ 3. COMPANY LINKEDIN (posts, culture, growth signals) ━━━━━━━━━━━━━
{_summarise(company_linkedin_data, 5000)}

━━━ 4. RECENT PROSPECT ACTIVITY & POSTS (quotes, engagement, topics) ━
{_summarise(activity, 8000)}

━━━ 5. PROSPECT PERSONA (psychological profile, pain points, comms DNA)
Communication Style: {style}
{_summarise(persona, 6000)}

━━━ 6. SERVICE MATCH & PRIMARY HOOK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Primary Hook: {primary_hook}
{_summarise(service_match, 3000)}

━━━ 7. SENDER INFO (who is writing this email) ━━━━━━━━━━━━━━━━━━━━━━━
{sender_text}

━━━ 8. COMPANY KNOWLEDGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ PRIMARY SOURCE — use this for all services, case studies, value prop, and proof.
These are real facts from the sender's uploaded company documents. Quote them directly.
⚠️ VARIETY RULE: Each of the 3 email variants MUST reference a DIFFERENT case study
and a DIFFERENT service line from below. Do NOT use the same case study in all 3 emails.
{knowledge_text if knowledge_text else "No company docs synced yet."}

━━━ 9. TARGETING BRIEF (manual overrides — use if section 8 is empty) ━
{brief_text if brief_text != "Not provided" else "Not provided — rely entirely on section 8 company knowledge above."}

CRITICAL: Always reference the sender's real company, services and results.
Use section 8 (company docs) as the primary source. Never fabricate.

━━━ 10. TONE & CTA PREFERENCES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tone: {tone}
CTA Style: {cta}

━━━ 11. DATA CONFIDENCE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Persona confidence: {persona_confidence:.0%}
LinkedIn data quality: {linkedin_data_quality}
Service match relevance: {top_service_relevance:.0%}
{"⚠️ LOW CONFIDENCE — lead with broad observations from public artifacts, avoid specific claims about the prospect's internal situation" if persona_confidence < 0.5 else "✓ HIGH CONFIDENCE — cite specific data points and artifacts directly"}

━━━ 12. RANKED HOOKS (strongest → weakest signal, use these to open) ━━
{_format_ranked_hooks(ranked_hooks or [])}
Pick your 3 opening hooks from this ranked list. Use the STRONGEST hooks regardless
of source type — if the top 3 are all prospect posts, use them all. Only diversify
source types if the top hooks are roughly equal in strength.
RULE: Every hook must reference the specific ARTIFACT listed — not a summary of the pain."""

    if prior_emails:
        prior_lines = [
            f"- {mem.get('memory', '')}"
            for mem in prior_emails
            if mem.get("memory")
        ]
        if prior_lines:
            context += (
                "\n\n━━━ 10. PRIOR OUTREACH HISTORY (AVOID REPEATING) ━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(prior_lines)
                + "\n\nWe have contacted this prospect before. "
                "Use a DIFFERENT angle. Do NOT repeat the same opening, hook, or subject line."
            )

    user_message = (
        "Write 3 cold email variants now — each with a DIFFERENT opening angle.\n\n"
        "Step 1 — Read through ALL sections of the research context carefully.\n"
        "Step 2 — Pick the 3 strongest hooks from the RANKED HOOKS list (section 12).\n"
        "  Use the highest-confidence hooks regardless of source type.\n"
        "  If the top 3 are all prospect posts, use them — don't force weak sources.\n"
        "  Only use lower-ranked hooks if the top ones are too similar to open with.\n"
        "  RULE: Each hook must reference the specific ARTIFACT from the ranked list,\n"
        "  not a pain category or a generalisation about the prospect's situation.\n"
        "  IMPORTANT: If a hook references a job posting that is likely filled (>3 months old),\n"
        "  skip it and use the next ranked hook instead.\n"
        "Step 3 — For each hook, pick a DIFFERENT service line AND case study from section 8 (company knowledge).\n"
        "  Variant A must use a different case study than Variant B and C. Never repeat the same case study.\n"
        "Step 4 — Write all 3 emails following the structure in the system prompt (200-350 words each).\n"
        "Step 5 — Apply all 4 quality checks to EACH variant. Rewrite any that fail.\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "- Each opening MUST cite something specific and CURRENT\n"
        "- Each context paragraph MUST reference specifics: company size, mission wording, product focus\n"
        "- All 3 must have different subject lines and different opening sentences\n"
        "- Sign off as the sender (use their name from Sender Info)\n"
        "- Return a JSON array of exactly 3 objects — no markdown, no extra text\n\n"
        f"{context}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await llm.ainvoke(messages)
    content = response.content or ""

    # Parse JSON array of 3 drafts
    drafts: list[dict[str, Any]] = []
    try:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    drafts.append({
                        "angle": item.get("angle", ""),
                        "subject": item.get("subject", ""),
                        "body": item.get("body", ""),
                        "personalization_notes": item.get("personalization_notes", ""),
                        "style_match": item.get("style_match", ""),
                        "email_quality_score": int(item.get("email_quality_score", 0)),
                        "quality_notes": item.get("quality_notes", ""),
                    })
        elif isinstance(parsed, dict):
            # Model returned single object — wrap it
            drafts.append({
                "angle": parsed.get("angle", "Variant 1"),
                "subject": parsed.get("subject", ""),
                "body": parsed.get("body", content),
                "personalization_notes": parsed.get("personalization_notes", ""),
                "style_match": parsed.get("style_match", ""),
                "email_quality_score": int(parsed.get("email_quality_score", 0)),
                "quality_notes": parsed.get("quality_notes", ""),
            })
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("[EmailComposer] Could not parse JSON response, using raw content as single draft")
        drafts = [{"angle": "Draft", "subject": "", "body": content,
                   "personalization_notes": "", "style_match": "",
                   "email_quality_score": 0, "quality_notes": ""}]

    # Append Calendly scheduling link to each draft body
    if calendly_link:
        for draft in drafts:
            body = draft.get("body", "")
            if body and calendly_link not in body:
                draft["body"] = body + f"\n\n{calendly_link}"

    # Best draft = highest quality score (used as the default selected email)
    best = max(drafts, key=lambda d: d.get("email_quality_score", 0)) if drafts else {}

    return {
        "email_drafts": drafts,
        "email_subject": best.get("subject", ""),
        "email_body": best.get("body", ""),
        "email_approved": False,
        "personalization_notes": best.get("personalization_notes", ""),
        "style_match": best.get("style_match", ""),
        "email_quality_score": best.get("email_quality_score", 0),
        "email_quality_notes": best.get("quality_notes", ""),
    }


# ── Mem0 integration helpers ─────────────────────────────────────────────────


def _extract_prospect_name(linkedin_data: dict) -> str:
    """Extract prospect name from LinkedIn data for Mem0 user_id."""
    name = linkedin_data.get("name", "")
    if not name:
        raw = linkedin_data.get("raw_response", "")
        if isinstance(raw, str) and "name" in raw.lower():
            for line in raw.split("\n"):
                if "name" in line.lower() and ":" in line:
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
    return name


def _recall_prior_emails(linkedin_data: dict) -> list[dict[str, Any]]:
    """Check Mem0 for any prior emails sent to this prospect."""
    try:
        from memory.mem0_store import is_mem0_ready, search_memory, prospect_user_id

        if not is_mem0_ready():
            return []

        name = _extract_prospect_name(linkedin_data)
        if not name:
            return []

        uid = prospect_user_id(name)
        memories = search_memory(
            query=f"email sent to {name} subject hook angle",
            user_id=uid,
            limit=5,
        )
        if memories:
            logger.info(
                "[EmailComposer] Found %d prior email memories for %s",
                len(memories), name,
            )
        return memories
    except Exception as exc:
        logger.debug("[EmailComposer] Mem0 recall failed: %s", exc)
        return []


def _store_email_memory(linkedin_data: dict, result: dict[str, Any]) -> None:
    """Store the generated email in Mem0 for future reference."""
    try:
        from memory.mem0_store import is_mem0_ready, store_memory, prospect_user_id

        if not is_mem0_ready():
            return

        name = _extract_prospect_name(linkedin_data)
        if not name:
            return

        subject = result.get("email_subject", "")
        body = result.get("email_body", "")
        if not body:
            return

        uid = prospect_user_id(name)
        content = (
            f"Email sent to {name}. "
            f"Subject: {subject}. "
            f"Opening angle: {body[:200]}"
        )
        store_memory(
            content=content,
            user_id=uid,
            metadata={
                "flow": "sales_outreach",
                "agent": "email_composer",
                "subject": subject,
            },
        )
        logger.info("[EmailComposer] Stored email memory for %s", name)
    except Exception as exc:
        logger.debug("[EmailComposer] Mem0 store failed: %s", exc)
