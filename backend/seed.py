"""Data seeder — runs on startup when the users collection is empty.
Restores the real imported snapshot (backend/data_seed/snapshot.json) when present,
so real data persists across fresh imports/restarts. Falls back to synthetic demo
data only when no snapshot has been captured yet."""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auth import hash_password
from database import db
from utils import new_id, now_iso

SNAPSHOT_PATH = Path(__file__).parent / 'data_seed' / 'snapshot.json'


def iso(dt):
    return dt.isoformat()


async def _restore_snapshot() -> bool:
    if not SNAPSHOT_PATH.exists():
        return False
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    collections = ['users', 'jobs', 'candidates', 'interviews', 'notes', 'activities',
                   'scorecards', 'departments', 'tags', 'interview_kits', 'availability', 'audit_log', 'files', 'counters',
                   'career_settings', 'applications']
    for name in collections:
        docs = snap.get(name) or []
        if docs:
            await db[name].insert_many([dict(d) for d in docs])
    pipeline = snap.get('pipeline')
    if pipeline:
        await db.settings.update_one({'key': 'pipeline_stages'}, {'$set': {'stages': pipeline['stages']}}, upsert=True)
    await db.candidates.create_index('job_id')
    await db.candidates.create_index('stage')
    await db.candidates.create_index('email')
    await db.interviews.create_index('scheduled_at')
    await db.interviews.create_index('interviewer_ids')
    await db.notifications.create_index('user_id')
    await db.activities.create_index('created_at')
    return True


