"""
Sales Outreach state schema — TypedDict flowing through the 6-agent pipeline.

Each agent reads upstream data and writes its own output keys.
errors uses operator.add (plain list append, NOT add_messages which requires role/content keys).
"""

import operator
from typing import Annotated, Any, TypedDict


class SalesOutreachState(TypedDict, total=False):
    """Shared state for the Sales Outreach flow."""

    # ── Input ─────────────────────────────────────────────────────────────
    linkedin_url: str
    company_website: str
    company_linkedin_url: str          # Company LinkedIn page (optional)
    service_catalog: list[dict[str, Any]]

    # ── Targeting Brief (from frontend) ─────────────────────────────────
    sender_name: str
    sender_company: str
    sender_role: str
    value_proposition: str        # What we offer and why it matters
    target_pain_points: str       # What problems we solve
    ideal_outcome: str            # What success looks like for the prospect
    email_tone: str               # "casual" | "professional" | "technical" | "friendly"
    case_studies: str             # Relevant social proof or results
    cta_preference: str           # Preferred call-to-action style

    # ── Agent 1: LinkedIn Researcher ──────────────────────────────────────
    linkedin_data: dict[str, Any]
    linkedin_data_quality: str  # "high" | "medium" | "low" | "failed"

    # ── Agent 2a: Company Researcher (website + search) ───────────────────
    company_data: dict[str, Any]

    # ── Agent 2b: Company LinkedIn Researcher (parallel with 2a) ──────────
    company_linkedin_data: dict[str, Any]

    # ── Agent 3: Activity Analyzer ────────────────────────────────────────
    activity_data: dict[str, Any]
    communication_style: str

    # ── Agent 4: Persona Builder ──────────────────────────────────────────
    persona: dict[str, Any]
    persona_confidence: float  # 0.0 - 1.0

    # ── Agent 5: Service Matcher ──────────────────────────────────────────
    service_match: dict[str, Any]
    primary_hook: str
    ranked_hooks: list[dict[str, Any]]   # [{source, artifact, quote, confidence, recency}, ...]
    top_service_relevance: float          # 0.0-1.0 from best service match

    # ── Agent 6: Email Composer ───────────────────────────────────────────
    email_drafts: list[dict[str, Any]]   # All 3 variants for user to choose from
    email_subject: str                   # Best draft's subject (auto-selected)
    email_body: str                      # Best draft's body (auto-selected)
    email_approved: bool
    personalization_notes: str
    style_match: str
    email_quality_score: int
    email_quality_notes: str

    # ── Agent 8: Output Formatter (structured JSON for frontend) ──────────
    linkedin_parsed: dict[str, Any]          # Structured LinkedIn profile
    company_parsed: dict[str, Any]           # Structured company research
    company_linkedin_parsed: dict[str, Any]  # Structured company LinkedIn
    activity_parsed: dict[str, Any]          # Structured activity analysis

    # ── Pipeline metadata ─────────────────────────────────────────────────
    errors: Annotated[list[dict[str, Any]], operator.add]
    run_id: str
    flow_version: str
