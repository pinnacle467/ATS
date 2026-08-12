"""Sandbox/mock job board — always connects and always publishes successfully.

Use this to exercise the ENTIRE publish -> application -> candidate ->
resume-parse -> fit-score pipeline with zero external setup or credentials.
Also used by automated tests. Real providers (Indeed/ZipRecruiter/LinkedIn)
require partner approval this environment cannot obtain — this one lets the
whole feature be verified end-to-end regardless.
"""
import uuid

from job_boards.base import ConnectionResult, JobBoardProvider, PublishResult


class MockProvider(JobBoardProvider):
    key = 'mock'
    display_name = 'Sandbox (Testing)'
    description = ('A fake job board for testing the full publish -> application -> candidate '
                    'pipeline end-to-end with zero external setup. Use "Simulate Application" on '
                    'a published job to see an inbound application flow through automatically.')
    requires_partner_approval = False
    auth_fields = []

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(ok=True, status='connected', account_label='Sandbox Account')

    async def publish_job(self, mapped_job: dict) -> PublishResult:
        ext_id = f'mock-{uuid.uuid4().hex[:10]}'
        return PublishResult(ok=True, status='published', external_job_id=ext_id,
                              external_posting_id=ext_id, external_url=f'https://sandbox.example/jobs/{ext_id}')

    async def update_job(self, mapped_job: dict, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status='updated', external_job_id=publication.get('external_job_id'),
                              external_posting_id=publication.get('external_posting_id'),
                              external_url=publication.get('external_url'))

    async def expire_job(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status='closed', external_job_id=publication.get('external_job_id'))

    async def get_job_status(self, publication: dict) -> PublishResult:
        return PublishResult(ok=True, status=publication.get('status', 'published'),
                              external_job_id=publication.get('external_job_id'))
