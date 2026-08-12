#!/usr/bin/env python3
"""
Verify bulk resume upload fix for ATS backend.
Tests that LLM_CONCURRENCY=1 prevents Cloudflare 520 timeouts.
"""
import io
import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load backend .env to check LLM_CONCURRENCY
load_dotenv('/app/backend/.env')

# Backend URL from frontend .env
BACKEND_URL = "https://recruit-full-load.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@ats.com"
ADMIN_PASSWORD = "Admin@123"

# Test results tracking
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}

def log_pass(test_name, details=""):
    print(f"✅ PASS: {test_name}")
    if details:
        print(f"   {details}")
    results['passed'].append(test_name)

def log_fail(test_name, details=""):
    print(f"❌ FAIL: {test_name}")
    if details:
        print(f"   {details}")
    results['failed'].append(test_name)

def log_warn(test_name, details=""):
    print(f"⚠️  WARN: {test_name}")
    if details:
        print(f"   {details}")
    results['warnings'].append(test_name)

def make_tiny_pdf(name):
    """Create a minimal valid PDF with some text using fpdf2."""
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', size=12)
        pdf.cell(200, 10, f'Resume of {name}', ln=1)
        pdf.cell(200, 10, f'{name.lower().replace(" ", ".")}@example.com', ln=1)
        pdf.cell(200, 10, 'Software Engineer with 5 years of experience in Python and FastAPI', ln=1)
        pdf.cell(200, 10, 'Phone: 555-0100', ln=1)
        pdf.cell(200, 10, 'Location: San Francisco, CA', ln=1)
        buf = io.BytesIO()
        pdf.output(buf)
        return buf.getvalue()
    except ImportError:
        # Fallback: send as .txt file which the parser also handles
        text = f"""Name: {name}
Email: {name.lower().replace(" ", ".")}@example.com
Phone: 555-0100
Location: San Francisco, CA
Summary: Software Engineer with 5 years of experience in Python and FastAPI
Experience:
- Senior Software Engineer at Tech Corp (2020-Present)
- Software Engineer at StartupXYZ (2018-2020)
Skills: Python, FastAPI, React, MongoDB, Docker"""
        return text.encode()

def login():
    """Login as admin and return JWT token."""
    print("\n🔐 Logging in as admin...")
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log_fail("Login", f"Status {resp.status_code}: {resp.text}")
        sys.exit(1)
    token = resp.json()['token']
    log_pass("Login", f"Token obtained")
    return token

def test_a_llm_concurrency():
    """Test A: Verify LLM_CONCURRENCY=1 is set in .env"""
    print("\n" + "="*60)
    print("TEST A: LLM_CONCURRENCY Setting")
    print("="*60)
    
    # Check .env file
    llm_concurrency = os.environ.get('LLM_CONCURRENCY')
    if llm_concurrency == '1':
        log_pass("LLM_CONCURRENCY in .env", f"Value is '1' (correct for free tier)")
    else:
        log_fail("LLM_CONCURRENCY in .env", f"Expected '1', got '{llm_concurrency}'")
    
    # Check health endpoint
    resp = requests.get(f"{BACKEND_URL}/health")
    if resp.status_code == 200:
        log_pass("Backend health check", "Backend is up")
    else:
        log_fail("Backend health check", f"Status {resp.status_code}")

