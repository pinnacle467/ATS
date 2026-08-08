"""One-off script: merge live site's mongodump into local MongoDB.
Policy: upsert live docs by their business key (id/key/_id). Existing local docs
matching that key are OVERWRITTEN with the live version. Local-only docs (no
matching key in live dump) are left untouched. Run once, then delete.
"""
import os
import sys
import bson
from pymongo import MongoClient, ReplaceOne
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

DUMP_DIR = '/app/backend/live_sync/ats_dump/sprout_ats'

client = MongoClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

# collection -> key field used to match/overwrite existing docs
KEY_FIELD = {
    'users': 'id',
    'jobs': 'id',
    'candidates': 'id',
    'interviews': 'id',
    'notes': 'id',
    'activities': 'id',
    'scorecards': 'id',
    'departments': 'id',
    'tags': 'id',
    'interview_kits': 'id',
    'audit_log': 'id',
    'files': 'id',
    'notifications': 'id',
    'password_resets': 'id',
    'analytics_events': 'id',
    'settings': 'key',
    'career_settings': 'key',
    'career_pages': 'key',
    'email_templates': 'key',
    'counters': '_id',
    'applications': 'id',
    'import_sessions': 'id',
}


def load_bson(name):
    path = os.path.join(DUMP_DIR, f'{name}.bson')
    if not os.path.exists(path):
        return []
    with open(path, 'rb') as f:
        return bson.decode_all(f.read())


summary = {}
for coll_name, key_field in KEY_FIELD.items():
    docs = load_bson(coll_name)
    if not docs:
        summary[coll_name] = {'live_docs': 0, 'inserted': 0, 'updated': 0}
        continue

    coll = db[coll_name]
    ops = []
    inserted = 0
    updated = 0
    for d in docs:
        key_val = d.get(key_field)
        if key_val is None:
            continue
        # Drop the live _id so Mongo assigns a fresh one on insert; matching is by
        # business key_field, not _id (except for `counters`, which uses _id itself).
        doc = dict(d)
        if key_field != '_id':
            doc.pop('_id', None)
            existing = coll.find_one({key_field: key_val}, {'_id': 1})
            if existing:
                doc['_id'] = existing['_id']
                updated += 1
            else:
                inserted += 1
            ops.append(ReplaceOne({key_field: key_val}, doc, upsert=True))
        else:
            existing = coll.find_one({'_id': key_val})
            if existing:
                updated += 1
            else:
                inserted += 1
            ops.append(ReplaceOne({'_id': key_val}, doc, upsert=True))

    if ops:
        coll.bulk_write(ops, ordered=False)
    summary[coll_name] = {'live_docs': len(docs), 'inserted': inserted, 'updated': updated}

for k, v in summary.items():
    print(f"{k:20s} live={v['live_docs']:4d}  inserted={v['inserted']:4d}  updated={v['updated']:4d}")
