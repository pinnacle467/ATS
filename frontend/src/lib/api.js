import axios from 'axios';
import { getTenantSlug, loginPath } from '@/lib/tenant';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  // FastAPI's `Query(None)` for List[str] params expects repeated keys
  // (industry=A&industry=B), but axios's default array serialization uses
  // bracket notation (industry[]=A&industry[]=B), which FastAPI silently
  // ignores. `indexes: null` makes axios use the repeated-key format instead.
  paramsSerializer: { indexes: null },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('ats_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Tells the backend which workspace unauthenticated calls belong to
  // (login, public careers pages). Authenticated calls are scoped from the JWT.
  const slug = getTenantSlug();
  if (slug) config.headers['X-Tenant-Slug'] = slug;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('ats_token');
      localStorage.removeItem('ats_user');
      const target = loginPath(getTenantSlug());
      if (window.location.pathname !== target) window.location.href = target;
    }
    return Promise.reject(err);
  }
);

// Platform (Super Admin) API — separate token, never tenant-scoped.
export const platformApi = axios.create({ baseURL: API });

platformApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('ats_platform_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

platformApi.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/platform/login')) {
      localStorage.removeItem('ats_platform_token');
      if (window.location.pathname !== '/platform/login') window.location.href = '/platform/login';
    }
    return Promise.reject(err);
  }
);

export const errMsg = (e, fallback = 'Something went wrong') =>
  e?.response?.data?.detail || e?.message || fallback;
