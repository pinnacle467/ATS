import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  BarChart3,
  Briefcase,
  CalendarDays,
  Link2,
  FileSignature,
  FileText,
  Globe,
  Image as ImageIcon,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  Search,
  Settings,
  Shield,
  UserCircle2,
  UserPlus,
  Users,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/lib/api';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, testid: 'sidebar-nav-dashboard' },
  { to: '/candidates', label: 'Candidates', icon: Users, testid: 'sidebar-nav-candidates' },
  { to: '/jobs', label: 'Jobs', icon: Briefcase, roles: ['admin', 'recruiter'], testid: 'sidebar-nav-jobs' },
  { to: '/interviews', label: 'Interviews', icon: CalendarDays, testid: 'sidebar-nav-interviews' },
  { to: '/scheduling', label: 'Scheduling', icon: Link2, roles: ['admin', 'recruiter'], testid: 'sidebar-nav-scheduling' },
  { to: '/offers', label: 'Offers', icon: FileSignature, testid: 'sidebar-nav-offers' },
  { to: '/admin', label: 'Admin', icon: Settings, roles: ['admin'], testid: 'sidebar-nav-admin' },
];

const CAREER_NAV = [
  { to: '/career-portal', label: 'Dashboard', icon: Globe, testid: 'sidebar-nav-career-dashboard' },
  { to: '/career-portal/analytics', label: 'Analytics', icon: BarChart3, testid: 'sidebar-nav-career-analytics' },
  { to: '/career-portal/jobs', label: 'Jobs', icon: Briefcase, testid: 'sidebar-nav-career-jobs' },
  { to: '/career-portal/content', label: 'Content', icon: FileText, testid: 'sidebar-nav-career-content' },
  { to: '/career-portal/media', label: 'Media Library', icon: ImageIcon, testid: 'sidebar-nav-career-media' },
  { to: '/career-portal/settings', label: 'Settings', icon: Settings, testid: 'sidebar-nav-career-settings' },
  { to: '/career-portal/security', label: 'Security', icon: Shield, testid: 'sidebar-nav-career-security' },
];

const timeAgo = (iso) => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

