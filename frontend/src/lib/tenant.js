// Tenant slug resolution + white-label accent application.
const SLUG_KEY = 'ats_tenant_slug';

let current = (() => {
  try {
    return localStorage.getItem(SLUG_KEY) || null;
  } catch {
    return null;
  }
})();

export const getTenantSlug = () => current;

export const setTenantSlug = (slug) => {
  if (!slug || slug === current) return;
  current = slug;
  try {
    localStorage.setItem(SLUG_KEY, slug);
  } catch {
    /* ignore */
  }
};

export const clearTenantSlug = () => {
  current = null;
  try {
    localStorage.removeItem(SLUG_KEY);
  } catch {
    /* ignore */
  }
};

export const loginPath = (slug) => (slug ? `/${slug}/login` : '/login');

// Public careers portal always lives under the tenant slug: /<slug>/careers...
export const careersPath = (sub = '') => {
  const slug = getTenantSlug();
  return slug ? `/${slug}/careers${sub}` : `/careers${sub}`;
};

// #059669 -> "158 64% 34%" (the format index.css uses for its CSS variables)
export const hexToHslTokens = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return null;
  const int = parseInt(m[1], 16);
  const r = ((int >> 16) & 255) / 255;
  const g = ((int >> 8) & 255) / 255;
  const b = (int & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
};

export const applyAccent = (hex) => {
  const tokens = hexToHslTokens(hex);
  if (!tokens) return;
  const root = document.documentElement;
  root.style.setProperty('--primary', tokens);
  root.style.setProperty('--ring', tokens);
};
