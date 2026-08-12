#!/usr/bin/env python3
"""
Test suite for Gemini smart notes + transcription feature in Interview scheduling API.

Review request: Verify new "Gemini smart notes + transcription" feature.
- New google_meet.py module with create_ai_meet_space() and has_meet_ai_scopes()
- google_calendar.py SCOPES now includes meet scopes
- GET /api/calendar/status returns can_create_meet_ai field
- POST /api/interviews accepts enable_gemini_ai field (defaults to True)

Admin user (admin@ats.com) does NOT have Google Calendar connected in this dev DB,
so we CANNOT verify real Meet space creation end-to-end. Focus on API surface + contract.
"""

import os
import sys
import requests

# Backend URL from frontend/.env
BACKEND_URL = "https://recruit-full-load.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@ats.com"
ADMIN_PASSWORD = "Admin@123"

# Track created interviews for cleanup
created_interview_ids = []


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    data = resp.json()
    return data.get("token")


def test_1_calendar_status_has_can_create_meet_ai(token: str):
    """
    Test 1: GET /api/calendar/status → 200 with can_create_meet_ai field.
    Since admin has no google_tokens, this must be false and connected: false.
    """
    print("\n=== Test 1: GET /api/calendar/status → verify can_create_meet_ai field ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_URL}/calendar/status", headers=headers)
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"   Response: {data}")
    
    # Verify required fields
    if "can_create_meet_ai" not in data:
        print(f"❌ FAIL: Response missing 'can_create_meet_ai' field")
        return False
    
    if "connected" not in data:
        print(f"❌ FAIL: Response missing 'connected' field")
        return False
    
    # Admin has no google_tokens, so both should be false
    if data["connected"] is not False:
        print(f"❌ FAIL: Expected connected=false, got {data['connected']}")
        return False
    
    if data["can_create_meet_ai"] is not False:
        print(f"❌ FAIL: Expected can_create_meet_ai=false (no tokens), got {data['can_create_meet_ai']}")
        return False
    
    print(f"✅ PASS: can_create_meet_ai={data['can_create_meet_ai']}, connected={data['connected']}")
    return True


def test_2_create_interview_with_enable_gemini_ai_true(token: str, candidate_id: str, admin_user_id: str):
    """
    Test 2: POST /api/interviews with enable_gemini_ai: true.
    Interview returned MUST have enable_gemini_ai: true.
    Should NOT have meet_space_name populated (no calendar connection).
    """
    print("\n=== Test 2: POST /api/interviews with enable_gemini_ai: true ===")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "candidate_id": candidate_id,
        "type": "phone_screen",
        "interviewer_ids": [admin_user_id],
        "scheduled_at": "2026-08-01T14:00:00Z",
        "timezone": "UTC",
        "duration_min": 45,
        "enable_gemini_ai": True
    }
    
    resp = requests.post(f"{BACKEND_URL}/interviews", json=body, headers=headers)
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    data = resp.json()
    interview_id = data.get("id")
    if interview_id:
        created_interview_ids.append(interview_id)
    
    print(f"   Created interview ID: {interview_id}")
    print(f"   enable_gemini_ai: {data.get('enable_gemini_ai')}")
    print(f"   gemini_ai_status: {data.get('gemini_ai_status')}")
    print(f"   meet_space_name: {data.get('meet_space_name')}")
    print(f"   status: {data.get('status')}")
    
    # Verify enable_gemini_ai is true
    if data.get("enable_gemini_ai") is not True:
        print(f"❌ FAIL: Expected enable_gemini_ai=true, got {data.get('enable_gemini_ai')}")
        return False
    
    # Should NOT have meet_space_name (no calendar connection)
    if data.get("meet_space_name"):
        print(f"⚠️  WARNING: meet_space_name is populated despite no calendar connection: {data.get('meet_space_name')}")
    
    # Status should be scheduled
    if data.get("status") != "scheduled":
        print(f"❌ FAIL: Expected status='scheduled', got {data.get('status')}")
        return False
    
    print(f"✅ PASS: Interview created with enable_gemini_ai=true")
    return True


def test_3_create_interview_with_enable_gemini_ai_false(token: str, candidate_id: str, admin_user_id: str):
    """
    Test 3: POST /api/interviews with enable_gemini_ai: false.
    Interview returned should have enable_gemini_ai: false.
    """
    print("\n=== Test 3: POST /api/interviews with enable_gemini_ai: false ===")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "candidate_id": candidate_id,
        "type": "phone_screen",
        "interviewer_ids": [admin_user_id],
        "scheduled_at": "2026-08-02T14:00:00Z",
        "timezone": "UTC",
        "duration_min": 45,
        "enable_gemini_ai": False
    }
    
    resp = requests.post(f"{BACKEND_URL}/interviews", json=body, headers=headers)
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    data = resp.json()
    interview_id = data.get("id")
    if interview_id:
        created_interview_ids.append(interview_id)
    
    print(f"   Created interview ID: {interview_id}")
    print(f"   enable_gemini_ai: {data.get('enable_gemini_ai')}")
    
    # Verify enable_gemini_ai is false
    if data.get("enable_gemini_ai") is not False:
        print(f"❌ FAIL: Expected enable_gemini_ai=false, got {data.get('enable_gemini_ai')}")
        return False
    
    print(f"✅ PASS: Interview created with enable_gemini_ai=false")
    return True


