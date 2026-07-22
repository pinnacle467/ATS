import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { KeyRound, Shield, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

function passwordStrength(pw) {
  if (!pw) return { score: 0, label: '', color: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const map = [
    { label: 'Very weak', color: 'bg-rose-500' },
    { label: 'Weak', color: 'bg-rose-400' },
    { label: 'Fair', color: 'bg-amber-400' },
    { label: 'Good', color: 'bg-emerald-400' },
    { label: 'Strong', color: 'bg-emerald-500' },
    { label: 'Excellent', color: 'bg-emerald-600' },
  ];
  return { score, ...map[Math.min(score, 5)] };
}

const fmtDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
};

export default function AccountPage() {
  const { user, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);

  const strength = useMemo(() => passwordStrength(pw), [pw]);
  const passwordsMatch = pw && pw === pw2;
  const meetsRules =
    pw.length >= 8 &&
    /[a-z]/.test(pw) && /[A-Z]/.test(pw) &&
    /\d/.test(pw);
  const canSubmit = current && meetsRules && passwordsMatch && pw !== current && !busy;

  const submit = async (e) => {
    e.preventDefault();
    if (!current) {
      toast.error('Enter your current password');
      return;
    }
    if (!meetsRules) {
      toast.error('New password does not meet requirements');
      return;
    }
    if (!passwordsMatch) {
      toast.error("Passwords don't match");
      return;
    }
    if (pw === current) {
      toast.error('New password must be different from current');
      return;
    }
    setBusy(true);
    try {
      await api.post('/auth/change-password', { current_password: current, new_password: pw });
      toast.success('Password updated. Please sign in again with your new password.');
      setCurrent(''); setPw(''); setPw2('');
      // Log out for security so all sessions must re-authenticate
      setTimeout(() => logout(), 1200);
    } catch (err) {
      toast.error(errMsg(err, 'Could not update password'));
    } finally {
      setBusy(false);
    }
  };

  const initials = (user?.name || '?')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Account &amp; Security</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your profile and change your password.</p>
      </div>

      {/* Profile card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>Your account details as stored in Pinnacle ATS.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-emerald-100 text-emerald-700 text-xl font-semibold flex items-center justify-center">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-lg">{user?.name}</div>
              <div className="text-sm text-muted-foreground truncate">{user?.email}</div>
              <div className="flex items-center gap-2 mt-1.5">
                <Badge variant="secondary" className="capitalize">{user?.role}</Badge>
                {user?.active ? (
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
                    <ShieldCheck className="h-3 w-3" /> Active
                  </span>
                ) : (
                  <span className="text-xs text-rose-600">Inactive</span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Last sign-in</div>
              <div className="mt-1 font-medium">{fmtDate(user?.last_login)}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Password last changed</div>
              <div className="mt-1 font-medium">{fmtDate(user?.password_updated_at)}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Change password card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" /> Change password
          </CardTitle>
          <CardDescription>
            After changing your password you&apos;ll be signed out and asked to sign in again for security.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4 max-w-md">
            <div className="space-y-1.5">
              <Label htmlFor="current">Current password</Label>
              <Input
                id="current"
                type="password"
                data-testid="change-current-password-input"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pw">New password</Label>
              <Input
                id="pw"
                type="password"
                data-testid="change-new-password-input"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                autoComplete="new-password"
                placeholder="At least 8 characters"
                required
              />
              {pw && (
                <div className="pt-1" data-testid="change-strength-meter">
                  <div className="flex gap-1 h-1">
                    {[0,1,2,3,4].map((i) => (
                      <div key={i} className={`flex-1 rounded-full ${i < strength.score ? strength.color : 'bg-muted'}`} />
                    ))}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Strength: {strength.label}</div>
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pw2">Confirm new password</Label>
              <Input
                id="pw2"
                type="password"
                data-testid="change-confirm-password-input"
                value={pw2}
                onChange={(e) => setPw2(e.target.value)}
                autoComplete="new-password"
                required
              />
              {pw2 && !passwordsMatch && (
                <p className="text-xs text-rose-600" data-testid="change-mismatch">Passwords don&apos;t match</p>
              )}
            </div>

            <div className="rounded-md border border-border bg-muted/30 p-3">
              <div className="text-xs font-medium mb-2 flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5" /> Password requirements
              </div>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li className={pw.length >= 8 ? 'text-emerald-700' : ''}>• At least 8 characters</li>
                <li className={/[a-z]/.test(pw) && /[A-Z]/.test(pw) ? 'text-emerald-700' : ''}>• Upper &amp; lower case letters</li>
                <li className={/\d/.test(pw) ? 'text-emerald-700' : ''}>• At least one number</li>
                <li className={pw && current && pw !== current ? 'text-emerald-700' : ''}>• Different from current password</li>
              </ul>
            </div>

            <Button type="submit" disabled={!canSubmit} data-testid="change-submit-button">
              {busy ? 'Updating...' : 'Update password'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
