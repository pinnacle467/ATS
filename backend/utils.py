import uuid
from datetime import datetime, timezone

from database import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def clean(doc):
    """Remove Mongo _id recursively; safe for JSON responses."""
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    if isinstance(doc, dict):
        return {k: clean(v) for k, v in doc.items() if k != '_id'}
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


async def log_activity(actor: dict, type_: str, message: str, candidate_id: str = None, job_id: str = None):
    await db.activities.insert_one({
        'id': new_id(),
        'type': type_,
        'actor_id': actor.get('id') if actor else None,
        'actor_name': actor.get('name') if actor else 'System',
        'candidate_id': candidate_id,
        'job_id': job_id,
        'message': message,
        'created_at': now_iso(),
    })


async def log_audit(actor: dict, action: str, entity_type: str, entity_id: str, details: str = ''):
    await db.audit_log.insert_one({
        'id': new_id(),
        'action': action,
        'actor_id': actor.get('id') if actor else None,
        'actor_name': actor.get('name') if actor else 'System',
        'entity_type': entity_type,
        'entity_id': entity_id,
        'details': details,
        'created_at': now_iso(),
    })


async def notify(user_id: str, type_: str, message: str, link: str = None):
    await db.notifications.insert_one({
        'id': new_id(),
        'user_id': user_id,
        'type': type_,
        'message': message,
        'link': link,
        'read': False,
        'created_at': now_iso(),
    })
