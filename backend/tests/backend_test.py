"""Multi-tenant SaaS API isolation, provisioning, auth, and branding regression tests."""
import base64
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")
CREDENTIALS_FILE = Path("/app/memory/test_credentials.md")


def _credentials_for(section_marker: str) -> dict:
    if not CREDENTIALS_FILE.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = CREDENTIALS_FILE.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", content)
    section = next((part for part in sections if section_marker.lower() in part.lower()), None)
    if not section:
        pytest.skip(f"Credentials section not found: {section_marker}")
    email = re.search(r"(?i)Email:\s*([^\s|]+)", section)
    password = re.search(r"(?i)Password:\s*([^\s|]+)", section)
    slug = re.search(r"slug\s*[`']([^`']+)[`']", section, re.I)
    if not email or not password:
        pytest.skip(f"Email/password not found in credentials section: {section_marker}")
    return {
        "email": email.group(1),
        "password": password.group(1),
        "slug": slug.group(1) if slug else None,
    }


def _login(creds: dict) -> tuple[requests.Session, dict]:
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": creds["email"], "password": creds["password"], "tenant_slug": creds["slug"]},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data.get("token"), str) and data["token"]
    assert data["user"]["email"] == creds["email"].lower()
    assert data["tenant"]["slug"] == creds["slug"]
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"})
    return session, data


@pytest.fixture(scope="session")
def context_creds():
    return _credentials_for("Founding tenant")


@pytest.fixture(scope="session")
def acme_creds():
    return _credentials_for("Test tenant")


@pytest.fixture(scope="session")
def platform_creds():
    return _credentials_for("Platform")


@pytest.fixture(scope="session")
def context_client(context_creds):
    return _login(context_creds)


@pytest.fixture(scope="session")
def acme_client(acme_creds):
    return _login(acme_creds)


@pytest.fixture(scope="session")
def platform_client(platform_creds):
    response = requests.post(
        f"{BASE_URL}/api/platform/login",
        json={"email": platform_creds["email"], "password": platform_creds["password"]},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["admin"]["email"] == platform_creds["email"].lower()
    assert data["admin"]["role"] == "platform_owner"
    assert isinstance(data.get("token"), str) and data["token"]
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"})
    return session, data


@pytest.fixture(scope="session")
def throwaway_tenant(platform_client):
    session, _ = platform_client
    suffix = f"qa-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    payload = {
        "name": f"TEST QA Workspace {suffix}",
        "slug": suffix,
        "plan": "free",
        "admin_name": "TEST Workspace Owner",
        "admin_email": f"owner-{suffix}@example.com",
        "admin_password": "TestOwner@1234",
    }
    response = session.post(f"{BASE_URL}/api/platform/tenants", json=payload, timeout=30)
    assert response.status_code == 200, response.text
    created = response.json()
    try:
        yield {**created, "password": payload["admin_password"]}
    finally:
        tenant_id = created["tenant"]["id"]
        # Reactivate first in case a suspension assertion aborts before restoration.
        session.patch(f"{BASE_URL}/api/platform/tenants/{tenant_id}", json={"status": "active"}, timeout=30)
        deleted = session.delete(f"{BASE_URL}/api/platform/tenants/{tenant_id}", timeout=30)
        assert deleted.status_code in (200, 404), deleted.text


def _get_json(client: requests.Session, endpoint: str):
    response = client.get(f"{BASE_URL}{endpoint}", timeout=30)
    assert response.status_code == 200, f"{endpoint}: {response.status_code} {response.text[:500]}"
    return response.json()


def _assert_scoped(rows: list, tenant_id: str):
    assert isinstance(rows, list)
    for row in rows:
        if "tenant_id" in row:
            assert row["tenant_id"] == tenant_id


