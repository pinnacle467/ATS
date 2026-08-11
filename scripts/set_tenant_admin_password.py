"""One-off: set the Context66 tenant super_admin password (kangabhijeet@gmail.com).

The platform owner is rotated automatically by migrate_tenancy.ensure_platform_owner()
from PLATFORM_OWNER_EMAIL / PLATFORM_OWNER_PASSWORD in backend/.env.

Usage: cd /app/backend && python ../scripts/set_tenant_admin_password.py <email> <password>
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from auth import hash_password  # noqa: E402
from database import raw_db  # noqa: E402
from utils import now_iso  # noqa: E402


async def main(email: str, password: str):
    email = email.lower().strip()
    user = await raw_db.users.find_one({'email': email})
    if not user:
        print(f'No user with email {email}')
        return
    await raw_db.users.update_one(
        {'id': user['id']},
        {'$set': {
            'password_hash': hash_password(password),
            'password_updated_at': now_iso(),
            'role': 'super_admin',
            'active': True,
        }},
    )
    print(f"Updated {email} (tenant {user.get('tenant_id')}) -> role super_admin, password reset")


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2]))
