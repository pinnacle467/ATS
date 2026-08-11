"""Motor proxy that enforces row-level tenant isolation.

`from database import db` returns a TenantDatabase. Every read gets
`{'tenant_id': <current tenant>}` merged into its filter and every write gets
`tenant_id` stamped on the document — so a route can never accidentally read or
write another tenant's rows.
"""
from tenant_context import GLOBAL_COLLECTIONS, TenantScopeError, get_tenant_id, in_request

_DB_PASSTHROUGH = {'name', 'client', 'command', 'list_collection_names', 'drop_collection'}


class TenantCollection:
    def __init__(self, coll, name: str):
        self._c = coll
        self._name = name

    # ---- helpers ----
    def _tid(self):
        tid = get_tenant_id()
        if tid is None and in_request():
            # Fail closed: never serve or write tenant-owned rows unscoped.
            raise TenantScopeError(
                f'"{self._name}" was accessed without a workspace. '
                'Send X-Tenant-Slug (or sign in) to identify the workspace.'
            )
        return tid

    def _f(self, filt=None):
        tid = self._tid()
        if tid is None:
            return filt if filt is not None else {}
        f = dict(filt or {})
        f['tenant_id'] = tid
        return f

    def _stamp(self, doc: dict):
        tid = self._tid()
        if tid is None:
            return doc
        return {**doc, 'tenant_id': tid}

    # ---- reads ----
    def find(self, filter=None, *args, **kwargs):
        return self._c.find(self._f(filter), *args, **kwargs)

    def find_one(self, filter=None, *args, **kwargs):
        return self._c.find_one(self._f(filter), *args, **kwargs)

    def count_documents(self, filter=None, **kwargs):
        return self._c.count_documents(self._f(filter), **kwargs)

    def distinct(self, key, filter=None, **kwargs):
        return self._c.distinct(key, self._f(filter), **kwargs)

    def aggregate(self, pipeline, **kwargs):
        tid = self._tid()
        pipe = list(pipeline)
        if tid is not None:
            pipe = [{'$match': {'tenant_id': tid}}] + pipe
        return self._c.aggregate(pipe, **kwargs)

    # ---- writes ----
    def insert_one(self, document, **kwargs):
        return self._c.insert_one(self._stamp(document), **kwargs)

    def insert_many(self, documents, **kwargs):
        return self._c.insert_many([self._stamp(d) for d in documents], **kwargs)

    def update_one(self, filter, update, **kwargs):
        return self._c.update_one(self._f(filter), update, **kwargs)

    def update_many(self, filter, update, **kwargs):
        return self._c.update_many(self._f(filter), update, **kwargs)

    def replace_one(self, filter, replacement, **kwargs):
        return self._c.replace_one(self._f(filter), self._stamp(replacement), **kwargs)

    def delete_one(self, filter, **kwargs):
        return self._c.delete_one(self._f(filter), **kwargs)

    def delete_many(self, filter, **kwargs):
        return self._c.delete_many(self._f(filter), **kwargs)

    def find_one_and_update(self, filter, update, **kwargs):
        return self._c.find_one_and_update(self._f(filter), update, **kwargs)

    def find_one_and_delete(self, filter, **kwargs):
        return self._c.find_one_and_delete(self._f(filter), **kwargs)

    def __getattr__(self, item):
        # create_index, index_information, drop_index, ... — no scoping needed
        return getattr(self._c, item)


class TenantDatabase:
    def __init__(self, raw):
        self.raw = raw

    def __getitem__(self, name):
        coll = self.raw[name]
        if name in GLOBAL_COLLECTIONS:
            return coll
        return TenantCollection(coll, name)

    def __getattr__(self, name):
        if name.startswith('_') or name in _DB_PASSTHROUGH:
            return getattr(self.raw, name)
        return self[name]
