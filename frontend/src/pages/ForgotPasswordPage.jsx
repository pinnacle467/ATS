import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

export default function ForgotPasswordPage() {
  const { user } = useAuth();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (!email) {
      toast.error('Please enter your email');
      return;
    }
    setBusy(true);
    try {
      await api.post('/auth/forgot-password', { email });
      setSent(true);
    } catch (err) {
      toast.error(errMsg(err, 'Could not send reset email'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <Link to="/login" className="flex items-center gap-2 mb-8 group">
            <PinnacleLogo size={40} />
            <div>
              <div className="font-display font-bold text-xl tracking-tight">Pinnacle ATS</div>
              <div className="text-xs text-muted-foreground">Lightweight applicant tracking</div>
            </div>
          </Link>

          {!sent ? (
            <>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Forgot your password?</h1>
              <p className="text-sm text-muted-foreground mb-6">
                Enter the email associated with your account and we&apos;ll send you a link to reset your password.
              </p>
              <Card className="border-border shadow-sm">
                <CardContent className="pt-6">
                  <form onSubmit={submit} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        data-testid="forgot-email-input"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@company.com"
                        autoComplete="email"
                        required
                      />
                    </div>
                    <Button type="submit" className="w-full" disabled={busy} data-testid="forgot-submit-button">
                      {busy ? 'Sending...' : 'Send reset link'}
                    </Button>
                  </form>
                  <div className="mt-6 text-center text-sm">
                    <Link to="/login" className="text-primary hover:underline font-medium" data-testid="back-to-login-link">
                      &larr; Back to sign in
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-emerald-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h1 className="font-display text-2xl font-semibold tracking-tight mb-2" data-testid="forgot-sent-heading">Check your inbox</h1>
              <p className="text-sm text-muted-foreground mb-1">
                If an account exists for <strong className="text-foreground">{email}</strong>, we&apos;ve sent a password reset link.
              </p>
              <p className="text-sm text-muted-foreground mb-6">
                The link expires in 60 minutes. Don&apos;t see it? Check spam or try again.
              </p>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setSent(false)} data-testid="forgot-try-again-button">
                  Try another email
                </Button>
                <Link to="/login" className="flex-1">
                  <Button className="w-full" data-testid="forgot-back-to-login-button">Back to sign in</Button>
                </Link>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="hidden lg:block relative bg-emerald-950 overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1708549566274-638eb2d2108b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzV8MHwxfHNlYXJjaHwyfHxlbWVyYWxkJTIwZ3JhZGllbnR8ZW58MHx8fGdyZWVufDE3ODQ3NjEwMjd8MA&ixlib=rb-4.1.0&q=85"
          alt="Abstract emerald gradient"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/20 via-transparent to-emerald-950/40" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        <div className="absolute bottom-12 left-12 right-12">
          <p className="font-display text-3xl xl:text-4xl font-semibold text-white leading-tight tracking-tight">
            Secure account access,<br />built for hiring teams.
          </p>
          <p className="text-sm text-white/80 mt-3 max-w-md leading-relaxed">
            Password resets are single-use and expire quickly, so your candidate pipeline stays protected.
          </p>
        </div>
      </div>
    </div>
  );
}
