import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { errMsg, platformApi } from '@/lib/api';

export default function PlatformLoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  if (localStorage.getItem('ats_platform_token')) return <Navigate to="/platform" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await platformApi.post('/platform/login', { email, password });
      localStorage.setItem('ats_platform_token', r.data.token);
      localStorage.setItem('ats_platform_admin', JSON.stringify(r.data.admin));
      navigate('/platform');
    } catch (err) {
      toast.error(errMsg(err, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-6" data-testid="platform-login-page">
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{ backgroundImage: 'radial-gradient(circle at 20% 15%, #1e293b 0, transparent 45%), radial-gradient(circle at 80% 80%, #0f766e 0, transparent 40%)' }}
      />
      <div className="relative w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-teal-500/15 border border-teal-400/30">
            <ShieldCheck className="h-5 w-5 text-teal-300" />
          </span>
          <div>
            <div className="font-display font-bold text-xl tracking-tight">Pinnacle Control</div>
            <div className="text-xs text-slate-400">Platform administration</div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 backdrop-blur p-6">
          <h1 className="font-display text-xl font-semibold mb-1">Owner sign-in</h1>
          <p className="text-sm text-slate-400 mb-6">Provision and manage customer workspaces.</p>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="pemail" className="text-slate-300">Email</Label>
              <Input
                id="pemail"
                type="email"
                data-testid="platform-email-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-slate-950 border-slate-800 text-slate-100"
                placeholder="owner@company.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ppass" className="text-slate-300">Password</Label>
              <Input
                id="ppass"
                type="password"
                data-testid="platform-password-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-950 border-slate-800 text-slate-100"
                placeholder="••••••••"
              />
            </div>
            <Button
              type="submit"
              disabled={busy}
              data-testid="platform-login-submit"
              className="w-full bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold"
            >
              {busy ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-xs text-slate-500">
          Looking for your company workspace?{' '}
          <Link to="/login" className="text-teal-300 hover:underline">Find it here</Link>
        </p>
      </div>
    </div>
  );
}