class TestTenantAuthentication:
    """Workspace-required tenant authentication and token-kind separation."""

    def test_login_without_workspace_is_400(self, context_creds):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": context_creds["email"], "password": context_creds["password"]},
            timeout=30,
        )
        assert response.status_code == 400, response.text
        assert "workspace" in response.json()["detail"].lower()

    def test_login_with_workspace_returns_user_token_tenant(self, context_client):
        _, data = context_client
        assert data["user"]["email"] == "admin@ats.com"
        assert data["tenant"]["slug"] == "context66"
        assert data["tenant"]["status"] == "active"
        assert "password_hash" not in data["user"]

    def test_platform_token_rejected_by_tenant_endpoint(self, platform_client):
        client, _ = platform_client
        response = client.get(f"{BASE_URL}/api/candidates", timeout=30)
        assert response.status_code == 403, response.text

    def test_tenant_token_rejected_by_platform_endpoint(self, context_client):
        client, _ = context_client
        response = client.get(f"{BASE_URL}/api/platform/tenants", timeout=30)
        assert response.status_code == 403, response.text


class TestTenantIsolationListings:
    """Every high-value listing and aggregate remains within its JWT tenant."""

    def test_core_counts_match_expected_tenants(self, context_client, acme_client):
        context, context_auth = context_client
        acme, acme_auth = acme_client
        c_candidates = _get_json(context, "/api/candidates?limit=500")
        a_candidates = _get_json(acme, "/api/candidates?limit=500")
        c_jobs = _get_json(context, "/api/jobs")
        a_jobs = _get_json(acme, "/api/jobs")
        c_interviews = _get_json(context, "/api/interviews")
        a_interviews = _get_json(acme, "/api/interviews")
        c_users = _get_json(context, "/api/users")
        a_users = _get_json(acme, "/api/users")

        assert c_candidates["total"] == 388
        assert a_candidates["total"] == 0
        assert len(c_jobs) == 9
        assert len(a_jobs) == 0
        assert len(c_interviews) == 80  # Two unbooked self-scheduling rows intentionally live under /scheduling/requests.
        assert len(a_interviews) == 0
        assert len(c_users) == 3
        assert len(a_users) == 1
        _assert_scoped(c_candidates["items"], context_auth["tenant"]["id"])
        _assert_scoped(a_candidates["items"], acme_auth["tenant"]["id"])
        _assert_scoped(c_jobs, context_auth["tenant"]["id"])
        _assert_scoped(a_jobs, acme_auth["tenant"]["id"])
        _assert_scoped(c_interviews, context_auth["tenant"]["id"])
        _assert_scoped(a_interviews, acme_auth["tenant"]["id"])
        _assert_scoped(c_users, context_auth["tenant"]["id"])
        _assert_scoped(a_users, acme_auth["tenant"]["id"])

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/departments",
            "/api/tags",
            "/api/audit-log?limit=500",
            "/api/offers",
            "/api/scheduling/requests",
        ],
    )
    def test_tenant_owned_listings_have_no_cross_tenant_ids(self, endpoint, context_client, acme_client):
        context, context_auth = context_client
        acme, acme_auth = acme_client
        c_rows = _get_json(context, endpoint)
        a_rows = _get_json(acme, endpoint)
        _assert_scoped(c_rows, context_auth["tenant"]["id"])
        _assert_scoped(a_rows, acme_auth["tenant"]["id"])
        c_ids = {r.get("id") for r in c_rows if r.get("id")}
        a_ids = {r.get("id") for r in a_rows if r.get("id")}
        assert not c_ids.intersection(a_ids)

    def test_dashboard_stats_are_empty_for_acme(self, context_client, acme_client):
        context, _ = context_client
        acme, _ = acme_client
        context_stats = _get_json(context, "/api/dashboard/stats")
        acme_stats = _get_json(acme, "/api/dashboard/stats")
        assert context_stats["open_roles"] > 0
        assert context_stats["active_candidates"] > 0
        assert acme_stats["open_roles"] == 0
        assert acme_stats["active_candidates"] == 0
        assert acme_stats["interviews_this_week"] == 0
        assert acme_stats["offers_pending"] == 0
        assert all(stage["count"] == 0 for stage in acme_stats["pipeline"])

    def test_pipeline_defaults_are_tenant_scoped(self, context_client, acme_client):
        context, context_auth = context_client
        acme, acme_auth = acme_client
        c_pipeline = _get_json(context, "/api/settings/pipeline")
        a_pipeline = _get_json(acme, "/api/settings/pipeline")
        assert len(a_pipeline["stages"]) == 6
        assert {stage["name"] for stage in a_pipeline["stages"]} == {"Applied", "Screening", "Interview", "Offer", "Hired", "Rejected"}
        if "tenant_id" in c_pipeline:
            assert c_pipeline["tenant_id"] == context_auth["tenant"]["id"]
        if "tenant_id" in a_pipeline:
            assert a_pipeline["tenant_id"] == acme_auth["tenant"]["id"]

    def test_career_analytics_and_settings_are_tenant_scoped(self, context_client, acme_client):
        context, context_auth = context_client
        acme, acme_auth = acme_client
        c_analytics = _get_json(context, "/api/career/analytics/overview?days=30")
        a_analytics = _get_json(acme, "/api/career/analytics/overview?days=30")
        assert a_analytics["views"] == 0
        assert a_analytics["applications"] == 0
        assert a_analytics["unique_visitors"] == 0
        c_settings = _get_json(context, "/api/career/settings")
        a_settings = _get_json(acme, "/api/career/settings")
        if "tenant_id" in c_settings:
            assert c_settings["tenant_id"] == context_auth["tenant"]["id"]
        if "tenant_id" in a_settings:
            assert a_settings["tenant_id"] == acme_auth["tenant"]["id"]
        assert c_settings.get("tenant_id") != a_settings.get("tenant_id")
        assert isinstance(c_analytics["timeseries"], list)
        assert isinstance(a_analytics["timeseries"], list)


