"""Entity-scoped change log endpoints. Uses the existing audit_log collection.
Only Admin+ can view (footprint visibility per user's spec)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import require_roles
from database import db
from utils import clean

router = APIRouter(tags=['change-log'])


@router.get('/candidates/{candidate_id}/change-log')
async def candidate_change_log(candidate_id: str, limit: int = 200,
                                user: dict = Depends(require_roles('admin', 'recruiter'))):
    """All audit_log entries scoped to a specific candidate, most-recent first."""
    cand = await db.candidates.find_one({'id': candidate_id}, {'_id': 0, 'id': 1, 'name': 1})
    if not cand:
        raise HTTPException(status_code=404, detail='Candidate not found')
    rows = await db.audit_log.find(
        {'entity_type': 'candidate', 'entity_id': candidate_id},
        {'_id': 0},
    ).sort('created_at', -1).to_list(min(max(limit, 1), 500))
    return {'candidate_id': candidate_id, 'name': cand.get('name'), 'entries': clean(rows), 'total': len(rows)}


@router.get('/jobs/{job_id}/change-log')
async def job_change_log(job_id: str, limit: int = 200,
                          user: dict = Depends(require_roles('admin', 'recruiter'))):
    """All audit_log entries scoped to a specific job, most-recent first."""
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0, 'id': 1, 'title': 1})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    rows = await db.audit_log.find(
        {'entity_type': 'job', 'entity_id': job_id},
        {'_id': 0},
    ).sort('created_at', -1).to_list(min(max(limit, 1), 500))
    return {'job_id': job_id, 'title': job.get('title'), 'entries': clean(rows), 'total': len(rows)}
