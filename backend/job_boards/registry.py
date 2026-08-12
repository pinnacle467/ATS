"""Central catalogue of every job board provider the ATS knows about.

Adding a new board later: write one new provider file implementing
JobBoardProvider, then add one line here. Nothing else in the app changes.
"""
from job_boards.generic_webhook_provider import GenericWebhookProvider
from job_boards.generic_xml_provider import GenericXMLProvider
from job_boards.mock_provider import MockProvider
from job_boards.partner_providers import IndeedProvider, LinkedInProvider, NaukriProvider, ZipRecruiterProvider

PROVIDER_CLASSES = {
    'indeed': IndeedProvider,
    'ziprecruiter': ZipRecruiterProvider,
    'linkedin': LinkedInProvider,
    'naukri': NaukriProvider,
    'generic_xml': GenericXMLProvider,
    'generic_webhook': GenericWebhookProvider,
    'mock': MockProvider,
}


def get_provider_class(key: str):
    return PROVIDER_CLASSES.get(key)


def provider_catalog() -> list:
    """Static metadata for the Job Boards connection cards — never includes credentials."""
    return [
        {
            'key': key,
            'display_name': cls.display_name,
            'description': cls.description,
            'requires_partner_approval': cls.requires_partner_approval,
            'auth_fields': cls.auth_fields,
        }
        for key, cls in PROVIDER_CLASSES.items()
    ]
