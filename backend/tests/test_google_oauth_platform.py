"""Tests for per-tenant Google OAuth control-panel endpoints and login-initiation."""
import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get('REACT_APP_BACKEND_URL')
    if not v:
        try:
            with open('/app/frontend/.env') as f:
                for line in f:
                    if line.startswith('REACT_APP_BACKEND_URL='):
                        v = line.split('=', 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    if not v:
        raise RuntimeError('REACT_APP_BACKEND_URL not configured')
    return v.rstrip('/')


BASE_URL = _load_backend_url()

PLATFORM_EMAIL = 'kangabhijeet@gmail.com'
PLATFORM_PASSWORD = 'Avi@2026'
TENANT_SLUG = 'context66'
TENANT_ADMIN_EMAIL = 'admin@ats.com'
TENANT_ADMIN_PASSWORD = 'Admin@123'


@pytest.fixture(scope='module')
def platform_token():
    r = requests.post(f'{BASE_URL}/api/platform/login',
                      json={'email': PLATFORM_EMAIL, 'password': PLATFORM_PASSWORD})
    assert r.status_code == 200, f'Platform login failed: {r.status_code} {r.text}'
    return r.json()['token']


@pytest.fixture(scope='module')
def platform_hdr(platform_token):
    return {'Authorization': f'Bearer {platform_token}'}


@pytest.fixture(scope='module')
def context66_tenant_id(platform_hdr):
    r = requests.get(f'{BASE_URL}/api/platform/tenants', headers=platform_hdr)
    assert r.status_code == 200, r.text
    tenants = r.json()
    if isinstance(tenants, dict):
        tenants = tenants.get('tenants') or tenants.get('items') or []
    match = next((t for t in tenants if t.get('slug') == TENANT_SLUG), None)
    assert match, f'No tenant with slug {TENANT_SLUG} in list of {len(tenants)}'
    # verify google field present in row
    assert 'google' in match, 'Tenant row missing google field'
    assert 'ai' in match, 'Tenant row missing ai field (regression)'
    return match['id']


class TestGoogleOAuthPlatformCRUD:
    def test_initial_get_unconfigured_or_configured(self, platform_hdr, context66_tenant_id):
        # Clean slate first
        requests.delete(f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
                        headers=platform_hdr)
        r = requests.get(f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
                         headers=platform_hdr)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['configured'] is False
        assert data['client_id'] is None
        assert data['has_secret'] is False
        # SHOULD NEVER include client_secret
        assert 'client_secret' not in data
        assert 'client_secret_encrypted' not in data

    def test_put_creates_settings(self, platform_hdr, context66_tenant_id):
        r = requests.put(
            f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
            headers=platform_hdr,
            json={'client_id': 'TEST_client_id_12345.apps.googleusercontent.com',
                  'client_secret': 'TEST_secret_abcdef'})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['configured'] is True
        assert data['client_id'] == 'TEST_client_id_12345.apps.googleusercontent.com'
        assert data['has_secret'] is True
        assert 'client_secret' not in data

    def test_get_after_put_returns_config(self, platform_hdr, context66_tenant_id):
        r = requests.get(f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
                         headers=platform_hdr)
        assert r.status_code == 200
        data = r.json()
        assert data['configured'] is True
        assert data['client_id'] == 'TEST_client_id_12345.apps.googleusercontent.com'
        assert data['has_secret'] is True

    def test_put_blank_secret_preserves_existing(self, platform_hdr, context66_tenant_id):
        # Update client_id, leave secret blank — should keep existing secret
        r = requests.put(
            f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
            headers=platform_hdr,
            json={'client_id': 'TEST_client_id_v2.apps.googleusercontent.com',
                  'client_secret': ''})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['configured'] is True, 'has_secret dropped when blank secret sent — bug!'
        assert data['client_id'] == 'TEST_client_id_v2.apps.googleusercontent.com'
        assert data['has_secret'] is True

    def test_tenants_list_shows_google_connected_badge(self, platform_hdr, context66_tenant_id):
        r = requests.get(f'{BASE_URL}/api/platform/tenants', headers=platform_hdr)
        assert r.status_code == 200
        tenants = r.json()
        if isinstance(tenants, dict):
            tenants = tenants.get('tenants') or tenants.get('items') or []
        t = next(x for x in tenants if x['id'] == context66_tenant_id)
        assert t['google']['configured'] is True
        assert t['google']['has_secret'] is True

    def test_delete_clears_settings(self, platform_hdr, context66_tenant_id):
        r = requests.delete(
            f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
            headers=platform_hdr)
        assert r.status_code == 200
        # Verify
        r = requests.get(f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google',
                         headers=platform_hdr)
        assert r.status_code == 200
        assert r.json()['configured'] is False

    def test_unauth_denied(self, context66_tenant_id):
        r = requests.get(f'{BASE_URL}/api/platform/tenants/{context66_tenant_id}/google')
        assert r.status_code in (401, 403)

    def test_invalid_tenant_404(self, platform_hdr):
        r = requests.get(f'{BASE_URL}/api/platform/tenants/does-not-exist-xyz/google',
                         headers=platform_hdr)
        assert r.status_code == 404


class TestGoogleOAuthLoginInitiation:
    """Verifies /api/oauth/google/login doesn't 500 even with empty fallback creds."""

    @pytest.fixture(scope='class')
    def tenant_token(self):
        r = requests.post(f'{BASE_URL}/api/auth/login',
                          json={'email': TENANT_ADMIN_EMAIL,
                                'password': TENANT_ADMIN_PASSWORD,
                                'tenant_slug': TENANT_SLUG})
        assert r.status_code == 200, f'Tenant login failed: {r.status_code} {r.text}'
        return r.json()['token']

    def test_google_login_returns_authorization_url(self, tenant_token):
        r = requests.get(f'{BASE_URL}/api/oauth/google/login',
                         headers={'Authorization': f'Bearer {tenant_token}',
                                  'X-Tenant-Slug': TENANT_SLUG})
        assert r.status_code == 200, f'{r.status_code} {r.text}'
        data = r.json()
        assert 'authorization_url' in data
        url = data['authorization_url']
        assert url.startswith('https://accounts.google.com/o/oauth2/v2/auth')
        assert 'redirect_uri=' in url
        assert 'scope=' in url

    def test_calendar_status_endpoint(self, tenant_token):
        r = requests.get(f'{BASE_URL}/api/calendar/status',
                         headers={'Authorization': f'Bearer {tenant_token}',
                                  'X-Tenant-Slug': TENANT_SLUG})
        assert r.status_code == 200
        assert 'connected' in r.json()
