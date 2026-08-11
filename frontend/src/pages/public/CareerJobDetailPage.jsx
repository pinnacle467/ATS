import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Briefcase, Copy, Facebook, Linkedin, MapPin, Twitter, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import { useCareerSettings, useCareerSecurity } from './CareerPublicLayout';
import { setMeta } from './CareerStaticPage';
import { track } from './tracking';
import { careersPath, getTenantSlug } from '@/lib/tenant';

const EMPTY_FORM = {
  first_name: '', last_name: '', email: '', phone: '', location: '', linkedin_url: '', portfolio_url: '',
  current_company: '', current_title: '', current_salary: '', expected_salary: '', notice_period: '',
  years_experience: '', cover_letter: '',
};

export default function CareerJobDetailPage() {
  const { jobSlug: slug } = useParams();
  const navigate = useNavigate();
  const settings = useCareerSettings();
  const security = useCareerSecurity();
  const [job, setJob] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [resumeFile, setResumeFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    api.get(`/career/public/jobs/${slug}`).then((r) => {
      setJob(r.data);
      // Analytics: fire once per job load so a job_view is attributed correctly
      // (deep-link visits, share-link visits, SPA nav from list all covered).
      track('job_view', { job_id: r.data?.id });
    }).catch(() => setNotFound(true));
  }, [slug]);

  // SEO: page title, meta description, OG tags, and Google JobPosting JSON-LD
  useEffect(() => {
    if (!job || !settings) return;
    const title = `${job.title} — ${settings.company_name}`;
    document.title = title;
    const desc = (job.description || job.jd_text || '').slice(0, 200) || settings.meta_description || '';
    setMeta('description', desc);
    setMeta('og:title', title, true);
    setMeta('og:description', desc, true);
    setMeta('og:type', 'website', true);
    setMeta('og:url', window.location.href, true);
    setMeta('og:image', `${backendUrl}/api/career/public/og-image?tenant=${getTenantSlug() || ''}`, true);
    setMeta('twitter:card', 'summary_large_image');
    setMeta('twitter:title', title);
    setMeta('twitter:description', desc);

    // Inject Google JobPosting JSON-LD only if enabled site-wide.
    if (settings.jobposting_seo_enabled === false) return;
    const existing = document.getElementById('jobposting-jsonld');
    if (existing) existing.remove();
    fetch(`${backendUrl}/api/career/public/jobs/${slug}/jobposting.json?tenant=${getTenantSlug() || ''}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        const script = document.createElement('script');
        script.type = 'application/ld+json';
        script.id = 'jobposting-jsonld';
        script.textContent = JSON.stringify(data);
        document.head.appendChild(script);
      })
      .catch(() => { /* SEO enhancement — silent fail */ });
    return () => {
      const s = document.getElementById('jobposting-jsonld');
      if (s) s.remove();
    };
  }, [job, settings, slug, backendUrl]);

  const shareUrl = window.location.href;

  const submit = async (e) => {
    e.preventDefault();
    if (!resumeFile) return toast.error('Please attach your resume');
    setSubmitting(true);
    try {
      // Fetch a reCAPTCHA v3 token if the site key is configured. The Google
      // script may still be loading — we wait up to ~4s before giving up.
      let recaptchaToken = '';
      if (security?.recaptcha_enabled && security?.recaptcha_site_key && window.grecaptcha) {
        try {
          await new Promise((resolve) => window.grecaptcha.ready(resolve));
          recaptchaToken = await window.grecaptcha.execute(security.recaptcha_site_key, { action: 'apply' });
        } catch (rcErr) {
          console.warn('reCAPTCHA execute failed', rcErr);
        }
      }
      const fd = new FormData();
      fd.append('job_id', job.id);
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      fd.append('resume', resumeFile);
      if (recaptchaToken) fd.append('recaptcha_token', recaptchaToken);
      await api.post('/career/public/apply', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      track('apply_submit', { job_id: job.id });
      setSubmitted(true);
    } catch (e2) {
      toast.error(errMsg(e2, 'Could not submit application'));
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) {
    return (
      <div className="px-4 py-20 text-center" data-testid="career-job-not-found">
        <h1 className="font-display text-2xl font-semibold mb-2">This role is no longer available</h1>
        <Button variant="outline" onClick={() => navigate(careersPath('/jobs'))} className="mt-4">Browse Open Roles</Button>
      </div>
    );
  }

  if (!job) return <div className="px-4 py-20 text-center text-muted-foreground">Loading...</div>;

  return (
    <div className="px-4 sm:px-6 py-10 max-w-3xl mx-auto" data-testid="career-job-detail-page">
      <Link to={careersPath('/jobs')} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6">
        <ArrowLeft className="h-3.5 w-3.5" /> All Roles
      </Link>

      <h1 className="font-display text-3xl font-semibold tracking-tight" data-testid="career-job-title">{job.title}</h1>
      <div className="flex items-center gap-4 text-sm text-muted-foreground mt-3 flex-wrap">
        <span className="flex items-center gap-1"><Briefcase className="h-3.5 w-3.5" /> {job.department}</span>
        <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {job.location || 'Remote'}</span>
      </div>
      <div className="flex gap-2 mt-3 flex-wrap">
        {job.employment_type && <Badge variant="outline">{job.employment_type}</Badge>}
        {job.remote_type && <Badge variant="outline">{job.remote_type}</Badge>}
        {job.experience_level && <Badge variant="outline">{job.experience_level}</Badge>}
      </div>

      <div className="flex items-center gap-2 mt-6">
        <Button onClick={() => { track('apply_start', { job_id: job.id }); setApplyOpen(true); }} data-testid="career-apply-now-button">Apply Now</Button>
        <div className="flex items-center gap-1 ml-2">
          <a href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noreferrer" data-testid="career-share-linkedin">
            <Button size="icon" variant="outline"><Linkedin className="h-4 w-4" /></Button>
          </a>
          <a href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noreferrer" data-testid="career-share-facebook">
            <Button size="icon" variant="outline"><Facebook className="h-4 w-4" /></Button>
          </a>
          <a href={`https://twitter.com/intent/tweet?url=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noreferrer" data-testid="career-share-twitter">
            <Button size="icon" variant="outline"><Twitter className="h-4 w-4" /></Button>
          </a>
          <Button
            size="icon"
            variant="outline"
            onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success('Link copied'); }}
            data-testid="career-share-copy"
          >
            <Copy className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {job.description && (
        <div className="mt-8 text-sm text-muted-foreground">{job.description}</div>
      )}
      {job.jd_text && (
        <div className="mt-8 whitespace-pre-wrap text-sm leading-relaxed" data-testid="career-job-description">{job.jd_text}</div>
      )}

      <div className="mt-10 border-t border-border pt-6">
        <Button onClick={() => { track('apply_start', { job_id: job.id }); setApplyOpen(true); }} size="lg" className="w-full sm:w-auto" data-testid="career-apply-now-button-bottom">Apply Now</Button>
      </div>

      <Dialog open={applyOpen} onOpenChange={(o) => { setApplyOpen(o); if (!o) { setSubmitted(false); setForm(EMPTY_FORM); setResumeFile(null); } }}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto" data-testid="career-apply-dialog">
          {submitted ? (
            <div className="text-center py-8" data-testid="career-apply-success">
              <h2 className="font-display text-xl font-semibold mb-2">Application submitted!</h2>
              <p className="text-muted-foreground text-sm">Thanks for applying to {job.title}. We'll be in touch soon.</p>
              <Button className="mt-6" onClick={() => setApplyOpen(false)}>Close</Button>
            </div>
          ) : (
            <>
              <DialogHeader><DialogTitle>Apply for {job.title}</DialogTitle></DialogHeader>
              <form onSubmit={submit} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>First Name *</Label><Input required value={form.first_name} onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))} data-testid="career-apply-first-name" /></div>
                  <div><Label>Last Name *</Label><Input required value={form.last_name} onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))} data-testid="career-apply-last-name" /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Email *</Label><Input type="email" required value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="career-apply-email" /></div>
                  <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} data-testid="career-apply-phone" /></div>
                </div>
                <div><Label>Location</Label><Input placeholder="City, Country" value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} data-testid="career-apply-location" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>LinkedIn URL</Label><Input value={form.linkedin_url} onChange={(e) => setForm((f) => ({ ...f, linkedin_url: e.target.value }))} data-testid="career-apply-linkedin" /></div>
                  <div><Label>Portfolio URL</Label><Input value={form.portfolio_url} onChange={(e) => setForm((f) => ({ ...f, portfolio_url: e.target.value }))} data-testid="career-apply-portfolio" /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Current Company</Label><Input value={form.current_company} onChange={(e) => setForm((f) => ({ ...f, current_company: e.target.value }))} data-testid="career-apply-current-company" /></div>
                  <div><Label>Current Title</Label><Input value={form.current_title} onChange={(e) => setForm((f) => ({ ...f, current_title: e.target.value }))} data-testid="career-apply-current-title" /></div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div><Label>Current Salary</Label><Input value={form.current_salary} onChange={(e) => setForm((f) => ({ ...f, current_salary: e.target.value }))} data-testid="career-apply-current-salary" /></div>
                  <div><Label>Expected Salary</Label><Input value={form.expected_salary} onChange={(e) => setForm((f) => ({ ...f, expected_salary: e.target.value }))} data-testid="career-apply-expected-salary" /></div>
                  <div><Label>Years Exp.</Label><Input value={form.years_experience} onChange={(e) => setForm((f) => ({ ...f, years_experience: e.target.value }))} data-testid="career-apply-years-experience" /></div>
                </div>
                <div><Label>Notice Period</Label><Input value={form.notice_period} onChange={(e) => setForm((f) => ({ ...f, notice_period: e.target.value }))} data-testid="career-apply-notice-period" /></div>
                <div><Label>Cover Letter</Label><Textarea rows={3} value={form.cover_letter} onChange={(e) => setForm((f) => ({ ...f, cover_letter: e.target.value }))} data-testid="career-apply-cover-letter" /></div>
                <div>
                  <Label>Resume *</Label>
                  <label
                    className="mt-1 flex items-center gap-2 border-2 border-dashed border-border rounded-lg px-4 py-3 text-sm cursor-pointer hover:border-primary/50 transition-colors"
                    data-testid="career-apply-resume-dropzone"
                  >
                    <Upload className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="truncate text-muted-foreground">{resumeFile ? resumeFile.name : 'Click to upload PDF or DOCX'}</span>
                    <input type="file" accept=".pdf,.docx,.doc" className="hidden" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} data-testid="career-apply-resume-input" />
                  </label>
                </div>
                <Button type="submit" className="w-full" disabled={submitting} data-testid="career-apply-submit-button">
                  {submitting ? 'Submitting...' : 'Submit Application'}
                </Button>
              </form>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