class TestPublicTokenTenantResolution:
    """Public scheduling token resolves its tenant without browser workspace state."""

    def test_existing_scheduling_token_resolves_without_tenant_header(self, context_client):
        context, _ = context_client
        requests_list = _get_json(context, "/api/scheduling/requests")
        assert requests_list, "No existing Context66 scheduling request is available for public-token regression"
        item = next((row for row in requests_list if row.get("scheduling_token")), None)
        assert item and item["scheduling_token"]
        token = item["scheduling_token"]
        public = requests.get(f"{BASE_URL}/api/schedule/{token}", timeout=30)
        assert public.status_code == 200, public.text
        data = public.json()
        assert data.get("candidate_name") == item.get("candidate_name")
        assert data.get("job_title") == item.get("job_title")
        assert data.get("company_name")
        Path("/app/test_reports/public_schedule_token.txt").write_text(token, encoding="utf-8")


class TestCrossTenantObjectAccess:
    """Acme cannot read or mutate Context66 candidate/job/interview objects."""

    def test_context_objects_cannot_be_read_or_modified_by_acme(self, context_client, acme_client):
        context, _ = context_client
        acme, _ = acme_client
        candidate = _get_json(context, "/api/candidates?limit=1")["items"][0]
        job = _get_json(context, "/api/jobs")[0]
        interview = _get_json(context, "/api/interviews")[0]

        attempts = [
            ("get", f"/api/candidates/{candidate['id']}", None),
            ("put", f"/api/candidates/{candidate['id']}", {"name": "TEST_CROSS_TENANT_MUTATION"}),
            ("delete", f"/api/candidates/{candidate['id']}", None),
            ("get", f"/api/jobs/{job['id']}", None),
            ("put", f"/api/jobs/{job['id']}", {"title": "TEST_CROSS_TENANT_MUTATION"}),
            ("delete", f"/api/jobs/{job['id']}", None),
            # Interview detail only implements PUT; unsupported GET/DELETE intentionally return 405.
            ("put", f"/api/interviews/{interview['id']}", {"status": "cancelled"}),
        ]
        mismatches = []
        for method, endpoint, payload in attempts:
            response = acme.request(method, f"{BASE_URL}{endpoint}", json=payload, timeout=30)
            if response.status_code != 404:
                mismatches.append(f"{method.upper()} {endpoint}: {response.status_code} {response.text}")

        assert _get_json(context, f"/api/candidates/{candidate['id']}")["name"] == candidate["name"]
        assert _get_json(context, f"/api/jobs/{job['id']}")["title"] == job["title"]
        fresh_interviews = _get_json(context, "/api/interviews")
        fresh_interview = next(row for row in fresh_interviews if row["id"] == interview["id"])
        assert fresh_interview["status"] == interview["status"]
        assert not mismatches, "; ".join(mismatches)


