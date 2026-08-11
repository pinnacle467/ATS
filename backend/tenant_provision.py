"""Provision a brand-new tenant: empty of business data, but with the defaults
a workspace needs to be usable (pipeline stages, default email templates,
first super_admin user)."""
from auth import hash_password
from database import db
from email_templates import seed_default_templates
from tenant_context import tenant_scope
from utils import new_id, now_iso

DEFAULT_STAGES = [
    {'name': 'Applied', 'scorecard_attributes': []},
    {'name': 'Screening', 'scorecard_attributes': ['Communication', 'Motivation']},
    {'name': 'Interview', 'scorecard_attributes': ['Communication', 'Technical Skill', 'Problem Solving', 'Culture Fit']},
    {'name': 'Offer', 'scorecard_attributes': []},
    {'name': 'Hired', 'scorecard_attributes': []},
    {'name': 'Rejected', 'scorecard_attributes': []},
]


async def provision_tenant_defaults(tenant_id: str, admin_name: str, admin_email: str, admin_password: str) -> dict:
    """Runs inside the new tenant's scope so every write is stamped with its tenant_id."""
    with tenant_scope(tenant_id):
        await db.settings.update_one(
            {'key': 'pipeline_stages'},
            {'$set': {'stages': DEFAULT_STAGES}},
            upsert=True,
        )
        await seed_default_templates()
        user = {
            'id': new_id(),
            'name': admin_name,
            'email': admin_email.lower(),
            'password_hash': hash_password(admin_password),
            'role': 'super_admin',
            'title': 'Workspace Owner',
            'active': True,
            'last_login': None,
            'created_at': now_iso(),
        }
        await db.users.insert_one(user)
    return {k: v for k, v in user.items() if k != 'password_hash'}
