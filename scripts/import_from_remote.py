"""One-off importer: pulls real data from the connected remote ATS build
(https://job-importer.preview.emergentagent.com) via its API and stores it
both in the local MongoDB and as a JSON snapshot (backend/data_seed/snapshot.json)
so future fresh imports/restarts restore this real data instead of synthetic demo data."""
import base64
import json
import sys

import requests

REMOTE = 'https://job-importer.preview.emergentagent.com/api'
ADMIN_EMAIL = 'admin@ats.com'
ADMIN_PASSWORD = 'Admin@123'

sys.path.insert(0, '/app/backend')
from pymongo import MongoClient  # noqa: E402
import os  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv('/app/backend/.env')
mongo = MongoClient(os.environ['MONGO_URL'])
db = mongo[os.environ['DB_NAME']]


def login():
    r = requests.post(f'{REMOTE}/auth/login', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD})
    r.raise_for_status()
    return r.json()['token']


def get(session, path, params=None):
    r = session.get(f'{REMOTE}{path}', params=params)
    r.raise_for_status()
    return r.json()


def main():
    token = login()
    s = requests.Session()
    s.headers['Authorization'] = f'Bearer {token}'

    users = get(s, '/users')
    jobs = get(s, '/jobs')
    departments = get(s, '/departments')
    tags = get(s, '/tags')
    pipeline = get(s, '/settings/pipeline')
    kits = get(s, '/interview-kits')

    candidates = []
    page = 1
    while True:
        data = get(s, '/candidates', {'page': page, 'limit': 500})
        items = data['items']
        for c in items:
            c.pop('job_title', None)
            c.pop('recruiter_name', None)
        candidates.extend(items)
        if len(candidates) >= data['total'] or not items:
            break
        page += 1

    interviews = get(s, '/interviews')
    for iv in interviews:
        iv.pop('candidate_name', None)
        iv.pop('job_title', None)
        iv.pop('interviewer_names', None)
        iv.pop('scorecards_submitted', None)

    notes, activities, scorecards = [], [], []
    for c in candidates:
        events = get(s, f"/candidates/{c['id']}/timeline")
        for e in events:
            kind = e.pop('kind')
            (notes if kind == 'note' else activities).append(e)
    for iv in interviews:
        scs = get(s, f"/interviews/{iv['id']}/scorecards")
        scorecards.extend(scs)

    availability = []
    for u in users:
        availability.extend(get(s, f"/availability/{u['id']}"))

    audit_log = get(s, '/audit-log', {'limit': 500})

    files = {}
    resume_ids = {c['resume_file_id'] for c in candidates if c.get('resume_file_id')}
    for fid in resume_ids:
        r = s.get(f'{REMOTE}/files/{fid}')
        r.raise_for_status()
        cd = r.headers.get('content-disposition', '')
        filename = cd.split('filename="')[1].rstrip('"') if 'filename="' in cd else fid
        files[fid] = {
            'id': fid,
            'filename': filename,
            'content_type': r.headers.get('content-type', 'application/octet-stream'),
            'size': len(r.content),
            'data_b64': base64.b64encode(r.content).decode(),
        }

    # Preserve local demo password hashes for any matching seeded emails (API never exposes hashes)
    local_users_by_email = {u['email']: u for u in db.users.find({}, {'_id': 0})}
    for u in users:
        local = local_users_by_email.get(u['email'])
        u['password_hash'] = local['password_hash'] if local else _default_hash()

    snapshot = {
        'users': users, 'jobs': jobs, 'candidates': candidates, 'interviews': interviews,
        'notes': notes, 'activities': activities, 'scorecards': scorecards,
        'departments': departments, 'tags': tags, 'pipeline': pipeline, 'interview_kits': kits,
        'availability': availability, 'audit_log': audit_log, 'files': list(files.values()),
    }

    with open('/app/backend/data_seed/snapshot.json', 'w') as f:
        json.dump(snapshot, f)

    collections = {
        'users': [dict(d) for d in users], 'jobs': [dict(d) for d in jobs],
        'candidates': [dict(d) for d in candidates], 'interviews': [dict(d) for d in interviews],
        'notes': [dict(d) for d in notes], 'activities': [dict(d) for d in activities],
        'scorecards': [dict(d) for d in scorecards],
        'departments': [dict(d) for d in departments], 'tags': [dict(d) for d in tags],
        'interview_kits': [dict(d) for d in kits],
        'availability': [dict(d) for d in availability], 'audit_log': [dict(d) for d in audit_log],
        'files': [dict(d) for d in files.values()],
    }
    for name, docs in collections.items():
        db[name].delete_many({})
        if docs:
            db[name].insert_many(docs)
    db.settings.update_one({'key': 'pipeline_stages'}, {'$set': {'stages': pipeline['stages']}}, upsert=True)
    db.notifications.delete_many({})
    db.import_sessions.delete_many({})

    print(f"Imported: {len(users)} users, {len(jobs)} jobs, {len(candidates)} candidates, "
          f"{len(interviews)} interviews, {len(notes)} notes, {len(activities)} activities, "
          f"{len(scorecards)} scorecards, {len(files)} files, {len(audit_log)} audit entries.")
    print("New users (no known password) set to temp password 'Imported@123':")
    for u in users:
        if u['email'] not in local_users_by_email:
            print(f"  - {u['email']}")


def _default_hash():
    from auth import hash_password
    return hash_password('Imported@123')


if __name__ == '__main__':
    main()
