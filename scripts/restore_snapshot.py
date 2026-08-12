"""Force-restore the live MongoDB database from backend/data_seed/snapshot.json,
OVERWRITING whatever is currently in it.

Use this on a VPS (or any environment) that already has data, after doing a
`git pull`, to make its database match the latest snapshot committed from the
Emergent preview. Unlike seed.py's `seed_if_empty()` (which only restores when
the `users` collection is completely empty — a one-time bootstrap), this
script ALWAYS overwrites every collection listed in dump_snapshot.COLLECTIONS,
regardless of current contents.

DESTRUCTIVE: every collection below is fully cleared before the snapshot's
documents are re-inserted. Anything in the target database that is NOT in the
snapshot (e.g. data created directly on the VPS) will be lost.

Usage:
    cd /path/to/app
    git pull
    python scripts/restore_snapshot.py --yes
    # then restart the app so it re-runs ensure_indexes() on the fresh data
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

import json
import os

from dotenv import load_dotenv  # noqa: E402

load_dotenv(str(Path(__file__).resolve().parent.parent / 'backend' / '.env'))

from pymongo import MongoClient  # noqa: E402

from dump_snapshot import COLLECTIONS, SNAPSHOT_PATH  # noqa: E402


def restore_snapshot(confirmed: bool) -> dict:
    if not SNAPSHOT_PATH.exists():
        raise SystemExit(f'No snapshot found at {SNAPSHOT_PATH} — nothing to restore.')

    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)

    mongo = MongoClient(os.environ['MONGO_URL'])
    db = mongo[os.environ['DB_NAME']]

    meta = snap.get('_meta', {})
    print(f"Snapshot generated_at={meta.get('generated_at')} db_name={meta.get('db_name')}")
    print(f"Target database: {os.environ['DB_NAME']} (MONGO_URL from backend/.env)")
    print()
    print('This will DELETE and REPLACE the following collections:')
    for name in COLLECTIONS:
        before = db[name].count_documents({})
        incoming = len(snap.get(name) or [])
        print(f'  - {name}: {before} doc(s) currently -> {incoming} doc(s) in snapshot')

    if not confirmed:
        print()
        print('Dry run only (no --yes flag passed). Re-run with --yes to actually overwrite.')
        return {'dry_run': True}

    report = {}
    for name in COLLECTIONS:
        docs = snap.get(name) or []
        db[name].delete_many({})
        if docs:
            db[name].insert_many([dict(d) for d in docs])
        report[name] = len(docs)

    print()
    print('Restore complete. Restart the app now so it re-creates indexes on the fresh data.')
    return {'dry_run': False, 'restored': report}


if __name__ == '__main__':
    confirmed = '--yes' in sys.argv
    result = restore_snapshot(confirmed)
    print(json.dumps(result, indent=2))
