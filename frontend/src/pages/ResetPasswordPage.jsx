import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
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

export default function ResetPasswordPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';

  const [verifying, setVerifying] = useState(true);
  const [verifyError, setVerifyError] = useState('');
  const [tokenEmail, setTokenEmail] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifyError('Missing reset token. Please use the link from your email.');
      setVerifying(false);
      return;
    }
    api
      .get('/auth/reset-password/verify', { params: { token } })
      .then((r) => setTokenEmail(r.data?.email || ''))
      .catch((err) => setVerifyError(errMsg(err, 'Invalid or expired reset link')))
      .finally(() => setVerifying(false));
  }, [token]);

  const strength = useMemo(() => passwordStrength(pw), [pw]);
  const passwordsMatch = pw && pw === pw2;
  const canSubmit = pw.length >= 8 && passwordsMatch && !busy;

  if (user && !done) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (pw.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    if (pw !== pw2) {
      toast.error("Passwords don't match");
      return;
    }
    setBusy(true);
    try {
      await api.post('/auth/reset-password', { token, new_password: pw });
      setDone(true);
      toast.success('Password updated. Please sign in.');
      setTimeout(() => navigate('/login'), 1800);
    } catch (err) {
      toast.error(errMsg(err, 'Could not reset password'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <Link to="/login" className="flex items-center gap-2 mb-8">
            <PinnacleLogo size={40} />
            <div>
              <div className="font-display font-bold text-xl tracking-tight">HireFlow</div>
              <div className="text-xs text-muted-foreground">Lightweight applicant tracking</div>
            </div>
          </Link>

          {verifying ? (
            <div className="flex items-center gap-3 text-sm text-muted-foreground" data-testid="reset-verifying">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              Verifying reset link...
            </div>
          ) : verifyError ? (
            <>
              <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-rose-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-2" data-testid="reset-error-heading">Link not valid</h1>
              <p className="text-sm text-muted-foreground mb-6" data-testid="reset-error-message">{verifyError}</p>
              <div className="flex gap-2">
                <Link to="/forgot-password" className="flex-1">
                  <Button className="w-full">Request a new link</Button>
                </Link>
                <Link to="/login" className="flex-1">
                  <Button variant="outline" className="w-full">Back to sign in</Button>
                </Link>
              </div>
            </>
          ) : done ? (
            <>
              <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-emerald-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-2" data-testid="reset-success-heading">Password updated</h1>
              <p className="text-sm text-muted-foreground mb-6">You&apos;ll be redirected to the sign-in page in a moment.</p>
              <Link to="/login"><Button className="w-full">Sign in now</Button></Link>
            </>
          ) : (
            <>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Set a new password</h1>
              <p className="text-sm text-muted-foreground mb-6">
                {tokenEmail ? <>Resetting password for <strong className="text-foreground">{tokenEmail}</strong>.</> : 'Choose a strong new password below.'}
              </p>
              <Card className="border-border shadow-sm">
                <CardContent className="pt-6">
                  <form onSubmit={submit} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="pw">New password</Label>
                      <Input
                        id="pw"
                        type="password"
                        data-testid="reset-password-input"
                        value={pw}
                        onChange={(e) => setPw(e.target.value)}
                        placeholder="At least 8 characters"
                        autoComplete="new-password"
                        required
                      />
                      {pw && (
                        <div className="pt-1" data-testid="reset-strength-meter">
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
                      <Label htmlFor="pw2">Confirm password</Label>
                      <Input
                        id="pw2"
                        type="password"
                        data-testid="reset-password-confirm-input"
                        value={pw2}
                        onChange={(e) => setPw2(e.target.value)}
                        placeholder="Re-enter password"
                        autoComplete="new-password"
                        required
                      />
                      {pw2 && !passwordsMatch && (
                        <p className="text-xs text-rose-600" data-testid="reset-mismatch">Passwords don&apos;t match</p>
                      )}
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1 pl-4 list-disc">
                      <li className={pw.length >= 8 ? 'text-emerald-600' : ''}>At least 8 characters</li>
                      <li className={/[a-z]/.test(pw) && /[A-Z]/.test(pw) ? 'text-emerald-600' : ''}>Upper &amp; lower case letters</li>
                      <li className={/\d/.test(pw) ? 'text-emerald-600' : ''}>At least one number</li>
                    </ul>
                    <Button type="submit" className="w-full" disabled={!canSubmit} data-testid="reset-submit-button">
                      {busy ? 'Updating...' : 'Update password'}
                    </Button>
                  </form>
                </CardContent>
              </Card>
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
            Fresh start,<br />same secure workspace.
          </p>
          <p className="text-sm text-white/80 mt-3 max-w-md leading-relaxed">
            Once you save your new password, this reset link will no longer work.
          </p>
        </div>
      </div>
    </div>
  );
}