export default function AppShell({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [notif, setNotif] = useState({ items: [], unread: 0 });
  const [search, setSearch] = useState('');
  const [mobileOpen, setMobileOpen] = useState(false);

  const loadNotifs = () => {
    api.get('/notifications').then((r) => setNotif(r.data)).catch(() => {});
  };

  useEffect(() => {
    loadNotifs();
    const t = setInterval(loadNotifs, 30000);
    return () => clearInterval(t);
  }, []);

  const markAllRead = async () => {
    await api.post('/notifications/mark-read');
    loadNotifs();
  };

  const initials = (user?.name || '?')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

// Role alias table — mirror of backend/permissions.py, so super_admin
// automatically satisfies nav items that require 'admin'/'recruiter'.
const NAV_ROLE_ALIASES = {
  super_admin: ['super_admin', 'admin', 'recruiter'],
  admin: ['admin', 'recruiter'],
  interview_panel: ['interview_panel', 'interviewer'],
  vendor: ['vendor'],
  recruiter: ['recruiter', 'admin'],
  interviewer: ['interviewer', 'interview_panel'],
};
function roleSatisfiesNav(userRole, requiredRoles) {
  const aliases = NAV_ROLE_ALIASES[userRole] || [userRole];
  return requiredRoles.some((r) => aliases.includes(r));
}

  const navItems = NAV.filter((n) => !n.roles || roleSatisfiesNav(user?.role, n.roles));

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[240px] bg-card border-r border-border flex flex-col transform transition-transform duration-200 lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-14 flex items-center gap-2 px-5 border-b border-border">
          <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity" data-testid="app-logo-link">
            <PinnacleLogo size={32} />
            <span className="font-display font-semibold text-lg tracking-tight">Pinnacle ATS</span>
          </Link>
        </div>
        <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
          {navItems.map((n) => {
            const active = n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to);
            const Icon = n.icon;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={n.testid}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'text-foreground bg-accent border-l-2 border-l-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                }`}
              >
                <Icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
          {['super_admin', 'admin', 'recruiter'].includes(user?.role) && (
            <>
              <div className="pt-4 pb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                Career Portal
              </div>
              {CAREER_NAV.map((n) => {
                const active = n.to === '/career-portal' ? location.pathname === n.to : location.pathname.startsWith(n.to);
                const Icon = n.icon;
                return (
                  <Link
                    key={n.to}
                    to={n.to}
                    data-testid={n.testid}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? 'text-foreground bg-accent border-l-2 border-l-primary'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {n.label}
                  </Link>
                );
              })}
            </>
          )}
        </nav>
        {['super_admin', 'admin', 'recruiter', 'vendor'].includes(user?.role) && (
          <div className="p-3 border-t border-border">
            <Button
              className="w-full"
              data-testid="sidebar-add-candidate-button"
              onClick={() => {
                setMobileOpen(false);
                navigate('/candidates/new');
              }}
            >
              <UserPlus className="h-4 w-4 mr-1" /> Add Candidate
            </Button>
          </div>
        )}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-foreground/30 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Main */}
      <div className="lg:pl-[240px]">
        {/* Topbar */}
        <header className="sticky top-0 z-20 h-14 bg-card border-b border-border flex items-center gap-3 px-4 sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5" />
          </Button>
          <form
            className="relative flex-1 max-w-md"
            onSubmit={(e) => {
              e.preventDefault();
              navigate(`/candidates?q=${encodeURIComponent(search)}`);
            }}
          >
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              data-testid="topbar-search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search candidates..."
              className="pl-9 h-9 bg-background"
            />
          </form>
          <div className="ml-auto flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="relative" data-testid="notifications-bell" aria-label="Notifications">
                  <Bell className="h-5 w-5" />
                  {notif.unread > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-0.5 rounded-full bg-destructive text-destructive-foreground text-[10px] font-semibold flex items-center justify-center">
                      {notif.unread}
                    </span>
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80" data-testid="notifications-menu">
                <div className="flex items-center justify-between px-2 py-1.5">
                  <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
                  {notif.unread > 0 && (
                    <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={markAllRead} data-testid="notifications-mark-all-read">
                      Mark all read
                    </Button>
                  )}
                </div>
                <DropdownMenuSeparator />
                {notif.items.length === 0 && (
                  <div className="px-3 py-6 text-sm text-muted-foreground text-center">No notifications yet</div>
                )}
                {notif.items.slice(0, 8).map((n) => (
                  <DropdownMenuItem
                    key={n.id}
                    className="flex flex-col items-start gap-0.5 py-2 cursor-pointer"
                    onClick={() => {
                      api.post(`/notifications/${n.id}/read`).then(loadNotifs);
                      if (n.link) navigate(n.link);
                    }}
                  >
                    <span className={`text-sm ${n.read ? 'text-muted-foreground' : 'font-medium'}`}>{n.message}</span>
                    <span className="text-xs text-muted-foreground font-mono">{timeAgo(n.created_at)}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="flex items-center gap-2 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  data-testid="user-menu-trigger"
                >
                  <span className="h-8 w-8 rounded-full bg-accent text-accent-foreground text-xs font-semibold flex items-center justify-center">
                    {initials}
                  </span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div className="text-sm font-medium">{user?.name}</div>
                  <div className="text-xs text-muted-foreground">{user?.email}</div>
                  <Badge variant="secondary" className="mt-1 capitalize">{user?.role}</Badge>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate('/account')} data-testid="account-menu" className="cursor-pointer">
                  <UserCircle2 className="h-4 w-4 mr-2" /> Account &amp; Security
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate('/my-integrations')} data-testid="my-integrations-menu" className="cursor-pointer">
                  <Mail className="h-4 w-4 mr-2" /> My Integrations
                </DropdownMenuItem>
                <DropdownMenuItem onClick={logout} data-testid="logout-button" className="cursor-pointer">
                  <LogOut className="h-4 w-4 mr-2" /> Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