def test_b_bulk_upload_4_files(token):
    """Test B: POST /api/resumes/parse-bulk with 4 tiny test files"""
    print("\n" + "="*60)
    print("TEST B: Bulk Upload (4 files)")
    print("="*60)
    
    # Create 4 test files
    files = []
    names = ["Alice Johnson", "Bob Smith", "Carol Davis", "David Wilson"]
    for name in names:
        pdf_data = make_tiny_pdf(name)
        filename = f"{name.replace(' ', '_').lower()}.pdf"
        files.append(('files', (filename, io.BytesIO(pdf_data), 'application/pdf')))
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Uploading {len(files)} files...")
    start_time = time.time()
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/resumes/parse-bulk",
            files=files,
            headers=headers,
            timeout=120  # 2 minutes max
        )
        elapsed = time.time() - start_time
        
        print(f"Response time: {elapsed:.2f}s")
        
        if resp.status_code != 200:
            log_fail("Bulk upload status", f"Status {resp.status_code}: {resp.text[:200]}")
            return
        
        data = resp.json()
        results_list = data.get('results', [])
        
        if len(results_list) != 4:
            log_fail("Bulk upload response count", f"Expected 4 results, got {len(results_list)}")
            return
        
        log_pass("Bulk upload response count", f"Got 4 results")
        
        # Check timing (must be under 100s to avoid Cloudflare timeout)
        if elapsed < 100:
            log_pass("Bulk upload timing", f"{elapsed:.2f}s < 100s (no Cloudflare timeout)")
        else:
            log_fail("Bulk upload timing", f"{elapsed:.2f}s >= 100s (would trigger Cloudflare 520)")
        
        # Check success rate
        successes = [r for r in results_list if r.get('status') == 'success']
        failures = [r for r in results_list if r.get('status') != 'success']
        
        print(f"Successes: {len(successes)}/4")
        print(f"Failures: {len(failures)}/4")
        
        if len(successes) >= 3:
            log_pass("Bulk upload success rate", f"{len(successes)}/4 succeeded (>= 3 required)")
        else:
            log_fail("Bulk upload success rate", f"Only {len(successes)}/4 succeeded (< 3)")
        
        # Check for concurrent_request_limit errors
        concurrent_errors = [r for r in results_list if 'concurrent_request_limit' in str(r.get('error', '')).lower()]
        if concurrent_errors:
            log_fail("No concurrent_request_limit errors", f"Found {len(concurrent_errors)} concurrent limit errors")
        else:
            log_pass("No concurrent_request_limit errors", "No concurrency errors detected")
        
        # Check for Cloudflare errors
        cloudflare_errors = [r for r in results_list if any(x in str(r.get('error', '')).lower() for x in ['cloudflare', 'overloaded', '520', '524', '502', '504'])]
        if cloudflare_errors:
            log_fail("No Cloudflare errors", f"Found {len(cloudflare_errors)} Cloudflare-related errors")
        else:
            log_pass("No Cloudflare errors", "No Cloudflare errors detected")
        
        # Print sample parsed data
        if successes:
            sample = successes[0]
            parsed = sample.get('parsed', {})
            print(f"\nSample parsed data from {sample.get('filename')}:")
            print(f"  Name: {parsed.get('name')}")
            print(f"  Email: {parsed.get('email')}")
            print(f"  Phone: {parsed.get('phone')}")
        
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        log_fail("Bulk upload timeout", f"Request timed out after {elapsed:.2f}s")
    except Exception as e:
        log_fail("Bulk upload exception", f"{type(e).__name__}: {e}")

def test_c_single_resume(token):
    """Test C: POST /api/resumes/parse with 1 test file"""
    print("\n" + "="*60)
    print("TEST C: Single Resume Parse")
    print("="*60)
    
    pdf_data = make_tiny_pdf("Emma Thompson")
    filename = "emma_thompson.pdf"
    
    headers = {"Authorization": f"Bearer {token}"}
    files = {'file': (filename, io.BytesIO(pdf_data), 'application/pdf')}
    
    print(f"Uploading single file: {filename}")
    start_time = time.time()
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/resumes/parse",
            files=files,
            headers=headers,
            timeout=90
        )
        elapsed = time.time() - start_time
        
        print(f"Response time: {elapsed:.2f}s")
        
        if resp.status_code != 200:
            log_fail("Single parse status", f"Status {resp.status_code}: {resp.text[:200]}")
            return
        
        data = resp.json()
        
        if data.get('status') == 'success':
            log_pass("Single parse status", "Status is 'success'")
        else:
            log_fail("Single parse status", f"Status is '{data.get('status')}'")
        
        if 'parsed' in data:
            log_pass("Single parse has parsed fields", "Parsed data present")
            parsed = data['parsed']
            print(f"  Name: {parsed.get('name')}")
            print(f"  Email: {parsed.get('email')}")
        else:
            log_fail("Single parse has parsed fields", "No parsed data in response")
        
        if 'file_id' in data:
            log_pass("Single parse has file_id", f"file_id: {data['file_id'][:8]}...")
        else:
            log_fail("Single parse has file_id", "No file_id in response")
        
    except Exception as e:
        log_fail("Single parse exception", f"{type(e).__name__}: {e}")

