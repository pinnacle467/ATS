"""Provider/adapter architecture for external job boards.

Every job board (Indeed, ZipRecruiter, LinkedIn, a generic XML feed, a generic
application webhook, ...) is represented by a subclass of `JobBoardProvider`.
The rest of the app (routes_job_boards.py, job_board_ingestion.py) only ever
talks to this interface — no board-specific logic leaks into core ATS code.
Adding a new board later means adding one new file here + one line in
`registry.py`; nothing else in the ATS changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# The subset of job-board fields the ATS's current Job model can actually
# populate today (title/description/department/location/employment_type/
# remote_type/salary_range/application_url/requisition_id/job_code). The full
# spec field list (country/state/city, structured salary, skills, benefits,
# contact info, ...) isn't captured by the Job model yet — rather than
# inventing new Job schema fields for this feature, we map what exists and
# are explicit in the UI about what isn't sent yet.
ATS_JOB_FIELDS = {
    'title', 'description', 'company', 'department', 'location',
    'remote_type', 'employment_type', 'salary_range', 'application_url',
    'requisition_id', 'job_reference_id',
}


@dataclass
class ConnectionResult:
    ok: bool
    status: str  # 'connected' | 'connection_error' | 'partner_approval_required'
    account_label: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PublishResult:
    ok: bool
    status: str  # 'published' | 'updated' | 'closed' | 'failed' | 'pending_retry' | 'partner_approval_required'
    external_job_id: Optional[str] = None
    external_posting_id: Optional[str] = None
    external_url: Optional[str] = None
    error: Optional[str] = None


class JobBoardProvider:
    """Abstract base every job board adapter implements."""

    key: str = 'base'
    display_name: str = 'Base Provider'
    description: str = ''
    requires_partner_approval: bool = False
    # Auth form fields shown in the "Connect" dialog: [{key, label, type, required}]
    auth_fields: list = []
    # Which of ATS_JOB_FIELDS this board can actually accept when publishing.
    supported_fields: set = ATS_JOB_FIELDS

    def __init__(self, integration: dict, credentials: Optional[dict] = None):
        self.integration = integration or {}
        self.credentials = credentials or {}  # decrypted, server-side only

    def unsupported_fields(self, populated_fields: set) -> set:
        """Fields the job actually has data for that this board will ignore."""
        return populated_fields & (ATS_JOB_FIELDS - self.supported_fields)

    async def test_connection(self) -> ConnectionResult:
        raise NotImplementedError

    async def publish_job(self, mapped_job: dict) -> PublishResult:
        raise NotImplementedError

    async def update_job(self, mapped_job: dict, publication: dict) -> PublishResult:
        raise NotImplementedError

    async def expire_job(self, publication: dict) -> PublishResult:
        raise NotImplementedError

    async def get_job_status(self, publication: dict) -> PublishResult:
        raise NotImplementedError
