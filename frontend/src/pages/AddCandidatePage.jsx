import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CheckCircle2, FileUp, FolderUp, Loader2, Plus, Save, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

const SOURCES = [
  { value: 'referral', label: 'Referral' },
  { value: 'job_board', label: 'Job Board' },
  { value: 'career_site', label: 'Career Site' },
  { value: 'linkedin', label: 'LinkedIn' },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const emptyDraft = () => ({
  name: '', email: '', phone: '', current_title: '', current_company: '', location: '',
  experience: [], education: [], skills: [], job_id: '', source: 'career_site', tags: [],
  resume_file_id: null, low_confidence_fields: [], notice_period: '', notes: '',
});

function parsedToDraft(result) {
  const p = result.parsed || {};
  return {
    ...emptyDraft(),
    name: p.name || '',
    email: p.email || '',
    phone: p.phone || '',
    current_title: p.current_title || '',
    current_company: p.current_company || '',
    location: p.location || '',
    experience: p.experience || [],
    education: p.education || [],
    skills: p.skills || [],
    notice_period: p.notice_period || '',
    resume_file_id: result.file_id,
    low_confidence_fields: result.low_confidence_fields || [],
    _filename: result.filename,
    _match: result.match || null,
    _mergeChoice: result.match ? (result.match.match_type === 'email' ? 'merge' : 'create') : 'create',
  };
}

function LowConfBadge() {
  return (
    <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50 text-[10px] gap-1">
      <AlertTriangle className="h-3 w-3" /> Review
    </Badge>
  );
}

function DraftForm({ draft, onChange, jobs, tags, onSave, onDiscard, saving, index }) {
  const low = draft.low_confidence_fields || [];
  const field = (key, label, placeholder, type = 'text') => (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Label className="text-xs">{label}</Label>
        {low.includes(key) && <LowConfBadge />}
      </div>
      <Input
        type={type}
        value={draft[key] || ''}
        onChange={(e) => onChange({ ...draft, [key]: e.target.value })}
        placeholder={placeholder}
        data-testid={`parsed-review-field-${key.replace('_', '-')}-${index}`}
        className={low.includes(key) ? 'ring-2 ring-amber-300' : ''}
      />
    </div>
  );

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-primary" />
          {draft._filename ? `Parsed from ${draft._filename}` : 'Candidate details'}
        </CardTitle>
        <div className="flex items-center gap-2">
          {low.length > 0 && (
            <span className="text-xs text-amber-700">{low.length} field{low.length === 1 ? '' : 's'} need review</span>
          )}
          {onDiscard && (
            <Button variant="ghost" size="icon" onClick={onDiscard} aria-label="Discard" data-testid={`draft-discard-${index}`}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {draft._match && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 space-y-2" data-testid={`draft-match-banner-${index}`}>
            <p className="text-sm text-amber-900">
              <strong>Matched existing candidate:</strong> {draft._match.candidate_name}
              {' '}
              <span className="text-xs text-amber-700">
                ({draft._match.match_type === 'email' ? 'same email address' : 'same name — please confirm this is the same person'})
              </span>
            </p>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 text-xs font-medium text-amber-900 cursor-pointer">
                <input
                  type="radio"
                  name={`merge-choice-${index}`}
                  checked={draft._mergeChoice === 'merge'}
                  onChange={() => onChange({ ...draft, _mergeChoice: 'merge' })}
                  data-testid={`draft-merge-radio-${index}`}
                />
                Merge into existing profile
              </label>
              <label className="flex items-center gap-1.5 text-xs font-medium text-amber-900 cursor-pointer">
                <input
                  type="radio"
                  name={`merge-choice-${index}`}
                  checked={draft._mergeChoice === 'create'}
                  onChange={() => onChange({ ...draft, _mergeChoice: 'create' })}
                  data-testid={`draft-create-radio-${index}`}
                />
                Create as a new candidate anyway
              </label>
            </div>
          </div>
        )}
        <div className="grid sm:grid-cols-2 gap-3">
          {field('name', 'Full Name *', 'Jane Doe')}
          {field('email', 'Email', 'jane@example.com', 'email')}
          {field('phone', 'Phone', '(555) 123-4567')}
          {field('location', 'Location', 'San Francisco, CA')}
          {field('current_title', 'Current Title', 'Software Engineer')}
          {field('current_company', 'Current Company', 'Acme Inc.')}
          {field('notice_period', 'Notice Period', 'e.g. 30 days, Immediate')}
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          {(!draft._match || draft._mergeChoice !== 'merge') && (
            <div className="space-y-1">
              <Label className="text-xs">Job *</Label>
              <Select value={draft.job_id} onValueChange={(v) => onChange({ ...draft, job_id: v })}>
                <SelectTrigger data-testid={`parsed-review-job-select-${index}`}><SelectValue placeholder="Assign to job" /></SelectTrigger>
                <SelectContent>
                  {jobs.filter((j) => j.status === 'open').map((j) => (
                    <SelectItem key={j.id} value={j.id}>{j.title} · {j.department}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {(!draft._match || draft._mergeChoice !== 'merge') && (
            <div className="space-y-1">
              <Label className="text-xs">Source</Label>
              <Select value={draft.source} onValueChange={(v) => onChange({ ...draft, source: v })}>
                <SelectTrigger data-testid={`parsed-review-source-select-${index}`}><SelectValue /></SelectTrigger>
                <SelectContent>{SOURCES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          {draft._match && draft._mergeChoice === 'merge' && (
            <p className="text-xs text-muted-foreground sm:col-span-2">
              The existing job, pipeline stage, source and tags for this candidate will stay unchanged — only contact info, skills, experience and education will be updated from the resume.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Skills (comma-separated)</Label>
          <Input
            value={(draft.skills || []).join(', ')}
            onChange={(e) => onChange({ ...draft, skills: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
            placeholder="Python, React, SQL"
            data-testid={`parsed-review-skills-${index}`}
          />
        </div>

        {/* Experience */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Work Experience</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onChange({ ...draft, experience: [...(draft.experience || []), { company: '', title: '', start_date: '', end_date: '', description: '' }] })}
            >
              <Plus className="h-3 w-3 mr-1" /> Add
            </Button>
          </div>
          {(draft.experience || []).map((e, i) => (
            <div key={i} className="grid grid-cols-2 sm:grid-cols-5 gap-2 items-center border border-border rounded-lg p-2">
              <Input className="h-8 text-xs" value={e.title || ''} placeholder="Title" onChange={(ev) => { const x = [...draft.experience]; x[i] = { ...x[i], title: ev.target.value }; onChange({ ...draft, experience: x }); }} />
              <Input className="h-8 text-xs" value={e.company || ''} placeholder="Company" onChange={(ev) => { const x = [...draft.experience]; x[i] = { ...x[i], company: ev.target.value }; onChange({ ...draft, experience: x }); }} />
              <Input className="h-8 text-xs" value={e.start_date || ''} placeholder="Start" onChange={(ev) => { const x = [...draft.experience]; x[i] = { ...x[i], start_date: ev.target.value }; onChange({ ...draft, experience: x }); }} />
              <Input className="h-8 text-xs" value={e.end_date || ''} placeholder="End" onChange={(ev) => { const x = [...draft.experience]; x[i] = { ...x[i], end_date: ev.target.value }; onChange({ ...draft, experience: x }); }} />
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8 justify-self-end" onClick={() => onChange({ ...draft, experience: draft.experience.filter((_, j) => j !== i) })} aria-label="Remove experience">
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>

        {/* Education */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Education</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onChange({ ...draft, education: [...(draft.education || []), { school: '', degree: '', start_date: '', end_date: '' }] })}
            >
              <Plus className="h-3 w-3 mr-1" /> Add
            </Button>
          </div>
          {(draft.education || []).map((e, i) => (
            <div key={i} className="grid grid-cols-2 sm:grid-cols-5 gap-2 items-center border border-border rounded-lg p-2">
              <Input className="h-8 text-xs" value={e.school || ''} placeholder="School" onChange={(ev) => { const x = [...draft.education]; x[i] = { ...x[i], school: ev.target.value }; onChange({ ...draft, education: x }); }} />
              <Input className="h-8 text-xs" value={e.degree || ''} placeholder="Degree" onChange={(ev) => { const x = [...draft.education]; x[i] = { ...x[i], degree: ev.target.value }; onChange({ ...draft, education: x }); }} />
              <Input className="h-8 text-xs" value={e.start_date || ''} placeholder="Start" onChange={(ev) => { const x = [...draft.education]; x[i] = { ...x[i], start_date: ev.target.value }; onChange({ ...draft, education: x }); }} />
              <Input className="h-8 text-xs" value={e.end_date || ''} placeholder="End" onChange={(ev) => { const x = [...draft.education]; x[i] = { ...x[i], end_date: ev.target.value }; onChange({ ...draft, education: x }); }} />
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8 justify-self-end" onClick={() => onChange({ ...draft, education: draft.education.filter((_, j) => j !== i) })} aria-label="Remove education">
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Initial note (optional)</Label>
          <Textarea rows={2} value={draft.notes || ''} onChange={(e) => onChange({ ...draft, notes: e.target.value })} placeholder="Any context about this candidate..." />
        </div>

        <Button onClick={onSave} disabled={saving} className="w-full sm:w-auto" data-testid={`parsed-review-save-button-${index}`}>
          {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
          {draft._match && draft._mergeChoice === 'merge' ? 'Merge into Existing Candidate' : 'Save Candidate'}
        </Button>
      </CardContent>
    </Card>
  );
}

export default function AddCandidatePage() {
  const navigate = useNavigate();
  const fileRef = useRef();
  const bulkRef = useRef();
  const folderRef = useRef();
  const [jobs, setJobs] = useState([]);
  const [tags, setTags] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [bulkProgress, setBulkProgress] = useState(null); // { current, total, phase }
  const [drafts, setDrafts] = useState([]);
  const [manualMode, setManualMode] = useState(false);
  const [savingIdx, setSavingIdx] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [bulkJobId, setBulkJobId] = useState('');
  const [savingAll, setSavingAll] = useState(false);

  useEffect(() => {
    Promise.all([api.get('/jobs'), api.get('/tags')]).then(([j, t]) => {
      setJobs(j.data);
      setTags(t.data);
    }).catch(() => {});
  }, []);

  const parseSingle = async (file) => {
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/resumes/parse', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setDrafts((d) => [...d, parsedToDraft(r.data)]);
      toast.success(`Parsed ${file.name}${r.data.low_confidence_fields.length ? ` — ${r.data.low_confidence_fields.length} fields flagged for review` : ''}`);
    } catch (e) {
      toast.error(errMsg(e, 'Parsing failed'));
    } finally {
      setParsing(false);
    }
  };

  // Chunked bulk parse: processes files in batches of 10 (backend limit is 25 per request)
  // so we can support dragging entire folders of resumes.
  const parseBulk = async (files) => {
    setParsing(true);
    const CHUNK = 10;
    const chunks = [];
    for (let i = 0; i < files.length; i += CHUNK) chunks.push(files.slice(i, i + CHUNK));
    let done = 0;
    let okCount = 0;
    const errors = [];
    setBulkProgress({ current: 0, total: files.length, phase: 'Parsing' });
    try {
      for (const batch of chunks) {
        const fd = new FormData();
        batch.forEach((f) => fd.append('files', f));
        try {
          const r = await api.post('/resumes/parse-bulk', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
          const ok = r.data.results.filter((x) => x.status === 'success');
          const bad = r.data.results.filter((x) => x.status === 'error');
          setDrafts((d) => [...d, ...ok.map(parsedToDraft)]);
          okCount += ok.length;
          bad.forEach((b) => errors.push(`${b.filename}: ${b.error}`));
        } catch (e) {
          batch.forEach((f) => errors.push(`${f.name}: ${errMsg(e, 'batch failed')}`));
        }
        done += batch.length;
        setBulkProgress({ current: done, total: files.length, phase: 'Parsing' });
      }
      if (okCount) toast.success(`Parsed ${okCount} resume${okCount === 1 ? '' : 's'} successfully`);
      if (errors.length) {
        // group errors into one toast to avoid spam when folder has many bad files
        const shown = errors.slice(0, 3).join('\n');
        toast.error(`${errors.length} file${errors.length === 1 ? '' : 's'} failed:\n${shown}${errors.length > 3 ? `\n…and ${errors.length - 3} more` : ''}`);
      }
    } finally {
      setParsing(false);
      setBulkProgress(null);
    }
  };

  // Recursively walk a FileSystemEntry (folder or file) yielding File objects
  const readEntry = (entry) => new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => resolve([file]), () => resolve([]));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const readBatch = () => {
        reader.readEntries(async (results) => {
          if (!results.length) {
            const nested = await Promise.all(all.map(readEntry));
            resolve(nested.flat());
          } else {
            all.push(...results);
            readBatch();
          }
        }, () => resolve([]));
      };
      readBatch();
    } else {
      resolve([]);
    }
  });

  const extractFilesFromDrop = async (dataTransfer) => {
    const items = dataTransfer.items;
    if (items && items.length && items[0].webkitGetAsEntry) {
      const entries = [];
      for (let i = 0; i < items.length; i++) {
        const e = items[i].webkitGetAsEntry?.();
        if (e) entries.push(e);
      }
      if (entries.length) {
        const collected = await Promise.all(entries.map(readEntry));
        return collected.flat();
      }
    }
    return Array.from(dataTransfer.files || []);
  };

  const onFiles = (fileList, bulk) => {
    const files = Array.from(fileList).filter((f) => /\.(pdf|docx)$/i.test(f.name));
    if (files.length === 0) {
      toast.error('No PDF or DOCX files found in the selection');
      return;
    }
    if (files.length === 1 && !bulk) parseSingle(files[0]);
    else parseBulk(files.slice(0, 100));
    if (files.length > 100) toast.warning(`Only processing the first 100 resumes (found ${files.length}). Add the rest in another batch.`);
  };

  const onDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    const files = await extractFilesFromDrop(e.dataTransfer);
    onFiles(files, true);
  };

  const saveDraft = async (idx) => {
    const d = drafts[idx];
    if (!d.name.trim()) {
      toast.error('Name is required');
      return;
    }
    if (d.email && !EMAIL_RE.test(d.email)) {
      toast.error('Please enter a valid email address');
      return;
    }
    const isMerge = d._match && d._mergeChoice === 'merge';
    if (!isMerge && !d.job_id) {
      toast.error('Please assign the candidate to a job');
      return;
    }
    setSavingIdx(idx);
    try {
      if (isMerge) {
        const parsed = {
          name: d.name, email: d.email, phone: d.phone, current_title: d.current_title,
          current_company: d.current_company, location: d.location, notice_period: d.notice_period,
          skills: d.skills, experience: d.experience, education: d.education,
        };
        const r = await api.post(`/candidates/${d._match.candidate_id}/merge-resume`, { file_id: d.resume_file_id, parsed });
        toast.success(`Resume merged into ${r.data.name}'s profile`);
        setDrafts((ds) => ds.filter((_, i) => i !== idx));
        if (drafts.length === 1) navigate(`/candidates/${r.data.id}`);
      } else {
        const body = { ...d };
        delete body._filename;
        delete body._match;
        delete body._mergeChoice;
        ['email', 'phone', 'current_title', 'current_company', 'location', 'notice_period', 'notes'].forEach((k) => {
          if (!body[k]) body[k] = null;
        });
        const r = await api.post('/candidates', body);
        toast.success(`${d.name} added to pipeline`);
        setDrafts((ds) => ds.filter((_, i) => i !== idx));
        if (drafts.length === 1) navigate(`/candidates/${r.data.id}`);
      }
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSavingIdx(null);
    }
  };

  // Save every draft that doesn't need a merge decision, using bulkJobId when a draft
  // doesn't already have a job. Skips drafts flagged with a "same-person" match banner
  // so the recruiter can review those manually.
  const saveAllDrafts = async () => {
    const eligible = drafts.map((d, i) => ({ d, i })).filter(({ d }) => {
      if (d._match) return false; // needs manual review
      if (!d.name?.trim()) return false;
      if (d.email && !EMAIL_RE.test(d.email)) return false;
      return true;
    });
    if (!eligible.length) {
      toast.error('No draft is ready to save. Fix names/emails or resolve match banners first.');
      return;
    }
    const needsJob = eligible.some(({ d }) => !d.job_id);
    if (needsJob && !bulkJobId) {
      toast.error('Choose a job to assign to drafts that don\'t already have one');
      return;
    }
    setSavingAll(true);
    setBulkProgress({ current: 0, total: eligible.length, phase: 'Saving to pipeline' });
    let saved = 0;
    const failedIdx = [];
    for (const { d, i } of eligible) {
      const body = { ...d };
      delete body._filename;
      delete body._match;
      delete body._mergeChoice;
      if (!body.job_id) body.job_id = bulkJobId;
      ['email', 'phone', 'current_title', 'current_company', 'location', 'notice_period', 'notes'].forEach((k) => {
        if (!body[k]) body[k] = null;
      });
      try {
        await api.post('/candidates', body);
        saved += 1;
      } catch (e) {
        failedIdx.push(i);
      }
      setBulkProgress({ current: saved + failedIdx.length, total: eligible.length, phase: 'Saving to pipeline' });
    }
    // Remove saved drafts, keep failures + match-banner drafts for review
    const keepSet = new Set([...failedIdx, ...drafts.map((d, i) => (d._match ? i : null)).filter((i) => i !== null)]);
    setDrafts((ds) => ds.filter((_, i) => keepSet.has(i)));
    setSavingAll(false);
    setBulkProgress(null);
    if (saved) toast.success(`Saved ${saved} candidate${saved === 1 ? '' : 's'} to the pipeline`);
    if (failedIdx.length) toast.error(`${failedIdx.length} draft${failedIdx.length === 1 ? '' : 's'} failed — review remaining items below`);
    if (!failedIdx.length && !drafts.some((d) => d._match)) {
      // clean exit — go to Candidates list
      navigate('/candidates');
    }
  };

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/candidates')} aria-label="Back">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Add Candidates</h1>
          <p className="text-sm text-muted-foreground">Upload resumes to auto-fill profiles with AI, or add manually.</p>
        </div>
      </div>

      {/* Upload zone */}
      <div
        data-testid="resume-upload-dropzone"
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-2xl p-8 text-center transition-colors bg-card ${dragOver ? 'border-primary bg-accent' : 'border-border'}`}
      >
        {parsing || bulkProgress ? (
          <div className="flex flex-col items-center gap-3 py-4">
            <Loader2 className="h-8 w-8 text-primary animate-spin" />
            <p className="text-sm font-medium" data-testid="bulk-progress-label">
              {bulkProgress
                ? `${bulkProgress.phase} ${bulkProgress.current} of ${bulkProgress.total} resume${bulkProgress.total === 1 ? '' : 's'}...`
                : 'Parsing resume with AI...'}
            </p>
            {bulkProgress ? (
              <div className="w-full max-w-md">
                <Progress
                  value={bulkProgress.total ? Math.round((bulkProgress.current / bulkProgress.total) * 100) : 0}
                  data-testid="bulk-progress-bar"
                />
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Extracting name, contact, experience, education & skills</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-2">
            <span className="h-12 w-12 rounded-xl bg-accent flex items-center justify-center">
              <FileUp className="h-6 w-6 text-accent-foreground" />
            </span>
            <div>
              <p className="text-sm font-medium">Drag & drop resumes or an entire folder here (PDF / DOCX)</p>
              <p className="text-xs text-muted-foreground mt-0.5">AI parses each resume in the background — up to 100 files per batch, chunked automatically</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center">
              <Button variant="outline" onClick={() => fileRef.current?.click()} data-testid="resume-upload-browse-button">
                <Upload className="h-4 w-4 mr-1" /> Upload Resume
              </Button>
              <Button variant="outline" onClick={() => bulkRef.current?.click()} data-testid="resume-upload-bulk-button">
                <Upload className="h-4 w-4 mr-1" /> Bulk Upload Files
              </Button>
              <Button variant="outline" onClick={() => folderRef.current?.click()} data-testid="resume-upload-folder-button">
                <FolderUp className="h-4 w-4 mr-1" /> Upload Folder
              </Button>
              <Button variant="ghost" onClick={() => { setManualMode(true); setDrafts((d) => [...d, emptyDraft()]); }} data-testid="add-manual-button">
                <Plus className="h-4 w-4 mr-1" /> Add Manually
              </Button>
            </div>
          </div>
        )}
        <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => { onFiles(e.target.files, false); e.target.value = ''; }} />
        <input ref={bulkRef} type="file" accept=".pdf,.docx" multiple className="hidden" onChange={(e) => { onFiles(e.target.files, true); e.target.value = ''; }} />
        <input
          ref={folderRef}
          type="file"
          className="hidden"
          multiple
          webkitdirectory=""
          data-testid="resume-upload-folder-input"
          onChange={(e) => { onFiles(e.target.files, true); e.target.value = ''; }}
        />
      </div>

      {/* Review drafts */}
      {drafts.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold">Review & Save ({drafts.length})</h2>
            {drafts.length > 1 && (
              <div className="flex flex-wrap items-center gap-2 bg-card border border-border rounded-xl px-3 py-2" data-testid="bulk-save-bar">
                <span className="text-xs text-muted-foreground">Assign remaining drafts to</span>
                <Select value={bulkJobId} onValueChange={setBulkJobId}>
                  <SelectTrigger className="h-8 w-[220px]" data-testid="bulk-save-job-select"><SelectValue placeholder="Choose a job" /></SelectTrigger>
                  <SelectContent>
                    {jobs.filter((j) => j.status === 'open').map((j) => (
                      <SelectItem key={j.id} value={j.id}>{j.title} · {j.department}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button size="sm" onClick={saveAllDrafts} disabled={savingAll} data-testid="bulk-save-all-button">
                  {savingAll ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
                  Save All ({drafts.filter((d) => !d._match).length})
                </Button>
              </div>
            )}
          </div>
          {drafts.map((d, i) => (
            <DraftForm
              key={i}
              index={i}
              draft={d}
              jobs={jobs}
              tags={tags}
              onChange={(nd) => setDrafts((ds) => ds.map((x, j) => (j === i ? nd : x)))}
              onSave={() => saveDraft(i)}
              onDiscard={() => setDrafts((ds) => ds.filter((_, j) => j !== i))}
              saving={savingIdx === i}
            />
          ))}
        </div>
      )}
    </div>
  );
}
