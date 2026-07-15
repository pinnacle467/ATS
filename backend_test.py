#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Sprout ATS
Tests all endpoints with proper authentication and RBAC
"""
import requests
import sys
import time
from pathlib import Path

# Public endpoint from frontend/.env
BASE_URL = "https://greenhouse-lite.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
CREDENTIALS = {
    'admin': {'email': 'admin@ats.com', 'password': 'Admin@123'},
    'recruiter': {'email': 'recruiter@ats.com', 'password': 'Recruit@123'},
    'interviewer': {'email': 'interviewer@ats.com', 'password': 'Interview@123'},
}

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class ATSTester:
    def __init__(self):
        self.tokens = {}
        self.users = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.critical_failures = []
        
    def log(self, msg, color=Colors.BLUE):
        print(f"{color}{msg}{Colors.END}")
        
    def test(self, name, method, endpoint, expected_status, token=None, data=None, files=None, timeout=10):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        self.tests_run += 1
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                if files:
                    headers.pop('Content-Type', None)
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - Status: {response.status_code}", Colors.GREEN)
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                self.tests_failed += 1
                self.log(f"❌ FAIL - Expected {expected_status}, got {response.status_code}", Colors.RED)
                try:
                    self.log(f"   Response: {response.json()}", Colors.YELLOW)
                except:
                    self.log(f"   Response: {response.text[:200]}", Colors.YELLOW)
                return False, {}
                
        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.log(f"❌ FAIL - Request timeout after {timeout}s", Colors.RED)
            return False, {}
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAIL - Error: {str(e)}", Colors.RED)
            return False, {}
    
    def test_auth(self):
        """Test authentication endpoints"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: AUTHENTICATION", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        # Test login for all 3 demo accounts
        for role, creds in CREDENTIALS.items():
            success, response = self.test(
                f"Login as {role}",
                "POST",
                "/auth/login",
                200,
                data=creds
            )
            if success and 'token' in response:
                self.tokens[role] = response['token']
                self.users[role] = response['user']
                self.log(f"   Token saved for {role}: {response['user']['name']}", Colors.GREEN)
            else:
                self.critical_failures.append(f"Login failed for {role}")
        
        # Test wrong password
        self.test(
            "Login with wrong password",
            "POST",
            "/auth/login",
            401,
            data={'email': 'admin@ats.com', 'password': 'WrongPassword'}
        )
        
        # Test GET /api/auth/me with token
        if 'admin' in self.tokens:
            success, user = self.test(
                "GET /api/auth/me with admin token",
                "GET",
                "/auth/me",
                200,
                token=self.tokens['admin']
            )
            if success:
                self.log(f"   User: {user.get('name')} ({user.get('role')})", Colors.GREEN)
    
    def test_rbac(self):
        """Test Role-Based Access Control"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: RBAC (Role-Based Access Control)", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        # Interviewer should only see assigned candidates (4 vs 16 total)
        if 'interviewer' in self.tokens:
            success, response = self.test(
                "Interviewer GET /api/candidates (should see only assigned)",
                "GET",
                "/candidates",
                200,
                token=self.tokens['interviewer']
            )
            if success:
                count = len(response.get('items', []))
                self.log(f"   Interviewer sees {count} candidates (expected ~4, not all 16)", Colors.YELLOW)
                if count < 10:
                    self.log(f"   ✓ RBAC working - limited visibility", Colors.GREEN)
        
        # Interviewer cannot POST /api/candidates (403)
        if 'interviewer' in self.tokens:
            self.test(
                "Interviewer POST /api/candidates (should be 403)",
                "POST",
                "/candidates",
                403,
                token=self.tokens['interviewer'],
                data={'name': 'Test Candidate', 'job_id': 'test'}
            )
        
        # Recruiter cannot access GET /api/audit-log (403)
        if 'recruiter' in self.tokens:
            self.test(
                "Recruiter GET /api/audit-log (should be 403)",
                "GET",
                "/audit-log",
                403,
                token=self.tokens['recruiter']
            )
    
    def test_resume_parsing(self):
        """Test resume parsing endpoints (LLM-powered, takes 15-60s)"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: RESUME PARSING (AI-powered, may take 15-60s)", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens:
            self.log("⚠️  Skipping - no recruiter token", Colors.YELLOW)
            return
        
        # Test single resume parse
        resume_path = Path('/app/tests/fixtures/resume_sarah_chen.pdf')
        if resume_path.exists():
            with open(resume_path, 'rb') as f:
                success, response = self.test(
                    "POST /api/resumes/parse (Sarah Chen resume)",
                    "POST",
                    "/resumes/parse",
                    200,
                    token=self.tokens['recruiter'],
                    files={'file': ('resume_sarah_chen.pdf', f, 'application/pdf')},
                    timeout=90  # LLM takes time
                )
                if success:
                    parsed = response.get('parsed', {})
                    self.log(f"   Name: {parsed.get('name')}", Colors.GREEN)
                    self.log(f"   Email: {parsed.get('email')}", Colors.GREEN)
                    self.log(f"   Low confidence fields: {response.get('low_confidence_fields', [])}", Colors.YELLOW)
        else:
            self.log(f"⚠️  Resume file not found: {resume_path}", Colors.YELLOW)
        
        # Test bulk resume parse
        resume1 = Path('/app/tests/fixtures/resume_sarah_chen.pdf')
        resume2 = Path('/app/tests/fixtures/resume_miguel_torres.pdf')
        if resume1.exists() and resume2.exists():
            with open(resume1, 'rb') as f1, open(resume2, 'rb') as f2:
                files = [
                    ('files', ('resume_sarah_chen.pdf', f1.read(), 'application/pdf')),
                    ('files', ('resume_miguel_torres.pdf', f2.read(), 'application/pdf'))
                ]
                success, response = self.test(
                    "POST /api/resumes/parse-bulk (2 resumes)",
                    "POST",
                    "/resumes/parse-bulk",
                    200,
                    token=self.tokens['recruiter'],
                    files=files,
                    timeout=120  # Bulk takes longer
                )
                if success:
                    results = response.get('results', [])
                    self.log(f"   Parsed {len(results)} resumes", Colors.GREEN)
                    for r in results:
                        self.log(f"   - {r.get('filename')}: {r.get('status')}", Colors.GREEN)
    
    def test_candidates(self):
        """Test candidates CRUD operations"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: CANDIDATES CRUD", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens:
            self.log("⚠️  Skipping - no recruiter token", Colors.YELLOW)
            return
        
        # Get jobs first for job_id
        success, jobs_response = self.test(
            "GET /api/jobs (to get job_id)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['recruiter']
        )
        if success and isinstance(jobs_response, list) and len(jobs_response) > 0:
            job_id = jobs_response[0].get('id')
        elif success and isinstance(jobs_response, dict):
            job_id = jobs_response.get('items', [{}])[0].get('id') if jobs_response.get('items') else None
        else:
            job_id = None
        
        # Create candidate
        candidate_data = {
            'name': 'Test Candidate API',
            'email': 'testapi@example.com',
            'phone': '+1234567890',
            'current_title': 'Software Engineer',
            'job_id': job_id,
            'source': 'referral',
            'skills': ['Python', 'FastAPI']
        }
        success, candidate = self.test(
            "POST /api/candidates (create)",
            "POST",
            "/candidates",
            200,
            token=self.tokens['recruiter'],
            data=candidate_data
        )
        candidate_id = candidate.get('id') if success else None
        
        if candidate_id:
            # List candidates with filters
            self.test(
                "GET /api/candidates?q=Test",
                "GET",
                "/candidates?q=Test",
                200,
                token=self.tokens['recruiter']
            )
            
            self.test(
                "GET /api/candidates?source=referral",
                "GET",
                "/candidates?source=referral",
                200,
                token=self.tokens['recruiter']
            )
            
            # Move stage
            success, moved = self.test(
                "POST /api/candidates/{id}/move-stage",
                "POST",
                f"/candidates/{candidate_id}/move-stage",
                200,
                token=self.tokens['recruiter'],
                data={'stage': 'Screening'}
            )
            if success:
                self.log(f"   Stage moved to: {moved.get('stage')}", Colors.GREEN)
            
            # Add note
            success, note = self.test(
                "POST /api/candidates/{id}/notes",
                "POST",
                f"/candidates/{candidate_id}/notes",
                200,
                token=self.tokens['recruiter'],
                data={'text': 'Test note from API', 'note_type': 'note'}
            )
            
            # Get timeline
            success, timeline = self.test(
                "GET /api/candidates/{id}/timeline",
                "GET",
                f"/candidates/{candidate_id}/timeline",
                200,
                token=self.tokens['recruiter']
            )
            if success:
                self.log(f"   Timeline events: {len(timeline)}", Colors.GREEN)
            
            # Bulk action - tag
            self.test(
                "POST /api/candidates/bulk-action (tag)",
                "POST",
                "/candidates/bulk-action",
                200,
                token=self.tokens['recruiter'],
                data={
                    'candidate_ids': [candidate_id],
                    'action': 'tag',
                    'tag': 'test-tag'
                }
            )
        
        # CSV export
        self.test(
            "GET /api/candidates/export/csv",
            "GET",
            "/candidates/export/csv",
            200,
            token=self.tokens['recruiter']
        )
    
    def test_jobs(self):
        """Test jobs CRUD operations"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: JOBS CRUD", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'admin' not in self.tokens:
            self.log("⚠️  Skipping - no admin token", Colors.YELLOW)
            return
        
        # Create job with default stages
        job_data = {
            'title': 'Test Backend Engineer',
            'department': 'Engineering',
            'location': 'Remote',
            'description': 'Test job from API',
            'status': 'open'
        }
        success, job = self.test(
            "POST /api/jobs (create with default stages)",
            "POST",
            "/jobs",
            200,
            token=self.tokens['admin'],
            data=job_data
        )
        job_id = job.get('id') if success else None
        
        if job_id:
            # Update status
            self.test(
                "PUT /api/jobs/{id} (update status to on_hold)",
                "PUT",
                f"/jobs/{job_id}",
                200,
                token=self.tokens['admin'],
                data={'status': 'on_hold'}
            )
            
            self.test(
                "PUT /api/jobs/{id} (update status to closed)",
                "PUT",
                f"/jobs/{job_id}",
                200,
                token=self.tokens['admin'],
                data={'status': 'closed'}
            )
    
    def test_interviews(self):
        """Test interview scheduling and scorecards"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: INTERVIEWS", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens or 'interviewer' not in self.tokens:
            self.log("⚠️  Skipping - missing tokens", Colors.YELLOW)
            return
        
        # Get a candidate
        success, cands = self.test(
            "GET /api/candidates (to get candidate_id)",
            "GET",
            "/candidates?limit=1",
            200,
            token=self.tokens['recruiter']
        )
        if success and isinstance(cands, dict) and 'items' in cands and len(cands['items']) > 0:
            candidate_id = cands['items'][0].get('id')
        else:
            candidate_id = None
        interviewer_id = self.users.get('interviewer', {}).get('id')
        
        if candidate_id and interviewer_id:
            # Create interview
            interview_data = {
                'candidate_id': candidate_id,
                'type': 'phone_screen',
                'interviewer_ids': [interviewer_id],
                'scheduled_at': '2026-08-20T14:00:00Z',
                'duration_min': 60
            }
            success, interview = self.test(
                "POST /api/interviews (create)",
                "POST",
                "/interviews",
                200,
                token=self.tokens['recruiter'],
                data=interview_data
            )
            interview_id = interview.get('id') if success else None
            
            if interview_id:
                # List interviews filtered by interviewer
                self.test(
                    "GET /api/interviews (as interviewer)",
                    "GET",
                    "/interviews",
                    200,
                    token=self.tokens['interviewer']
                )
                
                # Complete interview
                self.test(
                    "POST /api/interviews/{id}/complete",
                    "POST",
                    f"/interviews/{interview_id}/complete",
                    200,
                    token=self.tokens['interviewer']
                )
                
                # Submit scorecard
                scorecard_data = {
                    'ratings': {
                        'Communication': 4,
                        'Technical Skill': 5,
                        'Problem Solving': 4,
                        'Culture Fit': 5
                    },
                    'overall': 4,
                    'recommendation': 'strong_yes',
                    'notes': 'Excellent candidate'
                }
                success, scorecard = self.test(
                    "POST /api/interviews/{id}/scorecard (submit)",
                    "POST",
                    f"/interviews/{interview_id}/scorecard",
                    200,
                    token=self.tokens['interviewer'],
                    data=scorecard_data
                )
                
                # Try duplicate scorecard (should be 409)
                self.test(
                    "POST /api/interviews/{id}/scorecard (duplicate - should be 409)",
                    "POST",
                    f"/interviews/{interview_id}/scorecard",
                    409,
                    token=self.tokens['interviewer'],
                    data=scorecard_data
                )
            
            # Availability check
            self.test(
                "GET /api/interviews-availability-check",
                "GET",
                f"/interviews-availability-check?interviewer_ids={interviewer_id}&scheduled_at=2026-08-21T10:00:00Z&duration_min=60",
                200,
                token=self.tokens['recruiter']
            )
    
    def test_dashboard(self):
        """Test dashboard endpoints"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: DASHBOARD", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'admin' not in self.tokens:
            self.log("⚠️  Skipping - no admin token", Colors.YELLOW)
            return
        
        # Dashboard stats
        success, stats = self.test(
            "GET /api/dashboard/stats",
            "GET",
            "/dashboard/stats",
            200,
            token=self.tokens['admin']
        )
        if success:
            self.log(f"   Open roles: {stats.get('open_roles')}", Colors.GREEN)
            self.log(f"   Active candidates: {stats.get('active_candidates')}", Colors.GREEN)
            self.log(f"   Interviews this week: {stats.get('interviews_this_week')}", Colors.GREEN)
            self.log(f"   Offers pending: {stats.get('offers_pending')}", Colors.GREEN)
            self.log(f"   Time to hire avg: {stats.get('time_to_hire_avg')}", Colors.GREEN)
            self.log(f"   Pipeline stages: {len(stats.get('pipeline', []))}", Colors.GREEN)
        
        # My tasks
        success, tasks = self.test(
            "GET /api/dashboard/my-tasks",
            "GET",
            "/dashboard/my-tasks",
            200,
            token=self.tokens['admin']
        )
        if success:
            self.log(f"   Tasks: {len(tasks)}", Colors.GREEN)
        
        # Activities
        success, activities = self.test(
            "GET /api/activities",
            "GET",
            "/activities",
            200,
            token=self.tokens['admin']
        )
        if success:
            self.log(f"   Recent activities: {len(activities)}", Colors.GREEN)
    
    def test_admin(self):
        """Test admin panel endpoints"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: ADMIN PANEL", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'admin' not in self.tokens:
            self.log("⚠️  Skipping - no admin token", Colors.YELLOW)
            return
        
        # Create user
        user_data = {
            'name': 'Test User API',
            'email': 'testuser@ats.com',
            'password': 'TestPass@123',
            'role': 'recruiter',
            'title': 'Junior Recruiter'
        }
        success, user = self.test(
            "POST /api/users (create)",
            "POST",
            "/users",
            200,
            token=self.tokens['admin'],
            data=user_data
        )
        user_id = user.get('id') if success else None
        
        if user_id:
            # Change role
            self.test(
                "PUT /api/users/{id} (change role)",
                "PUT",
                f"/users/{user_id}",
                200,
                token=self.tokens['admin'],
                data={'role': 'interviewer'}
            )
            
            # Deactivate user
            self.test(
                "PUT /api/users/{id} (deactivate)",
                "PUT",
                f"/users/{user_id}",
                200,
                token=self.tokens['admin'],
                data={'active': False}
            )
            
            # Try login with deactivated user (should be 403)
            self.test(
                "POST /api/auth/login (deactivated user - should be 403)",
                "POST",
                "/auth/login",
                403,
                data={'email': 'testuser@ats.com', 'password': 'TestPass@123'}
            )
            
            # Delete user
            self.test(
                "DELETE /api/users/{id}",
                "DELETE",
                f"/users/{user_id}",
                200,
                token=self.tokens['admin']
            )
        
        # Pipeline settings
        pipeline_data = {
            'stages': [
                {'name': 'Applied', 'scorecard_attributes': []},
                {'name': 'Screening', 'scorecard_attributes': ['Communication']},
                {'name': 'Interview', 'scorecard_attributes': ['Technical Skill', 'Problem Solving']},
                {'name': 'Offer', 'scorecard_attributes': []},
                {'name': 'Hired', 'scorecard_attributes': []}
            ]
        }
        self.test(
            "PUT /api/settings/pipeline",
            "PUT",
            "/settings/pipeline",
            200,
            token=self.tokens['admin'],
            data=pipeline_data
        )
        
        # Departments CRUD
        success, dept = self.test(
            "POST /api/departments (create)",
            "POST",
            "/departments",
            200,
            token=self.tokens['admin'],
            data={'name': 'Test Department'}
        )
        dept_id = dept.get('id') if success else None
        
        if dept_id:
            self.test(
                "DELETE /api/departments/{id}",
                "DELETE",
                f"/departments/{dept_id}",
                200,
                token=self.tokens['admin']
            )
        
        # Tags CRUD
        success, tag = self.test(
            "POST /api/tags (create)",
            "POST",
            "/tags",
            200,
            token=self.tokens['admin'],
            data={'name': 'test-api-tag'}
        )
        tag_id = tag.get('id') if success else None
        
        if tag_id:
            self.test(
                "DELETE /api/tags/{id}",
                "DELETE",
                f"/tags/{tag_id}",
                200,
                token=self.tokens['admin']
            )
        
        # Audit log
        success, logs = self.test(
            "GET /api/audit-log",
            "GET",
            "/audit-log",
            200,
            token=self.tokens['admin']
        )
        if success:
            self.log(f"   Audit log entries: {len(logs)}", Colors.GREEN)
    
    def test_notifications(self):
        """Test notifications endpoints"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: NOTIFICATIONS", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'admin' not in self.tokens:
            self.log("⚠️  Skipping - no admin token", Colors.YELLOW)
            return
        
        # Get notifications
        success, response = self.test(
            "GET /api/notifications",
            "GET",
            "/notifications",
            200,
            token=self.tokens['admin']
        )
        if success:
            self.log(f"   Notifications: {len(response.get('items', []))}", Colors.GREEN)
            self.log(f"   Unread: {response.get('unread', 0)}", Colors.GREEN)
        
        # Mark all read
        self.test(
            "POST /api/notifications/mark-read",
            "POST",
            "/notifications/mark-read",
            200,
            token=self.tokens['admin']
        )
    
    def test_imports(self):
        """Test Excel/CSV candidate import feature"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: EXCEL/CSV IMPORT", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens or 'interviewer' not in self.tokens:
            self.log("⚠️  Skipping - missing tokens", Colors.YELLOW)
            return
        
        # Test 1: GET /api/imports/template (recruiter - should be 200)
        success, template = self.test(
            "GET /api/imports/template (recruiter - should be 200)",
            "GET",
            "/imports/template",
            200,
            token=self.tokens['recruiter']
        )
        if success:
            self.log(f"   Template downloaded successfully", Colors.GREEN)
        
        # Test 2: GET /api/imports/template (interviewer - should be 403)
        self.test(
            "GET /api/imports/template (interviewer - should be 403)",
            "GET",
            "/imports/template",
            403,
            token=self.tokens['interviewer']
        )
        
        # Test 3: POST /api/imports/preview with invalid file (should be 422)
        invalid_file_path = Path('/tmp/invalid_test.txt')
        invalid_file_path.write_text('This is not a valid xlsx or csv file')
        with open(invalid_file_path, 'rb') as f:
            self.test(
                "POST /api/imports/preview (invalid file - should be 422)",
                "POST",
                "/imports/preview",
                422,
                token=self.tokens['recruiter'],
                files={'file': ('invalid_test.txt', f, 'text/plain')}
            )
        invalid_file_path.unlink()
        
        # Test 4: POST /api/imports/preview with valid xlsx file
        import_file_path = Path('/app/tests/fixtures/import_test.xlsx')
        if not import_file_path.exists():
            self.log(f"⚠️  Import test file not found: {import_file_path}", Colors.YELLOW)
            return
        
        with open(import_file_path, 'rb') as f:
            success, preview = self.test(
                "POST /api/imports/preview (valid xlsx - should be 200)",
                "POST",
                "/imports/preview",
                200,
                token=self.tokens['recruiter'],
                files={'file': ('import_test.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            )
        
        if not success:
            self.log("⚠️  Preview failed, skipping commit tests", Colors.YELLOW)
            return
        
        import_id = preview.get('import_id')
        headers = preview.get('headers', [])
        suggested_mapping = preview.get('suggested_mapping', {})
        sample_rows = preview.get('sample_rows', [])
        total_rows = preview.get('total_rows', 0)
        
        self.log(f"   Import ID: {import_id}", Colors.GREEN)
        self.log(f"   Headers: {headers}", Colors.GREEN)
        self.log(f"   Total rows: {total_rows}", Colors.GREEN)
        self.log(f"   Sample rows: {len(sample_rows)}", Colors.GREEN)
        
        # Verify auto-mapping
        expected_mappings = {
            'Full Name': 'name',
            'Email Address': 'email',
            'Applied For': 'job',
            'Status': 'stage'
        }
        for header, expected_field in expected_mappings.items():
            if header in suggested_mapping:
                actual_field = suggested_mapping[header]
                if actual_field == expected_field:
                    self.log(f"   ✓ Auto-mapped '{header}' -> '{expected_field}'", Colors.GREEN)
                else:
                    self.log(f"   ✗ Auto-mapping mismatch: '{header}' -> '{actual_field}' (expected '{expected_field}')", Colors.RED)
        
        # Test 5: Get jobs for default_job_id
        success, jobs_response = self.test(
            "GET /api/jobs (to get default job)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['recruiter']
        )
        default_job_id = None
        if success:
            if isinstance(jobs_response, list) and len(jobs_response) > 0:
                # Find "Product Manager" job or use first job
                for job in jobs_response:
                    if 'Product Manager' in job.get('title', ''):
                        default_job_id = job.get('id')
                        break
                if not default_job_id:
                    default_job_id = jobs_response[0].get('id')
            elif isinstance(jobs_response, dict) and 'items' in jobs_response:
                items = jobs_response.get('items', [])
                for job in items:
                    if 'Product Manager' in job.get('title', ''):
                        default_job_id = job.get('id')
                        break
                if not default_job_id and items:
                    default_job_id = items[0].get('id')
        
        # Test 6: POST /api/imports/{id}/commit with suggested mapping + duplicate_strategy=skip
        commit_body = {
            'mapping': suggested_mapping,
            'default_job_id': default_job_id,
            'default_source': 'career_site',
            'duplicate_strategy': 'skip'
        }
        success, result = self.test(
            "POST /api/imports/{id}/commit (with default job, skip duplicates)",
            "POST",
            f"/imports/{import_id}/commit",
            200,
            token=self.tokens['recruiter'],
            data=commit_body
        )
        
        if success:
            created = result.get('created', 0)
            skipped_duplicates = result.get('skipped_duplicates', 0)
            errors = result.get('errors', [])
            
            self.log(f"   Created: {created}", Colors.GREEN)
            self.log(f"   Skipped duplicates: {skipped_duplicates}", Colors.GREEN)
            self.log(f"   Errors/Warnings: {len(errors)}", Colors.YELLOW)
            
            for error in errors[:5]:  # Show first 5 errors
                self.log(f"   - Row {error.get('row')}: {error.get('reason')}", Colors.YELLOW)
            
            # Expected: created=4-5, skipped_duplicates=1 (sarah.chen@example.com exists in seed)
            # Errors should include: missing-name row, unmatched-job row, invalid email warning
            if created >= 4:
                self.log(f"   ✓ Import created expected number of candidates", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected at least 4 created, got {created}", Colors.YELLOW)
            
            if skipped_duplicates >= 1:
                self.log(f"   ✓ Duplicate detection working (skipped {skipped_duplicates})", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected at least 1 duplicate skipped, got {skipped_duplicates}", Colors.YELLOW)
        
        # Test 7: Re-commit same import_id (should be 409)
        self.test(
            "POST /api/imports/{id}/commit (re-commit - should be 409)",
            "POST",
            f"/imports/{import_id}/commit",
            409,
            token=self.tokens['recruiter'],
            data=commit_body
        )
        
        # Test 8: Verify imported candidates appear in GET /api/candidates
        success, candidates = self.test(
            "GET /api/candidates (verify imported candidates)",
            "GET",
            "/candidates?q=Anita",
            200,
            token=self.tokens['recruiter']
        )
        if success:
            items = candidates.get('items', [])
            anita_found = any('Anita' in c.get('name', '') for c in items)
            if anita_found:
                self.log(f"   ✓ Found imported candidate 'Anita Desai'", Colors.GREEN)
                # Check stage
                anita = next((c for c in items if 'Anita' in c.get('name', '')), None)
                if anita:
                    stage = anita.get('stage')
                    self.log(f"   Stage: {stage}", Colors.GREEN)
                    if stage == 'Screening':
                        self.log(f"   ✓ Stage correctly set to 'Screening'", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Imported candidate 'Anita Desai' not found", Colors.YELLOW)
        
        # Test 9: Check timeline for imported notes with [Imported] prefix
        if success and items:
            candidate_with_notes = None
            for c in items:
                if 'imported' in c or c.get('import_id'):
                    candidate_with_notes = c
                    break
            
            if candidate_with_notes:
                candidate_id = candidate_with_notes.get('id')
                success, timeline = self.test(
                    "GET /api/candidates/{id}/timeline (check [Imported] notes)",
                    "GET",
                    f"/candidates/{candidate_id}/timeline",
                    200,
                    token=self.tokens['recruiter']
                )
                if success:
                    imported_notes = [t for t in timeline if '[Imported]' in t.get('text', '')]
                    if imported_notes:
                        self.log(f"   ✓ Found {len(imported_notes)} notes with [Imported] prefix", Colors.GREEN)
                    else:
                        self.log(f"   ⚠️  No notes with [Imported] prefix found", Colors.YELLOW)
        
        # Test 10: Check audit log for candidates_imported entry
        if 'admin' in self.tokens:
            success, logs = self.test(
                "GET /api/audit-log (check candidates_imported entry)",
                "GET",
                "/audit-log?limit=50",
                200,
                token=self.tokens['admin']
            )
            if success:
                import_logs = [log for log in logs if log.get('action') == 'candidates_imported']
                if import_logs:
                    self.log(f"   ✓ Found {len(import_logs)} candidates_imported audit log entries", Colors.GREEN)
                else:
                    self.log(f"   ⚠️  No candidates_imported audit log entries found", Colors.YELLOW)
        
        # Test 11: Check activity feed for import activity
        success, activities = self.test(
            "GET /api/activities (check import activity)",
            "GET",
            "/activities?limit=50",
            200,
            token=self.tokens['recruiter']
        )
        if success:
            import_activities = [a for a in activities if 'import' in a.get('action', '').lower()]
            if import_activities:
                self.log(f"   ✓ Found {len(import_activities)} import activities", Colors.GREEN)
            else:
                self.log(f"   ⚠️  No import activities found", Colors.YELLOW)
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TEST SUMMARY", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        total = self.tests_run
        passed = self.tests_passed
        failed = self.tests_failed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        self.log(f"\nTotal Tests: {total}", Colors.BLUE)
        self.log(f"Passed: {passed}", Colors.GREEN)
        self.log(f"Failed: {failed}", Colors.RED)
        self.log(f"Pass Rate: {pass_rate:.1f}%", Colors.YELLOW)
        
        if self.critical_failures:
            self.log("\n⚠️  CRITICAL FAILURES:", Colors.RED)
            for failure in self.critical_failures:
                self.log(f"   - {failure}", Colors.RED)
        
        return 0 if failed == 0 else 1

def main():
    tester = ATSTester()
    
    print(f"\n{'='*60}")
    print(f"🚀 Sprout ATS Backend API Testing")
    print(f"   Base URL: {BASE_URL}")
    print(f"{'='*60}\n")
    
    # Run all tests
    tester.test_auth()
    tester.test_rbac()
    tester.test_resume_parsing()
    tester.test_candidates()
    tester.test_jobs()
    tester.test_interviews()
    tester.test_dashboard()
    tester.test_admin()
    tester.test_notifications()
    
    # Print summary
    exit_code = tester.print_summary()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
