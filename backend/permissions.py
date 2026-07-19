"""Central definitions for the new 4-role RBAC model + helpers to strip
sensitive fields from responses depending on the caller's role.

New roles:
  - super_admin      : full unrestricted access
  - admin            : full CRUD on jobs/candidates/users, but cannot create/delete super_admin users
  - interview_panel  : sees only jobs they've been added to (team_members), no sensitive $$ fields
                       unless salary_visible=True on that team membership
  - vendor           : sees only jobs they've been added to, and only candidates they submitted

Legacy roles (kept for backwards-compat so unmigrated data still works):
  - 'admin'          -> treated as new 'admin'  (old admins are being migrated to 'super_admin' one-off)
  - 'recruiter'      -> treated as new 'admin'
  - 'interviewer'    -> treated as new 'interview_panel'
"""
from typing import Iterable, Optional

ROLE_SUPER_ADMIN = 'super_admin'
ROLE_ADMIN = 'admin'
ROLE_INTERVIEW_PANEL = 'interview_panel'
ROLE_VENDOR = 'vendor'

ALL_ROLES = [ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INTERVIEW_PANEL, ROLE_VENDOR]

# Human-readable labels for UI
ROLE_LABELS = {
    ROLE_SUPER_ADMIN: 'Super Admin',
    ROLE_ADMIN: 'Admin',
    ROLE_INTERVIEW_PANEL: 'Interview Panel',
    ROLE_VENDOR: 'Agency / Vendor',
    # legacy
    'recruiter': 'Admin (legacy)',
    'interviewer': 'Interview Panel (legacy)',
}

# When code does require_roles('admin') we want super_admin to also pass.
# When code does require_roles('recruiter') we want admin AND super_admin to pass.
# When code does require_roles('interviewer') we want interview_panel to also pass.
# This mapping expresses "which role names does a user with this actual role satisfy".
ROLE_ALIASES = {
    ROLE_SUPER_ADMIN: {ROLE_SUPER_ADMIN, ROLE_ADMIN, 'recruiter'},
    ROLE_ADMIN: {ROLE_ADMIN, 'recruiter'},
    ROLE_INTERVIEW_PANEL: {ROLE_INTERVIEW_PANEL, 'interviewer'},
    ROLE_VENDOR: {ROLE_VENDOR},
    # legacy
    'recruiter': {'recruiter', ROLE_ADMIN},
    'interviewer': {'interviewer', ROLE_INTERVIEW_PANEL},
}


def role_satisfies(user_role: str, required: Iterable[str]) -> bool:
    """True if the user's role satisfies at least one of the required role names."""
    aliases = ROLE_ALIASES.get(user_role, {user_role})
    return bool(aliases & set(required))


def is_super_admin(user: dict) -> bool:
    return user.get('role') == ROLE_SUPER_ADMIN


def is_admin_or_higher(user: dict) -> bool:
    return user.get('role') in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'recruiter')


def is_interview_panel(user: dict) -> bool:
    return user.get('role') in (ROLE_INTERVIEW_PANEL, 'interviewer')


def is_vendor(user: dict) -> bool:
    return user.get('role') == ROLE_VENDOR


def can_manage_role(actor_role: str, target_role: str) -> bool:
    """Can the actor create/edit/delete a user whose role is `target_role`?

    Rules:
      - super_admin can manage anyone (including other super_admins)
      - admin can manage admin/interview_panel/vendor (NOT super_admin)
      - anyone else cannot manage users
    """
    if actor_role == ROLE_SUPER_ADMIN:
        return True
    if actor_role in (ROLE_ADMIN, 'recruiter'):
        return target_role in (ROLE_ADMIN, ROLE_INTERVIEW_PANEL, ROLE_VENDOR, 'recruiter', 'interviewer')
    return False


# ------------- Field-level sensitivity -------------

# Fields hidden from Interview Panel members when they DON'T have salary_visible on that job
JOB_SENSITIVE_FIELDS = ('salary_range', 'budget', 'compensation', 'salary_min', 'salary_max')
CANDIDATE_SENSITIVE_FIELDS = ('expected_salary', 'current_ctc', 'notice_period')


def strip_job_sensitive(job: Optional[dict]) -> Optional[dict]:
    if not job:
        return job
    for f in JOB_SENSITIVE_FIELDS:
        job.pop(f, None)
    return job


def strip_candidate_sensitive(cand: Optional[dict]) -> Optional[dict]:
    if not cand:
        return cand
    for f in CANDIDATE_SENSITIVE_FIELDS:
        cand.pop(f, None)
    return cand


async def job_team_membership(db, user_id: str, job_id: str) -> Optional[dict]:
    """Return the team_members entry for this user on this job, or None."""
    job = await db.jobs.find_one({'id': job_id, 'team_members.user_id': user_id},
                                 {'_id': 0, 'team_members.$': 1})
    if not job or not job.get('team_members'):
        return None
    return job['team_members'][0]


async def visible_job_ids_for_user(db, user: dict) -> list:
    """List of job IDs the user has been explicitly added to.
    Used by interview_panel + vendor. Admin+ never call this (they see all).
    """
    cursor = db.jobs.find({'team_members.user_id': user['id']}, {'_id': 0, 'id': 1})
    return [j['id'] async for j in cursor]
