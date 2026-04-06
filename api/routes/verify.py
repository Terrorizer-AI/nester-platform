"""
Email verification chat endpoint.

POST /verify/chat
  - Accepts the full research context + conversation history + user question
  - Streams back an answer with exact citations from the research data
  - Uses gpt-4o to reason over the raw research and cite exact sources
"""

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verify", tags=["verify"])


SYSTEM_PROMPT = """You are a research audit assistant for a B2B sales email tool.

Your job: answer the user's questions about a cold email by citing EXACT data points
from the research that was used to write it.

You have access to the full research context:
- LinkedIn profile (prospect's experience, posts, headline, career history)
- Company website research (mission, products, pain points, tech stack)
- Company LinkedIn page (posts, employee count, growth signals, key people)
- Activity analysis (prospect's recent posts, communication style, buying signals)
- Persona analysis (psychological profile, motivations, decision style)
- Service match (which services match and why, primary hook reasoning)
- The email drafts themselves

CITATION RULES (mandatory):
- Every claim you make MUST be followed by a citation in this format:
  [Source: <source_name> → <field_path>]
  Examples:
  [Source: LinkedIn Profile → posts_and_activity.recent_posts[0].title]
  [Source: Company LinkedIn → recent_company_posts[1].content_snippet]
  [Source: Persona → engagement_strategy.best_opening_angle]
  [Source: Service Match → matches[0].talking_point]

- If a claim cannot be cited from the research, say so explicitly:
  "This was not directly supported by the research data."

- Quote exact text from the research wherever possible (3-10 words in quotes).

- If the user asks WHY something was chosen, explain the reasoning chain:
  1. What data point triggered it
  2. Why it was selected over alternatives
  3. Which quality test it passed

TONE: Direct, precise, like a senior analyst explaining their work.
No fluff. Answer the exact question asked."""


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class VerifyRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []
    research_context: dict[str, Any] = {}


def _build_context_block(ctx: dict[str, Any]) -> str:
    """Serialize the research context into a readable block for the LLM."""

    def _fmt(label: str, data: Any, max_chars: int = 2000) -> str:
        if not data:
            return f"\n### {label}\nNot available\n"
        if isinstance(data, dict):
            raw = data.get("raw_response")
            text = raw if (raw and isinstance(raw, str)) else json.dumps(data, indent=2)
        else:
            text = json.dumps(data, indent=2) if not isinstance(data, str) else data
        truncated = text[:max_chars] + ("..." if len(text) > max_chars else "")
        return f"\n### {label}\n{truncated}\n"

    parts = ["\n\n# FULL RESEARCH CONTEXT\n"]
    parts.append(_fmt("LinkedIn Profile", ctx.get("linkedin_data"), 2500))
    parts.append(_fmt("Company Website Research", ctx.get("company_data"), 2000))
    parts.append(_fmt("Company LinkedIn Page", ctx.get("company_linkedin_data"), 2000))
    parts.append(_fmt("Activity Analysis", ctx.get("activity_data"), 2000))
    parts.append(_fmt("Persona Analysis", ctx.get("persona"), 2500))
    parts.append(_fmt("Service Match", ctx.get("service_match"), 1500))

    # Email drafts
    drafts = ctx.get("email_drafts")
    if drafts:
        parts.append("\n### Email Drafts\n")
        for i, d in enumerate(drafts if isinstance(drafts, list) else []):
            parts.append(
                f"\n**Draft {i+1} — {d.get('angle', '')}**\n"
                f"Subject: {d.get('subject', '')}\n"
                f"Body:\n{d.get('body', '')}\n"
                f"Personalization Notes: {d.get('personalization_notes', '')}\n"
            )

    return "".join(parts)


async def _stream_answer(request: VerifyRequest):
    """Stream the LLM answer back as SSE."""
    from config.models import get_model, build_chat_llm

    llm = build_chat_llm(get_model("research"), temperature=0.2)

    context_block = _build_context_block(request.research_context)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT + context_block},
    ]

    # Add conversation history
    for msg in request.history:
        messages.append({"role": msg.role, "content": msg.content})

    # Add current question
    messages.append({"role": "user", "content": request.question})

    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error("[Verify] Stream error: %s", exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def verify_chat(request: VerifyRequest):
    """Stream a cited answer to a question about the email research."""
    return StreamingResponse(
        _stream_answer(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
