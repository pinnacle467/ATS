"""One-time migration to bring existing users into the new 4-role model.

New model: super_admin, admin, interview_panel, vendor
Old model: admin, recruiter, interviewer

Migration policy (as decided by product owner Jul 2025):
  - The two SEEDED admins (admin@ats.com, kangabhijeet@gmail.com) -> super_admin
  - Everyone else with old role 'admin' -> admin (a fresh admin created after the rename)
  - Everyone with role 'recruiter' -> admin
  - Everyone with role 'interviewer' -> interview_panel
  - vendor role users (if any) are left alone

Also ensures every job doc has a `team_members` array (defaulting to []).

Idempotent — safe to run on every startup. If DB is already migrated, does nothing.
"""
import logging

logger = logging.getLogger(__name__)

SUPER_ADMIN_SEED_EMAILS = {'admin@ats.com', 'kangabhijeet@gmail.com'}


async def migrate_to_new_rbac(db):
    """Idempotent one-off migration. Returns dict of counts."""
    counts = {'to_super_admin': 0, 'recruiter_to_admin': 0, 'interviewer_to_ip': 0, 'jobs_backfilled': 0}

    # Promote seeded admin emails to super_admin
    r = await db.users.update_many(
        {'email': {'$in': list(SUPER_ADMIN_SEED_EMAILS)}, 'role': {'$ne': 'super_admin'}},
        {'$set': {'role': 'super_admin'}},
    )
    counts['to_super_admin'] = r.modified_count

    # recruiter -> admin
    r = await db.users.update_many({'role': 'recruiter'}, {'$set': {'role': 'admin'}})
    counts['recruiter_to_admin'] = r.modified_count

    # interviewer -> interview_panel
    r = await db.users.update_many({'role': 'interviewer'}, {'$set': {'role': 'interview_panel'}})
    counts['interviewer_to_ip'] = r.modified_count

    # Backfill team_members = [] on any job that doesn't have it
    r = await db.jobs.update_many(
        {'team_members': {'$exists': False}},
        {'$set': {'team_members': []}},
    )
    counts['jobs_backfilled'] = r.modified_count

    if any(counts.values()):
        logger.info(f'RBAC migration: {counts}')
    return counts
