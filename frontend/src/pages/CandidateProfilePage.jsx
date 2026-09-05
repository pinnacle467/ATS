import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Briefcase,
  Building2,
  CalendarDays,
  ChevronDown,
  Clock,
  Download,
  ExternalLink,
  Factory,
  FileText,
  GraduationCap,
  Mail,
  MapPin,
  Maximize2,
  Pencil,
  Phone,
  RefreshCw,
  Save,
  Sparkles,
  Star,
  Tag,
  Target,
  Trash2,
  Wallet,
  X,
} from 'lucide-react';
import { renderAsync } from 'docx-preview';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { StageBadge, REJECTION_REASONS, SOURCES, initialsOf } from '@/pages/CandidatesPage';
import ChangeLog from '@/components/ChangeLog';
import { IndustryChips, IndustryTagEditor } from '@/components/IndustryPicker';
import OfferPanel from '@/components/OfferPanel';
import RoundFeedbackSection from '@/components/RoundFeedbackSection';
import SendEmailDialog from '@/components/SendEmailDialog';
import ScheduleRequestDialog from '@/components/ScheduleRequestDialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/context/AuthContext';
import { isAdminOrHigher } from '@/lib/roles';
import { api, errMsg } from '@/lib/api';
import { useCachedJobs } from '@/lib/referenceCache';

const RECO_LABEL = { strong_yes: 'Strong Yes', yes: 'Yes', no: 'No', strong_no: 'Strong No' };
const RECO_COLOR = { strong_yes: 'bg-green-100 text-green-800', yes: 'bg-emerald-100 text-emerald-800', no: 'bg-orange-100 text-orange-800', strong_no: 'bg-red-100 text-red-800' };

function fitScoreStyle(score) {
  if (score >= 75) return 'border-green-500 text-green-700 bg-green-50';
  if (score >= 50) return 'border-amber-500 text-amber-700 bg-amber-50';
  return 'border-red-500 text-red-700 bg-red-50';
}

// Confidence bucket → chip colour. Amber (medium) and red (low) explicitly
// prompt the recruiter to verify before trusting the value.
const CONFIDENCE_STYLE = {
  high:   { chip: 'bg-emerald-100 text-emerald-800 border-emerald-300', dot: 'bg-emerald-500', label: 'High confidence' },
  medium: { chip: 'bg-amber-100 text-amber-800 border-amber-300',       dot: 'bg-amber-500',   label: 'Medium confidence — please verify' },
  low:    { chip: 'bg-rose-100 text-rose-800 border-rose-300',          dot: 'bg-rose-500',    label: 'Low confidence — please verify' },
};

