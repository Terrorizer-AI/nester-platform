"""
Memory-powered RAG chat endpoint.

POST /chat/memory
  - Accepts a question + conversation history
  - Retrieves context from: run history output data + Mem0 semantic search
  - Streams an answer grounded in retrieved context
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from memory.mem0_store import is_mem0_ready, search_memory, get_all_memories
from memory.sqlite_ops import is_sqlite_ready, list_runs, get_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


SYSTEM_PROMPT = """You are Nester AI — a sales intelligence assistant with deep knowledge of every prospect and company researched through Nester's pipeline.

Your knowledge comes from the RESEARCH DATA section below. This is real data from completed pipeline runs — LinkedIn profiles, company research, activity analysis, persona insights, service matches, and generated emails.

RULES:
- Answer based on the research data provided below
- Be specific — quote names, titles, companies, pain points, and details from the data
- When referencing data, cite the source naturally: "Based on the LinkedIn research..." or "The company analysis shows..."
- You can compare prospects, find patterns, and surface insights across multiple runs
- For general questions ("how many prospects"), use the run stats
- Be conversational but direct — the user is a sales professional
- If asked about someone/something not in the data, say so clearly
- Format responses with markdown: use **bold** for emphasis, bullet lists for multiple points, headers for sections

TONE: Knowledgeable sales analyst who has studied every prospect in depth."""


class ChatMemoryRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = []


def _truncate(text: str, max_chars: int = 2000) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _format_parsed_data(label: str, data: Any) -> str:
    """Format parsed output data into readable text."""
    if not data or (isinstance(data, dict) and not data):
        return ""
    if isinstance(data, dict):
        # Filter out empty values
        clean = {k: v for k, v in data.items() if v}
        if not clean:
            return ""
        return f"\n### {label}\n{json.dumps(clean, indent=2, default=str)[:2500]}\n"
    return f"\n### {label}\n{str(data)[:2000]}\n"


def _build_run_context(question: str) -> str:
    """Build rich context from run history output data."""
    if not is_sqlite_ready():
        return "\n[No data available — backend not initialized]\n"

    runs = list_runs(limit=50)
    if not runs:
        return "\n[No pipeline runs yet — run a pipeline first]\n"

    sections: list[str] = []

    # For each completed run, pull the full output data
    for run_summary in runs:
        if run_summary.get("status") != "completed":
            continue

        run_detail = get_run(run_summary["run_id"])
        if not run_detail:
            continue

        output = run_detail.get("output_data", {})
        input_data = run_detail.get("input_data", {})
        if not isinstance(output, dict):
            try:
                output = json.loads(output) if isinstance(output, str) else {}
            except (json.JSONDecodeError, TypeError):
                output = {}
        if not isinstance(input_data, dict):
            try:
                input_data = json.loads(input_data) if isinstance(input_data, str) else {}
            except (json.JSONDecodeError, TypeError):
                input_data = {}

        prospect = run_summary.get("prospect_name", "Unknown")
        company = run_summary.get("company_name", "Unknown")
        duration = run_summary.get("duration_ms", 0)
        completed = run_summary.get("completed_at", "")

        sections.append(f"\n\n## Prospect: {prospect} — Company: {company}")
        sections.append(f"Run completed: {completed} | Duration: {duration}ms")

        # Input
        if input_data.get("linkedin_url"):
            sections.append(f"LinkedIn: {input_data['linkedin_url']}")
        if input_data.get("company_website"):
            sections.append(f"Website: {input_data['company_website']}")

        # Parsed output sections
        sections.append(_format_parsed_data("LinkedIn Profile", output.get("linkedin_parsed")))
        sections.append(_format_parsed_data("Company Intelligence", output.get("company_parsed")))
        sections.append(_format_parsed_data("Company LinkedIn", output.get("company_linkedin_parsed")))
        sections.append(_format_parsed_data("Activity Analysis", output.get("activity_parsed")))
        sections.append(_format_parsed_data("Persona", output.get("persona")))
        sections.append(_format_parsed_data("Service Match", output.get("service_match")))

        # Email drafts
        drafts = output.get("email_drafts", [])
        if isinstance(drafts, list) and drafts:
            sections.append("\n### Generated Emails")
            for i, d in enumerate(drafts[:4]):
                if isinstance(d, dict):
                    sections.append(
                        f"\n**Email {i+1}** — {d.get('angle', d.get('variant', ''))}\n"
                        f"Subject: {d.get('subject', '')}\n"
                        f"Body: {d.get('body', d.get('content', ''))}\n"
                    )

        # Primary hook
        hook = output.get("primary_hook", "")
        if hook:
            sections.append(f"\n### Primary Hook\n{hook}")

    if not sections:
        return "\n[No completed runs found]\n"

    return "\n# RESEARCH DATA\n" + "\n".join(s for s in sections if s) + "\n"


def _get_mem0_context(question: str) -> str:
    """Bonus: search Mem0 for additional semantic matches."""
    if not is_mem0_ready():
        return ""

    if not is_sqlite_ready():
        return ""

    namespaces: list[str] = []
    recent_runs = list_runs(limit=50)
    for run in recent_runs:
        p = run.get("prospect_name", "")
        c = run.get("company_name", "")
        if p:
            ns = f"prospect_{p.lower().strip().replace(' ', '_')}"
            if ns not in namespaces:
                namespaces.append(ns)
        if c:
            ns = f"company_{c.lower().strip().replace(' ', '_')}"
            if ns not in namespaces:
                namespaces.append(ns)

    if not namespaces:
        return ""

    mem_sections: list[str] = []
    for ns in namespaces[:15]:
        results = search_memory(query=question, user_id=ns, limit=3)
        if results:
            for mem in results:
                memory_text = mem.get("memory", "")
                score = mem.get("score", 0)
                if score and score < 0.3:
                    continue
                mem_sections.append(f"- {memory_text}")

    if not mem_sections:
        return ""

    return "\n\n# ADDITIONAL MEMORY CONTEXT\n" + "\n".join(mem_sections) + "\n"


def _get_run_stats() -> str:
    """Get quick stats from run history."""
    if not is_sqlite_ready():
        return ""

    runs = list_runs(limit=100)
    if not runs:
        return "\n# RUN STATS\nNo pipeline runs recorded yet.\n"

    total = len(runs)
    completed = sum(1 for r in runs if r.get("status") == "completed")
    prospects = list({r.get("prospect_name", "") for r in runs if r.get("prospect_name")})
    companies = list({r.get("company_name", "") for r in runs if r.get("company_name")})

    lines = [
        "\n# RUN STATS",
        f"Total runs: {total} ({completed} completed)",
        f"Prospects researched: {', '.join(prospects[:20]) or 'None'}",
        f"Companies researched: {', '.join(companies[:20]) or 'None'}",
    ]
    return "\n".join(lines) + "\n"


async def _stream_memory_answer(request: ChatMemoryRequest):
    """Stream the RAG answer back as SSE."""
    from config.models import get_model, build_chat_llm

    llm = build_chat_llm(get_model("research"), temperature=0.2)

    # Primary context: run history output data
    run_context = _build_run_context(request.question)
    run_stats = _get_run_stats()
    # Bonus: Mem0 semantic search
    mem0_context = _get_mem0_context(request.question)

    system_content = SYSTEM_PROMPT + run_stats + run_context + mem0_context

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_content},
    ]

    for msg in request.history:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": request.question})

    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error("[MemoryChat] Stream error: %s", exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/memory")
async def memory_chat(request: ChatMemoryRequest):
    """Stream a RAG-powered answer grounded in pipeline research data."""
    return StreamingResponse(
        _stream_memory_answer(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