class TestTenantStampedWrites:
    """Acme writes are visible only inside Acme and can be cleaned safely."""

    def test_candidate_job_department_tag_stamped_and_isolated(self, context_client, acme_client):
        context, _ = context_client
        acme, acme_auth = acme_client
        tenant_id = acme_auth["tenant"]["id"]
        before_context_candidates = _get_json(context, "/api/candidates?limit=1")["total"]
        before_context_jobs = len(_get_json(context, "/api/jobs"))
        suffix = uuid.uuid4().hex[:10]
        created = {}
        try:
            job_res = acme.post(
                f"{BASE_URL}/api/jobs",
                json={"title": f"TEST_Acme Job {suffix}", "department": "TEST_QA", "status": "open"},
                timeout=30,
            )
            assert job_res.status_code == 200, job_res.text
            created["job"] = job_res.json()

            candidate_res = acme.post(
                f"{BASE_URL}/api/candidates",
                json={"name": f"TEST_Acme Candidate {suffix}", "email": f"candidate-{suffix}@example.com", "job_id": created["job"]["id"]},
                timeout=30,
            )
            assert candidate_res.status_code == 200, candidate_res.text
            created["candidate"] = candidate_res.json()

            for kind in ("departments", "tags"):
                response = acme.post(f"{BASE_URL}/api/{kind}", json={"name": f"TEST_{kind}_{suffix}"}, timeout=30)
                assert response.status_code == 200, response.text
                created[kind] = response.json()

            assert any(j["id"] == created["job"]["id"] for j in _get_json(acme, "/api/jobs"))
            assert _get_json(acme, "/api/candidates?limit=500")["total"] == 1
            assert any(d["id"] == created["departments"]["id"] for d in _get_json(acme, "/api/departments"))
            assert any(t["id"] == created["tags"]["id"] for t in _get_json(acme, "/api/tags"))

            assert _get_json(context, "/api/candidates?limit=1")["total"] == before_context_candidates
            assert len(_get_json(context, "/api/jobs")) == before_context_jobs
            assert not any(d.get("id") == created["departments"]["id"] for d in _get_json(context, "/api/departments"))
            assert not any(t.get("id") == created["tags"]["id"] for t in _get_json(context, "/api/tags"))
        finally:
            if created.get("candidate"):
                acme.delete(f"{BASE_URL}/api/candidates/{created['candidate']['id']}", timeout=30)
            if created.get("job"):
                acme.delete(f"{BASE_URL}/api/jobs/{created['job']['id']}", timeout=30)
            if created.get("departments"):
                acme.delete(f"{BASE_URL}/api/departments/{created['departments']['id']}", timeout=30)
            if created.get("tags"):
                acme.delete(f"{BASE_URL}/api/tags/{created['tags']['id']}", timeout=30)


