import { createContext, useContext, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '@/lib/api';
import { track } from './tracking';

const CareerSettingsContext = createContext(null);
export const useCareerSettings = () => useContext(CareerSettingsContext);

// Small helper — same behavior as CareerStaticPage's setMeta but scoped here
function setMeta(name, content, isProperty = false) {
  if (!content) return;
  const attr = isProperty ? 'property' : 'name';
  let tag = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attr, name);
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', content);
}

// Public static pages that appear in the header nav if published
const STATIC_PAGE_NAV = [
  { key: 'about', label: 'About' },
  { key: 'benefits', label: 'Benefits' },
  { key: 'life', label: 'Life at Company' },
  { key: 'testimonials', label: 'Testimonials' },
];

export default function CareerPublicLayout({ children }) {
  const [settings, setSettings] = useState(null);
  const [publishedPages, setPublishedPages] = useState([]);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const location = useLocation();
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  // Track a page_view whenever the pathname/search changes (SPA navigations).
  // Individual pages may fire more specific events (job_view, apply_start etc).
  useEffect(() => {
    track('page_view');
  }, [location.pathname, location.search]);

  useEffect(() => {
    Promise.all([
      api.get('/career/public/settings'),
      api.get('/career/public/pages').catch(() => ({ data: [] })),
    ])
      .then(([s, p]) => {
        setSettings(s.data);
        setPublishedPages(p.data || []);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, []);

  // Inject Google Fonts links + set root-level CSS vars + meta tags whenever settings arrive
  useEffect(() => {
    if (!settings) return;
    // Fonts
    const injectFont = (url, id) => {
      if (!url) return;
      let link = document.getElementById(id);
      if (!link) {
        link = document.createElement('link');
        link.id = id;
        link.rel = 'stylesheet';
        document.head.appendChild(link);
      }
      link.href = url;
    };
    injectFont(settings.heading_font_url, 'career-heading-font');
    injectFont(settings.body_font_url, 'career-body-font');
    // CSS vars scoped to the portal wrapper (declared inline via style prop below)

    // Base meta tags
    const title = settings.tagline
      ? `${settings.company_name} — ${settings.tagline}`
      : `${settings.company_name} Careers`;
    document.title = title;
    const desc = settings.meta_description || settings.subheadline || '';
    setMeta('description', desc);
    if (settings.meta_keywords) setMeta('keywords', settings.meta_keywords);
    setMeta('og:title', title, true);
    setMeta('og:description', desc, true);
    setMeta('og:type', 'website', true);
    setMeta('og:url', window.location.href, true);
    setMeta('og:image', `${backendUrl}/api/career/public/og-image`, true);
    setMeta('twitter:card', 'summary_large_image');
    setMeta('twitter:title', title);
    setMeta('twitter:description', desc);
    setMeta('twitter:image', `${backendUrl}/api/career/public/og-image`);
  }, [settings, backendUrl]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background" data-testid="career-public-loading">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (notFound || !settings) {
    return (
      <div className="min-h-screen flex items-center justify-center text-center px-4 bg-background" data-testid="career-public-not-found">
        <div>
          <h1 className="font-display text-2xl font-semibold mb-2">Careers site not available</h1>
          <p className="text-muted-foreground">This company hasn't published a careers site yet.</p>
        </div>
      </div>
    );
  }

  // Build the CSS var wrapper — every child (layout, static pages, job pages) inherits
  // brand colors + fonts through these vars.
  const rootStyle = {
    '--brand-primary': settings.primary_color || '#1a5c47',
    '--brand-secondary': settings.secondary_color || '#f4b942',
    fontFamily: settings.body_font_family || undefined,
  };
  const headingFontStyle = settings.heading_font_family ? { fontFamily: settings.heading_font_family } : undefined;

  const publishedKeys = new Set(publishedPages.map((p) => p.key));
  const visibleNav = STATIC_PAGE_NAV.filter((p) => publishedKeys.has(p.key));

  return (
    <CareerSettingsContext.Provider value={settings}>
      <div className="min-h-screen flex flex-col bg-background career-portal-root" style={rootStyle}>
        <header className="border-b border-border sticky top-0 z-20 bg-card/95 backdrop-blur">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
            <Link to="/careers" className="flex items-center gap-2" data-testid="career-public-logo">
              {settings.logo_file_id ? (
                <img src={`${backendUrl}/api/career/public/logo`} alt={settings.company_name} className="h-9 w-9 rounded-lg object-cover" />
              ) : (
                <span
                  className="h-9 w-9 rounded-lg flex items-center justify-center font-display font-bold text-white"
                  style={{ background: 'var(--brand-primary)' }}
                >
                  {settings.company_name?.[0] || 'C'}
                </span>
              )}
              <span className="font-display font-semibold text-lg" style={headingFontStyle}>{settings.company_name}</span>
            </Link>
            <nav className="flex items-center gap-5 text-sm font-medium">
              <Link to="/careers" data-testid="career-nav-home" className="hover:text-primary transition-colors">Home</Link>
              <Link to="/careers/jobs" data-testid="career-nav-jobs" className="hover:text-primary transition-colors">Open Roles</Link>
              {visibleNav.map((p) => (
                <Link
                  key={p.key}
                  to={`/careers/${p.key}`}
                  className="hover:text-primary transition-colors hidden md:inline"
                  data-testid={`career-nav-${p.key}`}
                >
                  {p.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-border py-8 mt-8">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 text-sm text-muted-foreground flex items-center justify-between flex-wrap gap-2">
            <span>© {new Date().getFullYear()} {settings.company_name}</span>
            <span>Powered by Pinnacle ATS</span>
          </div>
        </footer>
      </div>

      {/* Scoped font override: any element inside .career-portal-root using .font-display
          picks up the heading font, if configured. */}
      {settings.heading_font_family && (
        <style>{`.career-portal-root .font-display { font-family: ${settings.heading_font_family}; }`}</style>
      )}
      {settings.primary_color && (
        <style>{`.career-portal-root .text-primary { color: ${settings.primary_color}; } .career-portal-root .bg-primary { background-color: ${settings.primary_color}; } .career-portal-root .hover\\:text-primary:hover { color: ${settings.primary_color}; }`}</style>
      )}
    </CareerSettingsContext.Provider>
  );
}
