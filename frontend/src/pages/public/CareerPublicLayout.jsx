import { createContext, useContext, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/lib/api';

const CareerSettingsContext = createContext(null);
export const useCareerSettings = () => useContext(CareerSettingsContext);

export default function CareerPublicLayout({ children }) {
  const [settings, setSettings] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get('/career/public/settings')
      .then((r) => setSettings(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, []);

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

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <CareerSettingsContext.Provider value={settings}>
      <div className="min-h-screen flex flex-col bg-background">
        <header className="border-b border-border sticky top-0 z-20 bg-card/95 backdrop-blur">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
            <Link to="/careers" className="flex items-center gap-2" data-testid="career-public-logo">
              {settings.logo_file_id ? (
                <img src={`${backendUrl}/api/career/public/logo`} alt={settings.company_name} className="h-9 w-9 rounded-lg object-cover" />
              ) : (
                <span
                  className="h-9 w-9 rounded-lg flex items-center justify-center font-display font-bold text-white"
                  style={{ background: settings.primary_color }}
                >
                  {settings.company_name?.[0] || 'C'}
                </span>
              )}
              <span className="font-display font-semibold text-lg">{settings.company_name}</span>
            </Link>
            <nav className="flex items-center gap-6 text-sm font-medium">
              <Link to="/careers" data-testid="career-nav-home" className="hover:text-primary transition-colors">Home</Link>
              <Link to="/careers/jobs" data-testid="career-nav-jobs" className="hover:text-primary transition-colors">Open Roles</Link>
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
    </CareerSettingsContext.Provider>
  );
}
