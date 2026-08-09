"""Standalone demo-data generator for a SAFE, fully-isolated demo instance.

Unlike seed.py's synthetic fallback (which only runs when no snapshot.json
exists), this script connects directly to a chosen database name and
populates it with a fictional company's hiring pipeline — used to give
prospects/customers a "wow" demo without ever touching real company data.

Run directly: `python3 demo_seed.py <mongo_url> <db_name>`
Safe to re-run: it wipes ONLY the target database first (never the real one),
so re-seeding for a fresh demo is idempotent.
"""
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from auth import hash_password


def new_id():
    import uuid
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def iso(dt):
    return dt.isoformat()


async def seed_demo(mongo_url: str, db_name: str):
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Safety: only ever wipe the explicitly-targeted demo database, never touch anything else.
    for coll in await db.list_collection_names():
        await db[coll].delete_many({})

    now = datetime.now(timezone.utc)

    # ---- Users (demo team — distinct from any real account) ----
    users = [
        {'id': new_id(), 'name': 'Jordan Ellis', 'email': 'demo.admin@pinnacleats.com', 'password_hash': hash_password('Demo@2026'), 'role': 'super_admin', 'title': 'Head of Talent', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'Priya Nair', 'email': 'demo.recruiter@pinnacleats.com', 'password_hash': hash_password('Demo@2026'), 'role': 'admin', 'title': 'Senior Recruiter', 'active': True, 'last_login': None, 'created_at': now_iso()},
        {'id': new_id(), 'name': 'Wes Carter', 'email': 'demo.interviewer@pinnacleats.com', 'password_hash': hash_password('Demo@2026'), 'role': 'interview_panel', 'title': 'Engineering Manager', 'active': True, 'last_login': None, 'created_at': now_iso()},
    ]
    await db.users.insert_many(users)
    admin, recruiter, interviewer = users

    # ---- Pipeline settings ----
    stages = [
        {'name': 'Applied', 'scorecard_attributes': []},
        {'name': 'Screening', 'scorecard_attributes': ['Communication', 'Motivation']},
        {'name': 'Interview', 'scorecard_attributes': ['Communication', 'Technical Skill', 'Problem Solving', 'Culture Fit']},
        {'name': 'Offer', 'scorecard_attributes': []},
        {'name': 'Hired', 'scorecard_attributes': []},
        {'name': 'Rejected', 'scorecard_attributes': []},
    ]
    await db.settings.update_one({'key': 'pipeline_stages'}, {'$set': {'stages': stages}}, upsert=True)

    # ---- Departments & tags ----
    await db.departments.insert_many([{'id': new_id(), 'name': d, 'created_at': now_iso()} for d in ['Engineering', 'Design', 'Product', 'Sales']])
    await db.tags.insert_many([{'id': new_id(), 'name': t, 'created_at': now_iso()} for t in ['strong-fit', 'referral', 'needs-visa', 'senior', 'remote-ok', 'fast-track']])

    # ---- Jobs ----
    stage_names = [s['name'] for s in stages]
    jobs_data = [
        ('Senior Backend Engineer', 'Engineering', 'San Francisco, CA (Hybrid)', 'open', recruiter['id']),
        ('Product Designer', 'Design', 'Remote (US)', 'open', recruiter['id']),
        ('Product Manager', 'Product', 'New York, NY', 'open', admin['id']),
        ('Enterprise Sales Lead', 'Sales', 'Austin, TX', 'on_hold', admin['id']),
    ]
    jobs = []
    for title, dep, loc, status, rid in jobs_data:
        jobs.append({'id': new_id(), 'title': title, 'department': dep, 'location': loc,
                     'description': f'We are hiring a {title} to join our {dep} team.',
                     'stages': stage_names, 'recruiter_id': rid, 'status': status,
                     'created_at': iso(now - timedelta(days=random.randint(20, 60))), 'updated_at': now_iso()})
    await db.jobs.insert_many(jobs)
    backend_job, design_job, pm_job, sales_job = jobs

    # ---- Candidates (with AI-style fit scores + industry tags to showcase both features) ----
    # name, email, title, company, location, job, stage, source, skills, industries, tags, fit, fit_summary, days_ago
    cands_data = [
        ('Sarah Chen', 'sarah.chen@example.com', 'Senior Software Engineer', 'CloudScale Inc.', 'San Francisco, CA', backend_job, 'Interview', 'referral',
         ['Python', 'Go', 'FastAPI', 'PostgreSQL', 'Kubernetes'], ['SaaS', 'IT / Software'], ['strong-fit', 'referral'],
         92, 'Excellent match — deep backend + distributed systems experience directly aligned with the role.', 18),
        ('Miguel Torres', 'miguel.torres@example.io', 'Lead Product Designer', 'Brightpath Studio', 'Austin, TX', design_job, 'Screening', 'job_board',
         ['Figma', 'Sketch', 'Prototyping', 'User Research'], ['Media & Entertainment', 'Consulting'], ['senior'],
         78, 'Strong design portfolio; less direct B2B SaaS experience than ideal.', 10),
        ('Priya Patel', 'priya.patel@example.org', 'Engineering Manager', 'FinEdge Technologies', 'Chicago, IL', backend_job, 'Offer', 'linkedin',
         ['Java', 'Spring Boot', 'Microservices', 'Kafka'], ['FinTech', 'Banking / BFSI'], ['fast-track'],
         95, 'Outstanding leadership + fintech domain depth. Top candidate for this pipeline.', 35),
        ('James Okafor', 'james.okafor@example.com', 'Product Manager', 'RetailHub', 'New York, NY', pm_job, 'Interview', 'career_site',
         ['Roadmapping', 'SQL', 'A/B Testing'], ['Retail', 'E-commerce'], ['remote-ok'],
         84, 'Solid product instincts with strong retail/e-commerce domain context.', 14),
        ('Emily Zhang', 'emily.zhang@example.com', 'Backend Engineer', 'Streamline AI', 'Palo Alto, CA', backend_job, 'Screening', 'job_board',
         ['Python', 'Django', 'AWS', 'Redis'], ['SaaS', 'IT / Software'], [],
         71, 'Good technical fundamentals; earlier-career, may need ramp-up time on scale.', 7),
        ('Carlos Mendez', 'carlos.mendez@example.com', 'Account Executive', 'SalesForce Pro', 'Austin, TX', sales_job, 'Applied', 'career_site',
         ['Negotiation', 'CRM', 'Outbound'], ['SaaS'], [],
         66, 'Decent outbound track record; limited enterprise deal-size experience so far.', 5),
        ('Aisha Rahman', 'aisha.rahman@example.com', 'UX Designer', 'Northwind Apps', 'Seattle, WA', design_job, 'Interview', 'referral',
         ['Figma', 'Design Systems', 'Accessibility'], ['IT / Software'], ['referral'],
         88, 'Strong systems-thinking designer with accessibility expertise — great culture fit signal from referral.', 21),
        ('Tom Bradley', 'tom.bradley@example.com', 'Software Engineer', 'MountainTech', 'Denver, CO', backend_job, 'Applied', 'job_board',
         ['Node.js', 'TypeScript', 'MongoDB'], ['IT / Software'], [],
         58, 'Junior-to-mid level profile; role calls for more seniority than shown.', 3),
        ('Nina Kowalski', 'nina.kowalski@example.com', 'Senior PM', 'GrowthLabs', 'Chicago, IL', pm_job, 'Screening', 'linkedin',
         ['Analytics', 'Agile', 'Stakeholder Management'], ['SaaS', 'Consulting'], ['senior'],
         81, 'Strong analytical PM background across multiple SaaS launches.', 9),
        ('Robert Ellis', 'robert.ellis@example.com', 'Full-stack Developer', 'WebWorks', 'Brooklyn, NY', backend_job, 'Rejected', 'career_site',
         ['React', 'Node.js', 'GraphQL'], ['IT / Software'], [],
         48, 'Frontend-leaning profile; gaps in backend depth required for this role.', 28),
        ('Grace Liu', 'grace.liu@example.com', 'Frontend Engineer', 'PixelPerfect', 'San Jose, CA', backend_job, 'Hired', 'referral',
         ['React', 'TypeScript', 'CSS', 'Testing'], ['IT / Software'], ['referral', 'strong-fit'],
         90, 'Excellent frontend craftsmanship, strong referral signal, hired.', 55),
        ('Omar Hassan', 'omar.hassan@example.com', 'Data Engineer', 'DataFlow Systems', 'Boston, MA', backend_job, 'Applied', 'linkedin',
         ['Python', 'Spark', 'Airflow', 'Snowflake'], ['IT / Software', 'Healthcare'], ['needs-visa'],
         86, 'Strong data pipeline experience across healthcare-adjacent datasets.', 2),
        ('Lucia Fernandez', 'lucia.fernandez@example.com', 'Product Designer', 'Sunshine Digital', 'Miami, FL', design_job, 'Applied', 'career_site',
         ['UI Design', 'Illustration', 'Webflow'], ['Media & Entertainment', 'E-commerce'], [],
         63, 'Good visual craft; limited enterprise product design exposure.', 1),
        ('Kevin Park', 'kevin.park@example.com', 'Sales Manager', 'CloudSell', 'Bellevue, WA', sales_job, 'Screening', 'referral',
         ['Enterprise Sales', 'Pipeline Management'], ['SaaS'], ['referral'],
         79, 'Proven enterprise SaaS sales management background.', 12),
        ('Marcus Johnson', 'marcus.johnson@example.com', 'DevOps Engineer', 'InfraCore', 'Oakland, CA', backend_job, 'Hired', 'linkedin',
         ['Terraform', 'Kubernetes', 'CI/CD', 'AWS'], ['IT / Software', 'Telecom'], [],
         93, 'Exceptional infra automation background across telecom-scale systems. Hired.', 70),
    ]
    candidates = []
    for idx, (name, email, title, company, loc, job, stage, source, skills, industries, tags, fit, fit_summary, days_ago) in enumerate(cands_data):
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
        candidates.append({
            'id': new_id(), 'name': name, 'email': email, 'phone': f'(415) 555-{1000+idx:04d}', 'current_title': title,
            'current_company': company, 'location': loc,
            'experience': [{'company': company, 'title': title, 'start_date': '2021', 'end_date': 'Present', 'description': None}],
            'education': [{'school': 'State University', 'degree': 'B.S.', 'start_date': '2013', 'end_date': '2017'}],
            'skills': skills, 'industry': industries, 'industry_source': 'auto',
            'job_id': job['id'], 'stage': stage, 'source': source, 'recruiter_id': job['recruiter_id'],
            'tags': tags, 'resume_file_id': None, 'low_confidence_fields': [],
            'notice_period': ['Immediate', '15 days', '30 days', '2 weeks'][idx % 4],
            'fit_score': fit, 'fit_score_summary': fit_summary,
            'status': status, 'rejection_reason': rejection_reason, 'applied_at': iso(applied), 'hired_at': hired_at,
            'created_at': iso(applied), 'updated_at': now_iso(),
        })
    await db.candidates.insert_many(candidates)
    cand_by_name = {c['name']: c for c in candidates}

    # ---- Interviews ----
    def upcoming(day_offset, hour):
        return iso((now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0))

    interviews = [
        {'id': new_id(), 'candidate_id': cand_by_name['Sarah Chen']['id'], 'job_id': backend_job['id'], 'stage': 'Interview', 'type': 'technical', 'interviewer_ids': [interviewer['id']], 'scheduled_at': upcoming(1, 14), 'duration_min': 60, 'location': None, 'video_link': 'https://meet.example.com/sarah-tech', 'notes': None, 'status': 'scheduled', 'created_by': recruiter['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['James Okafor']['id'], 'job_id': pm_job['id'], 'stage': 'Interview', 'type': 'panel', 'interviewer_ids': [interviewer['id']], 'scheduled_at': upcoming(2, 10), 'duration_min': 90, 'location': 'HQ Conference Room B', 'video_link': None, 'notes': None, 'status': 'scheduled', 'created_by': admin['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['Aisha Rahman']['id'], 'job_id': design_job['id'], 'stage': 'Interview', 'type': 'onsite', 'interviewer_ids': [interviewer['id']], 'scheduled_at': upcoming(3, 13), 'duration_min': 120, 'location': 'HQ Design Studio', 'video_link': None, 'notes': None, 'status': 'scheduled', 'created_by': recruiter['id'], 'created_at': now_iso()},
        {'id': new_id(), 'candidate_id': cand_by_name['Priya Patel']['id'], 'job_id': backend_job['id'], 'stage': 'Interview', 'type': 'technical', 'interviewer_ids': [interviewer['id']], 'scheduled_at': iso(now - timedelta(days=5)), 'duration_min': 60, 'location': None, 'video_link': 'https://meet.example.com/priya-tech', 'notes': None, 'status': 'feedback_submitted', 'created_by': recruiter['id'], 'created_at': iso(now - timedelta(days=8))},
    ]
    await db.interviews.insert_many(interviews)

    await db.scorecards.insert_one({
        'id': new_id(), 'interview_id': interviews[3]['id'], 'candidate_id': cand_by_name['Priya Patel']['id'],
        'interviewer_id': interviewer['id'], 'interviewer_name': interviewer['name'],
        'ratings': {'Communication': 5, 'Technical Skill': 4, 'Problem Solving': 5, 'Culture Fit': 4},
        'overall': 5, 'recommendation': 'strong_yes',
        'notes': 'Excellent systems design depth. Clear communicator. Strong hire.',
        'submitted_at': iso(now - timedelta(days=4)),
    })

    await db.interview_kits.insert_many([
        {'id': new_id(), 'stage': 'Screening', 'title': 'Phone Screen Guide', 'questions': ['Walk me through your background', 'Why are you interested in this role?', 'What are your compensation expectations?'], 'guidelines': 'Keep it to 30 minutes. Assess motivation and communication.', 'created_at': now_iso()},
        {'id': new_id(), 'stage': 'Interview', 'title': 'Technical Interview Kit', 'questions': ['Design a URL shortener at scale', 'Describe a hard production bug you fixed', 'Live coding: rate limiter implementation'], 'guidelines': 'Focus on problem solving process, not just the final answer.', 'created_at': now_iso()},
    ])

    acts = [
        (recruiter, 'application', 'added candidate Lucia Fernandez', cand_by_name['Lucia Fernandez']['id'], design_job['id'], 1),
        (recruiter, 'stage_change', 'moved Sarah Chen from Screening to Interview', cand_by_name['Sarah Chen']['id'], backend_job['id'], 2),
        (interviewer, 'feedback_submitted', 'submitted feedback for Priya Patel', cand_by_name['Priya Patel']['id'], backend_job['id'], 4),
        (recruiter, 'stage_change', 'moved Priya Patel from Interview to Offer', cand_by_name['Priya Patel']['id'], backend_job['id'], 3),
        (admin, 'interview_scheduled', 'scheduled a panel interview for James Okafor', cand_by_name['James Okafor']['id'], pm_job['id'], 2),
        (recruiter, 'stage_change', 'moved Grace Liu from Offer to Hired', cand_by_name['Grace Liu']['id'], backend_job['id'], 15),
    ]
    await db.activities.insert_many([
        {'id': new_id(), 'type': t, 'actor_id': a['id'], 'actor_name': a['name'], 'candidate_id': cid, 'job_id': jid,
         'message': msg, 'created_at': iso(now - timedelta(days=d, hours=random.randint(0, 8)))}
        for a, t, msg, cid, jid, d in acts
    ])

    await db.notes.insert_many([
        {'id': new_id(), 'candidate_id': cand_by_name['Sarah Chen']['id'], 'author_id': recruiter['id'], 'author_name': recruiter['name'], 'text': 'Referred by a former colleague. Very strong distributed systems background.', 'note_type': 'note', 'created_at': iso(now - timedelta(days=10))},
        {'id': new_id(), 'candidate_id': cand_by_name['Priya Patel']['id'], 'author_id': recruiter['id'], 'author_name': recruiter['name'], 'text': 'Sent offer details via email. Awaiting response by Friday.', 'note_type': 'email_log', 'created_at': iso(now - timedelta(days=2))},
    ])

    # ---- Indexes (mirrors seed.py so the demo behaves identically to production) ----
    await db.candidates.create_index('job_id')
    await db.candidates.create_index('stage')
    await db.candidates.create_index('email')
    await db.candidates.create_index('industry', name='industry_lookup')
    await db.interviews.create_index('scheduled_at')
    await db.interviews.create_index('interviewer_ids')
    await db.notifications.create_index('user_id')
    await db.activities.create_index('created_at')

    print(f'Demo data seeded into {db_name}: users={len(users)} jobs={len(jobs)} candidates={len(candidates)} interviews={len(interviews)}')
    client.close()


if __name__ == '__main__':
    mongo_url = sys.argv[1] if len(sys.argv) > 1 else 'mongodb://localhost:27017'
    db_name = sys.argv[2] if len(sys.argv) > 2 else 'sprout_ats_demo'
    asyncio.run(seed_demo(mongo_url, db_name))
