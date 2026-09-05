import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';
import { applyAccent } from '@/lib/tenant';

export default function LoginPage() {
  const { slug } = useParams();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [workspace, setWorkspace] = useState(null);
  const [wsError, setWsError] = useState('');

  useEffect(() => {
    if (!slug) return;
    api
      .get(`/tenants/by-slug/${slug}`)
      .then((r) => {
        setWorkspace(r.data);
        applyAccent(r.data.branding?.accent_color);
      })
      .catch(() => setWsError('This workspace does not exist. Check your sign-in link.'));
  }, [slug]);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Please enter your email and password');
      return;
    }
    setBusy(true);
    try {
      await login(email, password, slug);
      navigate('/');
    } catch (err) {
      toast.error(errMsg(err, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  const brand = workspace?.branding;
  const companyName = brand?.company_name || workspace?.name || 'HireFlow';
  const suspended = workspace?.status === 'suspended';

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background" data-testid="tenant-login-page">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-3 mb-8">
            {brand?.logo_url ? (
              <img src={brand.logo_url} alt={companyName} className="h-10 w-10 rounded-xl object-cover" data-testid="tenant-logo" />
            ) : (
              <PinnacleLogo size={40} />
            )}
            <div>
              <div className="font-display font-bold text-xl tracking-tight" data-testid="tenant-name">{companyName}</div>
              <div className="text-xs text-muted-foreground">
                {brand?.tagline || 'Applicant tracking, powered by HireFlow'}
              </div>
            </div>
          </div>

          {wsError ? (
            <Card className="border-destructive/30">
              <CardContent className="pt-6 space-y-3" data-testid="workspace-not-found">
                <h1 className="font-display text-xl font-semibold">Workspace not found</h1>
                <p className="text-sm text-muted-foreground">{wsError}</p>
                <Link to="/login" className="text-sm text-primary hover:underline font-medium">
                  Find your workspace
                </Link>
              </CardContent>
            </Card>
          ) : (
            <>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Welcome back</h1>
              <p className="text-sm text-muted-foreground mb-6">
                Sign in to <span className="font-medium text-foreground">{companyName}</span> to manage your hiring pipeline.
              </p>

              {suspended && (
                <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="workspace-suspended-banner">
                  This workspace is currently suspended. Please contact support.
                </div>
              )}

              <Card className="border-border shadow-sm">
                <CardContent className="pt-6">
                  <form onSubmit={submit} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        data-testid="login-email-input"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@company.com"
                        autoComplete="email"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="password">Password</Label>
                        <Link
                          to="/forgot-password"
                          className="text-xs text-primary hover:underline font-medium"
                          data-testid="forgot-password-link"
                        >
                          Forgot password?
                        </Link>
                      </div>
                      <Input
                        id="password"
                        type="password"
                        data-testid="login-password-input"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        autoComplete="current-password"
                      />
                    </div>
                    <Button type="submit" className="w-full" disabled={busy || suspended} data-testid="login-submit-button">
                      {busy ? 'Signing in...' : 'Sign in'}
                    </Button>
                  </form>
                </CardContent>
              </Card>

              <p className="mt-6 text-xs text-muted-foreground">
                Wrong workspace?{' '}
                <Link to="/login" className="text-primary hover:underline font-medium" data-testid="switch-workspace-link">
                  Switch workspace
                </Link>
              </p>
            </>
          )}
        </div>
      </div>

      <div className="hidden lg:block relative bg-slate-950 overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1620121692029-d088224ddc74?crop=entropy&cs=srgb&fm=jpg&q=85"
          alt="Abstract blue gradient"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-br from-blue-950/30 via-transparent to-blue-950/50" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />

        <div className="absolute inset-0 flex flex-col justify-center px-12">
          <p className="font-display text-3xl xl:text-4xl font-semibold text-white leading-tight tracking-tight">
            Hire faster with a pipeline<br />your whole team can see.
          </p>
          <p className="text-sm text-white/80 mt-3 max-w-md leading-relaxed">
            One workspace for resumes, interviews, and scorecards — so recruiters, hiring managers, and interviewers finally stay in sync.
          </p>
          <div className="mt-6 flex items-center gap-4 text-xs text-white/70">
            <div className="flex items-center gap-1.5">
              <div className="h-8 w-8 rounded-full bg-blue-500/90 border-2 border-white/30" />
              <div className="h-8 w-8 rounded-full bg-blue-400/90 border-2 border-white/30 -ml-4" />
              <div className="h-8 w-8 rounded-full bg-blue-300/90 border-2 border-white/30 -ml-4" />
            </div>
            <span>Trusted by hiring teams shipping roles this week</span>
          </div>
        </div>
      </div>
    </div>
  );
}
