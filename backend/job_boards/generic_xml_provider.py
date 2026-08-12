"""Generic XML Job Feed provider.

There's no external API to call — the ATS itself exposes a standard XML feed
(see routes_job_boards.public_job_feed_xml) that any aggregator/board
supporting XML feed ingestion can pull from. "Publishing" a job to this
provider simply marks it as included in that feed; "closing" removes it.
"""
import os

from job_boards.base import ConnectionResult, JobBoardProvider, PublishResult

APP_BASE_URL = os.environ['APP_BASE_URL']


class GenericXMLProvider(JobBoardProvider):
    key = 'generic_xml'
    display_name = 'Generic XML Feed'
    description = ('Exposes your published, open jobs as a standard XML feed at a fixed URL '
                    'that any job aggregator or board supporting XML feed ingestion can pull '
                    'from on their own schedule — no partner approval needed.')
    requires_partner_approval = False
    auth_fields = []

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(ok=True, status='connected', account_label='XML Feed')

    async def publish_job(self, mapped_job: dict) -> PublishResult:
        job_id = mapped_job['requisition_id']
        slug = self.integration.get('company_slug', '')
        return PublishResult(ok=True, status='published', external_job_id=job_id,
                              external_posting_id=job_id,
                              external_url=f'{APP_BASE_URL}/api/job-feeds/{slug}/jobs.xml')

    async def update_job(self, mapped_job: dict, publication: dict) -> PublishResult:
        return await self.publish_job(mapped_job)

    async def expire_job(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status='closed', external_job_id=publication.get('external_job_id'))

    async def get_job_status(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status=publication.get('status', 'published'))
