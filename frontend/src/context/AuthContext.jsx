import { createContext, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { applyAccent, clearTenantSlug, getTenantSlug, setTenantSlug } from '@/lib/tenant';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('ats_user')) || null;
    } catch {
      return null;
    }
  });
  const [tenant, setTenant] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('ats_tenant')) || null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  const storeTenant = (t) => {
    setTenant(t);
    if (t) {
      localStorage.setItem('ats_tenant', JSON.stringify(t));
      setTenantSlug(t.slug);
      applyAccent(t.branding?.accent_color);
    } else {
      localStorage.removeItem('ats_tenant');
    }
  };

  useEffect(() => {
    if (tenant?.branding?.accent_color) applyAccent(tenant.branding.accent_color);
    const token = localStorage.getItem('ats_token');
    if (!token) {
      setLoading(false);
      return;
    }
    Promise.all([api.get('/auth/me'), api.get('/tenant/me').catch(() => null)])
      .then(([me, t]) => {
        setUser(me.data);
        localStorage.setItem('ats_user', JSON.stringify(me.data));
        if (t?.data) storeTenant(t.data);
      })
      .catch(() => {
        localStorage.removeItem('ats_token');
        localStorage.removeItem('ats_user');
        setUser(null);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email, password, slug) => {
    const workspace = slug || getTenantSlug();
    const r = await api.post('/auth/login', { email, password, tenant_slug: workspace });
    localStorage.setItem('ats_token', r.data.token);
    localStorage.setItem('ats_user', JSON.stringify(r.data.user));
    setUser(r.data.user);
    if (r.data.tenant) storeTenant(r.data.tenant);
    return r.data.user;
  };

  const logout = () => {
    localStorage.removeItem('ats_token');
    localStorage.removeItem('ats_user');
    setUser(null);
  };

  const leaveWorkspace = () => {
    logout();
    localStorage.removeItem('ats_tenant');
    setTenant(null);
    clearTenantSlug();
  };

  return (
    <AuthContext.Provider value={{ user, tenant, setTenant: storeTenant, login, logout, leaveWorkspace, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
