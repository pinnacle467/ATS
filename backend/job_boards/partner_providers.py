"""Indeed / ZipRecruiter / LinkedIn — complete adapter framework, but real
connectivity is intentionally NOT implemented against a live API, because all
three require business-level partner approval that cannot be self-served with
just an API key:

  - Indeed:       Job Sync API (job postings) + "Apply with Indeed" (applications).
                  Must become a registered Indeed partner (docs.indeed.com), sign
                  Indeed's Developer Agreement, and have your app registered before
                  Partner Console issues OAuth credentials.
  - ZipRecruiter: Job API + Apply Webhook. Closed partner program — contact
                  atsintegrations@ziprecruiter.com to request ATS partner access;
                  self-serve signup is not available.
  - LinkedIn:     The Jobs Posting API is closed to new partnerships (per LinkedIn's
                  2026 docs) — new integrators are directed to "Apply Connect" or must
                  go through business.linkedin.com/hire/ats-partners/partner-application
                  for a Talent Solutions partnership.

Once approval is granted for any of these, replace the relevant subclass's
methods with real HTTP calls using `self.credentials`. Nothing else in the app
needs to change — routes_job_boards.py and job_board_ingestion.py only depend
on the JobBoardProvider interface, never on a specific board.
"""
from job_boards.base import ConnectionResult, JobBoardProvider, PublishResult

_MSG = ("{name} requires business-level partner/API approval before jobs can be "
        "published or applications received — entering an API key alone is not "
        "enough. See this provider's description for how to apply. Once approved, "
        "your credentials are saved and ready to activate immediately.")


class _UnapprovedPartnerProvider(JobBoardProvider):
    """Shared behaviour for boards this environment cannot connect to without
    partner approval it does not have. Credentials the admin enters are still
    stored (encrypted) so nothing needs to be re-entered once approval lands."""
    requires_partner_approval = True

    def _blocked_error(self) -> str:
        return _MSG.format(name=self.display_name)

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(ok=False, status='partner_approval_required', error=self._blocked_error())

    async def publish_job(self, mapped_job: dict) -> PublishResult:
        return PublishResult(ok=False, status='partner_approval_required', error=self._blocked_error())

    async def update_job(self, mapped_job: dict, publication: dict) -> PublishResult:
        return await self.publish_job(mapped_job)

    async def expire_job(self, publication: dict) -> PublishResult:
        return PublishResult(ok=False, status='partner_approval_required', error=self._blocked_error())

    async def get_job_status(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status=publication.get('status', 'draft'))


class IndeedProvider(_UnapprovedPartnerProvider):
    key = 'indeed'
    display_name = 'Indeed'
    description = ('Publish jobs to Indeed and receive applications via Apply with Indeed. '
                    'Requires becoming a registered Indeed partner at docs.indeed.com (Developer '
                    'Agreement + app registration) — not a self-serve developer key.')
    supported_fields = {'title', 'description', 'company', 'department', 'location',
                         'employment_type', 'application_url', 'requisition_id', 'job_reference_id'}
    auth_fields = [
        {'key': 'employer_account_id', 'label': 'Indeed Employer Account ID', 'type': 'text', 'required': True},
        {'key': 'client_id', 'label': 'OAuth Client ID', 'type': 'text', 'required': True},
        {'key': 'client_secret', 'label': 'OAuth Client Secret', 'type': 'password', 'required': True},
    ]


class ZipRecruiterProvider(_UnapprovedPartnerProvider):
    key = 'ziprecruiter'
    display_name = 'ZipRecruiter'
    description = ('Publish jobs to ZipRecruiter and receive applications via the Apply Webhook. '
                    'Closed partner program — email atsintegrations@ziprecruiter.com to request '
                    'ATS partner access; there is no public self-serve signup.')
    supported_fields = {'title', 'description', 'company', 'department', 'location',
                         'employment_type', 'salary_range', 'application_url', 'requisition_id'}
    auth_fields = [
        {'key': 'partner_api_key', 'label': 'Partner API Key', 'type': 'password', 'required': True},
    ]


class LinkedInProvider(_UnapprovedPartnerProvider):
    key = 'linkedin'
    display_name = 'LinkedIn'
    description = ('Publish jobs to LinkedIn Jobs. LinkedIn\'s Job Posting API is closed to new '
                    'partnerships as of 2026 — apply for a Talent Solutions partnership at '
                    'business.linkedin.com/hire/ats-partners/partner-application, or use "Apply Connect" instead.')
    supported_fields = {'title', 'description', 'company', 'department', 'location',
                         'remote_type', 'employment_type', 'application_url', 'requisition_id'}
    auth_fields = [
        {'key': 'client_id', 'label': 'OAuth Client ID', 'type': 'text', 'required': True},
        {'key': 'client_secret', 'label': 'OAuth Client Secret', 'type': 'password', 'required': True},
        {'key': 'organization_id', 'label': 'LinkedIn Organization ID', 'type': 'text', 'required': True},
    ]
