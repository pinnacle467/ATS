"""
Tests for the new Demo Reset feature (safety gating in non-demo sandbox env):
- GET /api/admin/demo/status -> {is_demo: false} since DEMO_MODE unset here
- POST /api/admin/demo/reseed -> 403 blocked, candidate collection untouched
"""
import os
import re
import requests
import pytest


def _load_backend_url():
    env_val = os.environ.get('REACT_APP_BACKEND_URL')
    if env_val:
        return env_val.rstrip('/')
    try:
        with open('/app/frontend/.env') as f:
            m = re.search(r'REACT_APP_BACKEND_URL=(.*)', f.read())
            if m:
                return m.group(1).strip().rstrip('/')
    except FileNotFoundError:
        pass
    raise RuntimeError('REACT_APP_BACKEND_URL not found')


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@ats.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def auth_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        pytest.skip("Admin login failed - skipping demo reset tests")
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def _candidate_count(headers):
    r = requests.get(f"{BASE_URL}/api/candidates?limit=1", headers=headers)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict) and "total" in data:
            return data["total"]
    return None


class TestDemoStatus:
    def test_demo_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/demo/status")
        assert r.status_code in (401, 403)

    def test_demo_status_is_false(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/demo/status", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "is_demo" in data
        assert data["is_demo"] is False


class TestDemoReseedBlocked:
    def test_reseed_blocked_with_403(self, auth_headers):
        before = _candidate_count(auth_headers)

        r = requests.post(f"{BASE_URL}/api/admin/demo/reseed", headers=auth_headers)
        assert r.status_code == 403
        data = r.json()
        assert data.get("detail") == "Demo reseed is only available on the demo instance"

        after = _candidate_count(auth_headers)
        if before is not None and after is not None:
            assert before == after, "Candidate collection was altered despite 403 block!"

    def test_reseed_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/admin/demo/reseed")
        assert r.status_code in (401, 403)