class TestPlatformAndProvisioning:
    """Platform owner listing/stats, tenant provisioning, suspension, and impersonation."""

    def test_platform_lists_seeded_tenants_and_counts(self, platform_client):
        client, _ = platform_client
        tenants = _get_json(client, "/api/platform/tenants")
        by_slug = {row["slug"]: row for row in tenants}
        assert {"context66", "acme"}.issubset(by_slug)
        assert by_slug["context66"]["counts"]["candidates"] == 388
        assert by_slug["context66"]["counts"]["jobs"] == 9
        assert by_slug["context66"]["counts"]["interviews"] == 82
        assert by_slug["context66"]["counts"]["users"] == 3
        assert by_slug["acme"]["counts"]["candidates"] == 0
        assert by_slug["acme"]["counts"]["jobs"] == 0
        assert by_slug["acme"]["counts"]["interviews"] == 0
        assert by_slug["acme"]["counts"]["users"] == 1
        stats = _get_json(client, "/api/platform/stats")
        assert stats["tenants"] >= 2
        assert stats["candidates"] >= 388
        assert stats["jobs"] >= 9

    def test_duplicate_and_reserved_slugs_rejected(self, platform_client):
        client, _ = platform_client
        base = {
            "name": "TEST Duplicate",
            "slug": "context66",
            "admin_name": "TEST Owner",
            "admin_email": "duplicate@example.com",
            "admin_password": "Duplicate@1234",
        }
        duplicate = client.post(f"{BASE_URL}/api/platform/tenants", json=base, timeout=30)
        assert duplicate.status_code == 409, duplicate.text
        reserved = client.post(
            f"{BASE_URL}/api/platform/tenants",
            json={**base, "slug": "platform", "admin_email": "reserved@example.com"},
            timeout=30,
        )
        assert reserved.status_code == 422, reserved.text

    def test_new_tenant_empty_defaults_and_immediate_login(self, throwaway_tenant):
        tenant = throwaway_tenant["tenant"]
        creds = {
            "email": throwaway_tenant["owner"]["email"],
            "password": throwaway_tenant["password"],
            "slug": tenant["slug"],
        }
        client, auth = _login(creds)
        assert auth["tenant"]["id"] == tenant["id"]
        assert _get_json(client, "/api/candidates?limit=500")["total"] == 0
        assert _get_json(client, "/api/jobs") == []
        assert _get_json(client, "/api/interviews") == []
        users = _get_json(client, "/api/users")
        assert len(users) == 1 and users[0]["email"] == creds["email"]
        assert len(_get_json(client, "/api/settings/pipeline")["stages"]) == 6
        templates = _get_json(client, "/api/career/email-templates")
        assert len(templates["templates"]) >= 4

    def test_suspension_blocks_login_and_existing_token_then_reactivation_restores(self, platform_client, throwaway_tenant):
        platform, _ = platform_client
        tenant = throwaway_tenant["tenant"]
        creds = {
            "email": throwaway_tenant["owner"]["email"],
            "password": throwaway_tenant["password"],
            "slug": tenant["slug"],
        }
        tenant_client, _ = _login(creds)
        suspended = platform.patch(
            f"{BASE_URL}/api/platform/tenants/{tenant['id']}", json={"status": "suspended"}, timeout=30
        )
        assert suspended.status_code == 200 and suspended.json()["status"] == "suspended"
        login = requests.post(f"{BASE_URL}/api/auth/login", json={"email": creds["email"], "password": creds["password"], "tenant_slug": creds["slug"]}, timeout=30)
        assert login.status_code == 403, login.text
        existing = tenant_client.get(f"{BASE_URL}/api/candidates", timeout=30)
        assert existing.status_code == 403, existing.text
        active = platform.patch(
            f"{BASE_URL}/api/platform/tenants/{tenant['id']}", json={"status": "active"}, timeout=30
        )
        assert active.status_code == 200 and active.json()["status"] == "active"
        restored = tenant_client.get(f"{BASE_URL}/api/candidates", timeout=30)
        assert restored.status_code == 200, restored.text

    def test_impersonation_returns_normal_tenant_token(self, platform_client, throwaway_tenant):
        platform, _ = platform_client
        tenant = throwaway_tenant["tenant"]
        response = platform.post(f"{BASE_URL}/api/platform/tenants/{tenant['id']}/impersonate", timeout=30)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["tenant"]["id"] == tenant["id"]
        tenant_client = requests.Session()
        tenant_client.headers.update({"Authorization": f"Bearer {data['token']}"})
        assert _get_json(tenant_client, "/api/candidates?limit=500")["total"] == 0
        rejected = tenant_client.get(f"{BASE_URL}/api/platform/tenants", timeout=30)
        assert rejected.status_code == 403, rejected.text


