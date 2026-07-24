import logging
import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

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
from reminder_scheduler import reminder_loop
from snapshot_scheduler import install_pre_commit_hook
from reply_scanner import reply_scan_loop
from email_templates import seed_default_templates
import routes_career
import routes_career_security
import routes_analytics

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
api_router.include_router(routes_career.router)
api_router.include_router(routes_career_security.router)
api_router.include_router(routes_analytics.router)
from routes_change_log import router as change_log_router
api_router.include_router(change_log_router)

app.include_router(api_router)

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
