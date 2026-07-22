import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { errMsg } from '@/lib/api';

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
                <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit-button">
                  {busy ? 'Signing in...' : 'Sign in'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="hidden lg:block relative bg-emerald-950 overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1708549566274-638eb2d2108b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzV8MHwxfHNlYXJjaHwyfHxlbWVyYWxkJTIwZ3JhZGllbnR8ZW58MHx8fGdyZWVufDE3ODQ3NjEwMjd8MA&ixlib=rb-4.1.0&q=85"
          alt="Abstract emerald gradient"
          className="absolute inset-0 h-full w-full object-cover"
        />
        {/* Subtle emerald brand overlay + darker bottom gradient for legible caption */}
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/20 via-transparent to-emerald-950/40" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />

        {/* Floating trust chips */}
        <div className="absolute top-8 right-8 flex flex-col items-end gap-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/15 backdrop-blur-md border border-white/20 px-3 py-1.5 text-xs font-medium text-white shadow-sm">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            AI-powered resume parsing
          </div>
          <div className="inline-flex items-center gap-2 rounded-full bg-white/15 backdrop-blur-md border border-white/20 px-3 py-1.5 text-xs font-medium text-white shadow-sm">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Structured interview scorecards
          </div>
        </div>

        <div className="absolute inset-0 flex flex-col justify-center px-12">
          <p className="font-display text-3xl xl:text-4xl font-semibold text-white leading-tight tracking-tight">
            Hire faster with a pipeline<br />your whole team can see.
          </p>
          <p className="text-sm text-white/80 mt-3 max-w-md leading-relaxed">
            One workspace for resumes, interviews, and scorecards — so recruiters, hiring managers, and interviewers finally stay in sync.
          </p>
          <div className="mt-6 flex items-center gap-4 text-xs text-white/70">
            <div className="flex items-center gap-1.5">
              <div className="h-8 w-8 rounded-full bg-emerald-500/90 border-2 border-white/30" />
              <div className="h-8 w-8 rounded-full bg-emerald-400/90 border-2 border-white/30 -ml-4" />
              <div className="h-8 w-8 rounded-full bg-emerald-300/90 border-2 border-white/30 -ml-4" />
            </div>
            <span>Trusted by hiring teams shipping roles this week</span>
          </div>
        </div>
      </div>
    </div>
  );
}
