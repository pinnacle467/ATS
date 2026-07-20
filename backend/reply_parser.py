"""LLM-powered extractor for candidate email replies.

Given the plain-text body of a candidate's reply, extract two fields:
  - notice_period            (str | null) — e.g. "60 days", "Immediate", "3 months"
  - expected_compensation    (str | null) — e.g. "22 LPA", "$130k base", "18 LPA fixed + 3 LPA variable"

The LLM MUST return null for any field the reply doesn't explicitly state. We
never overwrite an existing candidate field with a guessed value.
"""
from __future__ import annotations

import json
import os
import re

from emergentintegrations.llm.chat import LlmChat, UserMessage

from llm_helper import send_with_retry

SYSTEM_PROMPT = """You extract two fields from a candidate's email reply and return ONLY a valid JSON object — no markdown fences, no commentary.

Schema:
{
  "notice_period": string|null,
  "expected_compensation": string|null,
  "confidence": {"notice_period": number, "expected_compensation": number}
}

Rules:
- notice_period: how soon the candidate can join. Return their own phrasing when possible (e.g. "60 days", "Immediate", "1 month", "Serving notice, LWD 15 Aug"). Return null if the reply does not mention availability/notice period.
- expected_compensation: their expected salary/CTC/compensation. Return their own phrasing including currency and units (e.g. "22 LPA", "$130k base + equity", "18-20 LPA fixed"). Return null if the reply does not mention any compensation number.
- Confidence values are 0.0-1.0 for how certain you are the field was explicitly stated (not inferred). Use 0.0 for null fields.
- NEVER guess. NEVER hallucinate. If unsure, return null.
- If the reply is a signature-only / out-of-office / unrelated message, return both fields as null.
- Output raw JSON only."""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    return raw


EMPTY = {'notice_period': None, 'expected_compensation': None, 'confidence': {}}


async def parse_candidate_reply(text: str, session_label: str) -> dict:
    """Extract notice_period + expected_compensation from a candidate email reply."""
    if not (text or '').strip():
        return {**EMPTY}
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return {**EMPTY}

    chat = LlmChat(
        api_key=api_key,
        session_id=f'ats-reply-{session_label}',
        system_message=SYSTEM_PROMPT,
    ).with_model('openai', 'gpt-5.4-mini')

    msg = UserMessage(text=f'Extract from this candidate reply:\n\n{text[:8000]}')
    try:
        resp = await send_with_retry(chat, msg)
    except Exception:
        return {**EMPTY}
    raw = _strip_fences(resp if isinstance(resp, str) else str(resp))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            msg2 = UserMessage(text='Your previous output was not valid JSON. Return ONLY the raw JSON object.')
            resp2 = await send_with_retry(chat, msg2)
            raw2 = _strip_fences(resp2 if isinstance(resp2, str) else str(resp2))
            parsed = json.loads(raw2)
        except Exception:
            return {**EMPTY}
    merged = {**EMPTY, **{k: v for k, v in parsed.items() if k in EMPTY}}
    # Normalise: coerce empty strings to null so the downstream write logic skips them
    if isinstance(merged.get('notice_period'), str) and not merged['notice_period'].strip():
        merged['notice_period'] = None
    if isinstance(merged.get('expected_compensation'), str) and not merged['expected_compensation'].strip():
        merged['expected_compensation'] = None
    return merged
