import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { errMsg } from '@/lib/api';

const DEMO_ACCOUNTS = [
  { label: 'Admin', email: 'admin@ats.com', password: 'Admin@123' },
  { label: 'Recruiter', email: 'recruiter@ats.com', password: 'Recruit@123' },
  { label: 'Interviewer', email: 'interviewer@ats.com', password: 'Interview@123' },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Please enter your email and password');
      return;
    }
    setBusy(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      toast.error(errMsg(err, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-8">
            <PinnacleLogo size={40} />
            <div>
              <div className="font-display font-bold text-xl tracking-tight">Pinnacle ATS</div>
              <div className="text-xs text-muted-foreground">Lightweight applicant tracking</div>
            </div>
          </div>

          <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Welcome back</h1>
          <p className="text-sm text-muted-foreground mb-6">Sign in to manage your hiring pipeline.</p>

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
                  <Label htmlFor="password">Password</Label>
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
                <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit-button">
                  {busy ? 'Signing in...' : 'Sign in'}
                </Button>
              </form>

              <div className="mt-6">
                <div className="text-xs text-muted-foreground mb-2 text-center">Demo accounts — one-click sign in</div>
                <div className="grid grid-cols-3 gap-2">
                  {DEMO_ACCOUNTS.map((d) => (
                    <Button
                      key={d.label}
                      type="button"
                      variant="secondary"
                      size="sm"
                      data-testid={`demo-login-${d.label.toLowerCase()}`}
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          await login(d.email, d.password);
                          navigate('/');
                        } catch (err) {
                          toast.error(errMsg(err, 'Login failed'));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {d.label}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="hidden lg:block relative bg-accent">
        <img
          src="https://images.unsplash.com/photo-1588091210060-1ee4fab270ae?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2ODl8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBvZmZpY2UlMjBoaXJpbmclMjB0ZWFtJTIwbWVldGluZyUyMG1pbmltYWx8ZW58MHx8fGdyZWVufDE3ODQxMjE1NDh8MA&ixlib=rb-4.1.0&q=85"
          alt="Hiring team collaborating"
          className="absolute inset-0 h-full w-full object-cover opacity-80"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-foreground/60 to-transparent" />
        <div className="absolute bottom-10 left-10 right-10">
          <p className="font-display text-2xl font-semibold text-white leading-snug">
            Hire faster with a pipeline your whole team can see.
          </p>
          <p className="text-sm text-white/80 mt-2">AI resume parsing · kanban pipeline · structured scorecards</p>
        </div>
      </div>
    </div>
  );
}