def test_4_create_interview_without_enable_gemini_ai(token: str, candidate_id: str, admin_user_id: str):
    """
    Test 4: POST /api/interviews WITHOUT enable_gemini_ai key.
    Should default to true per pydantic model.
    """
    print("\n=== Test 4: POST /api/interviews WITHOUT enable_gemini_ai key (should default true) ===")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "candidate_id": candidate_id,
        "type": "phone_screen",
        "interviewer_ids": [admin_user_id],
        "scheduled_at": "2026-08-03T14:00:00Z",
        "timezone": "UTC",
        "duration_min": 45
        # NOTE: enable_gemini_ai is NOT included
    }
    
    resp = requests.post(f"{BACKEND_URL}/interviews", json=body, headers=headers)
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    data = resp.json()
    interview_id = data.get("id")
    if interview_id:
        created_interview_ids.append(interview_id)
    
    print(f"   Created interview ID: {interview_id}")
    print(f"   enable_gemini_ai: {data.get('enable_gemini_ai')}")
    
    # Verify enable_gemini_ai defaults to true
    if data.get("enable_gemini_ai") is not True:
        print(f"❌ FAIL: Expected enable_gemini_ai=true (default), got {data.get('enable_gemini_ai')}")
        return False
    
    print(f"✅ PASS: Interview created with enable_gemini_ai defaulting to true")
    return True


