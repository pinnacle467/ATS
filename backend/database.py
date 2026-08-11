import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from tenant_db import TenantDatabase

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)

# Unscoped handle — only for platform-level code (tenant registry, migrations).
raw_db = client[os.environ['DB_NAME']]

# Tenant-scoped handle used by all application code.
db = TenantDatabase(raw_db)