async def seed_if_empty():
    if await db.users.count_documents({}) > 0:
        return False
    if await _restore_snapshot():
        return True
    now = datetime.now(timezone.utc)

    # ---- Users ----
    users = [
        {'id': new_id(), 'name': 'Abhijeet Kang', 'email': 'admin@ats.com', 'password_hash': hash_password('Admin@123'), 'role': 'admin', 'title': 'Head of Talent', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'Rachel Kim', 'email': 'recruiter@ats.com', 'password_hash': hash_password('Recruit@123'), 'role': 'recruiter', 'title': 'Senior Recruiter', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'David Lee', 'email': 'interviewer@ats.com', 'password_hash': hash_password('Interview@123'), 'role': 'interviewer', 'title': 'Engineering Manager', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'Jane Foster', 'email': 'jane@ats.com', 'password_hash': hash_password('Jane@123'), 'role': 'recruiter', 'title': 'Recruiter', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'Sam Rivera', 'email': 'sam@ats.com', 'password_hash': hash_password('Sam@123'), 'role': 'interviewer', 'title': 'Staff Engineer', 'active': True, 'last_login': None, 'created_at': now_iso()},
    ]
    await db.users.insert_many(users)
    admin, rachel, david, jane, sam = users

    # ---- Pipeline settings ----
    default_attrs = ['Communication', 'Technical Skill', 'Problem Solving', 'Culture Fit']
    stages = [
        {'name': 'Applied', 'scorecard_attributes': []},
        {'name': 'Screening', 'scorecard_attributes': ['Communication', 'Motivation']},
        {'name': 'Interview', 'scorecard_attributes': default_attrs},
        {'name': 'Offer', 'scorecard_attributes': []},
        {'name': 'Hired', 'scorecard_attributes': []},
        {'name': 'Rejected', 'scorecard_attributes': []},
    ]
    await db.settings.update_one({'key': 'pipeline_stages'}, {'$set': {'stages': stages}}, upsert=True)

    # ---- Departments & tags ----
    deps = ['Engineering', 'Design', 'Product', 'Sales']
    await db.departments.insert_many([{'id': new_id(), 'name': d, 'created_at': now_iso()} for d in deps])
    tag_names = ['strong-fit', 'referral', 'needs-visa', 'senior', 'remote-ok', 'fast-track']
    await db.tags.insert_many([{'id': new_id(), 'name': t, 'created_at': now_iso()} for t in tag_names])

    # ---- Jobs ----
    stage_names = [s['name'] for s in stages]
    jobs_data = [
        ('Senior Backend Engineer', 'Engineering', 'San Francisco, CA (Hybrid)', 'open', rachel['id']),
        ('Product Designer', 'Design', 'Remote (US)', 'open', rachel['id']),
        ('Product Manager', 'Product', 'New York, NY', 'open', jane['id']),
        ('Sales Lead', 'Sales', 'Austin, TX', 'on_hold', jane['id']),
        ('Frontend Engineer', 'Engineering', 'Remote (US)', 'closed', rachel['id']),
    ]
    jobs = []
    for title, dep, loc, status, rid in jobs_data:
        jobs.append({'id': new_id(), 'title': title, 'department': dep, 'location': loc,
                     'description': f'We are hiring a {title} to join our {dep} team.',
                     'stages': stage_names, 'recruiter_id': rid, 'status': status,
                     'created_at': iso(now - timedelta(days=random.randint(20, 60))), 'updated_at': now_iso()})
    await db.jobs.insert_many(jobs)
    backend_job, design_job, pm_job, sales_job, fe_job = jobs

    # ---- Candidates ----
    notice_periods = ['Immediate', '15 days', '30 days', '30 days', '60 days', '2 weeks', '1 month', '90 days', 'Immediate', None]
    cands_data = [
        # name, email, phone, title, company, location, job, stage, source, skills, tags, days_ago
        ('Sarah Chen', 'sarah.chen@example.com', '(415) 555-0192', 'Senior Software Engineer', 'CloudScale Inc.', 'San Francisco, CA', backend_job, 'Interview', 'referral', ['Python', 'Go', 'FastAPI', 'PostgreSQL', 'Kubernetes'], ['strong-fit', 'referral'], 18),
        ('Miguel Torres', 'miguel.torres@example.io', None, 'Lead Product Designer', 'Brightpath Studio', 'Austin, TX', design_job, 'Screening', 'job_board', ['Figma', 'Sketch', 'Prototyping', 'User Research'], ['senior'], 10),
        ('Priya Patel', 'priya.patel@example.org', '+1-312-555-0147', 'Engineering Manager', 'FinEdge Technologies', 'Chicago, IL', backend_job, 'Offer', 'linkedin', ['Java', 'Spring Boot', 'Microservices', 'Kafka'], ['fast-track'], 35),
        ('James Okafor', 'james.okafor@example.com', '(212) 555-0135', 'Product Manager', 'RetailHub', 'New York, NY', pm_job, 'Interview', 'career_site', ['Roadmapping', 'SQL', 'A/B Testing'], ['remote-ok'], 14),
        ('Emily Zhang', 'emily.zhang@example.com', '(650) 555-0110', 'Backend Engineer', 'Streamline AI', 'Palo Alto, CA', backend_job, 'Screening', 'job_board', ['Python', 'Django', 'AWS', 'Redis'], [], 7),
        ('Carlos Mendez', 'carlos.mendez@example.com', '(512) 555-0166', 'Account Executive', 'SalesForce Pro', 'Austin, TX', sales_job, 'Applied', 'career_site', ['Negotiation', 'CRM', 'Outbound'], [], 5),
        ('Aisha Rahman', 'aisha.rahman@example.com', '(206) 555-0170', 'UX Designer', 'Northwind Apps', 'Seattle, WA', design_job, 'Interview', 'referral', ['Figma', 'Design Systems', 'Accessibility'], ['referral'], 21),
        ('Tom Bradley', 'tom.bradley@example.com', '(303) 555-0122', 'Software Engineer', 'MountainTech', 'Denver, CO', backend_job, 'Applied', 'job_board', ['Node.js', 'TypeScript', 'MongoDB'], [], 3),
        ('Nina Kowalski', 'nina.kowalski@example.com', '(773) 555-0189', 'Senior PM', 'GrowthLabs', 'Chicago, IL', pm_job, 'Screening', 'linkedin', ['Analytics', 'Agile', 'Stakeholder Management'], ['senior'], 9),
        ('Robert Ellis', 'robert.ellis@example.com', '(917) 555-0154', 'Full-stack Developer', 'WebWorks', 'Brooklyn, NY', backend_job, 'Rejected', 'career_site', ['React', 'Node.js', 'GraphQL'], [], 28),
        ('Grace Liu', 'grace.liu@example.com', '(408) 555-0198', 'Frontend Engineer', 'PixelPerfect', 'San Jose, CA', fe_job, 'Hired', 'referral', ['React', 'TypeScript', 'CSS', 'Testing'], ['referral', 'strong-fit'], 55),
        ('Omar Hassan', 'omar.hassan@example.com', None, 'Data Engineer', 'DataFlow Systems', 'Boston, MA', backend_job, 'Applied', 'linkedin', ['Python', 'Spark', 'Airflow', 'Snowflake'], ['needs-visa'], 2),
        ('Lucia Fernandez', 'lucia.fernandez@example.com', '(305) 555-0143', 'Product Designer', 'Sunshine Digital', 'Miami, FL', design_job, 'Applied', 'career_site', ['UI Design', 'Illustration', 'Webflow'], [], 1),
        ('Kevin Park', 'kevin.park@example.com', '(425) 555-0177', 'Sales Manager', 'CloudSell', 'Bellevue, WA', sales_job, 'Screening', 'referral', ['Enterprise Sales', 'Pipeline Management'], ['referral'], 12),
        ('Hannah Weber', 'hannah.weber@example.com', '(646) 555-0161', 'Associate PM', 'StartupXYZ', 'New York, NY', pm_job, 'Applied', 'job_board', ['User Stories', 'Jira', 'Data Analysis'], [], 4),
        ('Marcus Johnson', 'marcus.johnson@example.com', '(510) 555-0130', 'DevOps Engineer', 'InfraCore', 'Oakland, CA', backend_job, 'Hired', 'linkedin', ['Terraform', 'Kubernetes', 'CI/CD', 'AWS'], [], 70),
    ]
    candidates = []
    for idx, (name, email, phone, title, company, loc, job, stage, source, skills, tags, days_ago) in enumerate(cands_data):
        applied = now - timedelta(days=days_ago)
        status = 'active'
        hired_at = None
        rejection_reason = None
        if stage == 'Hired':
            status = 'hired'
            hired_at = iso(applied + timedelta(days=random.randint(20, 40)))
        elif stage == 'Rejected':
            status = 'rejected'
            rejection_reason = 'Not a technical fit for the role'
        rec_id = job['recruiter_id']
        candidates.append({
            'id': new_id(), 'name': name, 'email': email, 'phone': phone, 'current_title': title,
            'current_company': company, 'location': loc,
            'experience': [{'company': company, 'title': title, 'start_date': '2021', 'end_date': 'Present', 'description': None}],
            'education': [{'school': 'State University', 'degree': 'B.S.', 'start_date': '2013', 'end_date': '2017'}],
            'skills': skills, 'job_id': job['id'], 'stage': stage, 'source': source, 'recruiter_id': rec_id,
            'tags': tags, 'resume_file_id': None, 'low_confidence_fields': ['phone'] if phone is None else [],
            'notice_period': notice_periods[idx % len(notice_periods)],
            'status': status, 'rejection_reason': rejection_reason, 'applied_at': iso(applied), 'hired_at': hired_at,
            'created_at': iso(applied), 'updated_at': now_iso(),
        })
    await db.candidates.insert_many(candidates)
    cand_by_name = {c['name']: c for c in candidates}

    # ---- Interviews (this week + past) ----
    def upcoming(day_offset, hour):
        return iso((now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0))

    interviews = [
        {'id': new_id(), 'candidate_id': cand_by_name['Sarah Chen']['id'], 'job_id': backend_job['id'], 'stage': 'Interview', 'type': 'technical', 'interviewer_ids': [david['id']], 'scheduled_at': upcoming(1, 14), 'duration_min': 60, 'location': None, 'video_link': 'https://meet.example.com/sarah-tech', 'notes': None, 'status': 'scheduled', 'created_by': rachel['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['James Okafor']['id'], 'job_id': pm_job['id'], 'stage': 'Interview', 'type': 'panel', 'interviewer_ids': [david['id'], sam['id']], 'scheduled_at': upcoming(2, 10), 'duration_min': 90, 'location': 'HQ Conference Room B', 'video_link': None, 'notes': None, 'status': 'scheduled', 'created_by': jane['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['Aisha Rahman']['id'], 'job_id': design_job['id'], 'stage': 'Interview', 'type': 'onsite', 'interviewer_ids': [sam['id']], 'scheduled_at': upcoming(3, 13), 'duration_min': 120, 'location': 'HQ Design Studio', 'video_link': None, 'notes': None, 'status': 'scheduled', 'created_by': rachel['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['Miguel Torres']['id'], 'job_id': design_job['id'], 'stage': 'Screening', 'type': 'phone_screen', 'interviewer_ids': [david['id']], 'scheduled_at': iso(now - timedelta(days=1, hours=2)), 'duration_min': 30, 'location': None, 'video_link': 'https://meet.example.com/miguel-screen', 'notes': None, 'status': 'feedback_pending', 'created_by': rachel['id'], 'created_at': iso(now - timedelta(days=3))},
        {'id': new_id(), 'candidate_id': cand_by_name['Priya Patel']['id'], 'job_id': backend_job['id'], 'stage': 'Interview', 'type': 'technical', 'interviewer_ids': [david['id']], 'scheduled_at': iso(now - timedelta(days=5)), 'duration_min': 60, 'location': None, 'video_link': 'https://meet.example.com/priya-tech', 'notes': None, 'status': 'feedback_submitted', 'created_by': rachel['id'], 'created_at': iso(now - timedelta(days=8))},
        {'id': new_id(), 'candidate_id': cand_by_name['Emily Zhang']['id'], 'job_id': backend_job['id'], 'stage': 'Screening', 'type': 'phone_screen', 'interviewer_ids': [sam['id']], 'scheduled_at': upcoming(4, 11), 'duration_min': 30, 'location': None, 'video_link': 'https://meet.example.com/emily-screen', 'notes': None, 'status': 'scheduled', 'created_by': rachel['id'], 'created_at': now_iso()},
    ]
    await db.interviews.insert_many(interviews)

    # ---- Scorecard for Priya's completed interview ----
    await db.scorecards.insert_one({
        'id': new_id(), 'interview_id': interviews[4]['id'], 'candidate_id': cand_by_name['Priya Patel']['id'],
        'interviewer_id': david['id'], 'interviewer_name': david['name'],
        'ratings': {'Communication': 5, 'Technical Skill': 4, 'Problem Solving': 5, 'Culture Fit': 4},
        'overall': 5, 'recommendation': 'strong_yes',
        'notes': 'Excellent systems design depth. Clear communicator. Strong hire.',
        'submitted_at': iso(now - timedelta(days=4)),
    })

    # ---- Availability for interviewers (Mon-Fri 9-17) ----
    avail = []
    for u in (david, sam):
        for dow in range(5):
            avail.append({'id': new_id(), 'user_id': u['id'], 'day_of_week': dow, 'start_time': '09:00', 'end_time': '17:00', 'created_at': now_iso()})
    await db.availability.insert_many(avail)

    # ---- Interview kits ----
    await db.interview_kits.insert_many([
        {'id': new_id(), 'stage': 'Screening', 'title': 'Phone Screen Guide', 'questions': ['Walk me through your background', 'Why are you interested in this role?', 'What are your compensation expectations?'], 'guidelines': 'Keep it to 30 minutes. Assess motivation and communication.', 'created_at': now_iso()},
        {'id': new_id(), 'stage': 'Interview', 'title': 'Technical Interview Kit', 'questions': ['Design a URL shortener at scale', 'Describe a hard production bug you fixed', 'Live coding: rate limiter implementation'], 'guidelines': 'Focus on problem solving process, not just the final answer. Leave 10 min for candidate questions.', 'created_at': now_iso()},
    ])

    # ---- Activities ----
    acts = [
        (rachel, 'application', 'added candidate Lucia Fernandez', cand_by_name['Lucia Fernandez']['id'], design_job['id'], 1),
        (rachel, 'stage_change', 'moved Sarah Chen from Screening to Interview', cand_by_name['Sarah Chen']['id'], backend_job['id'], 2),
        (david, 'feedback_submitted', 'submitted feedback for Priya Patel', cand_by_name['Priya Patel']['id'], backend_job['id'], 4),
        (rachel, 'stage_change', 'moved Priya Patel from Interview to Offer', cand_by_name['Priya Patel']['id'], backend_job['id'], 3),
        (jane, 'interview_scheduled', 'scheduled a panel interview for James Okafor', cand_by_name['James Okafor']['id'], pm_job['id'], 2),
        (rachel, 'stage_change', 'moved Grace Liu from Offer to Hired', cand_by_name['Grace Liu']['id'], fe_job['id'], 15),
        (rachel, 'note', 'added a note on Miguel Torres', cand_by_name['Miguel Torres']['id'], design_job['id'], 1),
    ]
    await db.activities.insert_many([
        {'id': new_id(), 'type': t, 'actor_id': a['id'], 'actor_name': a['name'], 'candidate_id': cid, 'job_id': jid,
         'message': msg, 'created_at': iso(now - timedelta(days=d, hours=random.randint(0, 8)))}
        for a, t, msg, cid, jid, d in acts
    ])

    # ---- Notes ----
    await db.notes.insert_many([
        {'id': new_id(), 'candidate_id': cand_by_name['Sarah Chen']['id'], 'author_id': rachel['id'], 'author_name': rachel['name'], 'text': 'Referred by Marcus. Very strong distributed systems background.', 'note_type': 'note', 'created_at': iso(now - timedelta(days=10))},
        {'id': new_id(), 'candidate_id': cand_by_name['Priya Patel']['id'], 'author_id': rachel['id'], 'author_name': rachel['name'], 'text': 'Sent offer details via email. Awaiting response by Friday.', 'note_type': 'email_log', 'created_at': iso(now - timedelta(days=2))},
        {'id': new_id(), 'candidate_id': cand_by_name['Miguel Torres']['id'], 'author_id': rachel['id'], 'author_name': rachel['name'], 'text': 'Portfolio is impressive - strong design systems work at Brightpath.', 'note_type': 'note', 'created_at': iso(now - timedelta(days=1))},
    ])

    # ---- Notifications ----
    await db.notifications.insert_many([
        {'id': new_id(), 'user_id': david['id'], 'type': 'interview', 'message': 'You have been assigned a technical interview with Sarah Chen', 'link': '/interviews', 'read': False, 'created_at': iso(now - timedelta(hours=6))},
        {'id': new_id(), 'user_id': david['id'], 'type': 'feedback', 'message': 'Feedback pending for your interview with Miguel Torres', 'link': '/interviews', 'read': False, 'created_at': iso(now - timedelta(hours=20))},
        {'id': new_id(), 'user_id': rachel['id'], 'type': 'offer', 'message': 'Priya Patel moved to Offer stage', 'link': '/candidates', 'read': False, 'created_at': iso(now - timedelta(days=3))},
        {'id': new_id(), 'user_id': sam['id'], 'type': 'interview', 'message': 'You have been assigned a panel interview with James Okafor', 'link': '/interviews', 'read': False, 'created_at': iso(now - timedelta(hours=30))},
    ])

    # ---- Indexes ----
    await db.candidates.create_index('job_id')
    await db.candidates.create_index('stage')
    await db.candidates.create_index('email')
    await db.interviews.create_index('scheduled_at')
    await db.interviews.create_index('interviewer_ids')
    await db.notifications.create_index('user_id')
    await db.activities.create_index('created_at')
    return True
