import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useSearchParams } from 'react-router-dom';
import { AlertTriangle, CalendarCheck2, CheckCircle2, Loader2, Mail, RefreshCw, Unplug } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { api, errMsg } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';

const SCOPE_LABELS = [
  { key: 'can_send_email', label: 'Send emails on your behalf', icon: Mail, note: 'Used when you email candidates from the ATS.' },
  { key: 'can_read_inbox', label: 'Read reply emails from candidates', icon: Mail, note: 'Used by the LLM auto-parser to detect notice period & expected compensation from replies.' },
  { key: 'has_calendar', label: 'Create Google Calendar events', icon: CalendarCheck2, note: 'Used when scheduling interviews.' },
];

const SCOPE_MAP = {
  can_send_email: 'https://www.googleapis.com/auth/gmail.send',
  can_read_inbox: 'https://www.googleapis.com/auth/gmail.readonly',
  has_calendar: 'https://www.googleapis.com/auth/calendar',
};

export default function MyIntegrationsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const load = useCallback(() => {
    setLoading(true);
    api
      .get('/calendar/status')
      .then((r) => setStatus(r.data))
      .catch(() => setStatus({ connected: false }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  // OAuth returns to this page with ?calendar=connected|error when initiated from here
  useEffect(() => {
    const cal = searchParams.get('calendar');
    if (cal === 'connected') {
      toast.success('Google account connected');
      searchParams.delete('calendar');
      setSearchParams(searchParams, { replace: true });
      load();
    } else if (cal === 'error') {
      toast.error('Could not connect Google account. Please try again.');
      searchParams.delete('calendar');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, load]);

  const connect = async () => {
    setBusy(true);
    try {
      const r = await api.get('/oauth/google/login', { params: { return_to: '/my-integrations' } });
      const url = r.data?.authorization_url;
      if (url) {
        window.location.href = url;
      } else {
        toast.error('Could not start Google sign-in');
        setBusy(false);
      }
    } catch (e) {
      toast.error(errMsg(e, 'Could not start Google sign-in'));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Disconnect your Google account? You will no longer be able to send emails from the ATS or auto-sync interviews until you reconnect.')) return;
    setBusy(true);
    try {
      await api.post('/calendar/disconnect');
      toast.success('Google account disconnected');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not disconnect'));
    } finally {
      setBusy(false);
    }
  };

  const scopes = (status?.scopes) || [];
  const derived = {
    can_send_email: !!status?.can_send_email,
    can_read_inbox: !!status?.can_read_inbox,
    has_calendar: scopes.includes(SCOPE_MAP.has_calendar),
  };
  const isMissingAny = status?.connected && (!derived.can_send_email || !derived.can_read_inbox || !derived.has_calendar);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">My Integrations</h1>
        <p className="text-sm text-muted-foreground">Connect your own Google/Gmail account to send emails and sync interviews from your personal address.</p>
      </div>

      <Card data-testid="google-integration-card">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-white border flex items-center justify-center">
              {/* Google 'G' mark */}
              <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
                <path fill="#EA4335" d="M24 9.5c3.9 0 7.4 1.4 10.1 3.6l7.5-7.5C36.9 1.7 30.9-1 24 -1 14.6-1 6.4 4.6 2.5 12.6l8.7 6.8C13.3 13 18.2 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.9 7.2l7.6 5.9c4.4-4.1 7.1-10.1 7.1-17.6z"/>
                <path fill="#FBBC05" d="M11.2 28.7c-.6-1.8-.9-3.7-.9-5.7s.3-3.9.9-5.7l-8.7-6.8C.6 14.6-1 19.1-1 23s1.6 8.4 3.5 12.5l8.7-6.8z"/>
                <path fill="#34A853" d="M24 46.5c6.5 0 11.9-2.1 15.8-5.8l-7.6-5.9c-2.1 1.4-4.8 2.3-8.2 2.3-5.8 0-10.7-3.5-12.8-8.9l-8.7 6.8C6.4 41.4 14.6 46.5 24 46.5z"/>
              </svg>
            </div>
            <div>
              <CardTitle className="text-base">Google (Gmail + Calendar)</CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">Signed in as <span className="font-medium">{user?.email}</span></p>
            </div>
          </div>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : status?.connected ? (
            <Badge variant="secondary" className="bg-emerald-100 text-emerald-800 border-emerald-200">Connected</Badge>
          ) : (
            <Badge variant="secondary" className="bg-slate-100 text-slate-700 border-slate-200">Not connected</Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          {status?.connected ? (
            <>
              <div className="rounded-lg border bg-slate-50 px-3 py-2.5 text-sm flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 mt-0.5 text-emerald-600" />
                <div>
                  <div>Connected as <span className="font-medium">{status.email}</span></div>
                  <div className="text-xs text-muted-foreground mt-0.5">Emails you send from the ATS will go out from this Google account.</div>
                </div>
              </div>

              <div>
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Permissions granted</div>
                <ul className="space-y-2">
                  {SCOPE_LABELS.map((s) => {
                    const ok = derived[s.key];
                    const Icon = s.icon;
                    return (
                      <li key={s.key} className="flex items-start gap-3 rounded-md border px-3 py-2" data-testid={`scope-${s.key}`}>
                        <Icon className={`h-4 w-4 mt-0.5 ${ok ? 'text-emerald-600' : 'text-amber-600'}`} />
                        <div className="flex-1">
                          <div className="text-sm font-medium flex items-center gap-2">
                            {s.label}
                            {ok ? (
                              <span className="text-[10px] uppercase tracking-wide text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">Granted</span>
                            ) : (
                              <span className="text-[10px] uppercase tracking-wide text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">Missing</span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">{s.note}</div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {isMissingAny && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2.5 text-sm flex items-start gap-2" data-testid="integration-missing-scope-banner">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <div className="font-medium">Some permissions are missing</div>
                    <div className="text-xs mt-0.5">Reconnect below to grant the missing permissions. You will not lose any data.</div>
                  </div>
                </div>
              )}

              <Separator />

              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={connect} disabled={busy} data-testid="reconnect-google-button">
                  <RefreshCw className="h-4 w-4 mr-2" /> Reconnect / grant more permissions
                </Button>
                <Button variant="outline" onClick={load} disabled={busy || loading} data-testid="refresh-status-button">
                  Refresh status
                </Button>
                <Button variant="destructive" onClick={disconnect} disabled={busy} data-testid="disconnect-google-button">
                  <Unplug className="h-4 w-4 mr-2" /> Disconnect
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="rounded-lg border bg-slate-50 px-4 py-6 text-center">
                <Mail className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                <div className="text-sm font-medium">You haven't connected a Google account yet</div>
                <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
                  Emails sent from the ATS go out from your <em>own</em> Gmail — connect your account to enable sending
                  candidate emails, syncing interviews to your calendar, and auto-parsing candidate replies.
                </p>
                <Button className="mt-4" onClick={connect} disabled={busy} data-testid="connect-google-button">
                  {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Mail className="h-4 w-4 mr-2" />}
                  Connect Gmail &amp; Calendar
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        We only use your Google account to send emails to candidates from your address, sync interviews to your calendar, and
        (optionally) read replies from candidates you've emailed via the ATS so we can auto-extract notice period &amp;
        expected compensation. You can disconnect at any time.
      </p>
    </div>
  );
}
