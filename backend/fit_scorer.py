"""Job-fit scoring: compares a candidate's resume/profile against a job's JD via LLM."""
import base64

from database import db
from grok_client import grok_json
from resume_parser import extract_text_from_bytes
from utils import now_iso

FIT_SYSTEM_PROMPT = """You are an expert technical recruiter. Compare a candidate's resume/profile against a
job description and rate how well the candidate fits the role, from 0 to 100 (100 = perfect fit).
Return ONLY a valid JSON object — no markdown fences, no commentary:
{"score": integer 0-100, "summary": "1-2 sentence explanation of the fit, mentioning key matches or gaps"}"""


async def _score_text(resume_text: str, jd_text: str, session_label: str) -> dict:
    parsed = await grok_json(
        system=FIT_SYSTEM_PROMPT,
        user=f'JOB DESCRIPTION:\n{jd_text[:8000]}\n\nCANDIDATE RESUME/PROFILE:\n{resume_text[:8000]}',
        reasoning_effort='low',
    )
    try:
        score = max(0, min(100, int(parsed.get('score'))))
    except (TypeError, ValueError):
        score = None
    summary = (parsed.get('summary') or '').strip() or None
    return {'score': score, 'summary': summary}


async def resume_text_for(cand: dict) -> str:
    fid = cand.get('resume_file_id')
    if fid:
        f = await db.files.find_one({'id': fid})
        if f:
            try:
                data = base64.b64decode(f['data_b64'])
                text = extract_text_from_bytes(data, f['filename'])
                if len(text) >= 30:
                    return text
            except Exception:
                pass
    parts = [cand.get('name') or '', cand.get('current_title') or '', cand.get('current_company') or '']
    parts += cand.get('skills') or []
    for e in cand.get('experience') or []:
        parts.append(f"{e.get('title', '')} at {e.get('company', '')}: {e.get('description') or ''}")
    for e in cand.get('education') or []:
        parts.append(f"{e.get('degree', '')} - {e.get('school', '')}")
    return '\n'.join(p for p in parts if p)


async def recompute_candidate_fit(candidate_id: str):
    """Fire-and-forget background task: (re)score a candidate against their assigned job's JD."""
    cand = await db.candidates.find_one({'id': candidate_id})
    if not cand or not cand.get('job_id'):
        return
    job = await db.jobs.find_one({'id': cand['job_id']})
    # Prefer explicit jd_text (uploaded/pasted JD); fall back to the shorter job description
    # so recruiters see fit scores even before they've attached a formal JD document.
    jd_source = (job or {}).get('jd_text') or (job or {}).get('description') or ''
    if not job or not jd_source.strip():
        await db.candidates.update_one({'id': candidate_id}, {'$set': {
            'fit_score': None, 'fit_score_summary': None, 'fit_score_computed_at': None,
        }})
        return
    resume_text = await resume_text_for(cand)
    try:
        result = await _score_text(resume_text, jd_source, candidate_id[:8])
    except Exception:
        return
    await db.candidates.update_one({'id': candidate_id}, {'$set': {
        'fit_score': result['score'], 'fit_score_summary': result['summary'], 'fit_score_computed_at': now_iso(),
    }})


async def recompute_job_candidates_fit(job_id: str):
    ids = await db.candidates.distinct('id', {'job_id': job_id})
    for cid in ids:
        await recompute_candidate_fit(cid)