class TestTenantBranding:
    """Public branding, admin updates/validation/logo, and non-admin authorization."""

    def test_public_branding_lookup(self):
        response = requests.get(f"{BASE_URL}/api/tenants/by-slug/context66", timeout=30)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["slug"] == "context66"
        assert data["status"] == "active"
        assert isinstance(data["branding"], dict)
        assert "accent_color" in data["branding"]

    def test_admin_branding_update_invalid_hex_logo_and_non_admin_rejection(self, throwaway_tenant):
        tenant = throwaway_tenant["tenant"]
        creds = {
            "email": throwaway_tenant["owner"]["email"],
            "password": throwaway_tenant["password"],
            "slug": tenant["slug"],
        }
        client, _ = _login(creds)
        updated = client.put(
            f"{BASE_URL}/api/tenant/branding",
            json={"company_name": "TEST White Label Co", "tagline": "TEST Hire well", "accent_color": "#2563eb"},
            timeout=30,
        )
        assert updated.status_code == 200, updated.text
        branding = updated.json()["branding"]
        assert branding["company_name"] == "TEST White Label Co"
        assert branding["tagline"] == "TEST Hire well"
        assert branding["accent_color"] == "#2563eb"
        public = requests.get(f"{BASE_URL}/api/tenants/by-slug/{tenant['slug']}", timeout=30).json()
        assert public["branding"] == branding

        invalid = client.put(f"{BASE_URL}/api/tenant/branding", json={"accent_color": "blue"}, timeout=30)
        assert invalid.status_code == 422, invalid.text

        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        logo = requests.post(
            f"{BASE_URL}/api/tenant/logo",
            files={"file": ("test-logo.png", png, "image/png")},
            headers={"Authorization": client.headers["Authorization"]},
            timeout=30,
        )
        assert logo.status_code == 200, logo.text
        assert logo.json()["branding"]["logo_url"].startswith("data:image/png;base64,")
        public_logo = requests.get(f"{BASE_URL}/api/tenants/by-slug/{tenant['slug']}", timeout=30).json()["branding"]["logo_url"]
        assert public_logo.startswith("data:image/png;base64,")

        suffix = uuid.uuid4().hex[:8]
        user_response = client.post(
            f"{BASE_URL}/api/users",
            json={
                "name": "TEST Non Admin",
                "email": f"nonadmin-{suffix}@example.com",
                "password": "NonAdmin@1234",
                "role": "interview_panel",
            },
            timeout=30,
        )
        assert user_response.status_code == 200, user_response.text
        non_admin = user_response.json()
        try:
            non_admin_client, _ = _login({"email": non_admin["email"], "password": "NonAdmin@1234", "slug": tenant["slug"]})
            denied = non_admin_client.put(f"{BASE_URL}/api/tenant/branding", json={"company_name": "SHOULD NOT SAVE"}, timeout=30)
            assert denied.status_code == 403, denied.text
        finally:
            client.delete(f"{BASE_URL}/api/users/{non_admin['id']}", timeout=30)



class TestFailClosedPublicCareerScope:
    """Public career data fails closed without a workspace and isolates by slug."""

    PUBLIC_ENDPOINTS = [
        "/api/career/public/settings",
        "/api/career/public/jobs",
        "/api/career/public/pages",
        "/api/career/public/logo",
        "/api/career/public/security-config",
    ]

    @pytest.mark.parametrize("endpoint", PUBLIC_ENDPOINTS)
    def test_public_endpoint_without_workspace_is_400(self, endpoint):
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=30)
        assert response.status_code == 400, f"{endpoint}: {response.status_code} {response.text[:500]}"
        detail = response.json().get("detail", "")
        assert "was accessed without a workspace" in detail

    @pytest.mark.parametrize("endpoint", PUBLIC_ENDPOINTS)
    def test_public_endpoint_context66_header_succeeds(self, endpoint):
        response = requests.get(
            f"{BASE_URL}{endpoint}", headers={"X-Tenant-Slug": "context66"}, timeout=30
        )
        if endpoint.endswith("/logo") and response.status_code == 404:
            assert response.json().get("detail") == "No logo set"
            return
        assert response.status_code == 200, f"{endpoint}: {response.status_code} {response.text[:500]}"
        if "jobs" in endpoint:
            rows = response.json()
            assert isinstance(rows, list) and rows
            assert all(row.get("title") for row in rows)
        else:
            assert response.json() is not None

    def test_query_tenant_context66_and_acme_cannot_leak_jobs(self):
        context = requests.get(
            f"{BASE_URL}/api/career/public/jobs", params={"tenant": "context66"}, timeout=30
        )
        assert context.status_code == 200, context.text
        context_rows = context.json()
        assert context_rows
        context_ids = {row["id"] for row in context_rows}

        acme = requests.get(
            f"{BASE_URL}/api/career/public/jobs", params={"tenant": "acme"}, timeout=30
        )
        assert acme.status_code in (200, 404), acme.text
        if acme.status_code == 200:
            acme_ids = {row["id"] for row in acme.json()}
            assert not context_ids.intersection(acme_ids)
            assert acme.json() == []
        else:
            assert "not available" in acme.json().get("detail", "").lower()


