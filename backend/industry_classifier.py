"""Standalone industry classifier — used by the backfill/migration path for
candidates whose industry needs (re)computing outside the normal resume-parse
flow (e.g. an existing candidate imported before this feature existed).

New resume uploads classify industry inline as part of `resume_parser.
parse_resume_text()` (one LLM call does both field extraction + industry
classification). This module exists so the backfill script doesn't need to
reconstruct/re-run the full resume parse — it just needs the industries.
"""
from grok_client import grok_json
from industry_taxonomy import INDUSTRY_PROMPT_RULES, normalize_industry_list

CLASSIFY_SYSTEM_PROMPT = f"""You are an expert at analyzing a candidate's work history to determine which
business/domain industries they have experience in. You receive raw resume/profile text and return ONLY a
valid JSON object — no markdown fences, no commentary.

JSON schema:
{{"industries": [string]}}

{INDUSTRY_PROMPT_RULES}"""


async def classify_industries_from_resume(resume_text: str) -> list:
    if not resume_text or not resume_text.strip():
        return []
    try:
        parsed = await grok_json(
            system=CLASSIFY_SYSTEM_PROMPT,
            user=f'Candidate resume/profile text:\n\n{resume_text[:15000]}',
            reasoning_effort='low',
            max_tokens=1024,
        )
    except Exception:
        return []
    return normalize_industry_list(parsed.get('industries') or [])
