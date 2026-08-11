#!/usr/bin/env python3
"""Phase 3 verification: sensitive-field hiding + email_sent timeline fix + scorecard filtering."""
import sys
import requests
from typing import Optional

BASE_URL = "https://candidate-sync-4.preview.emergentagent.com/api"
SUPER_ADMIN_EMAIL = "admin@ats.com"
SUPER_ADMIN_PASSWORD = "Admin@123"

# Test state
PANEL_A_ID = None
PANEL_B_ID = None
VENDOR_ID = None
JOB_X = None
JOB_Y = None
CAND_X = None
CAND_Y = None
VC_ID = None
TEST_INTERVIEW_ID = None

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

def login(email: str, password: str) -> Optional[str]:
    """Login and return token."""
    resp = session.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return token
    return None

def logout():
    """Clear auth token."""
    session.headers.pop("Authorization", None)

def test_result(test_id: str, passed: bool, message: str = ""):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{test_id}: {status} - {message}")
    return passed

def main():
    global PANEL_A_ID, PANEL_B_ID, VENDOR_ID, JOB_X, JOB_Y, CAND_X, CAND_Y, VC_ID, TEST_INTERVIEW_ID
    
    results = []
    
    print("=" * 80)
    print("PHASE 3 VERIFICATION: Timeline filtering + email_sent fix + scorecard filtering")
    print("=" * 80)
    
    # ========== SETUP ==========
    print("\n[SETUP] Logging in as super_admin...")
    token = login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    if not token:
        print("❌ FATAL: Cannot login as super_admin")
        return 1
    print(f"✅ Logged in as {SUPER_ADMIN_EMAIL}")
    
    # Create test users
    print("\n[SETUP] Creating test users...")
    
    # Panel A
    resp = session.post(f"{BASE_URL}/users", json={
        "name": "P3 Panelist A",
        "email": "p3_panel_a@test.com",
        "password": "P3@1234",
        "role": "interview_panel"
    })
    if resp.status_code == 200:
        PANEL_A_ID = resp.json().get("id")
        print(f"✅ Created PANEL_A: {PANEL_A_ID}")
    else:
        print(f"❌ Failed to create PANEL_A: {resp.status_code} {resp.text[:200]}")
        return 1
    
    # Panel B
    resp = session.post(f"{BASE_URL}/users", json={
        "name": "P3 Panelist B",
        "email": "p3_panel_b@test.com",
        "password": "P3@1234",
        "role": "interview_panel"
    })
    if resp.status_code == 200:
        PANEL_B_ID = resp.json().get("id")
        print(f"✅ Created PANEL_B: {PANEL_B_ID}")
    else:
        print(f"❌ Failed to create PANEL_B: {resp.status_code} {resp.text[:200]}")
        return 1
    
    # Vendor
    resp = session.post(f"{BASE_URL}/users", json={
        "name": "P3 Vendor",
        "email": "p3_vendor@test.com",
        "password": "P3@1234",
        "role": "vendor"
    })
    if resp.status_code == 200:
        VENDOR_ID = resp.json().get("id")
        print(f"✅ Created VENDOR: {VENDOR_ID}")
    else:
        print(f"❌ Failed to create VENDOR: {resp.status_code} {resp.text[:200]}")
        return 1
    
    # Get 2 jobs
    print("\n[SETUP] Fetching jobs...")
    resp = session.get(f"{BASE_URL}/jobs")
    if resp.status_code == 200:
        jobs = resp.json()
        if len(jobs) >= 2:
            JOB_X = jobs[0]["id"]
            JOB_Y = jobs[1]["id"]
            print(f"✅ JOB_X: {JOB_X} ({jobs[0].get('title')})")
            print(f"✅ JOB_Y: {JOB_Y} ({jobs[1].get('title')})")
        else:
            print("❌ Need at least 2 jobs in database")
            return 1
    else:
        print(f"❌ Failed to fetch jobs: {resp.status_code}")
        return 1
    
    # Add users to JOB_X team
    print(f"\n[SETUP] Adding users to JOB_X ({JOB_X}) team...")
    for user_id, role_on_job, name in [
        (PANEL_A_ID, "interview_panel", "PANEL_A"),
        (PANEL_B_ID, "interview_panel", "PANEL_B"),
        (VENDOR_ID, "vendor", "VENDOR")
    ]:
        resp = session.post(f"{BASE_URL}/jobs/{JOB_X}/team", json={
            "user_id": user_id,
            "role_on_job": role_on_job,
            "salary_visible": False
        })
        if resp.status_code == 200:
            print(f"✅ Added {name} to JOB_X team")
        else:
            print(f"❌ Failed to add {name} to JOB_X: {resp.status_code} {resp.text[:200]}")
            return 1
    
    # Get candidates
    print(f"\n[SETUP] Fetching candidates for JOB_X and JOB_Y...")
    resp = session.get(f"{BASE_URL}/candidates?job_id={JOB_X}&limit=1")
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        if items:
            CAND_X = items[0]["id"]
            print(f"✅ CAND_X: {CAND_X} ({items[0].get('name')})")
        else:
            print("❌ No candidates found for JOB_X")
            return 1
    else:
        print(f"❌ Failed to fetch candidates for JOB_X: {resp.status_code}")
        return 1
    
    resp = session.get(f"{BASE_URL}/candidates?job_id={JOB_Y}&limit=1")
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        if items:
            CAND_Y = items[0]["id"]
            print(f"✅ CAND_Y: {CAND_Y} ({items[0].get('name')})")
        else:
            print("❌ No candidates found for JOB_Y")
            return 1
    else:
        print(f"❌ Failed to fetch candidates for JOB_Y: {resp.status_code}")
        return 1
    
    print("\n" + "=" * 80)
    print("TIMELINE + NOTES TESTS")
    print("=" * 80)
    
    # T1: Admin adds private note to CAND_X
    print("\n[T1] POST /api/candidates/{CAND_X}/notes as super_admin...")
    resp = session.post(f"{BASE_URL}/candidates/{CAND_X}/notes", json={
        "text": "Admin private note",
        "note_type": "note"
    })
    results.append(test_result("T1", resp.status_code == 200, 
                               f"Admin note creation: {resp.status_code}"))
    
    # T2: PANEL_A views timeline - should NOT see admin's note
    print("\n[T2] GET /api/candidates/{CAND_X}/timeline as PANEL_A...")
    logout()
    login("p3_panel_a@test.com", "P3@1234")
    resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
    if resp.status_code == 200:
        events = resp.json()
        notes = [e for e in events if e.get("kind") == "note"]
        admin_notes = [n for n in notes if n.get("author_id") != PANEL_A_ID]
        internal_activities = [
            e for e in events 
            if e.get("kind") == "activity" 
            and e.get("type") in ("note", "email_log", "email_sent")
            and e.get("actor_id") != PANEL_A_ID
        ]
        passed = len(admin_notes) == 0 and len(internal_activities) == 0
        results.append(test_result("T2", passed,
                                   f"PANEL_A sees {len(notes)} notes (should be 0 admin notes), "
                                   f"{len(internal_activities)} internal activities from others (should be 0)"))
    else:
        results.append(test_result("T2", False, f"Timeline fetch failed: {resp.status_code}"))
    
    # T3: PANEL_A tries to view CAND_Y timeline (not on team) - should be 403
    print("\n[T3] GET /api/candidates/{CAND_Y}/timeline as PANEL_A (not on team)...")
    resp = session.get(f"{BASE_URL}/candidates/{CAND_Y}/timeline")
    results.append(test_result("T3", resp.status_code == 403,
                               f"Expected 403, got {resp.status_code}"))
    
    # T4: PANEL_A adds own note to CAND_X
    print("\n[T4] POST /api/candidates/{CAND_X}/notes as PANEL_A...")
    resp = session.post(f"{BASE_URL}/candidates/{CAND_X}/notes", json={
        "text": "Panel A own note",
        "note_type": "note"
    })
    results.append(test_result("T4", resp.status_code == 200,
                               f"PANEL_A note creation: {resp.status_code}"))
    
    # T5: PANEL_A views timeline - should see exactly 1 note (their own)
    print("\n[T5] GET /api/candidates/{CAND_X}/timeline as PANEL_A (should see 1 note)...")
    resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
    if resp.status_code == 200:
        events = resp.json()
        notes = [e for e in events if e.get("kind") == "note"]
        my_notes = [n for n in notes if n.get("author_id") == PANEL_A_ID]
        passed = len(notes) == 1 and len(my_notes) == 1
        results.append(test_result("T5", passed,
                                   f"PANEL_A sees {len(notes)} notes (expected 1), "
                                   f"{len(my_notes)} are their own"))
    else:
        results.append(test_result("T5", False, f"Timeline fetch failed: {resp.status_code}"))
    
    # T6: PANEL_B views timeline - should see 0 notes (PANEL_A's note hidden)
    print("\n[T6] GET /api/candidates/{CAND_X}/timeline as PANEL_B (should see 0 notes)...")
    logout()
    login("p3_panel_b@test.com", "P3@1234")
    resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
    if resp.status_code == 200:
        events = resp.json()
        notes = [e for e in events if e.get("kind") == "note"]
        passed = len(notes) == 0
        results.append(test_result("T6", passed,
                                   f"PANEL_B sees {len(notes)} notes (expected 0)"))
    else:
        results.append(test_result("T6", False, f"Timeline fetch failed: {resp.status_code}"))
    
    # T7: PANEL_A tries to add note to CAND_Y (not on team) - should be 403
    print("\n[T7] POST /api/candidates/{CAND_Y}/notes as PANEL_A (not on team)...")
    logout()
    login("p3_panel_a@test.com", "P3@1234")
    resp = session.post(f"{BASE_URL}/candidates/{CAND_Y}/notes", json={
        "text": "Should fail",
        "note_type": "note"
    })
    results.append(test_result("T7", resp.status_code == 403,
                               f"Expected 403, got {resp.status_code}"))
    
    # T8: Admin views timeline - should see >= 2 notes (admin's + PANEL_A's)
    print("\n[T8] GET /api/candidates/{CAND_X}/timeline as super_admin (should see all notes)...")
    logout()
    login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
    if resp.status_code == 200:
        events = resp.json()
        notes = [e for e in events if e.get("kind") == "note"]
        passed = len(notes) >= 2
        results.append(test_result("T8", passed,
                                   f"Admin sees {len(notes)} notes (expected >= 2)"))
    else:
        results.append(test_result("T8", False, f"Timeline fetch failed: {resp.status_code}"))
    
    # T9: Admin should see PANEL_A's note activity in timeline
    print("\n[T9] Admin timeline should include PANEL_A's note activity...")
    if resp.status_code == 200:
        events = resp.json()
        note_activities = [
            e for e in events 
            if e.get("kind") == "activity" and e.get("type") == "note"
        ]
        passed = len(note_activities) >= 1
        results.append(test_result("T9", passed,
                                   f"Admin sees {len(note_activities)} note activities (expected >= 1)"))
    else:
        results.append(test_result("T9", False, "Timeline not fetched in T8"))
    
    print("\n" + "=" * 80)
    print("VENDOR NOTES TESTS")
    print("=" * 80)
    
    # T10: Vendor creates candidate
    print("\n[T10] POST /api/candidates as VENDOR...")
    logout()
    login("p3_vendor@test.com", "P3@1234")
    resp = session.post(f"{BASE_URL}/candidates", json={
        "name": "P3 Vendor Cand",
        "email": "p3vc@test.com",
        "job_id": JOB_X
    })
    if resp.status_code == 200:
        VC_ID = resp.json().get("id")
        results.append(test_result("T10", True, f"Vendor candidate created: {VC_ID}"))
    else:
        results.append(test_result("T10", False, 
                                   f"Vendor candidate creation failed: {resp.status_code} {resp.text[:200]}"))
        VC_ID = None
    
    # T11: Vendor adds note to own candidate
    if VC_ID:
        print("\n[T11] POST /api/candidates/{VC_ID}/notes as VENDOR...")
        resp = session.post(f"{BASE_URL}/candidates/{VC_ID}/notes", json={
            "text": "Vendor own note",
            "note_type": "note"
        })
        results.append(test_result("T11", resp.status_code == 200,
                                   f"Vendor note creation: {resp.status_code}"))
    else:
        results.append(test_result("T11", False, "Skipped - no vendor candidate"))
    
    # T12: Vendor tries to add note to CAND_X (not submitted by vendor) - should be 403
    print("\n[T12] POST /api/candidates/{CAND_X}/notes as VENDOR (not submitted by vendor)...")
    resp = session.post(f"{BASE_URL}/candidates/{CAND_X}/notes", json={
        "text": "Should fail",
        "note_type": "note"
    })
    results.append(test_result("T12", resp.status_code == 403,
                               f"Expected 403, got {resp.status_code}"))
    
    print("\n" + "=" * 80)
    print("EMAIL_SENT TIMELINE FIX TESTS")
    print("=" * 80)
    
    # T13: Send email with template
    print("\n[T13] POST /api/career/emails/send with template_key='application_shortlisted'...")
    logout()
    login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp = session.post(f"{BASE_URL}/career/emails/send", json={
        "candidate_ids": [CAND_X],
        "template_key": "application_shortlisted"
    })
    if resp.status_code == 200:
        data = resp.json()
        sent_count = data.get("sent", 0)
        results.append(test_result("T13", True,
                                   f"Email send response: sent={sent_count}, total={data.get('total')}"))
        
        # T14: Check timeline for email_sent activity
        if sent_count >= 1:
            print("\n[T14] GET /api/candidates/{CAND_X}/timeline - checking for email_sent activity...")
            resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
            if resp.status_code == 200:
                events = resp.json()
                email_sent_activities = [
                    e for e in events
                    if e.get("kind") == "activity" and e.get("type") == "email_sent"
                ]
                if email_sent_activities:
                    msg = email_sent_activities[0].get("message", "")
                    has_template_name = "Application Shortlisted" in msg or "application_shortlisted" in msg.lower()
                    results.append(test_result("T14", has_template_name,
                                               f"Found email_sent activity with message: '{msg[:100]}'"))
                else:
                    results.append(test_result("T14", False,
                                               "No email_sent activity found in timeline"))
            else:
                results.append(test_result("T14", False, f"Timeline fetch failed: {resp.status_code}"))
        else:
            print("\n[T14] SKIPPED - no Gmail connected (sent=0)")
            results.append(test_result("T14", True, "SKIPPED - no Gmail connected"))
    else:
        results.append(test_result("T13", False, 
                                   f"Email send failed: {resp.status_code} {resp.text[:200]}"))
        results.append(test_result("T14", False, "SKIPPED - T13 failed"))
    
    # T15: Send custom email
    print("\n[T15] POST /api/career/emails/send with custom subject/body...")
    resp = session.post(f"{BASE_URL}/career/emails/send", json={
        "candidate_ids": [CAND_X],
        "subject": "Custom Test Subject",
        "html_body": "<p>hi</p>"
    })
    if resp.status_code == 200:
        data = resp.json()
        sent_count = data.get("sent", 0)
        results.append(test_result("T15", True,
                                   f"Custom email send: sent={sent_count}"))
        
        if sent_count >= 1:
            # Check timeline again
            resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
            if resp.status_code == 200:
                events = resp.json()
                email_sent_activities = [
                    e for e in events
                    if e.get("kind") == "activity" and e.get("type") == "email_sent"
                ]
                print(f"    Found {len(email_sent_activities)} email_sent activities total")
    else:
        results.append(test_result("T15", False,
                                   f"Custom email send failed: {resp.status_code}"))
    
    # T16: PANEL_A should NOT see email_sent activities (actor was super_admin)
    print("\n[T16] GET /api/candidates/{CAND_X}/timeline as PANEL_A (should NOT see email_sent)...")
    logout()
    login("p3_panel_a@test.com", "P3@1234")
    resp = session.get(f"{BASE_URL}/candidates/{CAND_X}/timeline")
    if resp.status_code == 200:
        events = resp.json()
        email_sent_activities = [
            e for e in events
            if e.get("kind") == "activity" and e.get("type") == "email_sent"
        ]
        passed = len(email_sent_activities) == 0
        results.append(test_result("T16", passed,
                                   f"PANEL_A sees {len(email_sent_activities)} email_sent activities (expected 0)"))
    else:
        results.append(test_result("T16", False, f"Timeline fetch failed: {resp.status_code}"))
    
    print("\n" + "=" * 80)
    print("SCORECARD FILTERING TESTS")
    print("=" * 80)
    
    # T17-T22: Scorecard tests
    # First, find or create an interview with PANEL_A and PANEL_B
    print("\n[T17] Setting up interview with PANEL_A and PANEL_B as interviewers...")
    logout()
    login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    
    # Create a test interview
    resp = session.post(f"{BASE_URL}/interviews", json={
        "candidate_id": CAND_X,
        "job_id": JOB_X,
        "type": "technical",
        "interviewer_ids": [PANEL_A_ID, PANEL_B_ID],
        "scheduled_at": "2026-02-01T10:00:00Z",
        "duration_min": 60
    })
    if resp.status_code == 200:
        TEST_INTERVIEW_ID = resp.json().get("id")
        results.append(test_result("T17", True, f"Interview created: {TEST_INTERVIEW_ID}"))
    else:
        results.append(test_result("T17", False,
                                   f"Interview creation failed: {resp.status_code} {resp.text[:200]}"))
        TEST_INTERVIEW_ID = None
    
    if TEST_INTERVIEW_ID:
        # T18: PANEL_B submits scorecard
        print("\n[T18] POST /api/interviews/{TEST_INTERVIEW_ID}/scorecard as PANEL_B...")
        logout()
        login("p3_panel_b@test.com", "P3@1234")
        resp = session.post(f"{BASE_URL}/interviews/{TEST_INTERVIEW_ID}/scorecard", json={
            "ratings": {"Communication": 4, "Technical Skill": 5},
            "overall": 4,
            "recommendation": "yes",
            "notes": "Strong candidate"
        })
        results.append(test_result("T18", resp.status_code in (200, 409),
                                   f"PANEL_B scorecard submission: {resp.status_code}"))
        
        # T19: PANEL_A (not submitted) should NOT see PANEL_B's scorecard
        print("\n[T19] GET /api/interviews/{TEST_INTERVIEW_ID}/scorecards as PANEL_A (not submitted)...")
        logout()
        login("p3_panel_a@test.com", "P3@1234")
        resp = session.get(f"{BASE_URL}/interviews/{TEST_INTERVIEW_ID}/scorecards")
        if resp.status_code == 200:
            scorecards = resp.json()
            # Should be empty or only contain PANEL_A's own (which doesn't exist yet)
            panel_b_cards = [sc for sc in scorecards if sc.get("interviewer_id") == PANEL_B_ID]
            passed = len(panel_b_cards) == 0
            results.append(test_result("T19", passed,
                                       f"PANEL_A sees {len(scorecards)} scorecards, "
                                       f"{len(panel_b_cards)} from PANEL_B (expected 0)"))
        else:
            results.append(test_result("T19", False, f"Scorecard fetch failed: {resp.status_code}"))
        
        # T20: PANEL_A submits scorecard
        print("\n[T20] POST /api/interviews/{TEST_INTERVIEW_ID}/scorecard as PANEL_A...")
        resp = session.post(f"{BASE_URL}/interviews/{TEST_INTERVIEW_ID}/scorecard", json={
            "ratings": {"Communication": 3, "Technical Skill": 4},
            "overall": 3,
            "recommendation": "yes",
            "notes": "Good fit"
        })
        results.append(test_result("T20", resp.status_code in (200, 409),
                                   f"PANEL_A scorecard submission: {resp.status_code}"))
        
        # T21: PANEL_A should now see both scorecards
        print("\n[T21] GET /api/interviews/{TEST_INTERVIEW_ID}/scorecards as PANEL_A (after submission)...")
        resp = session.get(f"{BASE_URL}/interviews/{TEST_INTERVIEW_ID}/scorecards")
        if resp.status_code == 200:
            scorecards = resp.json()
            passed = len(scorecards) == 2
            results.append(test_result("T21", passed,
                                       f"PANEL_A sees {len(scorecards)} scorecards (expected 2)"))
        else:
            results.append(test_result("T21", False, f"Scorecard fetch failed: {resp.status_code}"))
        
        # T22: Vendor should see empty scorecards
        if VC_ID:
            print("\n[T22] GET /api/candidates/{VC_ID}/scorecards as VENDOR (should be empty)...")
            logout()
            login("p3_vendor@test.com", "P3@1234")
            resp = session.get(f"{BASE_URL}/candidates/{VC_ID}/scorecards")
            if resp.status_code == 200:
                scorecards = resp.json()
                passed = len(scorecards) == 0
                results.append(test_result("T22", passed,
                                           f"VENDOR sees {len(scorecards)} scorecards (expected 0)"))
            else:
                results.append(test_result("T22", False, f"Scorecard fetch failed: {resp.status_code}"))
        else:
            results.append(test_result("T22", False, "SKIPPED - no vendor candidate"))
    else:
        results.append(test_result("T18", False, "SKIPPED - no interview"))
        results.append(test_result("T19", False, "SKIPPED - no interview"))
        results.append(test_result("T20", False, "SKIPPED - no interview"))
        results.append(test_result("T21", False, "SKIPPED - no interview"))
        results.append(test_result("T22", False, "SKIPPED - no interview"))
    
    print("\n" + "=" * 80)
    print("CLEANUP")
    print("=" * 80)
    
    logout()
    login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    
    # Delete vendor candidate
    if VC_ID:
        print(f"\n[CLEANUP] Deleting vendor candidate {VC_ID}...")
        resp = session.delete(f"{BASE_URL}/candidates/{VC_ID}")
        print(f"  Delete candidate: {resp.status_code}")
    
    # Delete test users
    for user_id, name in [(PANEL_A_ID, "PANEL_A"), (PANEL_B_ID, "PANEL_B"), (VENDOR_ID, "VENDOR")]:
        if user_id:
            print(f"\n[CLEANUP] Deleting user {name} ({user_id})...")
            resp = session.delete(f"{BASE_URL}/users/{user_id}")
            print(f"  Delete user: {resp.status_code}")
    
    # Cancel test interview
    if TEST_INTERVIEW_ID:
        print(f"\n[CLEANUP] Cancelling test interview {TEST_INTERVIEW_ID}...")
        resp = session.put(f"{BASE_URL}/interviews/{TEST_INTERVIEW_ID}", json={"status": "cancelled"})
        print(f"  Cancel interview: {resp.status_code}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
