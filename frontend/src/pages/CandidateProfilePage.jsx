import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Briefcase,
  Building2,
  CalendarDays,
  Clock,
  Download,
  FileText,
  GraduationCap,
  Mail,
  MapPin,
  Maximize2,
  Phone,
  Star,
  Tag,
  Target,
  Trash2,
} from 'lucide-react';
import { renderAsync } from 'docx-preview';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { StageBadge, REJECTION_REASONS } from '@/pages/CandidatesPage';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

const RECO_LABEL = { strong_yes: 'Strong Yes', yes: 'Yes', no: 'No', strong_no: 'Strong No' };
const RECO_COLOR = { strong_yes: 'bg-green-100 text-green-800', yes: 'bg-emerald-100 text-emerald-800', no: 'bg-orange-100 text-orange-800', strong_no: 'bg-red-100 text-red-800' };

function fitScoreStyle(score) {
  if (score >= 75) return 'border-green-500 text-green-700 bg-green-50';
  if (score >= 50) return 'border-amber-500 text-amber-700 bg-amber-50';
  return 'border-red-500 text-red-700 bg-red-50';
}

export default function CandidateProfilePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [cand, setCand] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [scorecards, setScorecards] = useState([]);
  const [stages, setStages] = useState([]);
  const [note, setNote] = useState('');
  const [noteType, setNoteType] = useState('note');
  const [resumeUrl, setResumeUrl] = useState(null);
  const [resumeType, setResumeType] = useState(null); // null | 'loading' | 'pdf' | 'docx' | 'unsupported' | 'error'
  const [resumeBlob, setResumeBlob] = useState(null);
  const docxContainerRef = useRef(null);
  const expandedDocxContainerRef = useRef(null);
  const [resumeExpandOpen, setResumeExpandOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectCategory, setRejectCategory] = useState('');
  const [pendingStage, setPendingStage] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [jobs, setJobs] = useState([]);

  const isRecruiter = user?.role === 'admin' || user?.role === 'recruiter';

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
    if (isRecruiter) api.get('/jobs').then((r) => setJobs(r.data || [])).catch(() => {});
  }, [isRecruiter]);

  useEffect(() => {
    let url;
    let cancelled = false;
    setResumeUrl(null);
    setResumeBlob(null);
    setResumeType(cand?.resume_file_id ? 'loading' : null);
    if (cand?.resume_file_id) {
      api
        .get(`/files/${cand.resume_file_id}`, { responseType: 'blob' })
        .then((r) => {
          if (cancelled) return;
          const contentType = (r.headers['content-type'] || '').toLowerCase();
          const dispo = r.headers['content-disposition'] || '';
          const nameMatch = dispo.match(/filename="?([^"]+)"?/i);
          const ext = (nameMatch?.[1] || '').toLowerCase().split('.').pop();
          const blob = new Blob([r.data], { type: r.headers['content-type'] });
          if (contentType.includes('pdf') || ext === 'pdf') {
            url = URL.createObjectURL(blob);
            setResumeUrl(url);
            setResumeType('pdf');
          } else if (contentType.includes('word') || contentType.includes('officedocument') || ext === 'docx' || ext === 'doc') {
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

  if (notFound)
    return (
      <div className="text-center py-20">
        <p className="text-lg font-medium">Candidate not available</p>
        <p className="text-sm text-muted-foreground mt-1">This candidate doesn't exist or you don't have access.</p>
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
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-display text-2xl font-semibold tracking-tight" data-testid="candidate-name">{cand.name}</h1>
              <StageBadge stage={cand.stage} />
              {cand.low_confidence_fields?.length > 0 && (
                <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50">Needs review: {cand.low_confidence_fields.join(', ')}</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {cand.current_title || 'No title'}{cand.current_company ? ` at ${cand.current_company}` : ''} · applied {cand.applied_at ? new Date(cand.applied_at).toLocaleDateString() : '—'} · source: {(cand.source || '').replace('_', ' ')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRecruiter && (
            <Select value={cand.stage} onValueChange={onStageChange}>
              <SelectTrigger className="w-[160px]" data-testid="candidate-stage-select"><SelectValue /></SelectTrigger>
              <SelectContent>{stages.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          )}
          {user?.role === 'admin' && (
            <Button variant="outline" size="icon" onClick={deleteCandidate} aria-label="Delete candidate" data-testid="candidate-delete-button">
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
        </div>
      </div>

      {cand.status === 'rejected' && cand.rejection_reason && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded-xl px-4 py-3">Rejected: {cand.rejection_reason}</div>
      )}

      <div className="grid lg:grid-cols-3 gap-5">
        {/* Left: details + resume */}
        <div className="lg:col-span-2 space-y-5">
          <Card className="shadow-none">
            <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Contact & Details</CardTitle></CardHeader>
            <CardContent className="grid sm:grid-cols-2 gap-3 text-sm">
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
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Tag className="h-4 w-4 text-muted-foreground" />
                {(cand.tags || []).length === 0 && <span className="text-muted-foreground">No tags</span>}
                {(cand.tags || []).map((t) => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
              </div>
              {(cand.skills || []).length > 0 && (
                <div className="sm:col-span-2">
                  <Separator className="my-2" />
                  <div className="flex flex-wrap gap-1.5">
                    {cand.skills.map((s) => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                  </div>
                </div>
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
                {cand.resume_file_id && (resumeType === 'pdf' || resumeType === 'docx') && (
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
              {resumeType === 'pdf' && resumeUrl && (
                <iframe title="Resume preview" src={resumeUrl} className="w-full h-[720px] rounded-lg border border-border bg-white" />
              )}
              {(resumeType === 'docx' || resumeType === 'docx-error') && (
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
              {resumeType === 'unsupported' && (
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

        {/* Right: notes + timeline */}
        <div className="space-y-5">
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
    </div>
  );
}
