import '@/App.css';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import AppShell from '@/components/AppShell';
import LoginPage from '@/pages/LoginPage';
import DashboardPage from '@/pages/DashboardPage';
import CandidatesPage from '@/pages/CandidatesPage';
import CandidateProfilePage from '@/pages/CandidateProfilePage';
import AddCandidatePage from '@/pages/AddCandidatePage';
import ImportCandidatesPage from '@/pages/ImportCandidatesPage';
import InterviewsPage from '@/pages/InterviewsPage';
import JobsPage from '@/pages/JobsPage';
import JobDetailPage from '@/pages/JobDetailPage';
import AdminPage from '@/pages/AdminPage';
import CareerDashboardPage from '@/pages/career/CareerDashboardPage';
import CareerJobsPage from '@/pages/career/CareerJobsPage';
import CareerSettingsPage from '@/pages/career/CareerSettingsPage';
import CareerContentPage from '@/pages/career/CareerContentPage';
import CareerMediaPage from '@/pages/career/CareerMediaPage';
import CareerPublicLayout from '@/pages/public/CareerPublicLayout';
import CareerHomePage from '@/pages/public/CareerHomePage';
import CareerJobsListPage from '@/pages/public/CareerJobsListPage';
import CareerJobDetailPage from '@/pages/public/CareerJobDetailPage';
import CareerStaticPage from '@/pages/public/CareerStaticPage';

const Protected = ({ children, roles }) => {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <AppShell>{children}</AppShell>;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Protected><DashboardPage /></Protected>} />
          <Route path="/candidates" element={<Protected><CandidatesPage /></Protected>} />
          <Route path="/candidates/new" element={<Protected roles={['admin', 'recruiter']}><AddCandidatePage /></Protected>} />
          <Route path="/candidates/import" element={<Protected roles={['admin', 'recruiter']}><ImportCandidatesPage /></Protected>} />
          <Route path="/candidates/:id" element={<Protected><CandidateProfilePage /></Protected>} />
          <Route path="/interviews" element={<Protected><InterviewsPage /></Protected>} />
          <Route path="/jobs" element={<Protected roles={['admin', 'recruiter']}><JobsPage /></Protected>} />
          <Route path="/jobs/:id" element={<Protected roles={['admin', 'recruiter']}><JobDetailPage /></Protected>} />
          <Route path="/admin" element={<Protected roles={['admin']}><AdminPage /></Protected>} />
          <Route path="/career-portal" element={<Protected roles={['admin', 'recruiter']}><CareerDashboardPage /></Protected>} />
          <Route path="/career-portal/jobs" element={<Protected roles={['admin', 'recruiter']}><CareerJobsPage /></Protected>} />
          <Route path="/career-portal/settings" element={<Protected roles={['admin', 'recruiter']}><CareerSettingsPage /></Protected>} />
          <Route path="/career-portal/content" element={<Protected roles={['admin', 'recruiter']}><CareerContentPage /></Protected>} />
          <Route path="/career-portal/media" element={<Protected roles={['admin', 'recruiter']}><CareerMediaPage /></Protected>} />
          <Route path="/careers" element={<CareerPublicLayout><CareerHomePage /></CareerPublicLayout>} />
          <Route path="/careers/jobs" element={<CareerPublicLayout><CareerJobsListPage /></CareerPublicLayout>} />
          <Route path="/careers/jobs/:slug" element={<CareerPublicLayout><CareerJobDetailPage /></CareerPublicLayout>} />
          <Route path="/careers/:key" element={<CareerPublicLayout><CareerStaticPage /></CareerPublicLayout>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}

export default App;
