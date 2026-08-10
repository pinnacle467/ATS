import '@/App.css';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import AppShell from '@/components/AppShell';
import LoginPage from '@/pages/LoginPage';
import ForgotPasswordPage from '@/pages/ForgotPasswordPage';
import ResetPasswordPage from '@/pages/ResetPasswordPage';
import DashboardPage from '@/pages/DashboardPage';
import CandidatesPage from '@/pages/CandidatesPage';
import CandidateProfilePage from '@/pages/CandidateProfilePage';
import AddCandidatePage from '@/pages/AddCandidatePage';
import ImportCandidatesPage from '@/pages/ImportCandidatesPage';
import InterviewsPage from '@/pages/InterviewsPage';
import JobsPage from '@/pages/JobsPage';
import JobDetailPage from '@/pages/JobDetailPage';
import OffersPage from '@/pages/OffersPage';
import PublicOfferPage from '@/pages/PublicOfferPage';
import AdminPage from '@/pages/AdminPage';
import MyIntegrationsPage from '@/pages/MyIntegrationsPage';
import AccountPage from '@/pages/AccountPage';
import CareerDashboardPage from '@/pages/career/CareerDashboardPage';
import CareerJobsPage from '@/pages/career/CareerJobsPage';
import CareerSettingsPage from '@/pages/career/CareerSettingsPage';
import CareerSecurityPage from '@/pages/career/CareerSecurityPage';
import CareerContentPage from '@/pages/career/CareerContentPage';
import CareerMediaPage from '@/pages/career/CareerMediaPage';
import CareerAnalyticsPage from '@/pages/career/CareerAnalyticsPage';
import CareerPublicLayout from '@/pages/public/CareerPublicLayout';
import CareerHomePage from '@/pages/public/CareerHomePage';
import CareerJobsListPage from '@/pages/public/CareerJobsListPage';
import CareerJobDetailPage from '@/pages/public/CareerJobDetailPage';
import CareerStaticPage from '@/pages/public/CareerStaticPage';
import SchedulePage from '@/pages/public/SchedulePage';
import SchedulingDashboardPage from '@/pages/SchedulingDashboardPage';

// Role hierarchy alias map — mirrors backend/permissions.py ROLE_ALIASES so
// super_admin passes any 'admin'/'recruiter' check, and interview_panel passes
// any legacy 'interviewer' check. Prevents redirect loops after RBAC migration.
const ROLE_ALIASES = {
  super_admin: ['super_admin', 'admin', 'recruiter'],
  admin: ['admin', 'recruiter'],
  interview_panel: ['interview_panel', 'interviewer'],
  vendor: ['vendor'],
  recruiter: ['recruiter', 'admin'],
  interviewer: ['interviewer', 'interview_panel'],
};

function roleSatisfies(userRole, requiredRoles) {
  const aliases = ROLE_ALIASES[userRole] || [userRole];
  return requiredRoles.some((r) => aliases.includes(r));
}

const Protected = ({ children, roles }) => {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roleSatisfies(user.role, roles)) return <Navigate to="/" replace />;
  return <AppShell>{children}</AppShell>;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/" element={<Protected><DashboardPage /></Protected>} />
          <Route path="/candidates" element={<Protected><CandidatesPage /></Protected>} />
          <Route path="/candidates/new" element={<Protected roles={['admin', 'recruiter']}><AddCandidatePage /></Protected>} />
          <Route path="/candidates/import" element={<Protected roles={['admin', 'recruiter']}><ImportCandidatesPage /></Protected>} />
          <Route path="/candidates/:id" element={<Protected><CandidateProfilePage /></Protected>} />
          <Route path="/interviews" element={<Protected><InterviewsPage /></Protected>} />
          <Route path="/scheduling" element={<Protected roles={['admin', 'recruiter']}><SchedulingDashboardPage /></Protected>} />
          <Route path="/offers" element={<Protected><OffersPage /></Protected>} />
          <Route path="/offer/:token" element={<PublicOfferPage />} />
          <Route path="/jobs" element={<Protected roles={['admin', 'recruiter']}><JobsPage /></Protected>} />
          <Route path="/jobs/:id" element={<Protected roles={['admin', 'recruiter']}><JobDetailPage /></Protected>} />
          <Route path="/admin" element={<Protected roles={['admin']}><AdminPage /></Protected>} />
          <Route path="/my-integrations" element={<Protected><MyIntegrationsPage /></Protected>} />
          <Route path="/account" element={<Protected><AccountPage /></Protected>} />
          <Route path="/career-portal" element={<Protected roles={['admin', 'recruiter']}><CareerDashboardPage /></Protected>} />
          <Route path="/career-portal/jobs" element={<Protected roles={['admin', 'recruiter']}><CareerJobsPage /></Protected>} />
          <Route path="/career-portal/settings" element={<Protected roles={['admin', 'recruiter']}><CareerSettingsPage /></Protected>} />
          <Route path="/career-portal/security" element={<Protected roles={['admin', 'recruiter']}><CareerSecurityPage /></Protected>} />
          <Route path="/career-portal/content" element={<Protected roles={['admin', 'recruiter']}><CareerContentPage /></Protected>} />
          <Route path="/career-portal/media" element={<Protected roles={['admin', 'recruiter']}><CareerMediaPage /></Protected>} />
          <Route path="/career-portal/analytics" element={<Protected roles={['admin', 'recruiter']}><CareerAnalyticsPage /></Protected>} />
          <Route path="/careers" element={<CareerPublicLayout><CareerHomePage /></CareerPublicLayout>} />
          <Route path="/careers/jobs" element={<CareerPublicLayout><CareerJobsListPage /></CareerPublicLayout>} />
          <Route path="/careers/jobs/:slug" element={<CareerPublicLayout><CareerJobDetailPage /></CareerPublicLayout>} />
          <Route path="/careers/:key" element={<CareerPublicLayout><CareerStaticPage /></CareerPublicLayout>} />
          <Route path="/schedule/interview/:token" element={<SchedulePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}

export default App;
