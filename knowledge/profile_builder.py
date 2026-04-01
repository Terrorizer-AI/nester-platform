"""
Company profile builder — LLM reads all synced docs and generates a rich
master profile that is always injected into service_matcher and email_composer.

The profile covers:
  - What the company does (services, products, solutions)
  - Value propositions and differentiators
  - Real case studies with client names and numbers
  - Ideal Customer Profile (ICP)
  - Pricing / packages (if in docs)
  - Common objections + responses
  - Tone of voice / brand personality
  - Key team members or founders (if mentioned)

Re-generated automatically by drive_sync.py whenever docs change.
Called manually via: POST /knowledge/sync?regenerate=true
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROFILE_SYSTEM_PROMPT = """You are a company knowledge analyst. Your job is to read all the company's documents and create a comprehensive Company Master Profile that will be used to write highly personalized sales emails.

The profile must be extremely detailed and cover EVERY piece of useful information found in the documents. Sales reps will use this profile to write emails — they need real specifics, not generic summaries.

Structure your response as follows:

## COMPANY OVERVIEW
- Company name, founding year, location
- What the company does (be specific — not "provides AI solutions" but exactly what solutions)
- Core products / services with descriptions
- Target markets and industries served

## VALUE PROPOSITIONS & DIFFERENTIATORS
- What makes this company different from competitors
- Specific unique selling points (with numbers/data if available)
- Key benefits customers get

## CASE STUDIES & RESULTS
- List EVERY case study or success story mentioned
- Include: client name/industry, problem, solution, EXACT results (% improvements, dollar amounts, time saved)
- Quote any specific metrics or testimonials verbatim

## IDEAL CUSTOMER PROFILE (ICP)
- Company size, industry, geography
- Job titles of typical buyers
- Pain points this company solves
- Signs a prospect is a good fit

## SERVICES & PRICING
- List all services/packages with details
- Pricing if mentioned (exact numbers)
- Typical engagement structure

## OBJECTION HANDLING
- Common objections and how to respond
- Risk mitigators (guarantees, pilots, case studies)

## TONE & BRAND VOICE
- How the company communicates
- Key phrases or language patterns used
- What to avoid saying

## KEY PEOPLE
- Founders, leadership, key team members
- Their backgrounds / expertise (if mentioned)

Be exhaustive. Every real number, client name, and specific detail matters for sales personalization."""


def build_company_profile(openai_api_key: str) -> str:
    """
    Read all knowledge chunks and generate a company master profile via LLM.
    Saves to SQLite and returns the profile text.
    """
    from memory.sqlite_ops import get_all_knowledge_chunks, save_company_profile, list_knowledge_files, is_sqlite_ready

    if not is_sqlite_ready():
        from memory.sqlite_ops import init_sqlite_ops
        init_sqlite_ops()

    chunks = get_all_knowledge_chunks()
    if not chunks:
        logger.warning("[ProfileBuilder] No knowledge chunks found — nothing to profile")
        return ""

    files = list_knowledge_files()
    doc_count = len(files)

    # Build full document text from all chunks (ordered by file + chunk index)
    doc_sections: dict[str, list[str]] = {}
    for chunk in chunks:
        fname = chunk["file_name"]
        if fname not in doc_sections:
            doc_sections[fname] = []
        doc_sections[fname].append(chunk["content"])

    # Format as document-by-document input
    full_text_parts = []
    for fname, chunk_texts in doc_sections.items():
        full_text_parts.append(f"\n\n{'='*60}")
        full_text_parts.append(f"DOCUMENT: {fname}")
        full_text_parts.append('='*60)
        full_text_parts.append("\n".join(chunk_texts))

    full_text = "\n".join(full_text_parts)

    # Limit to ~80K chars to stay within context (gpt-4o has 128K tokens)
    if len(full_text) > 80000:
        full_text = full_text[:80000] + "\n\n[... additional content truncated ...]"

    logger.info("[ProfileBuilder] Generating company profile from %d docs, %d chars", doc_count, len(full_text))

    from openai import OpenAI
    client = OpenAI(api_key=openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Here are all the company documents ({doc_count} files):\n\n"
                f"{full_text}\n\n"
                "Generate the comprehensive Company Master Profile now. "
                "Be exhaustive — include every real number, client name, and specific detail."
            )},
        ],
    )

    profile_text = response.choices[0].message.content or ""

    save_company_profile(profile_text, doc_count)
    logger.info("[ProfileBuilder] Company profile saved (%d chars)", len(profile_text))

    return profile_text