def test_d_over_limit(token):
    """Test D: POST /api/resumes/parse-bulk with 26 files (over 25 limit)"""
    print("\n" + "="*60)
    print("TEST D: Over Limit (26 files)")
    print("="*60)
    
    # Create 26 tiny files
    files = []
    for i in range(26):
        pdf_data = make_tiny_pdf(f"Person {i+1}")
        filename = f"person_{i+1}.pdf"
        files.append(('files', (filename, io.BytesIO(pdf_data), 'application/pdf')))
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Uploading {len(files)} files (over 25 limit)...")
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/resumes/parse-bulk",
            files=files,
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 422:
            detail = resp.json().get('detail', '')
            if '25' in detail:
                log_pass("Over limit validation", f"422 with correct message: {detail}")
            else:
                log_warn("Over limit validation", f"422 but message doesn't mention 25: {detail}")
        else:
            log_fail("Over limit validation", f"Expected 422, got {resp.status_code}")
        
    except Exception as e:
        log_fail("Over limit exception", f"{type(e).__name__}: {e}")

def test_e_empty_batch(token):
    """Test E: POST /api/resumes/parse-bulk with 0 files"""
    print("\n" + "="*60)
    print("TEST E: Empty Batch")
    print("="*60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print("Uploading 0 files...")
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/resumes/parse-bulk",
            files=[],
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 422:
            log_pass("Empty batch validation", f"422 (FastAPI validation error)")
        else:
            log_fail("Empty batch validation", f"Expected 422, got {resp.status_code}")
        
    except Exception as e:
        log_fail("Empty batch exception", f"{type(e).__name__}: {e}")

def test_f_regression(token):
    """Test F: Regression tests on existing endpoints"""
    print("\n" + "="*60)
    print("TEST F: Regression Tests")
    print("="*60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 1: GET /api/candidates?limit=5
    print("\n1. GET /api/candidates?limit=5")
    try:
        resp = requests.get(f"{BACKEND_URL}/candidates?limit=5", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            count = len(data.get('items', []))
            log_pass("GET /api/candidates", f"200, got {count} candidates")
        else:
            log_fail("GET /api/candidates", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("GET /api/candidates", f"{type(e).__name__}: {e}")
    
    # Test 2: GET /api/candidates/{specific_id}
    print("\n2. GET /api/candidates/63baf66b-555d-42cf-ab8f-c9a2c5f75fc3")
    try:
        resp = requests.get(f"{BACKEND_URL}/candidates/63baf66b-555d-42cf-ab8f-c9a2c5f75fc3", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            notice_period_meta = data.get('notice_period_meta', {})
            value = notice_period_meta.get('value')
            if value == "60 days":
                log_pass("GET specific candidate", f"200, notice_period_meta.value = '60 days' (seeded data intact)")
            else:
                log_warn("GET specific candidate", f"200, but notice_period_meta.value = '{value}' (expected '60 days')")
        else:
            log_fail("GET specific candidate", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("GET specific candidate", f"{type(e).__name__}: {e}")
    
    # Test 3: GET /api/candidates/bulk-scan-replies/status
    print("\n3. GET /api/candidates/bulk-scan-replies/status")
    try:
        resp = requests.get(f"{BACKEND_URL}/candidates/bulk-scan-replies/status", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Check for undo fields
            if 'can_undo' in data:
                log_pass("GET bulk-scan-replies/status", f"200, has 'can_undo' field")
            else:
                log_warn("GET bulk-scan-replies/status", f"200, but missing 'can_undo' field")
        else:
            log_fail("GET bulk-scan-replies/status", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("GET bulk-scan-replies/status", f"{type(e).__name__}: {e}")

def test_g_timing_validation(token):
    """Test G: The actual bug validation - can 4 files complete without Cloudflare 520?"""
    print("\n" + "="*60)
    print("TEST G: Timing Validation (Critical Bug Fix Test)")
    print("="*60)
    print("This is the most important test: can a batch of 4 files complete")
    print("without a Cloudflare 520 timeout?")
    
    # Create 4 test files with realistic names
    files = []
    names = ["John Anderson", "Sarah Martinez", "Michael Chen", "Jessica Brown"]
    for name in names:
        pdf_data = make_tiny_pdf(name)
        filename = f"{name.replace(' ', '_').lower()}_resume.pdf"
        files.append(('files', (filename, io.BytesIO(pdf_data), 'application/pdf')))
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\nUploading {len(files)} files for timing validation...")
    start_time = time.time()
    
    try:
        resp = requests.post(
            f"{BACKEND_URL}/resumes/parse-bulk",
            files=files,
            headers=headers,
            timeout=120
        )
        elapsed = time.time() - start_time
        
        print(f"\n⏱️  Wall-clock time: {elapsed:.2f}s")
        
        # Check if we got a response (any 2xx)
        if 200 <= resp.status_code < 300:
            log_pass("Timing: Got response", f"Received {resp.status_code} response")
        else:
            log_fail("Timing: Got response", f"Status {resp.status_code}: {resp.text[:200]}")
            return
        
        # Check timing (must be under 100s)
        if elapsed < 100:
            log_pass("Timing: Under 100s", f"{elapsed:.2f}s < 100s (no Cloudflare timeout risk)")
        else:
            log_fail("Timing: Under 100s", f"{elapsed:.2f}s >= 100s (WOULD TRIGGER CLOUDFLARE 520)")
        
        # Parse response
        data = resp.json()
        results_list = data.get('results', [])
        
        successes = [r for r in results_list if r.get('status') == 'success']
        failures = [r for r in results_list if r.get('status') != 'success']
        
        print(f"\n📊 Batch results:")
        print(f"   Successes: {len(successes)}/{len(results_list)}")
        print(f"   Failures: {len(failures)}/{len(results_list)}")
        
        if len(successes) > 0:
            log_pass("Timing: Some successes", f"{len(successes)}/{len(results_list)} files parsed successfully")
        else:
            log_fail("Timing: Some successes", f"0/{len(results_list)} files succeeded")
        
        # Check for concurrent_request_limit errors in backend logs
        print("\n🔍 Checking backend logs for concurrent_request_limit errors...")
        try:
            import subprocess
            log_output = subprocess.check_output(
                "tail -n 100 /var/log/supervisor/backend.err.log | grep -i 'concurrent_request_limit' | tail -n 5",
                shell=True,
                stderr=subprocess.STDOUT,
                text=True
            )
            if log_output.strip():
                log_warn("Backend logs: concurrent errors", f"Found recent concurrent_request_limit errors in logs (but request completed)")
                print(f"   Last few occurrences:\n{log_output}")
            else:
                log_pass("Backend logs: No concurrent errors", "No concurrent_request_limit errors in recent logs")
        except subprocess.CalledProcessError:
            log_pass("Backend logs: No concurrent errors", "No concurrent_request_limit errors found")
        
        # Final verdict
        if elapsed < 100 and len(successes) > 0:
            print("\n" + "="*60)
            print("✅ BUG FIX VERIFIED: Bulk upload completes without Cloudflare 520")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("❌ BUG FIX NOT VERIFIED: Issues remain")
            print("="*60)
        
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        log_fail("Timing: Request timeout", f"Request timed out after {elapsed:.2f}s (CLOUDFLARE 520 LIKELY)")
    except Exception as e:
        log_fail("Timing: Exception", f"{type(e).__name__}: {e}")

def print_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✅ Passed: {len(results['passed'])}")
    print(f"❌ Failed: {len(results['failed'])}")
    print(f"⚠️  Warnings: {len(results['warnings'])}")
    print()
    
    if results['failed']:
        print("Failed tests:")
        for test in results['failed']:
            print(f"  - {test}")
        print()
    
    if results['warnings']:
        print("Warnings:")
        for test in results['warnings']:
            print(f"  - {test}")
        print()
    
    pass_rate = len(results['passed']) / (len(results['passed']) + len(results['failed'])) * 100 if (len(results['passed']) + len(results['failed'])) > 0 else 0
    print(f"Pass rate: {pass_rate:.1f}%")
    print("="*60)

def main():
    print("="*60)
    print("BULK RESUME UPLOAD FIX VERIFICATION")
    print("="*60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print()
    
    # Login
    token = login()
    
    # Run all tests
    test_a_llm_concurrency()
    test_b_bulk_upload_4_files(token)
    test_c_single_resume(token)
    test_d_over_limit(token)
    test_e_empty_batch(token)
    test_f_regression(token)
    test_g_timing_validation(token)
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    if results['failed']:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
