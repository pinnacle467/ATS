import axios from 'axios';

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
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('ats_token');
      localStorage.removeItem('ats_user');
      if (window.location.pathname !== '/login') window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export const errMsg = (e, fallback = 'Something went wrong') =>
  e?.response?.data?.detail || e?.message || fallback;
