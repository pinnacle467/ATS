import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from database import client
from seed import seed_if_empty
import routes_auth
import routes_resumes
import routes_jobs
import routes_candidates
import routes_interviews
import routes_dashboard
import routes_admin
import routes_notifications

app = FastAPI(title='Sprout ATS')

api_router = APIRouter(prefix='/api')


@api_router.get('/')
async def root():
    return {'message': 'Sprout ATS API', 'status': 'ok'}


api_router.include_router(routes_auth.router)
api_router.include_router(routes_resumes.router)
api_router.include_router(routes_jobs.router)
api_router.include_router(routes_candidates.router)
api_router.include_router(routes_interviews.router)
api_router.include_router(routes_dashboard.router)
api_router.include_router(routes_admin.router)
api_router.include_router(routes_notifications.router)

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
        logger.info('Seeded demo data')


@app.on_event('shutdown')
async def shutdown_db_client():
    client.close()
