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
BASE_URL = "https://import-ats-build.preview.emergentagent.com/api"

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
                # For file downloads, return binary content
                if 'application/pdf' in response.headers.get('Content-Type', '') or \
                   'application/vnd.openxmlformats-officedocument' in response.headers.get('Content-Type', '') or \
                   'application/octet-stream' in response.headers.get('Content-Type', ''):
                    return True, response.content
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
    
    def test_resume_compression(self):
        """Test resume auto-compression feature"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: RESUME AUTO-COMPRESSION", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens:
            self.log("⚠️  Skipping - no recruiter token", Colors.YELLOW)
            return
        
        import io
        
        # Test 1: Single PDF upload with compression check
        self.log("\n📄 Test 1: PDF compression (resume_sarah_chen.pdf)", Colors.BLUE)
        pdf_path = Path('/app/tests/fixtures/resume_sarah_chen.pdf')
        if pdf_path.exists():
            original_size = pdf_path.stat().st_size
            self.log(f"   Original file size: {original_size} bytes", Colors.YELLOW)
            
            with open(pdf_path, 'rb') as f:
                success, response = self.test(
                    "POST /api/resumes/parse (PDF with compression)",
                    "POST",
                    "/resumes/parse",
                    200,
                    token=self.tokens['recruiter'],
                    files={'file': ('resume_sarah_chen.pdf', f, 'application/pdf')},
                    timeout=90
                )
                
                if success:
                    # Verify parsing worked correctly
                    parsed = response.get('parsed', {})
                    file_id = response.get('file_id')
                    
                    if not parsed.get('name') or not parsed.get('email'):
                        self.critical_failures.append("PDF parsing failed - missing name or email (compression may have affected text extraction)")
                        self.log("   ❌ CRITICAL: Parsing incomplete - name or email missing", Colors.RED)
                    else:
                        self.log(f"   ✅ Parsing successful: {parsed.get('name')}, {parsed.get('email')}", Colors.GREEN)
                    
                    # Test file retrieval and size comparison
                    if file_id:
                        success2, file_response = self.test(
                            "GET /api/files/{file_id} (retrieve compressed PDF)",
                            "GET",
                            f"/files/{file_id}",
                            200,
                            token=self.tokens['recruiter'],
                            timeout=10
                        )
                        
                        if success2:
                            stored_size = len(file_response) if isinstance(file_response, bytes) else len(str(file_response))
                            self.log(f"   Stored file size: {stored_size} bytes", Colors.YELLOW)
                            
                            if stored_size > original_size:
                                self.critical_failures.append(f"PDF compression FAILED - stored file ({stored_size}B) is LARGER than original ({original_size}B)")
                                self.log(f"   ❌ CRITICAL: File got LARGER after compression!", Colors.RED)
                            elif stored_size == original_size:
                                self.log(f"   ⚠️  File size unchanged (compression had no effect, but this is acceptable)", Colors.YELLOW)
                            else:
                                reduction = ((original_size - stored_size) / original_size) * 100
                                self.log(f"   ✅ Compression successful: {reduction:.1f}% reduction", Colors.GREEN)
                            
                            # Verify file is valid PDF (basic check)
                            if isinstance(file_response, bytes):
                                if file_response.startswith(b'%PDF'):
                                    self.log(f"   ✅ Downloaded file is a valid PDF", Colors.GREEN)
                                else:
                                    self.critical_failures.append("Downloaded PDF is corrupted (missing PDF header)")
                                    self.log(f"   ❌ CRITICAL: Downloaded file is NOT a valid PDF!", Colors.RED)
        else:
            self.log(f"⚠️  PDF test file not found: {pdf_path}", Colors.YELLOW)
        
        # Test 2: DOCX upload with compression check
        self.log("\n📄 Test 2: DOCX compression (resume_priya_patel.docx)", Colors.BLUE)
        docx_path = Path('/app/tests/fixtures/resume_priya_patel.docx')
        if docx_path.exists():
            original_size = docx_path.stat().st_size
            self.log(f"   Original file size: {original_size} bytes", Colors.YELLOW)
            
            with open(docx_path, 'rb') as f:
                success, response = self.test(
                    "POST /api/resumes/parse (DOCX with compression)",
                    "POST",
                    "/resumes/parse",
                    200,
                    token=self.tokens['recruiter'],
                    files={'file': ('resume_priya_patel.docx', f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
                    timeout=90
                )
                
                if success:
                    # Verify parsing worked correctly
                    parsed = response.get('parsed', {})
                    file_id = response.get('file_id')
                    
                    if not parsed.get('name') or not parsed.get('email'):
                        self.critical_failures.append("DOCX parsing failed - missing name or email (compression may have affected text extraction)")
                        self.log("   ❌ CRITICAL: Parsing incomplete - name or email missing", Colors.RED)
                    else:
                        self.log(f"   ✅ Parsing successful: {parsed.get('name')}, {parsed.get('email')}", Colors.GREEN)
                    
                    # Test file retrieval and size comparison
                    if file_id:
                        success2, file_response = self.test(
                            "GET /api/files/{file_id} (retrieve compressed DOCX)",
                            "GET",
                            f"/files/{file_id}",
                            200,
                            token=self.tokens['recruiter'],
                            timeout=10
                        )
                        
                        if success2:
                            stored_size = len(file_response) if isinstance(file_response, bytes) else len(str(file_response))
                            self.log(f"   Stored file size: {stored_size} bytes", Colors.YELLOW)
                            
                            if stored_size > original_size:
                                self.critical_failures.append(f"DOCX compression FAILED - stored file ({stored_size}B) is LARGER than original ({original_size}B)")
                                self.log(f"   ❌ CRITICAL: File got LARGER after compression!", Colors.RED)
                            elif stored_size == original_size:
                                self.log(f"   ⚠️  File size unchanged (compression had no effect, but this is acceptable)", Colors.YELLOW)
                            else:
                                reduction = ((original_size - stored_size) / original_size) * 100
                                self.log(f"   ✅ Compression successful: {reduction:.1f}% reduction", Colors.GREEN)
                            
                            # Verify file is valid DOCX (basic check - DOCX is a ZIP file)
                            if isinstance(file_response, bytes):
                                if file_response.startswith(b'PK'):
                                    self.log(f"   ✅ Downloaded file is a valid DOCX (ZIP format)", Colors.GREEN)
                                else:
                                    self.critical_failures.append("Downloaded DOCX is corrupted (missing ZIP header)")
                                    self.log(f"   ❌ CRITICAL: Downloaded file is NOT a valid DOCX!", Colors.RED)
        else:
            self.log(f"⚠️  DOCX test file not found: {docx_path}", Colors.YELLOW)
        
        # Test 3: Bulk upload with compression
        self.log("\n📄 Test 3: Bulk upload with compression", Colors.BLUE)
        pdf1_path = Path('/app/tests/fixtures/resume_sarah_chen.pdf')
        pdf2_path = Path('/app/tests/fixtures/resume_miguel_torres.pdf')
        
        if pdf1_path.exists() and pdf2_path.exists():
            original_sizes = {
                'resume_sarah_chen.pdf': pdf1_path.stat().st_size,
                'resume_miguel_torres.pdf': pdf2_path.stat().st_size
            }
            self.log(f"   Original sizes: Sarah={original_sizes['resume_sarah_chen.pdf']}B, Miguel={original_sizes['resume_miguel_torres.pdf']}B", Colors.YELLOW)
            
            with open(pdf1_path, 'rb') as f1, open(pdf2_path, 'rb') as f2:
                files = [
                    ('files', ('resume_sarah_chen.pdf', f1.read(), 'application/pdf')),
                    ('files', ('resume_miguel_torres.pdf', f2.read(), 'application/pdf'))
                ]
                success, response = self.test(
                    "POST /api/resumes/parse-bulk (2 PDFs with compression)",
                    "POST",
                    "/resumes/parse-bulk",
                    200,
                    token=self.tokens['recruiter'],
                    files=files,
                    timeout=120
                )
                
                if success:
                    results = response.get('results', [])
                    self.log(f"   Parsed {len(results)} resumes", Colors.GREEN)
                    
                    for result in results:
                        filename = result.get('filename')
                        status = result.get('status')
                        file_id = result.get('file_id')
                        parsed = result.get('parsed', {})
                        
                        if status != 'success':
                            self.critical_failures.append(f"Bulk upload failed for {filename}: {result.get('error')}")
                            self.log(f"   ❌ {filename}: {status} - {result.get('error')}", Colors.RED)
                        elif not parsed.get('name'):
                            self.critical_failures.append(f"Bulk upload parsing incomplete for {filename}")
                            self.log(f"   ❌ {filename}: Parsing incomplete", Colors.RED)
                        else:
                            self.log(f"   ✅ {filename}: {status}, parsed {parsed.get('name')}", Colors.GREEN)
        else:
            self.log(f"⚠️  Bulk test files not found", Colors.YELLOW)
        
        # Test 4: Sanity check - verify other endpoints unaffected
        self.log("\n📄 Test 4: Sanity checks (no regressions)", Colors.BLUE)
        
        # Check jobs endpoint
        self.test(
            "GET /api/jobs (sanity check)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['recruiter'],
            timeout=10
        )
        
        # Check candidates endpoint
        self.test(
            "GET /api/candidates?limit=5 (sanity check)",
            "GET",
            "/candidates?limit=5",
            200,
            token=self.tokens['recruiter'],
            timeout=10
        )
        
        # Check dashboard stats
        self.test(
            "GET /api/dashboard/stats (sanity check)",
            "GET",
            "/dashboard/stats",
            200,
            token=self.tokens['recruiter'],
            timeout=10
        )
    
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
    
    def test_bulk_delete(self):
        """Test bulk delete candidates feature (admin-only)"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: BULK DELETE CANDIDATES (ADMIN-ONLY)", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'admin' not in self.tokens or 'recruiter' not in self.tokens:
            self.log("⚠️  Skipping - missing tokens", Colors.YELLOW)
            return
        
        # Test 1: Get existing candidates to identify IDs for deletion
        success, cands_response = self.test(
            "GET /api/candidates (as recruiter to list candidates)",
            "GET",
            "/candidates?limit=10",
            200,
            token=self.tokens['recruiter']
        )
        
        if not success or not isinstance(cands_response, dict) or 'items' not in cands_response:
            self.log("⚠️  Could not get candidate list, skipping bulk delete tests", Colors.YELLOW)
            return
        
        candidates = cands_response.get('items', [])
        if len(candidates) < 2:
            self.log("⚠️  Not enough candidates for bulk delete test (need at least 2)", Colors.YELLOW)
            return
        
        # Pick 2 candidates that are NOT critical seed data (avoid first few)
        # Use candidates from the middle/end of the list
        test_candidate_ids = [c['id'] for c in candidates[-2:]]
        self.log(f"   Selected {len(test_candidate_ids)} candidates for deletion test", Colors.GREEN)
        
        # Test 2: Recruiter attempts bulk delete (should be 403)
        success, response = self.test(
            "POST /api/candidates/bulk-action with action=delete (recruiter - should be 403)",
            "POST",
            "/candidates/bulk-action",
            403,
            token=self.tokens['recruiter'],
            data={
                'candidate_ids': test_candidate_ids,
                'action': 'delete'
            }
        )
        if success:
            self.log("   ✓ Recruiter correctly denied bulk delete (403)", Colors.GREEN)
        
        # Test 3: Admin bulk deletes candidates (should be 200)
        success, response = self.test(
            "POST /api/candidates/bulk-action with action=delete (admin - should be 200)",
            "POST",
            "/candidates/bulk-action",
            200,
            token=self.tokens['admin'],
            data={
                'candidate_ids': test_candidate_ids,
                'action': 'delete'
            }
        )
        
        if success:
            count = response.get('count', 0)
            self.log(f"   ✓ Admin successfully deleted {count} candidates", Colors.GREEN)
            if count == len(test_candidate_ids):
                self.log(f"   ✓ Deleted count matches requested count", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Expected {len(test_candidate_ids)} deleted, got {count}", Colors.YELLOW)
        
        # Test 4: Verify candidates are gone (should be 404)
        for cid in test_candidate_ids:
            success, response = self.test(
                f"GET /api/candidates/{cid} (should be 404 after delete)",
                "GET",
                f"/candidates/{cid}",
                404,
                token=self.tokens['admin']
            )
            if success:
                self.log(f"   ✓ Candidate {cid} correctly returns 404", Colors.GREEN)
        
        # Test 5: Verify other bulk actions still work - move_stage
        # Get a fresh candidate for testing other bulk actions
        success, cands_response = self.test(
            "GET /api/candidates (get fresh candidate for other bulk actions)",
            "GET",
            "/candidates?limit=2",
            200,
            token=self.tokens['admin']
        )
        
        if success and isinstance(cands_response, dict) and 'items' in cands_response:
            test_candidates = cands_response.get('items', [])
            if len(test_candidates) >= 1:
                test_cid = test_candidates[0]['id']
                
                # Test move_stage
                success, response = self.test(
                    "POST /api/candidates/bulk-action with action=move_stage",
                    "POST",
                    "/candidates/bulk-action",
                    200,
                    token=self.tokens['admin'],
                    data={
                        'candidate_ids': [test_cid],
                        'action': 'move_stage',
                        'stage': 'Screening'
                    }
                )
                if success:
                    self.log(f"   ✓ Bulk move_stage still works", Colors.GREEN)
                    # Verify the change
                    success, candidate = self.test(
                        f"GET /api/candidates/{test_cid} (verify stage change)",
                        "GET",
                        f"/candidates/{test_cid}",
                        200,
                        token=self.tokens['admin']
                    )
                    if success and candidate.get('stage') == 'Screening':
                        self.log(f"   ✓ Stage correctly updated to 'Screening'", Colors.GREEN)
                
                # Test tag
                success, response = self.test(
                    "POST /api/candidates/bulk-action with action=tag",
                    "POST",
                    "/candidates/bulk-action",
                    200,
                    token=self.tokens['admin'],
                    data={
                        'candidate_ids': [test_cid],
                        'action': 'tag',
                        'tag': 'test-bulk-tag'
                    }
                )
                if success:
                    self.log(f"   ✓ Bulk tag still works", Colors.GREEN)
                    # Verify the tag
                    success, candidate = self.test(
                        f"GET /api/candidates/{test_cid} (verify tag added)",
                        "GET",
                        f"/candidates/{test_cid}",
                        200,
                        token=self.tokens['admin']
                    )
                    if success and 'test-bulk-tag' in candidate.get('tags', []):
                        self.log(f"   ✓ Tag correctly added", Colors.GREEN)
                
                # Test assign
                recruiter_id = self.users.get('recruiter', {}).get('id')
                if recruiter_id:
                    success, response = self.test(
                        "POST /api/candidates/bulk-action with action=assign",
                        "POST",
                        "/candidates/bulk-action",
                        200,
                        token=self.tokens['admin'],
                        data={
                            'candidate_ids': [test_cid],
                            'action': 'assign',
                            'recruiter_id': recruiter_id
                        }
                    )
                    if success:
                        self.log(f"   ✓ Bulk assign still works", Colors.GREEN)
                        # Verify the assignment
                        success, candidate = self.test(
                            f"GET /api/candidates/{test_cid} (verify assignment)",
                            "GET",
                            f"/candidates/{test_cid}",
                            200,
                            token=self.tokens['admin']
                        )
                        if success and candidate.get('recruiter_id') == recruiter_id:
                            self.log(f"   ✓ Recruiter correctly assigned", Colors.GREEN)
                
                # Test reject
                success, response = self.test(
                    "POST /api/candidates/bulk-action with action=reject",
                    "POST",
                    "/candidates/bulk-action",
                    200,
                    token=self.tokens['admin'],
                    data={
                        'candidate_ids': [test_cid],
                        'action': 'reject',
                        'reason': 'Not a good fit for the role'
                    }
                )
                if success:
                    self.log(f"   ✓ Bulk reject still works", Colors.GREEN)
                    # Verify the rejection
                    success, candidate = self.test(
                        f"GET /api/candidates/{test_cid} (verify rejection)",
                        "GET",
                        f"/candidates/{test_cid}",
                        200,
                        token=self.tokens['admin']
                    )
                    if success:
                        if candidate.get('stage') == 'Rejected' and candidate.get('status') == 'rejected':
                            self.log(f"   ✓ Candidate correctly rejected (stage=Rejected, status=rejected)", Colors.GREEN)
                        if candidate.get('rejection_reason') == 'Not a good fit for the role':
                            self.log(f"   ✓ Rejection reason correctly set", Colors.GREEN)
        
        # Test 6: Sanity check unrelated endpoints still work
        self.test(
            "GET /api/dashboard/stats (sanity check after bulk-delete)",
            "GET",
            "/dashboard/stats",
            200,
            token=self.tokens['admin']
        )
        
        self.test(
            "GET /api/jobs (sanity check after bulk-delete)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['admin']
        )
        
        self.test(
            "GET /api/imports/template (sanity check after bulk-delete)",
            "GET",
            "/imports/template",
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
    
    def test_resume_matching_and_merge(self):
        """Test resume-to-existing-candidate matching & merge feature"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TESTING: RESUME MATCHING & MERGE", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        
        if 'recruiter' not in self.tokens:
            self.log("⚠️  Skipping - no recruiter token", Colors.YELLOW)
            return
        
        # Step 1: Parse resume_sarah_chen.pdf standalone (no existing candidate yet)
        self.log("\n📄 Step 1: Parse resume_sarah_chen.pdf standalone", Colors.BLUE)
        resume_path = Path('/app/tests/fixtures/resume_sarah_chen.pdf')
        if not resume_path.exists():
            self.log(f"⚠️  Resume file not found: {resume_path}", Colors.YELLOW)
            self.critical_failures.append("resume_sarah_chen.pdf not found - cannot test matching feature")
            return
        
        with open(resume_path, 'rb') as f:
            success, response = self.test(
                "POST /api/resumes/parse (standalone, no match yet)",
                "POST",
                "/resumes/parse",
                200,
                token=self.tokens['recruiter'],
                files={'file': ('resume_sarah_chen.pdf', f, 'application/pdf')},
                timeout=90
            )
        
        if not success:
            self.critical_failures.append("Step 1 failed - cannot parse resume")
            return
        
        parsed_name = response.get('parsed', {}).get('name')
        parsed_email = response.get('parsed', {}).get('email')
        match_field = response.get('match')
        file_id_initial = response.get('file_id')
        
        self.log(f"   Parsed name: {parsed_name}", Colors.GREEN)
        self.log(f"   Parsed email: {parsed_email}", Colors.GREEN)
        self.log(f"   Match field: {match_field}", Colors.YELLOW)
        
        if not parsed_name or not parsed_email:
            self.critical_failures.append("Step 1 failed - parsed name or email is missing")
            return
        
        # Verify match field exists in response (should be null/None at this point)
        if 'match' not in response:
            self.critical_failures.append("Step 1 CRITICAL: 'match' field missing from response")
            self.log("   ❌ CRITICAL: 'match' field not present in response", Colors.RED)
        elif match_field is None:
            self.log("   ✅ Match field is null (no existing candidate found)", Colors.GREEN)
        else:
            self.log(f"   ⚠️  Match field is NOT null: {match_field} (may be from prior testing)", Colors.YELLOW)
        
        # Step 2: Create a NEW test candidate with exact parsed name, no email, no resume_file_id
        self.log("\n📄 Step 2: Create NEW candidate with parsed name (no email, no resume)", Colors.BLUE)
        
        # Get a valid job_id
        success, jobs_response = self.test(
            "GET /api/jobs (to get job_id)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['recruiter']
        )
        
        job_id = None
        if success:
            if isinstance(jobs_response, list) and len(jobs_response) > 0:
                job_id = jobs_response[0].get('id')
            elif isinstance(jobs_response, dict) and 'items' in jobs_response:
                items = jobs_response.get('items', [])
                if items:
                    job_id = items[0].get('id')
        
        if not job_id:
            self.critical_failures.append("Step 2 failed - no valid job_id found")
            return
        
        candidate_data = {
            'name': parsed_name,  # Use exact parsed name
            'email': None,  # Leave email as null
            'job_id': job_id,
            'source': 'career_site',
            'tags': ['test-matching']
        }
        
        success, candidate = self.test(
            "POST /api/candidates (create test candidate)",
            "POST",
            "/candidates",
            200,
            token=self.tokens['recruiter'],
            data=candidate_data
        )
        
        if not success:
            self.critical_failures.append("Step 2 failed - cannot create candidate")
            return
        
        candidate_id = candidate.get('id')
        original_job_id = candidate.get('job_id')
        original_stage = candidate.get('stage')
        original_tags = candidate.get('tags', [])
        original_source = candidate.get('source')
        original_recruiter_id = candidate.get('recruiter_id')
        
        self.log(f"   Created candidate ID: {candidate_id}", Colors.GREEN)
        self.log(f"   Original job_id: {original_job_id}", Colors.YELLOW)
        self.log(f"   Original stage: {original_stage}", Colors.YELLOW)
        self.log(f"   Original tags: {original_tags}", Colors.YELLOW)
        self.log(f"   Original source: {original_source}", Colors.YELLOW)
        self.log(f"   Original recruiter_id: {original_recruiter_id}", Colors.YELLOW)
        
        # Step 3: Parse resume_sarah_chen.pdf again - should now match by name
        self.log("\n📄 Step 3: Parse resume_sarah_chen.pdf again (should match by name)", Colors.BLUE)
        
        with open(resume_path, 'rb') as f:
            success, response = self.test(
                "POST /api/resumes/parse (should match existing candidate)",
                "POST",
                "/resumes/parse",
                200,
                token=self.tokens['recruiter'],
                files={'file': ('resume_sarah_chen.pdf', f, 'application/pdf')},
                timeout=90
            )
        
        if not success:
            self.critical_failures.append("Step 3 failed - cannot parse resume")
            return
        
        match_field = response.get('match')
        file_id_1 = response.get('file_id')
        parsed_data = response.get('parsed', {})
        
        self.log(f"   Match field: {match_field}", Colors.YELLOW)
        self.log(f"   File ID: {file_id_1}", Colors.GREEN)
        
        if match_field is None:
            self.critical_failures.append("Step 3 CRITICAL: 'match' field is null (should match by name)")
            self.log("   ❌ CRITICAL: 'match' field is null, expected name match", Colors.RED)
        elif not isinstance(match_field, dict):
            self.critical_failures.append(f"Step 3 CRITICAL: 'match' field is not a dict: {match_field}")
            self.log(f"   ❌ CRITICAL: 'match' field is not a dict: {match_field}", Colors.RED)
        else:
            match_type = match_field.get('match_type')
            match_candidate_id = match_field.get('candidate_id')
            match_candidate_name = match_field.get('candidate_name')
            
            if match_type == 'name':
                self.log(f"   ✅ Match type is 'name' (correct)", Colors.GREEN)
            else:
                self.critical_failures.append(f"Step 3 CRITICAL: match_type is '{match_type}', expected 'name'")
                self.log(f"   ❌ CRITICAL: match_type is '{match_type}', expected 'name'", Colors.RED)
            
            if match_candidate_id == candidate_id:
                self.log(f"   ✅ Matched candidate_id is correct: {match_candidate_id}", Colors.GREEN)
            else:
                self.critical_failures.append(f"Step 3 CRITICAL: matched candidate_id '{match_candidate_id}' != created candidate_id '{candidate_id}'")
                self.log(f"   ❌ CRITICAL: matched candidate_id mismatch", Colors.RED)
            
            if match_candidate_name:
                self.log(f"   ✅ Matched candidate_name: {match_candidate_name}", Colors.GREEN)
            else:
                self.log(f"   ⚠️  Matched candidate_name is empty", Colors.YELLOW)
        
        # Step 4: Call merge-resume endpoint
        self.log("\n📄 Step 4: Call POST /api/candidates/{id}/merge-resume", Colors.BLUE)
        
        merge_data = {
            'file_id': file_id_1,
            'parsed': parsed_data
        }
        
        success, merge_response = self.test(
            "POST /api/candidates/{id}/merge-resume",
            "POST",
            f"/candidates/{candidate_id}/merge-resume",
            200,
            token=self.tokens['recruiter'],
            data=merge_data
        )
        
        if not success:
            self.critical_failures.append("Step 4 CRITICAL: merge-resume endpoint failed")
            self.log("   ❌ CRITICAL: merge-resume endpoint returned non-200", Colors.RED)
        else:
            self.log("   ✅ Merge-resume endpoint returned 200", Colors.GREEN)
        
        # Step 5: GET candidate - verify resume fields populated, pipeline fields unchanged
        self.log("\n📄 Step 5: GET /api/candidates/{id} - verify merge results", Colors.BLUE)
        
        success, updated_candidate = self.test(
            "GET /api/candidates/{id} (verify merge)",
            "GET",
            f"/candidates/{candidate_id}",
            200,
            token=self.tokens['recruiter']
        )
        
        if not success:
            self.critical_failures.append("Step 5 failed - cannot get candidate")
            return
        
        # Check resume fields are populated
        resume_fields = {
            'current_title': updated_candidate.get('current_title'),
            'current_company': updated_candidate.get('current_company'),
            'location': updated_candidate.get('location'),
            'skills': updated_candidate.get('skills', []),
            'experience': updated_candidate.get('experience', []),
            'education': updated_candidate.get('education', []),
            'resume_file_id': updated_candidate.get('resume_file_id')
        }
        
        self.log(f"   Resume fields after merge:", Colors.YELLOW)
        for field, value in resume_fields.items():
            if field == 'resume_file_id':
                if value == file_id_1:
                    self.log(f"     ✅ {field}: {value} (correct)", Colors.GREEN)
                else:
                    self.critical_failures.append(f"Step 5 CRITICAL: resume_file_id '{value}' != expected '{file_id_1}'")
                    self.log(f"     ❌ {field}: {value} (expected {file_id_1})", Colors.RED)
            elif value:
                self.log(f"     ✅ {field}: {value if not isinstance(value, list) else f'{len(value)} items'}", Colors.GREEN)
            else:
                self.log(f"     ⚠️  {field}: empty/null", Colors.YELLOW)
        
        # Check pipeline fields are UNCHANGED
        pipeline_fields = {
            'job_id': (updated_candidate.get('job_id'), original_job_id),
            'stage': (updated_candidate.get('stage'), original_stage),
            'tags': (updated_candidate.get('tags', []), original_tags),
            'source': (updated_candidate.get('source'), original_source),
            'recruiter_id': (updated_candidate.get('recruiter_id'), original_recruiter_id)
        }
        
        self.log(f"   Pipeline fields (should be UNCHANGED):", Colors.YELLOW)
        all_pipeline_unchanged = True
        for field, (current, original) in pipeline_fields.items():
            if current == original:
                self.log(f"     ✅ {field}: {current} (unchanged)", Colors.GREEN)
            else:
                all_pipeline_unchanged = False
                self.critical_failures.append(f"Step 5 CRITICAL: {field} changed from '{original}' to '{current}' (should be unchanged)")
                self.log(f"     ❌ {field}: {current} (was {original}) - SHOULD NOT CHANGE", Colors.RED)
        
        if all_pipeline_unchanged:
            self.log(f"   ✅ All pipeline fields correctly unchanged", Colors.GREEN)
        
        # Step 6: Update candidate email to match resume's email, parse again - should match by email
        self.log("\n📄 Step 6: Update candidate email, parse again (should match by email)", Colors.BLUE)
        
        success, update_response = self.test(
            "PUT /api/candidates/{id} (set email to match resume)",
            "PUT",
            f"/candidates/{candidate_id}",
            200,
            token=self.tokens['recruiter'],
            data={'email': parsed_email}
        )
        
        if not success:
            self.critical_failures.append("Step 6 failed - cannot update candidate email")
        else:
            self.log(f"   ✅ Updated candidate email to: {parsed_email}", Colors.GREEN)
        
        # Parse resume again
        with open(resume_path, 'rb') as f:
            success, response = self.test(
                "POST /api/resumes/parse (should match by email now)",
                "POST",
                "/resumes/parse",
                200,
                token=self.tokens['recruiter'],
                files={'file': ('resume_sarah_chen.pdf', f, 'application/pdf')},
                timeout=90
            )
        
        if not success:
            self.critical_failures.append("Step 6 failed - cannot parse resume")
        else:
            match_field = response.get('match')
            self.log(f"   Match field: {match_field}", Colors.YELLOW)
            
            if match_field and isinstance(match_field, dict):
                match_type = match_field.get('match_type')
                if match_type == 'email':
                    self.log(f"   ✅ Match type is 'email' (correct - email takes priority)", Colors.GREEN)
                else:
                    self.critical_failures.append(f"Step 6 CRITICAL: match_type is '{match_type}', expected 'email'")
                    self.log(f"   ❌ CRITICAL: match_type is '{match_type}', expected 'email'", Colors.RED)
                
                if match_field.get('candidate_id') == candidate_id:
                    self.log(f"   ✅ Still matches same candidate", Colors.GREEN)
            else:
                self.critical_failures.append("Step 6 CRITICAL: 'match' field is null or not a dict")
                self.log("   ❌ CRITICAL: 'match' field is null or not a dict", Colors.RED)
        
        # Step 7: Parse resume_miguel_torres.pdf (no match) - confirm match is null
        self.log("\n📄 Step 7: Parse resume_miguel_torres.pdf (no match expected)", Colors.BLUE)
        
        miguel_path = Path('/app/tests/fixtures/resume_miguel_torres.pdf')
        if not miguel_path.exists():
            self.log(f"⚠️  Resume file not found: {miguel_path}", Colors.YELLOW)
        else:
            with open(miguel_path, 'rb') as f:
                success, response = self.test(
                    "POST /api/resumes/parse (Miguel Torres - no match)",
                    "POST",
                    "/resumes/parse",
                    200,
                    token=self.tokens['recruiter'],
                    files={'file': ('resume_miguel_torres.pdf', f, 'application/pdf')},
                    timeout=90
                )
            
            if not success:
                self.critical_failures.append("Step 7 failed - cannot parse Miguel Torres resume")
            else:
                match_field = response.get('match')
                parsed = response.get('parsed', {})
                
                self.log(f"   Parsed name: {parsed.get('name')}", Colors.GREEN)
                self.log(f"   Match field: {match_field}", Colors.YELLOW)
                
                if 'match' not in response:
                    self.critical_failures.append("Step 7 CRITICAL: 'match' field missing from response")
                    self.log("   ❌ CRITICAL: 'match' field not present in response", Colors.RED)
                elif match_field is None:
                    self.log("   ✅ Match field is null (no match found - correct)", Colors.GREEN)
                else:
                    self.log(f"   ⚠️  Match field is NOT null: {match_field} (may be from prior testing)", Colors.YELLOW)
                
                # Verify other fields are unaffected (no regression)
                if response.get('file_id') and response.get('parsed') and response.get('status') == 'success':
                    self.log("   ✅ Response structure normal (no regression)", Colors.GREEN)
        
        # Step 8: Sanity checks
        self.log("\n📄 Step 8: Sanity checks (no regressions)", Colors.BLUE)
        
        self.test(
            "GET /api/jobs (sanity check)",
            "GET",
            "/jobs",
            200,
            token=self.tokens['recruiter']
        )
        
        self.test(
            "GET /api/candidates?limit=5 (sanity check)",
            "GET",
            "/candidates?limit=5",
            200,
            token=self.tokens['recruiter']
        )
    
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
    tester.test_bulk_resume_concurrency_fix()  # NEW: Test bulk resume concurrency fix (429 rate limit)
    tester.test_resume_compression()  # Test resume auto-compression feature
    tester.test_resume_parsing()
    tester.test_candidates()
    tester.test_bulk_delete()  # Test bulk delete feature
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
