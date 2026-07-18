import asyncio
import base64
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from auth import get_current_user, require_roles
from database import db
from resume_compressor import compress_resume
from resume_parser import extract_text_from_bytes, low_confidence_fields, parse_resume_text
from utils import new_id, now_iso

router = APIRouter(tags=['resumes'])

MAX_SIZE = 10 * 1024 * 1024  # 10 MB


async def _find_match(parsed: dict):
    """Look for an existing candidate this resume likely belongs to (e.g. one
    created via a CSV/Excel import that doesn't have a resume yet). Email match
    is treated as high-confidence; name-only match as a lower-confidence hint
    the user should confirm before merging."""
    email = (parsed.get('email') or '').strip()
    name = (parsed.get('name') or '').strip()
    if email:
        cand = await db.candidates.find_one({'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'}})
        if cand:
            return {'candidate_id': cand['id'], 'candidate_name': cand['name'], 'match_type': 'email'}
    if name:
        cand = await db.candidates.find_one({'name': {'$regex': f'^{re.escape(name)}$', '$options': 'i'}})
        if cand:
            return {'candidate_id': cand['id'], 'candidate_name': cand['name'], 'match_type': 'name'}
    return None


async def _store_file(data: bytes, filename: str, content_type: str, user_id: str) -> str:
    try:
        data = await asyncio.to_thread(compress_resume, data, filename)
    except Exception:
        pass  # never block storage on a compression hiccup — store original bytes
    fid = new_id()
    await db.files.insert_one({
        'id': fid,
        'filename': filename,
        'content_type': content_type or 'application/octet-stream',
        'size': len(data),
        'data_b64': base64.b64encode(data).decode(),
        'uploaded_by': user_id,
        'created_at': now_iso(),
    })
    return fid


async def _parse_one(data: bytes, filename: str, content_type: str, user_id: str) -> dict:
    try:
        if len(data) > MAX_SIZE:
            return {'filename': filename, 'status': 'error', 'error': 'File exceeds 10MB limit'}
        text = extract_text_from_bytes(data, filename)
        if len(text) < 30:
            return {'filename': filename, 'status': 'error', 'error': 'Could not extract readable text from file'}
        fid = await _store_file(data, filename, content_type, user_id)
        parsed = await parse_resume_text(text, fid[:8])
        return {
            'filename': filename,
            'status': 'success',
            'file_id': fid,
            'parsed': parsed,
            'low_confidence_fields': low_confidence_fields(parsed),
            'match': await _find_match(parsed),
        }
    except ValueError as e:
        return {'filename': filename, 'status': 'error', 'error': str(e)}
    except Exception as e:
        return {'filename': filename, 'status': 'error', 'error': f'Parsing failed: {e}'}


@router.post('/resumes/parse')
async def parse_resume(file: UploadFile = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    data = await file.read()
    result = await _parse_one(data, file.filename, file.content_type, user['id'])
    if result['status'] == 'error':
        raise HTTPException(status_code=422, detail=result['error'])
    return result


@router.post('/resumes/parse-bulk')
async def parse_resumes_bulk(files: list[UploadFile] = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    if len(files) > 25:
        raise HTTPException(status_code=422, detail='Maximum 25 files per bulk request (frontend chunks larger batches)')
    payloads = []
    for f in files:
        payloads.append((await f.read(), f.filename, f.content_type))
    results = await asyncio.gather(*[_parse_one(d, n, c, user['id']) for d, n, c in payloads])
    return {'results': results}


@router.get('/files/{file_id}')
async def get_file(file_id: str, download: bool = False, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({'id': file_id})
    if not doc:
        raise HTTPException(status_code=404, detail='File not found')
    data = base64.b64decode(doc['data_b64'])
    disposition = 'attachment' if download else 'inline'
    return Response(
        content=data,
        media_type=doc.get('content_type', 'application/octet-stream'),
        headers={'Content-Disposition': f'{disposition}; filename="{doc["filename"]}"'},
    )
