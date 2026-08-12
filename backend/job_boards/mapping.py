"""Maps an ATS job document to the normalized job-board field set (see
base.ATS_JOB_FIELDS) used by every provider's publish_job/update_job."""
import os

APP_BASE_URL = os.environ['APP_BASE_URL']


def map_job_to_board_fields(job: dict, company_name: str) -> dict:
    mapped = {
        'title': job.get('title'),
        'description': job.get('jd_text') or job.get('description'),
        'company': company_name,
        'department': job.get('department'),
        'location': job.get('location'),
        'remote_type': job.get('remote_type'),
        'employment_type': job.get('employment_type'),
        'salary_range': job.get('salary_range'),
        'application_url': f"{APP_BASE_URL}/careers/jobs/{job['slug']}" if job.get('slug') else None,
        'requisition_id': job['id'],
        'job_reference_id': job.get('job_code'),
    }
    return {k: v for k, v in mapped.items() if v not in (None, '', [])}


def populated_field_names(job: dict) -> set:
    """Which board-mappable fields this job actually has a value for (used to
    decide which "unsupported field" warnings are worth showing)."""
    mapped = map_job_to_board_fields(job, 'x')
    return set(mapped.keys()) - {'requisition_id', 'company'}