class TestPasswordResetTenantScope:
    """Password reset requires a workspace and stores a tenant-scoped reset record."""

    def test_forgot_password_requires_workspace_and_persists_tenant_id(self, context_creds):
        no_workspace = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": context_creds["email"]},
            timeout=30,
        )
        assert no_workspace.status_code == 400, no_workspace.text
        assert "workspace" in no_workspace.json().get("detail", "").lower()

        backend_env = dotenv_values("/app/backend/.env")
        mongo_url = backend_env.get("MONGO_URL")
        db_name = backend_env.get("DB_NAME")
        assert mongo_url and db_name
        mongo = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        raw = mongo[db_name]
        tenant = raw.tenants.find_one({"slug": "context66"}, {"_id": 0, "id": 1})
        assert tenant and tenant.get("id")
        before_ids = {
            row["id"] for row in raw.password_resets.find(
                {"email": context_creds["email"].lower()}, {"_id": 0, "id": 1}
            )
        }

        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": context_creds["email"]},
            headers={"X-Tenant-Slug": "context66"},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "ok": True,
            "message": "If an account exists for that email, a reset link has been sent.",
        }
        after = list(raw.password_resets.find(
            {"email": context_creds["email"].lower()}, {"_id": 0, "id": 1, "tenant_id": 1}
        ))
        created = [row for row in after if row["id"] not in before_ids]
        assert len(created) == 1, "Forgot-password did not create exactly one new reset record"
        assert created[0].get("tenant_id") == tenant["id"]
        mongo.close()

    def test_bad_reset_token_is_400(self):
        response = requests.get(
            f"{BASE_URL}/api/auth/reset-password/verify",
            params={"token": "TEST_invalid_reset_token_123456789"},
            timeout=30,
        )
        assert response.status_code == 400, response.text
        assert "invalid" in response.json().get("detail", "").lower()


class TestAuthenticatedModuleRegression:
    """All authenticated Context66 modules remain scoped and free of workspace errors."""

    def test_context66_modules_and_detail_views_return_data(self, context_client):
        client, _ = context_client
        candidates = _get_json(client, "/api/candidates?limit=2")
        jobs = _get_json(client, "/api/jobs")
        assert candidates["items"] and candidates["total"] == 388
        assert jobs and len(jobs) == 9

        endpoints = [
            "/api/dashboard/stats",
            f"/api/candidates/{candidates['items'][0]['id']}",
            f"/api/jobs/{jobs[0]['id']}",
            "/api/interviews",
            "/api/scheduling/requests",
            "/api/offers",
            "/api/users",
            "/api/departments",
            "/api/tags",
            "/api/audit-log?limit=20",
            "/api/settings/pipeline",
            "/api/notifications",
            "/api/career/settings",
            "/api/career/dashboard",
            "/api/career/pages",
            "/api/career/media",
            "/api/career/settings/security",
            "/api/career/analytics/overview?days=30",
            "/api/career/analytics/events?limit=20",
        ]
        for endpoint in endpoints:
            response = client.get(f"{BASE_URL}{endpoint}", timeout=30)
            assert response.status_code == 200, f"{endpoint}: {response.status_code} {response.text[:500]}"
            assert "without a workspace" not in response.text.lower()
            assert response.json() is not None

    def test_seo_and_portal_urls_are_tenant_prefixed(self, context_client):
        client, _ = context_client
        settings = _get_json(client, "/api/career/settings")
        assert settings["portal_url"].endswith("/context66/careers")

        robots = requests.get(
            f"{BASE_URL}/api/career/seo/robots.txt", params={"tenant": "context66"}, timeout=30
        )
        assert robots.status_code == 200, robots.text
        assert "Allow: /context66/careers" in robots.text

        sitemap = requests.get(
            f"{BASE_URL}/api/career/seo/sitemap.xml", params={"tenant": "context66"}, timeout=30
        )
        assert sitemap.status_code == 200, sitemap.text
        assert "/context66/careers" in sitemap.text
        assert "/careers/jobs/" in sitemap.text