def test_5_python_module_has_meet_ai_scopes():
    """
    Test 5: Verify has_meet_ai_scopes helper works correctly.
    Run: python3 -c "from google_meet import has_meet_ai_scopes; ..."
    """
    print("\n=== Test 5: Python module test - has_meet_ai_scopes helper ===")
    
    test_script = """
from google_meet import has_meet_ai_scopes

# Test 1: Both scopes present
assert has_meet_ai_scopes('https://www.googleapis.com/auth/meetings.space.created https://www.googleapis.com/auth/meetings.space.settings') is True, "Test 1 failed"

# Test 2: Only calendar scope (missing meet scopes)
assert has_meet_ai_scopes('https://www.googleapis.com/auth/calendar') is False, "Test 2 failed"

# Test 3: Empty string
assert has_meet_ai_scopes('') is False, "Test 3 failed"

# Test 4: Only one meet scope (missing the other)
assert has_meet_ai_scopes('https://www.googleapis.com/auth/meetings.space.created') is False, "Test 4 failed"

print('helper OK')
"""
    
    import subprocess
    result = subprocess.run(
        ["python3", "-c", test_script],
        cwd="/app/backend",
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ FAIL: Python script exited with code {result.returncode}")
        print(f"   stdout: {result.stdout}")
        print(f"   stderr: {result.stderr}")
        return False
    
    if "helper OK" not in result.stdout:
        print(f"❌ FAIL: Expected 'helper OK' in output")
        print(f"   stdout: {result.stdout}")
        return False
    
    print(f"   {result.stdout.strip()}")
    print(f"✅ PASS: has_meet_ai_scopes helper works correctly")
    return True


def test_6_google_calendar_scopes_includes_meet():
    """
    Test 6: Confirm google_calendar.SCOPES includes both meet scopes.
    Run: cd /app/backend && python3 -c "from google_calendar import SCOPES; ..."
    """
    print("\n=== Test 6: Python module test - SCOPES includes meet scopes ===")
    
    test_script = """
from google_calendar import SCOPES
scopes_str = ' '.join(SCOPES)
has_created = 'space.created' in scopes_str
has_settings = 'space.settings' in scopes_str
print(has_created, has_settings)
"""
    
    import subprocess
    result = subprocess.run(
        ["python3", "-c", test_script],
        cwd="/app/backend",
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ FAIL: Python script exited with code {result.returncode}")
        print(f"   stdout: {result.stdout}")
        print(f"   stderr: {result.stderr}")
        return False
    
    output = result.stdout.strip()
    print(f"   Output: {output}")
    
    if output != "True True":
        print(f"❌ FAIL: Expected 'True True', got '{output}'")
        return False
    
    print(f"✅ PASS: SCOPES includes both 'space.created' and 'space.settings'")
    return True


def test_7_google_apps_meet_import():
    """
    Test 7: Confirm google-apps-meet==0.5.0 is in requirements.txt
    and imports without error.
    """
    print("\n=== Test 7: Python module test - google-apps-meet import ===")
    
    # Check requirements.txt
    import subprocess
    result = subprocess.run(
        ["grep", "google-apps-meet", "/app/backend/requirements.txt"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ FAIL: google-apps-meet not found in requirements.txt")
        return False
    
    print(f"   requirements.txt: {result.stdout.strip()}")
    
    if "google-apps-meet==0.5.0" not in result.stdout:
        print(f"❌ FAIL: Expected google-apps-meet==0.5.0, got {result.stdout.strip()}")
        return False
    
    # Test import
    test_script = """
from google.apps import meet_v2beta
client_class = meet_v2beta.SpacesServiceClient
print(f'Import OK: {client_class.__name__}')
"""
    
    result = subprocess.run(
        ["python3", "-c", test_script],
        cwd="/app/backend",
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ FAIL: Import failed with code {result.returncode}")
        print(f"   stdout: {result.stdout}")
        print(f"   stderr: {result.stderr}")
        return False
    
    print(f"   {result.stdout.strip()}")
    print(f"✅ PASS: google-apps-meet==0.5.0 in requirements.txt and imports correctly")
    return True


def test_8_regression_password_reset():
    """
    Test 8: Regression - password-reset flow still works.
    POST /api/auth/forgot-password with {"email":"kangabhijeet@gmail.com"} → 200 ok:true.
    Do NOT actually reset the password.
    """
    print("\n=== Test 8: Regression - password-reset flow ===")
    
    resp = requests.post(
        f"{BACKEND_URL}/auth/forgot-password",
        json={"email": "kangabhijeet@gmail.com"}
    )
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    data = resp.json()
    print(f"   Response: {data}")
    
    if data.get("ok") is not True:
        print(f"❌ FAIL: Expected ok=true, got {data.get('ok')}")
        return False
    
    print(f"✅ PASS: Password reset endpoint returns ok=true")
    return True


def test_9_cleanup_interviews(token: str):
    """
    Test 9: Cleanup - delete the 3 interviews created in tests 2/3/4.
    """
    print("\n=== Test 9: Cleanup - delete created interviews ===")
    
    if not created_interview_ids:
        print("   No interviews to clean up")
        return True
    
    headers = {"Authorization": f"Bearer {token}"}
    success_count = 0
    
    for interview_id in created_interview_ids:
        # Cancel the interview (set status to cancelled)
        resp = requests.put(
            f"{BACKEND_URL}/interviews/{interview_id}",
            json={"status": "cancelled"},
            headers=headers
        )
        
        if resp.status_code == 200:
            print(f"   ✅ Cancelled interview {interview_id}")
            success_count += 1
        else:
            print(f"   ⚠️  Failed to cancel interview {interview_id}: {resp.status_code}")
    
    print(f"✅ PASS: Cleaned up {success_count}/{len(created_interview_ids)} interviews")
    return True


def main():
    print("=" * 80)
    print("Gemini Smart Notes + Transcription Feature Test Suite")
    print("=" * 80)
    
    # Login as admin
    print(f"\n🔐 Logging in as {ADMIN_EMAIL}...")
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    print(f"✅ Login successful")
    
    # Get admin user ID
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = requests.get(f"{BACKEND_URL}/auth/me", headers=headers)
    if me_resp.status_code != 200:
        print(f"❌ Failed to get current user: {me_resp.status_code}")
        sys.exit(1)
    admin_user = me_resp.json()
    admin_user_id = admin_user.get("id")
    print(f"   Admin user ID: {admin_user_id}")
    
    # Get a candidate ID for testing
    candidates_resp = requests.get(f"{BACKEND_URL}/candidates?limit=1", headers=headers)
    if candidates_resp.status_code != 200:
        print(f"❌ Failed to get candidates: {candidates_resp.status_code}")
        sys.exit(1)
    candidates = candidates_resp.json()
    if not candidates:
        print(f"❌ No candidates found in database")
        sys.exit(1)
    candidate_id = candidates[0].get("id")
    print(f"   Using candidate ID: {candidate_id} ({candidates[0].get('name')})")
    
    # Run all tests
    results = []
    
    results.append(("Test 1: calendar/status has can_create_meet_ai", 
                    test_1_calendar_status_has_can_create_meet_ai(token)))
    
    results.append(("Test 2: POST interviews with enable_gemini_ai=true", 
                    test_2_create_interview_with_enable_gemini_ai_true(token, candidate_id, admin_user_id)))
    
    results.append(("Test 3: POST interviews with enable_gemini_ai=false", 
                    test_3_create_interview_with_enable_gemini_ai_false(token, candidate_id, admin_user_id)))
    
    results.append(("Test 4: POST interviews without enable_gemini_ai (default true)", 
                    test_4_create_interview_without_enable_gemini_ai(token, candidate_id, admin_user_id)))
    
    results.append(("Test 5: has_meet_ai_scopes helper", 
                    test_5_python_module_has_meet_ai_scopes()))
    
    results.append(("Test 6: SCOPES includes meet scopes", 
                    test_6_google_calendar_scopes_includes_meet()))
    
    results.append(("Test 7: google-apps-meet import", 
                    test_7_google_apps_meet_import()))
    
    results.append(("Test 8: Regression - password reset", 
                    test_8_regression_password_reset()))
    
    results.append(("Test 9: Cleanup interviews", 
                    test_9_cleanup_interviews(token)))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{'=' * 80}")
    print(f"TOTAL: {passed}/{total} tests passed ({100*passed//total}% pass rate)")
    print(f"{'=' * 80}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
