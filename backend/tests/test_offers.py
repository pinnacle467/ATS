"""Backend tests for Offer Letter Approval Workflow (Lever-style).
Covers: create offer, sequential approval chain, rejection, cancel,
letter preview, send + public accept/decline flow, template CRUD.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@ats.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def test_users(session):
    """Create two temp approver users with known passwords, cleanup after module."""
    created = []
    for i, role in enumerate(["admin", "interview_panel"]):
        payload = {
            "name": f"TEST_Approver{i+1}",
            "email": f"test_approver{i+1}_{int(time.time())}@example.com",
            "password": "Approver@123",
            "role": role,
        }
        r = session.post(f"{API}/users", json=payload)
        assert r.status_code in (200, 201), r.text
        u = r.json()
        u["password"] = payload["password"]
        created.append(u)
    yield created
    for u in created:
        session.delete(f"{API}/users/{u['id']}")


@pytest.fixture(scope="module")
def test_candidate(session):
    r = session.get(f"{API}/candidates", params={"limit": 1})
    assert r.status_code == 200
    candidates = r.json() if isinstance(r.json(), list) else r.json().get("candidates", [])
    if not candidates:
        pytest.skip("No candidates available to attach offer to")
    return candidates[0]


class TestOfferLifecycle:
    def test_create_offer_requires_approvers(self, session, test_candidate):
        r = session.post(f"{API}/offers", json={"candidate_id": test_candidate["id"], "approvers": []})
        assert r.status_code == 422

    def test_create_offer_success(self, session, test_candidate, test_users):
        payload = {
            "candidate_id": test_candidate["id"],
            "start_date": "2026-03-01",
            "base_salary": 120000,
            "salary_currency": "USD",
            "bonus": "10% annual",
            "equity": "5000 RSUs",
            "reporting_manager": "Jane Doe",
            "offer_expiry_date": "2026-02-20",
            "custom_notes": "Welcome aboard!",
            "approvers": [{"user_id": test_users[0]["id"]}, {"user_id": test_users[1]["id"]}],
        }
        r = session.post(f"{API}/offers", json=payload)
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer["status"] == "pending_approval"
        assert offer["current_step"] == 1
        assert len(offer["approvers"]) == 2
        assert offer["approvers"][0]["user_id"] == test_users[0]["id"]
        assert offer["approvers"][0]["status"] == "pending"
        assert offer["candidate_id"] == test_candidate["id"]
        pytest.offer_id = offer["id"]

    def test_get_offer(self, session, test_candidate):
        r = session.get(f"{API}/offers/{pytest.offer_id}")
        assert r.status_code == 200
        assert r.json()["id"] == pytest.offer_id

    def test_wrong_user_cannot_approve(self, session):
        """Admin (creator) is not step-1 approver -> should be forbidden."""
        r = session.post(f"{API}/offers/{pytest.offer_id}/approve", json={})
        assert r.status_code == 403

    def test_step1_approver_approves(self, test_users):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": test_users[0]["email"], "password": test_users[0]["password"]})
        assert r.status_code == 200, r.text
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})

        r = s.post(f"{API}/offers/{pytest.offer_id}/approve", json={"comment": "Looks good"})
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer["current_step"] == 2
        assert offer["status"] == "pending_approval"
        assert offer["approvers"][0]["status"] == "approved"
        assert offer["approvers"][0]["comment"] == "Looks good"

    def test_step1_approver_cannot_approve_again(self, test_users):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": test_users[0]["email"], "password": test_users[0]["password"]})
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})
        r = s.post(f"{API}/offers/{pytest.offer_id}/approve", json={})
        assert r.status_code == 403

    def test_step2_approver_approves_completes_offer(self, test_users):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": test_users[1]["email"], "password": test_users[1]["password"]})
        assert r.status_code == 200
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})

        r = s.post(f"{API}/offers/{pytest.offer_id}/approve", json={})
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer["status"] == "approved"

    def test_preview_letter(self, session):
        r = session.get(f"{API}/offers/{pytest.offer_id}/letter")
        assert r.status_code == 200
        data = r.json()
        assert "html" in data and "subject" in data
        assert "120,000" in data["html"] or "120000" in data["html"]

    def test_send_offer_generates_link(self, session):
        r = session.post(f"{API}/offers/{pytest.offer_id}/send")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "link" in data
        assert "/offer/" in data["link"]
        pytest.offer_link_token = data["link"].split("/offer/")[-1]

    def test_public_get_offer(self):
        r = requests.get(f"{API}/offers/public/{pytest.offer_link_token}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "sent"
        assert "letter_html" in data

    def test_public_respond_accept(self):
        r = requests.post(f"{API}/offers/public/{pytest.offer_link_token}/respond", json={"response": "accepted"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_public_respond_idempotent_blocked(self):
        r = requests.post(f"{API}/offers/public/{pytest.offer_link_token}/respond", json={"response": "declined"})
        assert r.status_code == 404

    def test_public_get_after_response_shows_accepted(self):
        r = requests.get(f"{API}/offers/public/{pytest.offer_link_token}")
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_invalid_token_returns_404(self):
        r = requests.get(f"{API}/offers/public/some-fake-token-xyz")
        assert r.status_code == 404


class TestRejectionFlow:
    def test_reject_empty_comment_blocked(self, session, test_candidate, test_users):
        r = session.post(f"{API}/offers", json={
            "candidate_id": test_candidate["id"],
            "approvers": [{"user_id": test_users[0]["id"]}],
        })
        assert r.status_code == 200
        offer_id = r.json()["id"]
        pytest.reject_offer_id = offer_id

        s = requests.Session()
        lr = s.post(f"{API}/auth/login", json={"email": test_users[0]["email"], "password": test_users[0]["password"]})
        token = lr.json().get("access_token") or lr.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})

        r = s.post(f"{API}/offers/{offer_id}/reject", json={"comment": ""})
        assert r.status_code == 422

        r = s.post(f"{API}/offers/{offer_id}/reject", json={"comment": "Salary mismatch"})
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer["status"] == "rejected"
        assert offer["approvers"][0]["comment"] == "Salary mismatch"

    def test_cancel_offer(self, session, test_candidate, test_users):
        r = session.post(f"{API}/offers", json={
            "candidate_id": test_candidate["id"],
            "approvers": [{"user_id": test_users[0]["id"]}],
        })
        offer_id = r.json()["id"]
        r = session.post(f"{API}/offers/{offer_id}/cancel")
        assert r.status_code == 200
        r = session.get(f"{API}/offers/{offer_id}")
        assert r.json()["status"] == "cancelled"


class TestTemplateSettings:
    def test_get_template(self, session):
        r = session.get(f"{API}/offers/settings/template")
        assert r.status_code == 200
        data = r.json()
        assert "subject" in data and "html_body" in data

    def test_update_and_persist_template(self, session):
        r = session.get(f"{API}/offers/settings/template")
        original = r.json()
        new_subject = "TEST_Subject_" + str(int(time.time()))
        r = session.put(f"{API}/offers/settings/template", json={
            "subject": new_subject, "html_body": original["html_body"],
        })
        assert r.status_code == 200
        assert r.json()["subject"] == new_subject

        r = session.get(f"{API}/offers/settings/template")
        assert r.json()["subject"] == new_subject

        # restore original
        session.put(f"{API}/offers/settings/template", json={
            "subject": original["subject"], "html_body": original["html_body"],
        })

    def test_non_admin_cannot_access_template(self, test_users):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": test_users[1]["email"], "password": test_users[1]["password"]})
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})
        r = s.get(f"{API}/offers/settings/template")
        assert r.status_code == 403


class TestListAndFilters:
    def test_list_offers(self, session):
        r = session.get(f"{API}/offers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pending_my_approval_filter(self, test_users):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": test_users[0]["email"], "password": test_users[0]["password"]})
        token = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {token}"})
        r = s.get(f"{API}/offers", params={"pending_my_approval": True})
        assert r.status_code == 200
        for o in r.json():
            assert o["status"] == "pending_approval"
