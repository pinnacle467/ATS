import logging
import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from database import client
from db_indexes import ensure_indexes, scan_for_duplicate_ids
from seed import seed_if_empty
import routes_auth
import routes_resumes
import routes_jobs
import routes_candidates
import routes_interviews
import routes_dashboard
import routes_admin
import routes_notifications
import routes_imports
import routes_calendar
import routes_offers
import routes_scheduling
import routes_job_boards
from reminder_scheduler import reminder_loop
from scheduling_reminders import scheduling_reminder_loop
from snapshot_scheduler import install_pre_commit_hook
from reply_scanner import reply_scan_loop
from email_templates import seed_default_templates
import routes_career
import routes_career_security
import routes_analytics
import routes_platform
import routes_tenant
from tenant_context import (
    TenantScopeError,
    enter_request,
    exit_request,
    reset_tenant_id,
    set_tenant_id,
    tenant_scope,
)
from tenants import get_tenant_by_slug

app = FastAPI(title='Pinnacle ATS')

api_router = APIRouter(prefix='/api')


@api_router.get('/')
async def root():
    return {'message': 'Pinnacle ATS API', 'status': 'ok'}


api_router.include_router(routes_auth.router)
api_router.include_router(routes_resumes.router)
api_router.include_router(routes_jobs.router)
api_router.include_router(routes_candidates.router)
api_router.include_router(routes_interviews.router)
api_router.include_router(routes_dashboard.router)
api_router.include_router(routes_admin.router)
api_router.include_router(routes_notifications.router)
api_router.include_router(routes_imports.router)
api_router.include_router(routes_calendar.router)
api_router.include_router(routes_offers.router)
api_router.include_router(routes_scheduling.router)
api_router.include_router(routes_job_boards.router)
api_router.include_router(routes_job_boards.public_router)
api_router.include_router(routes_career.router)
api_router.include_router(routes_career_security.router)
api_router.include_router(routes_analytics.router)
api_router.include_router(routes_platform.router)
api_router.include_router(routes_tenant.router)
from routes_change_log import router as change_log_router
api_router.include_router(change_log_router)

app.include_router(api_router)


@app.middleware('http')
async def tenant_context_middleware(request, call_next):
    """Resolves the tenant for UNAUTHENTICATED requests (public careers pages,
    login) from the X-Tenant-Slug header or a ?tenant= query param.
    Authenticated requests are re-scoped from the JWT inside get_current_user,
    which always wins over the header."""
    slug = request.headers.get('X-Tenant-Slug') or request.query_params.get('tenant')
    tenant_id = None
    if slug:
        t = await get_tenant_by_slug(slug)
        tenant_id = t['id'] if t else None
    token = set_tenant_id(tenant_id)
    req_token = enter_request()
    try:
        return await call_next(request)
    finally:
        exit_request(req_token)
        reset_tenant_id(token)


@app.exception_handler(TenantScopeError)
async def tenant_scope_error_handler(request, exc):
    logging.getLogger(__name__).warning('Unscoped tenant access blocked on %s: %s', request.url.path, exc)
    return JSONResponse(status_code=400, content={'detail': str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=['*'],
    allow_headers=['*'],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event('startup')
async def startup():
    created = await seed_if_empty()
    if created:
        logger.info('Seeded database (from snapshot or demo data)')
    # Multi-tenancy: ensure the founding tenant exists, backfill tenant_id on
    # every legacy row, and ensure the platform owner account exists. Idempotent.
    from migrate_tenancy import run_tenancy_migration
    tenancy = {}
    try:
        tenancy = await run_tenancy_migration()
        logger.info('Tenancy migration: %s', tenancy)
    except Exception:
        logger.exception('Tenancy migration failed')
    # Default email templates belong to a tenant — seed them for the founding one.
    with tenant_scope(tenancy.get('tenant_id')):
        inserted = await seed_default_templates()
    if inserted:
        logger.info(f'Seeded {inserted} default email template(s)')
    # RBAC migration — idempotent, promotes seeded admins to super_admin and
    # renames recruiter->admin, interviewer->interview_panel; backfills job.team_members
    from database import db as _db
    from migrate_rbac import migrate_to_new_rbac
    rbac_counts = await migrate_to_new_rbac(_db)
    if any(rbac_counts.values()):
        logger.info(f'RBAC migration applied: {rbac_counts}')
    # Ensure unique indexes on business IDs (idempotent). Guarantees no
    # duplicate job/candidate/interview/user/file IDs can ever be inserted.
    try:
        dupes = await scan_for_duplicate_ids(_db)
        bad = {k: v for k, v in dupes.items() if v}
        if bad:
            logger.error(f'Duplicate IDs detected BEFORE indexing (must resolve manually): {bad}')
        idx_report = await ensure_indexes(_db)
        if idx_report['created']:
            logger.info(f'Created unique indexes: {idx_report["created"]}')
        if idx_report['existed']:
            logger.info(f'Unique indexes already existed: {idx_report["existed"]}')
        if idx_report['errors']:
            logger.error(f'Index creation errors: {idx_report["errors"]}')
    except Exception:
        logger.exception('ensure_indexes failed')
    asyncio.create_task(reminder_loop())
    asyncio.create_task(scheduling_reminder_loop())
    logger.info('scheduling_reminder_loop scheduled — sending 24h/1h interview reminders every 5 minutes')
    # Snapshot durability: instead of a periodic timer, we install a git
    # pre-commit hook that dumps MongoDB → data_seed/snapshot.json
    # synchronously before every commit (including Emergent's "Save to
    # GitHub"). This guarantees pushed snapshots are never stale.
    try:
        hook_result = install_pre_commit_hook()
        if hook_result.get('installed'):
            logger.info(
                'pre-commit snapshot hook installed at %s (wrote_file=%s) — every '
                'git commit will refresh data_seed/snapshot.json synchronously',
                hook_result.get('path'), hook_result.get('wrote_file'),
            )
        else:
            logger.warning(
                'pre-commit snapshot hook NOT installed: %s',
                hook_result.get('reason'),
            )
    except Exception:
        logger.exception('failed to install pre-commit snapshot hook')
    asyncio.create_task(reply_scan_loop())
    logger.info('reply_scan_loop scheduled — scanning candidate email replies every 5 minutes')


@app.on_event('shutdown')
async def shutdown_db_client():
    client.close()
