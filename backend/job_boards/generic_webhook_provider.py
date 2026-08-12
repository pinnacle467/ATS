"""Generic Application Webhook provider.

There's no "push" here either — this represents any external system (a niche
board, a custom career page, an agency portal, Zapier, ...) that will POST
applications to the ATS's webhook endpoint (see routes_job_boards under
POST /integrations/job-boards/applications). "Publishing" a job just marks it
ready to receive applications tagged with its requisition ID and returns the
exact webhook URL + auth details the recruiter needs to hand to that system.
"""
import os

from job_boards.base import ConnectionResult, JobBoardProvider, PublishResult

APP_BASE_URL = os.environ['APP_BASE_URL']


class GenericWebhookProvider(JobBoardProvider):
    key = 'generic_webhook'
    display_name = 'Generic Application Webhook'
    description = ('Accepts inbound applications POSTed by any external system (custom career '
                    'pages, niche boards, Zapier, agency portals) via a secure, signed webhook. '
                    'No partner approval needed — you control both ends.')
    requires_partner_approval = False
    auth_fields = []

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(ok=True, status='connected', account_label='Webhook Endpoint')

    async def publish_job(self, mapped_job: dict) -> PublishResult:
        job_id = mapped_job['requisition_id']
        slug = self.integration.get('company_slug', '')
        url = f"{APP_BASE_URL}/api/integrations/job-boards/applications?tenant={slug}&webhook_id={self.integration.get('id')}"
        return PublishResult(ok=True, status='published', external_job_id=job_id,
                              external_posting_id=job_id, external_url=url)

    async def update_job(self, mapped_job: dict, publication: dict) -> PublishResult:
        return await self.publish_job(mapped_job)

    async def expire_job(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status='closed', external_job_id=publication.get('external_job_id'))

    async def get_job_status(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status=publication.get('status', 'published'))