// Vertical stepper shown in the sidebar "Pipeline Status" card — purely
// informational (the actual stage change control lives in the header select).
function PipelineStepper({ stages, currentStage }) {
  const list = stages.filter((s) => s !== 'Rejected');
  const currentIdx = list.indexOf(currentStage);
  return (
    <div>
      {list.map((s, i) => {
        const passed = i <= currentIdx;
        const isLast = i === list.length - 1;
        return (
          <div key={s} className="flex gap-3" data-testid={`pipeline-step-${s}`}>
            <div className="flex flex-col items-center">
              <span className={`h-3 w-3 rounded-full shrink-0 ${passed ? 'bg-primary' : 'bg-border'}`} />
              {!isLast && <span className={`w-0.5 flex-1 ${i < currentIdx ? 'bg-primary' : 'bg-border'}`} style={{ minHeight: 22 }} />}
            </div>
            <span className={`text-xs pb-5 -mt-0.5 ${i === currentIdx ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>{s}</span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Small chip shown next to notice_period / expected_compensation on the profile
 * card. Renders only when the value was auto-extracted from Gmail (meta.source ===
 * 'auto'). Clicking opens a popover with the extracted snippet, a link to the
 * original Gmail thread, and prior history.
 */
function AutoExtractedBadge({ meta, history }) {
  if (!meta || meta.source !== 'auto') return null;
  const conf = meta.confidence || 'low';
  const style = CONFIDENCE_STYLE[conf] || CONFIDENCE_STYLE.low;
  const extractedAt = meta.extracted_at ? new Date(meta.extracted_at) : null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-full border ${style.chip} px-1.5 py-px text-[10px] font-medium hover:opacity-80 transition-opacity`}
          title={style.label}
          data-testid="auto-extracted-badge"
        >
          <Sparkles className="h-2.5 w-2.5" />
          <span>Auto</span>
          <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
        </button>
      </PopoverTrigger>
      <PopoverContent side="top" className="w-80 text-xs space-y-2" data-testid="auto-extracted-popover">
        <div className="flex items-center justify-between">
          <p className="font-semibold text-sm">Auto-extracted from email</p>
          <Badge variant="outline" className={`${style.chip} text-[10px]`}>{style.label}</Badge>
        </div>
        {meta.snippet ? (
          <div>
            <p className="text-muted-foreground mb-0.5">Source snippet:</p>
            <p className="italic border-l-2 border-border pl-2 py-0.5 text-slate-700">&ldquo;{meta.snippet}&rdquo;</p>
          </div>
        ) : (
          <p className="text-muted-foreground italic">No verbatim snippet returned by extractor.</p>
        )}
        {meta.source_subject && (
          <p><span className="text-muted-foreground">Email subject:</span> {meta.source_subject}</p>
        )}
        {extractedAt && (
          <p><span className="text-muted-foreground">Extracted:</span> {extractedAt.toLocaleString()}</p>
        )}
        {meta.source_thread_url && (
          <a
            href={meta.source_thread_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            <ExternalLink className="h-3 w-3" /> Open in Gmail
          </a>
        )}
        {Array.isArray(history) && history.length > 1 && (
          <div className="pt-2 border-t">
            <p className="text-muted-foreground mb-1">History (last {history.length}):</p>
            <ul className="space-y-1">
              {history.map((h, idx) => (
                <li key={`${h.extracted_at || idx}`} className="flex justify-between gap-2">
                  <span className="truncate">{h.value || <em className="text-muted-foreground">null</em>}</span>
                  <span className="text-muted-foreground shrink-0">
                    {h.extracted_at ? new Date(h.extracted_at).toLocaleDateString() : '—'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

export default function CandidateProfilePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [cand, setCand] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [scorecards, setScorecards] = useState([]);
  const [stages, setStages] = useState([]);
  const [upcomingInterviews, setUpcomingInterviews] = useState([]);
  const [note, setNote] = useState('');
  const [noteType, setNoteType] = useState('note');
  const [resumeUrl, setResumeUrl] = useState(null);
  const [resumeType, setResumeType] = useState(null); // null | 'loading' | 'pdf' | 'docx' | 'unsupported' | 'error'
  const [resumeBlob, setResumeBlob] = useState(null);
  const [resumeFilename, setResumeFilename] = useState('');
  // Track viewport width so the resume preview can degrade gracefully on mobile,
  // where iOS Safari + most Android browsers cannot render PDFs inside an
  // <iframe src="blob:...">. Below md (768px) we show a big tap-friendly
  // "Open Resume" card instead of the broken iframe.
  const [isMobileViewport, setIsMobileViewport] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 767px)').matches;
  });
  const docxContainerRef = useRef(null);
  const expandedDocxContainerRef = useRef(null);
  const [resumeExpandOpen, setResumeExpandOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectCategory, setRejectCategory] = useState('');
  const [pendingStage, setPendingStage] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [jobs] = useCachedJobs();
  const [emailDialogOpen, setEmailDialogOpen] = useState(false);
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingDetails, setSavingDetails] = useState(false);
  const [scanningReplies, setScanningReplies] = useState(false);
  // Inline name-edit state — separate from the Details card edit so users can
  // rename a candidate quickly from the header without opening the full form.
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [savingName, setSavingName] = useState(false);

  const isRecruiter = ['super_admin', 'admin', 'recruiter'].includes(user?.role);
  const isAdminPlus = ['super_admin', 'admin'].includes(user?.role);

  const load = useCallback(() => {
    api
      .get(`/candidates/${id}`)
      .then((r) => {
        setCand(r.data);
        if (r.data.job?.stages) setStages(r.data.job.stages);
        else api.get('/settings/pipeline').then((p) => setStages((p.data.stages || []).map((s) => s.name)));
      })
      .catch((e) => {
        if (e.response?.status === 403 || e.response?.status === 404) setNotFound(true);
      });
    api.get(`/candidates/${id}/timeline`).then((r) => setTimeline(r.data)).catch(() => {});
    api.get(`/candidates/${id}/scorecards`).then((r) => setScorecards(r.data)).catch(() => {});
    api.get('/interviews', { params: { candidate_id: id, status: 'scheduled' } })
      .then((r) => setUpcomingInterviews((r.data || []).filter((iv) => iv.scheduled_at && new Date(iv.scheduled_at) >= new Date())))
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Fit score is computed async in the background — retry once shortly after load if pending.
  useEffect(() => {
    if (cand?.job_id && cand?.job?.jd_text && cand?.fit_score == null) {
      const t = setTimeout(() => load(), 6000);
      return () => clearTimeout(t);
    }
  }, [cand?.id, cand?.job_id, cand?.fit_score, cand?.job?.jd_text, load]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const mq = window.matchMedia('(max-width: 767px)');
    const handler = (e) => setIsMobileViewport(e.matches);
    // Modern + Safari-legacy compat: addEventListener when available, else
    // fall back to the deprecated addListener API.
    if (mq.addEventListener) mq.addEventListener('change', handler);
    else mq.addListener(handler);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', handler);
      else mq.removeListener(handler);
    };
  }, []);

  useEffect(() => {
    let url;
    let cancelled = false;
    setResumeUrl(null);
    setResumeBlob(null);
    setResumeFilename('');
    setResumeType(cand?.resume_file_id ? 'loading' : null);
    if (cand?.resume_file_id) {
      api
        .get(`/files/${cand.resume_file_id}`, { responseType: 'blob' })
        .then((r) => {
          if (cancelled) return;
          const contentType = (r.headers['content-type'] || '').toLowerCase();
          const dispo = r.headers['content-disposition'] || '';
          const nameMatch = dispo.match(/filename="?([^"]+)"?/i);
          const filename = nameMatch?.[1] || '';
          const ext = filename.toLowerCase().split('.').pop();
          const blob = new Blob([r.data], { type: r.headers['content-type'] });
          setResumeFilename(filename);
          if (contentType.includes('pdf') || ext === 'pdf') {
            url = URL.createObjectURL(blob);
            setResumeUrl(url);
            setResumeType('pdf');
          } else if (contentType.includes('word') || contentType.includes('officedocument') || ext === 'docx' || ext === 'doc') {
            // Also create a blob URL for the "Open in new tab" affordance on
            // mobile — desktop still uses `renderAsync` to render inline.
            url = URL.createObjectURL(blob);
            setResumeUrl(url);
            setResumeBlob(blob);
            setResumeType('docx');
          } else {
            url = URL.createObjectURL(blob);
            setResumeUrl(url);
            setResumeType('unsupported');
          }
        })
        .catch(() => !cancelled && setResumeType('error'));
    }
    return () => {
      cancelled = true;
      url && URL.revokeObjectURL(url);
    };
  }, [cand?.resume_file_id]);

  // Render DOCX preview into its container once both the blob and the DOM node are ready
  useEffect(() => {
    if (resumeType === 'docx' && resumeBlob && docxContainerRef.current) {
      const container = docxContainerRef.current;
      container.innerHTML = '';
      renderAsync(resumeBlob, container, container, {
        className: 'docx-preview',
        inWrapper: true,
        ignoreWidth: true,
        ignoreHeight: true,
        breakPages: false,
      }).catch(() => setResumeType('docx-error'));
    }
  }, [resumeType, resumeBlob]);

  // Render the same DOCX preview into the larger expanded-view container when it opens.
  // Small delay lets the Dialog's open animation/layout settle first (docx-preview measures
  // the container's actual width when ignoreWidth is used — rendering too early against an
  // in-transition/zero-width container produces a blank result).
  useEffect(() => {
    if (resumeExpandOpen && resumeType === 'docx' && resumeBlob) {
      const timer = setTimeout(() => {
        const container = expandedDocxContainerRef.current;
        if (!container) return;
        container.innerHTML = '';
        renderAsync(resumeBlob, container, container, {
          className: 'docx-preview-expanded',
          inWrapper: true,
          ignoreWidth: true,
          ignoreHeight: true,
          breakPages: false,
        }).catch((err) => console.error('Expanded DOCX render failed:', err));
      }, 200);
      return () => clearTimeout(timer);
    }
  }, [resumeExpandOpen, resumeType, resumeBlob]);

  const moveStage = async (stage, reason) => {
    try {
      await api.post(`/candidates/${id}/move-stage`, { stage, reason });
      toast.success(`Moved to ${stage}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const onStageChange = (stage) => {
    if (stage === 'Rejected') {
      setPendingStage(stage);
      setRejectCategory('');
      setRejectReason('');
      setRejectOpen(true);
    } else {
      moveStage(stage);
    }
  };

  const changeSource = async (newSource) => {
    if (!newSource || newSource === cand.source) return;
    try {
      await api.put(`/candidates/${id}`, { source: newSource });
      toast.success(`Source updated to ${(SOURCES.find((s) => s.value === newSource)?.label) || newSource}`);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Failed to update source'));
    }
  };

  const changeJob = async (newJobId) => {
    if (!newJobId || newJobId === cand.job_id) return;
    try {
      await api.put(`/candidates/${id}`, { job_id: newJobId });
      const newJob = jobs.find((j) => j.id === newJobId);
      const newStages = newJob?.stages || [];
      if (newStages.length && !newStages.includes(cand.stage)) {
        await api.post(`/candidates/${id}/move-stage`, { stage: newStages[0] });
      }
      toast.success(`Candidate moved to ${newJob?.title || 'the selected job'}`);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not change job'));
    }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    try {
      await api.post(`/candidates/${id}/notes`, { text: note, note_type: noteType });
      setNote('');
      toast.success(noteType === 'email_log' ? 'Email logged' : 'Note added');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const downloadResume = async () => {
    try {
      const r = await api.get(`/files/${cand.resume_file_id}?download=true`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${cand.name}-resume`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errMsg(e, 'Download failed'));
    }
  };

  const deleteCandidate = async () => {
    if (!window.confirm(`Delete ${cand.name}? This cannot be undone.`)) return;
    try {
      await api.delete(`/candidates/${id}`);
      toast.success('Candidate deleted');
      navigate('/candidates');
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const startEditDetails = () => {
    setEditForm({
      email: cand.email || '',
      phone: cand.phone || '',
      location: cand.location || '',
      current_title: cand.current_title || '',
      current_company: cand.current_company || '',
      notice_period: cand.notice_period || '',
      expected_compensation: cand.expected_compensation || '',
      tags: (cand.tags || []).join(', '),
      industry: cand.industry || [],
    });
    setEditingDetails(true);
  };

  const cancelEditDetails = () => {
    setEditingDetails(false);
    setEditForm({});
  };

  const startEditName = () => {
    setNameDraft(cand?.name || '');
    setEditingName(true);
  };

  const cancelEditName = () => {
    setEditingName(false);
    setNameDraft('');
  };

  const saveName = async () => {
    const next = (nameDraft || '').trim();
    if (!next) {
      toast.error('Name cannot be empty');
      return;
    }
    if (next === cand?.name) {
      cancelEditName();
      return;
    }
    setSavingName(true);
    try {
      await api.put(`/candidates/${id}`, { name: next });
      toast.success('Name updated');
      setEditingName(false);
      setNameDraft('');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Failed to update name'));
    } finally {
      setSavingName(false);
    }
  };

  const saveDetails = async () => {
    setSavingDetails(true);
    try {
      const payload = {
        email: editForm.email?.trim() || null,
        phone: editForm.phone?.trim() || null,
        location: editForm.location?.trim() || null,
        current_title: editForm.current_title?.trim() || null,
        current_company: editForm.current_company?.trim() || null,
        notice_period: editForm.notice_period?.trim() || null,
        tags: (editForm.tags || '').split(',').map((t) => t.trim()).filter(Boolean),
        industry: editForm.industry || [],
      };
      if (isAdminPlus) {
        payload.expected_compensation = editForm.expected_compensation?.trim() || null;
      }
      await api.put(`/candidates/${id}`, payload);
      toast.success('Details updated');
      setEditingDetails(false);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Failed to update details'));
    } finally {
      setSavingDetails(false);
    }
  };

  const scanReplies = async (overwrite = false) => {
    // If the caller is forcing overwrite, confirm — this can destroy a recruiter's
    // manual edits (notice_period + expected_compensation) if the LLM extracts
    // different values from Gmail.
    if (overwrite) {
      const ok = window.confirm(
        'Force re-scan Gmail and overwrite any manually entered Notice Period and Expected Compensation for this candidate?\n\n'
        + 'This cannot be undone (previous values are kept in history, but the visible fields will be replaced).'
      );
      if (!ok) return;
    }
    setScanningReplies(true);
    try {
      const r = await api.post(`/candidates/${id}/scan-replies`, null, { params: { overwrite } });
      if (r.data?.ok === false) {
        const reason = r.data.reason;
        if (reason === 'no_gmail_connected') {
          toast.error('Connect your Gmail first from My Integrations.', {
            action: { label: 'Open', onClick: () => navigate('/my-integrations') },
            duration: 8000,
          });
        } else if (reason === 'missing_readonly_scope' || reason === 'insufficient_scope' || reason === 'invalid_token') {
          toast.error('Reconnect your Gmail to grant inbox-read permission.', {
            action: { label: 'Reconnect', onClick: () => navigate('/my-integrations') },
            duration: 10000,
          });
        } else if (reason === 'no_email_on_candidate') {
          toast.error('This candidate has no email on file.');
        } else {
          toast.error(r.data.message || `Could not scan replies (${reason || 'unknown error'})`);
        }
      } else if (r.data?.updated) {
        toast.success(overwrite ? 'Force re-scan complete — details updated' : 'Extracted candidate reply — details updated');
        load();
      } else if (r.data?.replies_scanned > 0) {
        toast.message(`Scanned ${r.data.replies_scanned} repl${r.data.replies_scanned === 1 ? 'y' : 'ies'} — nothing new to extract`);
      } else {
        toast.message('No replies found in your inbox yet');
      }
    } catch (e) {
      toast.error(errMsg(e, 'Scan failed'));
    } finally {
      setScanningReplies(false);
    }
  };

  if (notFound)
    return (
      <div className="text-center py-20">
        <p className="text-lg font-medium">Candidate not available</p>
        <p className="text-sm text-muted-foreground mt-1">This candidate doesn&apos;t exist or you don&apos;t have access.</p>
        <Button className="mt-4" variant="outline" onClick={() => navigate('/candidates')}>Back to candidates</Button>
      </div>
    );

  if (!cand)
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/candidates')} aria-label="Back" data-testid="candidate-back-button">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <span className="h-12 w-12 rounded-full bg-primary/10 text-primary text-sm font-semibold flex items-center justify-center shrink-0 mt-0.5">
            {initialsOf(cand.name)}
          </span>
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              {editingName ? (
                <div className="flex items-center gap-2">
                  <Input
                    autoFocus
                    value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); saveName(); }
                      if (e.key === 'Escape') { e.preventDefault(); cancelEditName(); }
                    }}
                    disabled={savingName}
                    className="h-9 text-2xl font-display font-semibold tracking-tight px-2 w-[280px] sm:w-[360px]"
                    maxLength={120}
                    data-testid="candidate-name-input"
                    aria-label="Edit candidate name"
                  />
                  <Button
                    size="icon"
                    variant="default"
                    onClick={saveName}
                    disabled={savingName || !nameDraft.trim()}
                    className="h-8 w-8"
                    data-testid="candidate-name-save-button"
                    aria-label="Save name"
                    title="Save (Enter)"
                  >
                    <Save className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={cancelEditName}
                    disabled={savingName}
                    className="h-8 w-8"
                    data-testid="candidate-name-cancel-button"
                    aria-label="Cancel edit"
                    title="Cancel (Esc)"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 group">
                  <h1 className="font-display text-2xl font-semibold tracking-tight" data-testid="candidate-name">{cand.name}</h1>
                  {isRecruiter && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={startEditName}
                      className="h-7 w-7 text-muted-foreground opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
                      data-testid="candidate-name-edit-button"
                      aria-label="Edit name"
                      title="Edit name"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              )}
              {cand.candidate_code && (
                <span className="text-xs font-mono text-muted-foreground bg-secondary rounded-full px-2.5 py-0.5" data-testid="candidate-code">{cand.candidate_code}</span>
              )}
              <StageBadge stage={cand.stage} />
              {cand.low_confidence_fields?.length > 0 && (
                <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50">Needs review: {cand.low_confidence_fields.join(', ')}</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {cand.current_title || 'No title'}{cand.current_company ? ` at ${cand.current_company}` : ''} · applied {cand.applied_at ? new Date(cand.applied_at).toLocaleDateString() : '—'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRecruiter && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEmailDialogOpen(true)}
              disabled={!cand.email}
              title={cand.email ? 'Send email to this candidate' : 'No email on file'}
              data-testid="candidate-send-email-button"
            >
              <Mail className="h-4 w-4 mr-1.5" /> Send Email
            </Button>
          )}
          {isRecruiter && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setScheduleDialogOpen(true)}
              title="Send a scheduling link so the candidate can pick a time"
              data-testid="candidate-schedule-interview-button"
            >
              <CalendarDays className="h-4 w-4 mr-1.5" /> Schedule Interview
            </Button>
          )}
          {isRecruiter && (
            <Select value={cand.source || ''} onValueChange={changeSource}>
              <SelectTrigger className="w-[160px]" data-testid="candidate-source-select" title="Change source">
                <SelectValue placeholder="Source">
                  {SOURCES.find((s) => s.value === cand.source)?.label || (cand.source ? cand.source.replace('_', ' ') : 'Set source')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>{SOURCES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
            </Select>
          )}
          {isRecruiter && (
            <Select value={cand.stage} onValueChange={onStageChange}>
              <SelectTrigger className="w-[160px]" data-testid="candidate-stage-select"><SelectValue /></SelectTrigger>
              <SelectContent>{stages.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          )}
          {['super_admin', 'admin'].includes(user?.role) && (
            <Button variant="outline" size="icon" onClick={deleteCandidate} aria-label="Delete candidate" data-testid="candidate-delete-button">
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
        </div>
      </div>

      {cand.status === 'rejected' && cand.rejection_reason && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded-xl px-4 py-3">Rejected: {cand.rejection_reason}</div>
      )}

      <Tabs defaultValue="overview" className="w-full" data-testid="candidate-tabs">
        <TabsList className="bg-transparent border-b border-border rounded-none p-0 h-auto justify-start gap-6" data-testid="candidate-tabs-list">
          <TabsTrigger value="overview" className="rounded-none border-b-2 border-transparent px-1 pb-2.5 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-primary data-[state=active]:text-primary" data-testid="candidate-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="feedback" className="rounded-none border-b-2 border-transparent px-1 pb-2.5 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-primary data-[state=active]:text-primary" data-testid="candidate-tab-feedback">Interviews & Feedback</TabsTrigger>
          <TabsTrigger value="offer" className="rounded-none border-b-2 border-transparent px-1 pb-2.5 data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-primary data-[state=active]:text-primary" data-testid="candidate-tab-offer">Offer</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-4 space-y-5">
        <div className="grid lg:grid-cols-3 gap-5">
        {/* Left: details + resume */}
        <div className="lg:col-span-2 space-y-5">
          <Card className="shadow-none">
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-semibold">Contact & Details</CardTitle>
              {isRecruiter && !editingDetails && (
                <div className="flex items-center gap-1">
                  {isAdminPlus && cand.email && (
                    <div className="inline-flex items-center rounded-md border border-input">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs rounded-r-none border-r border-input"
                        onClick={() => scanReplies(false)}
                        disabled={scanningReplies}
                        data-testid="candidate-scan-replies-button"
                        title="Scan your Gmail inbox for candidate replies and auto-fill Notice Period / Expected Compensation (does not overwrite manual values)"
                      >
                        {scanningReplies ? 'Scanning…' : (<><Sparkles className="h-3.5 w-3.5 mr-1" /> Scan replies</>)}
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-1.5 rounded-l-none"
                            disabled={scanningReplies}
                            data-testid="candidate-scan-replies-menu"
                            title="More scan options"
                            aria-label="More scan options"
                          >
                            <ChevronDown className="h-3.5 w-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-64">
                          <DropdownMenuItem
                            onSelect={() => scanReplies(false)}
                            data-testid="candidate-scan-replies-menu-normal"
                          >
                            <Sparkles className="h-3.5 w-3.5 mr-2" /> Scan replies
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onSelect={() => scanReplies(true)}
                            className="text-rose-600 focus:text-rose-700 focus:bg-rose-50"
                            data-testid="candidate-scan-replies-menu-force"
                          >
                            <RefreshCw className="h-3.5 w-3.5 mr-2" /> Force re-scan (overwrite manual)
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={startEditDetails}
                    data-testid="candidate-details-edit-button"
                  >
                    <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                  </Button>
                </div>
              )}
              {editingDetails && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={cancelEditDetails}
                    disabled={savingDetails}
                    data-testid="candidate-details-cancel-button"
                  >
                    <X className="h-3.5 w-3.5 mr-1" /> Cancel
                  </Button>
                  <Button
                    size="sm"
                    className="h-7 text-xs"
                    onClick={saveDetails}
                    disabled={savingDetails}
                    data-testid="candidate-details-save-button"
                  >
                    <Save className="h-3.5 w-3.5 mr-1" /> {savingDetails ? 'Saving…' : 'Save'}
                  </Button>
                </div>
              )}
            </CardHeader>
            <CardContent className="grid sm:grid-cols-2 gap-3 text-sm">
              {editingDetails ? (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Mail className="h-3.5 w-3.5" /> Email</Label>
                    <Input value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} placeholder="candidate@example.com" data-testid="edit-email" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Phone className="h-3.5 w-3.5" /> Phone</Label>
                    <Input value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} placeholder="+1 555 000 1234" data-testid="edit-phone" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" /> Location</Label>
                    <Input value={editForm.location} onChange={(e) => setEditForm((f) => ({ ...f, location: e.target.value }))} placeholder="City, Country" data-testid="edit-location" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Briefcase className="h-3.5 w-3.5" /> Current Title</Label>
                    <Input value={editForm.current_title} onChange={(e) => setEditForm((f) => ({ ...f, current_title: e.target.value }))} placeholder="Senior Engineer" data-testid="edit-current-title" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Building2 className="h-3.5 w-3.5" /> Current Company</Label>
                    <Input value={editForm.current_company} onChange={(e) => setEditForm((f) => ({ ...f, current_company: e.target.value }))} placeholder="Company Inc." data-testid="edit-current-company" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Notice Period</Label>
                    <Input value={editForm.notice_period} onChange={(e) => setEditForm((f) => ({ ...f, notice_period: e.target.value }))} placeholder="e.g. 60 days, Immediate" data-testid="edit-notice-period" />
                  </div>
                  {isAdminPlus && (
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Wallet className="h-3.5 w-3.5" /> Expected Compensation <span className="text-[10px] uppercase tracking-wide text-amber-600">Admin only</span></Label>
                      <Input value={editForm.expected_compensation} onChange={(e) => setEditForm((f) => ({ ...f, expected_compensation: e.target.value }))} placeholder="e.g. 22 LPA, $130k base" data-testid="edit-expected-compensation" />
                    </div>
                  )}
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Tag className="h-3.5 w-3.5" /> Tags (comma-separated)</Label>
                    <Input value={editForm.tags} onChange={(e) => setEditForm((f) => ({ ...f, tags: e.target.value }))} placeholder="e.g. senior, remote, referral" data-testid="edit-tags" />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5"><Factory className="h-3.5 w-3.5" /> Industries</Label>
                    <IndustryTagEditor value={editForm.industry || []} onChange={(v) => setEditForm((f) => ({ ...f, industry: v }))} testId="edit-industry" />
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2"><Mail className="h-4 w-4 text-muted-foreground" />{cand.email || <span className="text-muted-foreground">No email</span>}</div>
                  <div className="flex items-center gap-2"><Phone className="h-4 w-4 text-muted-foreground" />{cand.phone || <span className="text-muted-foreground">No phone</span>}</div>
                  <div className="flex items-center gap-2"><MapPin className="h-4 w-4 text-muted-foreground" />{cand.location || <span className="text-muted-foreground">No location</span>}</div>
                  <div className="flex items-center gap-2" data-testid="candidate-job-field">
                    <Briefcase className="h-4 w-4 text-muted-foreground shrink-0" />
                    {isRecruiter ? (
                      <Select value={cand.job_id || ''} onValueChange={changeJob}>
                        <SelectTrigger className="h-8 text-sm" data-testid="candidate-job-select">
                          <SelectValue placeholder="Assign a job" />
                        </SelectTrigger>
                        <SelectContent>
                          {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title} · {j.department}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    ) : (
                      cand.job?.title || <span className="text-muted-foreground">No job assigned</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2"><Star className="h-4 w-4 text-muted-foreground" />Recruiter: {cand.recruiter?.name || '—'}</div>
                  <div className="flex items-center gap-2" data-testid="candidate-notice-period">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    Notice Period: {cand.notice_period || <span className="text-muted-foreground">Not specified</span>}
                    <AutoExtractedBadge meta={cand.notice_period_meta} history={cand.notice_period_history} />
                  </div>
                  {isAdminPlus && (
                    <div className="flex items-center gap-2" data-testid="candidate-expected-compensation">
                      <Wallet className="h-4 w-4 text-muted-foreground" />
                      Expected Comp.: {cand.expected_compensation || <span className="text-muted-foreground">Not specified</span>}
                      <AutoExtractedBadge meta={cand.expected_compensation_meta} history={cand.expected_compensation_history} />
                    </div>
                  )}
                  <div className="flex items-center gap-2 flex-wrap">
                    <Tag className="h-4 w-4 text-muted-foreground" />
                    {(cand.tags || []).length === 0 && <span className="text-muted-foreground">No tags</span>}
                    {(cand.tags || []).map((t) => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
                  </div>
                  <div className="sm:col-span-2">
                    <Separator className="my-2" />
                    <div className="flex items-start gap-2" data-testid="candidate-industries">
                      <Factory className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-muted-foreground mb-1">Industries</p>
                        <IndustryChips industries={cand.industry || []} testId="candidate-industry-chips" />
                      </div>
                    </div>
                  </div>
                  {(cand.skills || []).length > 0 && (
                    <div className="sm:col-span-2">
                      <Separator className="my-2" />
                      <div className="flex flex-wrap gap-1.5">
                        {cand.skills.map((s) => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {cand.job_id && (
            <Card className="shadow-none" data-testid="candidate-fit-score">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><Target className="h-4 w-4" /> Job Fit Score</CardTitle></CardHeader>
              <CardContent>
                {cand.fit_score != null ? (
                  <div className="flex items-center gap-4">
                    <div
                      className={`flex items-center justify-center h-16 w-16 rounded-full border-[3px] font-display text-xl font-bold shrink-0 ${fitScoreStyle(cand.fit_score)}`}
                      data-testid="candidate-fit-score-value"
                    >
                      {cand.fit_score}
                    </div>
                    <div className="flex-1 min-w-0">
                      {cand.fit_score_summary && <p className="text-sm">{cand.fit_score_summary}</p>}
                      <p className="text-xs text-muted-foreground font-mono mt-1">
                        vs. {cand.job?.title || 'job'}{cand.fit_score_computed_at ? ` · scored ${new Date(cand.fit_score_computed_at).toLocaleString()}` : ''}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground py-1" data-testid="candidate-fit-score-pending">
                    {!cand.job?.jd_text
                      ? 'This job has no job description attached yet — add one on the Job page to see a fit score.'
                      : 'Calculating fit score against the job description...'}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {(cand.experience?.length > 0 || cand.education?.length > 0) && (
            <Card className="shadow-none">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Background</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {cand.experience?.length > 0 && (
                  <div className="space-y-2.5">
                    {cand.experience.map((e, i) => (
                      <div key={i} className="flex gap-3">
                        <Building2 className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                        <div>
                          <div className="text-sm font-medium">{e.title} · {e.company}</div>
                          <div className="text-xs text-muted-foreground font-mono">{e.start_date || '?'} – {e.end_date || '?'}</div>
                          {e.description && <div className="text-xs text-muted-foreground mt-0.5">{e.description}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {cand.education?.length > 0 && (
                  <div className="space-y-2.5">
                    {cand.education.map((e, i) => (
                      <div key={i} className="flex gap-3">
                        <GraduationCap className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                        <div>
                          <div className="text-sm font-medium">{e.degree ? `${e.degree} · ` : ''}{e.school}</div>
                          <div className="text-xs text-muted-foreground font-mono">{e.start_date || '?'} – {e.end_date || '?'}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Resume preview */}
          <Card className="shadow-none" data-testid="candidate-resume-preview">
            <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-semibold flex items-center gap-2"><FileText className="h-4 w-4" /> Resume</CardTitle>
              <div className="flex items-center gap-2">
                {cand.resume_file_id && !isMobileViewport && (resumeType === 'pdf' || resumeType === 'docx') && (
                  <Button size="sm" variant="outline" onClick={() => setResumeExpandOpen(true)} data-testid="candidate-resume-expand-button">
                    <Maximize2 className="h-4 w-4 mr-1" /> Expand
                  </Button>
                )}
                {cand.resume_file_id && (
                  <Button size="sm" variant="outline" onClick={downloadResume} data-testid="candidate-resume-download">
                    <Download className="h-4 w-4 mr-1" /> Download
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {!cand.resume_file_id && <p className="text-sm text-muted-foreground py-4 text-center">No resume on file for this candidate.</p>}
              {resumeType === 'loading' && <p className="text-sm text-muted-foreground py-4 text-center">Loading preview...</p>}
              {resumeType === 'error' && <p className="text-sm text-destructive py-4 text-center">Could not load resume preview. Try downloading instead.</p>}

              {/* Mobile: iframe/docx-preview does NOT work reliably on iOS Safari
                  and most Android browsers — show a big tap-friendly card
                  instead that hands the file off to the native viewer. */}
              {isMobileViewport && cand.resume_file_id && resumeUrl && (resumeType === 'pdf' || resumeType === 'docx' || resumeType === 'unsupported') && (
                <div
                  className="w-full rounded-lg border border-border bg-secondary/30 p-6 flex flex-col items-center justify-center gap-3 text-center"
                  data-testid="candidate-resume-mobile-open"
                >
                  <FileText className="h-10 w-10 text-muted-foreground" />
                  <div className="space-y-1">
                    <p className="text-sm font-medium">{resumeFilename || 'Resume'}</p>
                    <p className="text-xs text-muted-foreground">Mobile browsers can’t preview {resumeType === 'docx' ? 'Word documents' : 'PDFs'} inline. Tap below to open with your device viewer.</p>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 w-full max-w-xs pt-1">
                    <Button
                      className="w-full"
                      onClick={() => window.open(resumeUrl, '_blank', 'noopener,noreferrer')}
                      data-testid="candidate-resume-open-button"
                    >
                      <ExternalLink className="h-4 w-4 mr-1.5" /> Open Resume
                    </Button>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={downloadResume}
                      data-testid="candidate-resume-mobile-download-button"
                    >
                      <Download className="h-4 w-4 mr-1.5" /> Download
                    </Button>
                  </div>
                </div>
              )}

              {/* Desktop: keep the existing inline previews */}
              {!isMobileViewport && resumeType === 'pdf' && resumeUrl && (
                <iframe title="Resume preview" src={resumeUrl} className="w-full h-[720px] rounded-lg border border-border bg-white" />
              )}
              {!isMobileViewport && (resumeType === 'docx' || resumeType === 'docx-error') && (
                <div
                  ref={docxContainerRef}
                  data-testid="candidate-resume-docx-preview"
                  className="docx-preview-wrapper w-full h-[720px] overflow-auto rounded-lg border border-border bg-white p-4 text-black"
                >
                  {resumeType === 'docx-error' && (
                    <p className="text-sm text-destructive py-4 text-center">Could not render this Word document. Try downloading instead.</p>
                  )}
                </div>
              )}
              {!isMobileViewport && resumeType === 'unsupported' && (
                <p className="text-sm text-muted-foreground py-4 text-center">Preview is not available for this file type — use Download instead.</p>
              )}
            </CardContent>
          </Card>

          {/* Scorecards */}
          {scorecards.length > 0 && (
            <Card className="shadow-none" data-testid="candidate-scorecards">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Interview Feedback</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {scorecards.map((sc) => (
                  <div key={sc.id} className="border border-border rounded-lg p-3">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="text-sm font-medium">{sc.interviewer_name}</div>
                      <div className="flex items-center gap-2">
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${RECO_COLOR[sc.recommendation] || 'bg-secondary'}`}>{RECO_LABEL[sc.recommendation] || sc.recommendation}</span>
                        <span className="flex items-center gap-0.5 text-sm font-medium"><Star className="h-3.5 w-3.5 text-amber-500 fill-amber-500" />{sc.overall}/5</span>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                      {Object.entries(sc.ratings || {}).map(([k, v]) => (
                        <span key={k} className="text-xs text-muted-foreground">{k}: <span className="font-medium text-foreground">{v}/5</span></span>
                      ))}
                    </div>
                    {sc.notes && <p className="text-sm mt-2">{sc.notes}</p>}
                    <p className="text-xs text-muted-foreground font-mono mt-1.5">{new Date(sc.submitted_at).toLocaleString()}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: pipeline status + upcoming interviews + notes + timeline */}
        <div className="space-y-5">
          {stages.filter((s) => s !== 'Rejected').length > 1 && cand.status !== 'rejected' && (
            <Card className="shadow-none" data-testid="candidate-pipeline-status">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Pipeline Status</CardTitle>
                <p className="text-xs text-muted-foreground truncate">{cand.job?.title || 'No job assigned'}</p>
              </CardHeader>
              <CardContent>
                <PipelineStepper stages={stages} currentStage={cand.stage} />
              </CardContent>
            </Card>
          )}

          <Card className="shadow-none" data-testid="candidate-upcoming-interviews">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Upcoming Interviews</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {upcomingInterviews.length === 0 && <p className="text-sm text-muted-foreground py-2 text-center">No upcoming interviews scheduled.</p>}
              {upcomingInterviews.map((iv) => (
                <div key={iv.id} className="flex items-center gap-3 px-2 py-2 rounded-lg" data-testid={`candidate-upcoming-interview-${iv.id}`}>
                  <span className="h-8 w-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center shrink-0">
                    <CalendarDays className="h-4 w-4" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate capitalize">{(iv.type || 'Interview').replace('_', ' ')}</p>
                    <p className="text-xs text-muted-foreground truncate">{(iv.interviewer_names || []).join(', ') || 'No interviewer assigned'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground font-mono shrink-0 text-right">
                    {new Date(iv.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="shadow-none" data-testid="candidate-notes">
            <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Add Note / Log Email</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Select value={noteType} onValueChange={setNoteType}>
                <SelectTrigger className="h-9" data-testid="note-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="note">Note</SelectItem>
                  <SelectItem value="email_log">Email log</SelectItem>
                </SelectContent>
              </Select>
              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={noteType === 'email_log' ? 'Summarize the email sent/received...' : 'Write a note about this candidate...'}
                data-testid="note-textarea"
                rows={3}
              />
              <Button size="sm" onClick={addNote} disabled={!note.trim()} data-testid="note-submit-button">
                {noteType === 'email_log' ? 'Log Email' : 'Add Note'}
              </Button>
            </CardContent>
          </Card>

          <Card className="shadow-none" data-testid="candidate-activity-timeline">
            <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Activity Timeline</CardTitle></CardHeader>
            <CardContent>
              {timeline.length === 0 && <p className="text-sm text-muted-foreground py-3 text-center">No activity yet.</p>}
              <div className="space-y-0">
                {timeline.map((ev, i) => (
                  <div key={ev.id || i} className="relative pl-5 pb-4 border-l border-border last:pb-0 ml-1.5">
                    <span className={`absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full ${ev.kind === 'note' ? (ev.note_type === 'email_log' ? 'bg-sky-500' : 'bg-amber-500') : 'bg-primary'}`} />
                    <div className="text-sm">
                      {ev.kind === 'note' ? (
                        <>
                          <span className="font-medium">{ev.author_name}</span>{' '}
                          <span className="text-muted-foreground">{ev.note_type === 'email_log' ? 'logged an email' : 'noted'}:</span>
                          <p className="mt-0.5">{ev.text}</p>
                        </>
                      ) : (
                        <><span className="font-medium">{ev.actor_name}</span> {ev.message}</>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono mt-0.5">{new Date(ev.created_at).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Change Log (Admin+ only) */}
      {isAdminOrHigher(user) && cand && (
        <Card className="shadow-none" data-testid="candidate-change-log-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Clock className="h-4 w-4" /> Change Log
              <span className="text-xs font-normal text-muted-foreground">Every edit is tracked</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[420px] overflow-y-auto thin-scroll pr-1">
              <ChangeLog entityType="candidate" entityId={cand.id} />
            </div>
          </CardContent>
        </Card>
      )}
        </TabsContent>
        <TabsContent value="feedback" className="mt-4">
          <RoundFeedbackSection
            candidateId={cand.id}
            roundFeedback={cand.round_feedback || []}
            canEdit={isRecruiter}
            onChanged={load}
          />
        </TabsContent>
        <TabsContent value="offer" className="mt-4">
          <OfferPanel candidateId={cand.id} candidateName={cand.name} isRecruiter={isRecruiter} />
        </TabsContent>
      </Tabs>

      {/* Reject dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Reject {cand.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Rejection reason</Label>
              <Select value={rejectCategory} onValueChange={setRejectCategory}>
                <SelectTrigger data-testid="reject-reason-select"><SelectValue placeholder="Choose a reason" /></SelectTrigger>
                <SelectContent>{REJECTION_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {rejectCategory === 'Not Fit' && (
              <div className="space-y-1.5">
                <Label>Details</Label>
                <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="e.g. Not a technical fit for the role" data-testid="reject-reason-textarea" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>Cancel</Button>
            <Button
              variant="destructive"
              data-testid="reject-confirm-button"
              onClick={() => {
                if (!rejectCategory) {
                  toast.error('Please choose a rejection reason');
                  return;
                }
                if (rejectCategory === 'Not Fit' && !rejectReason.trim()) {
                  toast.error('Please provide details for Not Fit');
                  return;
                }
                const finalReason = rejectCategory === 'Not Fit' ? `Not Fit: ${rejectReason.trim()}` : rejectCategory;
                moveStage(pendingStage, finalReason);
                setRejectOpen(false);
                setRejectReason('');
                setRejectCategory('');
              }}
            >
              Reject Candidate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Expanded resume preview modal */}
      <Dialog open={resumeExpandOpen} onOpenChange={setResumeExpandOpen}>
        <DialogContent className="sm:max-w-5xl w-[95vw] h-[92vh] flex flex-col" data-testid="candidate-resume-expand-modal">
          <DialogHeader className="flex-row items-center justify-between space-y-0 pr-8">
            <DialogTitle className="flex items-center gap-2"><FileText className="h-4 w-4" /> {cand.name} — Resume</DialogTitle>
            <Button size="sm" variant="outline" onClick={downloadResume} data-testid="candidate-resume-expand-download">
              <Download className="h-4 w-4 mr-1" /> Download
            </Button>
          </DialogHeader>
          <div className="flex-1 min-h-0">
            {resumeType === 'pdf' && resumeUrl && (
              <iframe title="Resume preview expanded" src={resumeUrl} className="w-full h-full rounded-lg border border-border bg-white" />
            )}
            {resumeType === 'docx' && (
              <div
                ref={expandedDocxContainerRef}
                data-testid="candidate-resume-docx-preview-expanded"
                className="docx-preview-wrapper w-full h-full overflow-auto rounded-lg border border-border bg-white p-6 text-black"
              />
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Send Email dialog */}
      <SendEmailDialog
        open={emailDialogOpen}
        onOpenChange={setEmailDialogOpen}
        candidateIds={cand ? [cand.id] : []}
        candidateNames={cand ? [cand.name] : []}
        onSent={() => load()}
      />

      {/* Schedule Interview dialog */}
      {cand && (
        <ScheduleRequestDialog
          open={scheduleDialogOpen}
          onOpenChange={setScheduleDialogOpen}
          candidate={cand}
          onCreated={() => load()}
        />
      )}
    </div>
  );
}
