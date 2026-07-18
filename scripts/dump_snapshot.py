"""Dump the current live MongoDB `sprout_ats` database into
backend/data_seed/snapshot.json so it will be restored by seed.py on the next
fresh chat import (where MongoDB starts empty but the repo — including this
snapshot file — is pulled in from GitHub).

Runs both as a one-off CLI (`python scripts/dump_snapshot.py`) and as the target
of the periodic background task registered in server.py.

Design principles:
- Rewrites snapshot.json atomically (tmp file + rename) so a mid-write crash
  can't leave a truncated snapshot behind.
- Includes every collection the app writes to. New collections should be added
  to COLLECTIONS below.
- Emits a machine-readable log line so the periodic task can be observed easily.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(str(Path(__file__).resolve().parent.parent / 'backend' / '.env'))

from pymongo import MongoClient  # noqa: E402

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / 'backend' / 'data_seed' / 'snapshot.json'
COLLECTIONS = [
    'users', 'jobs', 'candidates', 'interviews', 'notes', 'activities',
    'scorecards', 'departments', 'tags', 'interview_kits', 'availability',
    'audit_log', 'files', 'counters', 'career_settings', 'applications',
    'notifications', 'import_sessions',
]


def dump_snapshot() -> dict:
    mongo = MongoClient(os.environ['MONGO_URL'])
    db = mongo[os.environ['DB_NAME']]
    snap: dict = {'_meta': {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'db_name': os.environ['DB_NAME'],
    }}
    for name in COLLECTIONS:
        docs = list(db[name].find({}, {'_id': 0}))
        snap[name] = docs
    # The seed uses a special settings key for pipeline stages
    pipeline_setting = db.settings.find_one({'key': 'pipeline_stages'}, {'_id': 0})
    if pipeline_setting:
        snap['pipeline'] = {'stages': pipeline_setting.get('stages', [])}
    counts = {k: len(v) for k, v in snap.items() if isinstance(v, list)}

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', delete=False, dir=str(SNAPSHOT_PATH.parent), suffix='.tmp') as f:
        json.dump(snap, f)
        tmp_path = f.name
    os.replace(tmp_path, SNAPSHOT_PATH)
    return {'counts': counts, 'bytes': SNAPSHOT_PATH.stat().st_size, 'path': str(SNAPSHOT_PATH)}


if __name__ == '__main__':
    result = dump_snapshot()
    print(json.dumps({'ok': True, **result}))
