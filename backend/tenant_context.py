"""Request-scoped tenant identity.

Every authenticated request stores its tenant_id here (set by auth.get_current_user
or the tenant middleware). The TenantDatabase proxy in tenant_db.py reads it and
injects `tenant_id` into every query/insert automatically, so route code never has
to remember to filter by tenant.

When no tenant is set (background loops, platform-owner endpoints, public token
lookups before the tenant is known) the proxy passes queries through unscoped.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_tenant_id: ContextVar = ContextVar('tenant_id', default=None)
# True only while an HTTP request is being served. Inside a request, touching a
# tenant-owned collection without a resolved tenant is a bug (and a potential
# cross-tenant leak), so the proxy fails closed instead of querying globally.
_in_request: ContextVar = ContextVar('in_request', default=False)


class TenantScopeError(Exception):
    """Raised when tenant-owned data is touched inside a request that has no tenant."""

# Collections that are NOT tenant-owned:
#  - tenants / platform_admins : platform level
#  - password_resets           : looked up by a globally-unique secret token
#  - counters                  : keyed by a tenant-prefixed _id instead (utils.py)
GLOBAL_COLLECTIONS = {'tenants', 'platform_admins', 'password_resets', 'counters', 'tenant_ai_settings'}


def get_tenant_id():
    return _tenant_id.get()


def set_tenant_id(tid):
    return _tenant_id.set(tid)


def reset_tenant_id(token):
    try:
        _tenant_id.reset(token)
    except ValueError:
        pass


def enter_request():
    return _in_request.set(True)


def exit_request(token):
    try:
        _in_request.reset(token)
    except ValueError:
        pass


def in_request() -> bool:
    return _in_request.get()


@contextmanager
def tenant_scope(tid):
    token = _tenant_id.set(tid)
    try:
        yield
    finally:
        reset_tenant_id(token)
