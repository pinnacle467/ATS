import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, Info, Loader2, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

/**
 * Send Email to one or many candidates.
 * Props:
 *   open: boolean
 *   onOpenChange: (o: boolean) => void
 *   candidateIds: string[]  — 1 or more candidate ids
 *   candidateNames?: string[]  — optional, shown for context
 *   onSent?: (result) => void  — called after a successful send
 */
export default function SendEmailDialog({ open, onOpenChange, candidateIds = [], candidateNames = [], onSent }) {
  const [mode, setMode] = useState('template'); // 'template' | 'custom'
  const [templates, setTemplates] = useState([]);
  const [templateKey, setTemplateKey] = useState('');
  const [variables, setVariables] = useState({});
  const [subject, setSubject] = useState('');
  const [htmlBody, setHtmlBody] = useState('');
  const [preview, setPreview] = useState(null); // { subject, html }
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [sending, setSending] = useState(false);
  const [gmailStatus, setGmailStatus] = useState(null); // {connected, email} | null
  const [connectingGmail, setConnectingGmail] = useState(false);

  const count = candidateIds.length;
  const isBulk = count > 1;

  // Load templates and Gmail connection status when dialog opens
  useEffect(() => {
    if (!open) return;
    setLoadingTemplates(true);
    api
      .get('/career/email-templates')
      .then((r) => {
        const tpls = (r.data.templates || []).filter((t) => t.enabled !== false);
        setTemplates(tpls);
        setVariables(r.data.variables || {});
        // Default to first non-auto template (i.e. one meant for manual send)
        if (tpls.length && !templateKey) {
          const first = tpls.find((t) => !t.auto_send) || tpls[0];
          setTemplateKey(first.key);
        }
      })
      .catch((e) => toast.error(errMsg(e, 'Failed to load email templates')))
      .finally(() => setLoadingTemplates(false));
    api
      .get('/calendar/status')
      .then((r) => setGmailStatus(r.data))
      .catch(() => setGmailStatus({ connected: false, email: null }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const connectGmail = async () => {
    setConnectingGmail(true);
    try {
      const r = await api.get('/oauth/google/login');
      const url = r.data?.authorization_url;
      if (url) {
        // Open in a new tab so the user doesn't lose their draft
        window.open(url, '_blank', 'noopener');
        toast.message('Complete the Google sign-in in the new tab, then click Refresh below.');
      } else {
        toast.error('Could not start Google sign-in');
      }
    } catch (e) {
      toast.error(errMsg(e, 'Could not start Google sign-in'));
    } finally {
      setConnectingGmail(false);
    }
  };

  const refreshGmailStatus = () => {
    api.get('/calendar/status').then((r) => {
      setGmailStatus(r.data);
      if (r.data?.connected) toast.success(`Connected as ${r.data.email}`);
      else toast.error('Still not connected — did you finish the sign-in?');
    }).catch(() => {});
  };

  // Reset transient state when closed
  useEffect(() => {
    if (!open) {
      setPreview(null);
      setSending(false);
    }
  }, [open]);

  const activeTemplate = useMemo(() => templates.find((t) => t.key === templateKey), [templates, templateKey]);

  // When switching to template mode or changing template, prefill subject/body so the user can tweak
  useEffect(() => {
    if (mode === 'template' && activeTemplate) {
      setSubject(activeTemplate.subject || '');
      setHtmlBody(activeTemplate.html_body || '');
    }
  }, [mode, activeTemplate?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchPreview = async () => {
    if (mode === 'template' && templateKey) {
      try {
        const r = await api.get(`/career/email-templates/${templateKey}/preview`);
        setPreview(r.data);
      } catch (e) {
        toast.error(errMsg(e, 'Preview failed'));
      }
    } else {
      // For custom mode, just show the raw subject/html (no server-side sample fill)
      setPreview({ subject, html: htmlBody });
    }
  };

  const send = async () => {
    if (mode === 'custom' && (!subject.trim() || !htmlBody.trim())) {
      toast.error('Subject and message are required for a custom email');
      return;
    }
    if (mode === 'template' && !templateKey) {
      toast.error('Please choose a template');
      return;
    }
    setSending(true);
    try {
      const payload = { candidate_ids: candidateIds };
      if (mode === 'template') {
        payload.template_key = templateKey;
        // Only send overrides if the user actually edited them
        if (activeTemplate && subject && subject !== activeTemplate.subject) payload.subject = subject;
        if (activeTemplate && htmlBody && htmlBody !== activeTemplate.html_body) payload.html_body = htmlBody;
      } else {
        payload.subject = subject;
        payload.html_body = htmlBody;
      }
      const r = await api.post('/career/emails/send', payload);
      const { sent, failed, skipped_no_email, skipped_missing, total } = r.data;

      // Craft a helpful summary toast
      if (sent === 0 && failed === 0 && (skipped_no_email || skipped_missing)) {
        toast.error(`No emails sent — ${skipped_no_email} without email, ${skipped_missing} not found`);
      } else if (sent > 0 && failed === 0 && !skipped_no_email && !skipped_missing) {
        toast.success(`Sent to ${sent} candidate${sent === 1 ? '' : 's'}`);
      } else {
        const parts = [];
        if (sent) parts.push(`${sent} sent`);
        if (failed) parts.push(`${failed} failed`);
        if (skipped_no_email) parts.push(`${skipped_no_email} skipped (no email)`);
        if (skipped_missing) parts.push(`${skipped_missing} not found`);
        (failed > 0 ? toast.error : toast.success)(`Result: ${parts.join(', ')} of ${total}`);
      }

      // Surface the very first failure reason (e.g. no_gmail_connected) so the admin knows what to fix
      const firstFail = (r.data.results || []).find((x) => !x.sent && x.reason && x.reason !== 'no_email_on_candidate');
      if (firstFail && firstFail.reason === 'no_gmail_connected') {
        toast.error('Your Gmail is not connected. Click "Connect Gmail" above to sign in with your Google account.', { duration: 8000 });
        // Refresh the status banner so the connect button shows
        api.get('/calendar/status').then((r) => setGmailStatus(r.data)).catch(() => {});
      }

      onSent?.(r.data);
      if (sent > 0) onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e, 'Send failed'));
    } finally {
      setSending(false);
    }
  };

  const previewNames = candidateNames.slice(0, 3).join(', ') + (count > 3 ? ` +${count - 3} more` : '');

  return (
    <Dialog open={open} onOpenChange={(o) => !sending && onOpenChange(o)}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Send email to {count} candidate{count === 1 ? '' : 's'}
          </DialogTitle>
        </DialogHeader>

        {candidateNames.length > 0 && (
          <p className="text-xs text-muted-foreground -mt-2">Recipients: {previewNames}</p>
        )}

        {/* Gmail connection banner — emails are sent from the logged-in user's own Gmail */}
        {gmailStatus && !gmailStatus.connected && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2.5 text-sm flex items-start gap-2" data-testid="gmail-not-connected-banner">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-medium">Connect your Gmail to send</div>
              <div className="text-xs mt-0.5">Emails go out from your own Gmail account. Click Connect Gmail to sign in with Google — you can keep this dialog open.</div>
              <div className="mt-2 flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={connectGmail}
                  disabled={connectingGmail}
                  data-testid="connect-gmail-button"
                >
                  {connectingGmail ? 'Opening…' : 'Connect Gmail'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={refreshGmailStatus}
                  data-testid="refresh-gmail-status-button"
                >
                  I've signed in — refresh
                </Button>
              </div>
            </div>
          </div>
        )}
        {gmailStatus?.connected && !gmailStatus.can_send_email && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2.5 text-sm flex items-start gap-2" data-testid="gmail-scope-missing-banner">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-medium">Reconnect Gmail to grant send permission</div>
              <div className="text-xs mt-0.5">Your Google account is connected but doesn't grant email-send access yet. Click below to reconnect and grant the extra permission.</div>
              <div className="mt-2 flex gap-2">
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={connectGmail} disabled={connectingGmail} data-testid="reconnect-gmail-button">
                  {connectingGmail ? 'Opening…' : 'Reconnect Gmail'}
                </Button>
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={refreshGmailStatus}>Refresh</Button>
              </div>
            </div>
          </div>
        )}
        {gmailStatus?.connected && gmailStatus.can_send_email && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-900 px-3 py-2 text-xs flex items-center gap-2" data-testid="gmail-connected-banner">
            <Mail className="h-3.5 w-3.5" /> Sending from <span className="font-medium">{gmailStatus.email}</span>
          </div>
        )}

        {/* Mode toggle */}
        <div className="flex rounded-lg border border-border overflow-hidden w-fit" data-testid="email-mode-toggle">
          <button
            type="button"
            onClick={() => setMode('template')}
            className={`px-3 py-1.5 text-sm ${mode === 'template' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            data-testid="email-mode-template"
          >
            Use template
          </button>
          <button
            type="button"
            onClick={() => setMode('custom')}
            className={`px-3 py-1.5 text-sm ${mode === 'custom' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            data-testid="email-mode-custom"
          >
            Write custom
          </button>
        </div>

        {mode === 'template' && (
          <div className="space-y-2">
            <Label>Template</Label>
            <Select value={templateKey} onValueChange={setTemplateKey}>
              <SelectTrigger data-testid="email-template-select">
                <SelectValue placeholder={loadingTemplates ? 'Loading…' : 'Choose a template'} />
              </SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.key} value={t.key}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activeTemplate?.description && (
              <p className="text-xs text-muted-foreground">{activeTemplate.description}</p>
            )}
          </div>
        )}

        <div className="space-y-2">
          <Label>Subject</Label>
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Email subject"
            data-testid="email-subject-input"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Message (HTML supported)</Label>
            <button
              type="button"
              onClick={fetchPreview}
              className="text-xs text-primary hover:underline"
              data-testid="email-preview-button"
            >
              Preview
            </button>
          </div>
          <Textarea
            value={htmlBody}
            onChange={(e) => setHtmlBody(e.target.value)}
            placeholder={mode === 'custom' ? 'Type your message. HTML tags work.' : 'Edit the template body if you want to tweak it for this send'}
            className="min-h-[160px] font-mono text-sm"
            data-testid="email-body-textarea"
          />
          {Object.keys(variables).length > 0 && (
            <div className="rounded-lg bg-secondary/50 border border-border p-2 text-xs text-muted-foreground">
              <div className="flex items-start gap-1.5">
                <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <div>
                  <span className="font-medium">Variables:</span>{' '}
                  {Object.keys(variables).map((v) => (
                    <code key={v} className="mx-0.5 px-1 py-0.5 bg-card rounded border border-border">{v}</code>
                  ))}
                  {isBulk && <div className="mt-1">Each candidate gets a personalized copy — variables are filled per-recipient.</div>}
                </div>
              </div>
            </div>
          )}
        </div>

        {preview && (
          <div className="rounded-lg border border-border bg-card p-3 space-y-2" data-testid="email-preview-panel">
            <div className="text-xs font-medium text-muted-foreground">Preview (with sample data)</div>
            <div className="text-sm font-semibold">{preview.subject}</div>
            <div
              className="prose prose-sm max-w-none text-sm border-t border-border pt-2"
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{ __html: preview.html }}
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>Cancel</Button>
          <Button onClick={send} disabled={sending || count === 0} data-testid="email-send-button">
            {sending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
            <Mail className="h-4 w-4 mr-1.5" />
            {sending ? 'Sending…' : `Send${isBulk ? ` to ${count}` : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
