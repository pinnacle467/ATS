import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Download, FileSpreadsheet, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api, errMsg } from '@/lib/api';
import { useCachedJobs } from '@/lib/referenceCache';

const FIELD_LABELS = {
  skip: '— Skip —',
  name: 'Name',
  email: 'Email',
  phone: 'Phone',
  current_title: 'Current Title',
  current_company: 'Current Company',
  location: 'Location',
  skills: 'Skills',
  job: 'Job (matched by title)',
  stage: 'Stage',
  source: 'Source',
  tags: 'Tags',
  applied_at: 'Applied Date',
  notice_period: 'Notice Period',
  notes: 'Notes',
};

const STEPS = ['Upload', 'Map Columns', 'Results'];

export default function ImportCandidatesPage() {
  const navigate = useNavigate();
  const fileRef = useRef();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState(null); // {import_id, headers, suggested_mapping, sample_rows, total_rows, target_fields}
  const [mapping, setMapping] = useState({});
  const [jobs] = useCachedJobs();
  const [defaultJob, setDefaultJob] = useState('none');
  const [defaultSource, setDefaultSource] = useState('career_site');
  const [dupStrategy, setDupStrategy] = useState('skip');
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const r = await api.get('/imports/template', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'candidate_import_template.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errMsg(e, 'Could not download template'));
    }
  };

  const upload = async (file) => {
    if (!/\.(xlsx|csv)$/i.test(file.name)) {
      toast.error('Please upload a .xlsx or .csv file');
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/imports/preview', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setPreview(r.data);
      setMapping(r.data.suggested_mapping);
      setStep(1);
      toast.success(`Read ${r.data.total_rows} rows from ${r.data.filename}`);
    } catch (e) {
      toast.error(errMsg(e, 'Could not read file'));
    } finally {
      setBusy(false);
    }
  };

  const mappedFields = Object.values(mapping).filter((v) => v !== 'skip');
  const nameMissing = !mappedFields.includes('name');
  const jobMapped = mappedFields.includes('job');

  const commit = async () => {
    if (nameMissing) return toast.error('Map a column to Name before importing');
    if (!jobMapped && defaultJob === 'none') return toast.error('No Job column mapped — choose a default job to assign all candidates to');
    setBusy(true);
    try {
      const r = await api.post(`/imports/${preview.import_id}/commit`, {
        mapping,
        default_job_id: defaultJob !== 'none' ? defaultJob : null,
        default_source: defaultSource,
        duplicate_strategy: dupStrategy,
      });
      setResult(r.data);
      setStep(2);
      toast.success(`Imported ${r.data.created} candidates`);
    } catch (e) {
      toast.error(errMsg(e, 'Import failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/candidates')} aria-label="Back" data-testid="import-back-button">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Import Candidates from Excel</h1>
          <p className="text-sm text-muted-foreground">Migrate your existing candidate data (.xlsx or .csv) into the ATS.</p>
        </div>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2" data-testid="import-stepper">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <span className={`h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold ${i <= step ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>
              {i + 1}
            </span>
            <span className={`text-sm ${i === step ? 'font-medium' : 'text-muted-foreground'}`}>{s}</span>
            {i < STEPS.length - 1 && <span className="w-8 h-px bg-border mx-1" />}
          </div>
        ))}
      </div>

      {/* Step 1: Upload */}
      {step === 0 && (
        <div className="space-y-4">
          <div
            data-testid="import-upload-dropzone"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
            }}
            className={`border-2 border-dashed rounded-2xl p-10 text-center transition-colors bg-card ${dragOver ? 'border-primary bg-accent' : 'border-border'}`}
          >
            {busy ? (
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="h-8 w-8 text-primary animate-spin" />
                <p className="text-sm font-medium">Reading spreadsheet...</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <span className="h-12 w-12 rounded-xl bg-accent flex items-center justify-center">
                  <FileSpreadsheet className="h-6 w-6 text-accent-foreground" />
                </span>
                <div>
                  <p className="text-sm font-medium">Drag & drop your Excel or CSV file here</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Columns are auto-detected — you'll review the mapping before anything is imported (up to 5,000 rows)</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => fileRef.current?.click()} data-testid="import-browse-button">
                    <Upload className="h-4 w-4 mr-1" /> Choose File
                  </Button>
                  <Button variant="ghost" onClick={downloadTemplate} data-testid="import-template-button">
                    <Download className="h-4 w-4 mr-1" /> Download Template
                  </Button>
                </div>
              </div>
            )}
            <input ref={fileRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => { if (e.target.files[0]) upload(e.target.files[0]); e.target.value = ''; }} />
          </div>
          <Card className="shadow-none">
            <CardContent className="pt-5 text-sm text-muted-foreground space-y-1.5">
              <p className="font-medium text-foreground">How migration works</p>
              <p>1. Upload a spreadsheet with one candidate per row (name, email, phone, title, company, job, stage, skills, tags, applied date, notes...).</p>
              <p>2. We auto-match your columns to ATS fields — adjust anything before importing.</p>
              <p>3. Candidates are matched to jobs by title, placed in their pipeline stage, and duplicates (by email) are detected automatically.</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 2: Mapping */}
      {step === 1 && preview && (
        <div className="space-y-4">
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Column Mapping — {preview.filename} ({preview.total_rows} rows)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {nameMissing && (
                <div className="flex items-center gap-2 text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" /> Map one column to <strong>Name</strong> (required).
                </div>
              )}
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {preview.headers.map((h) => (
                  <div key={h} className="border border-border rounded-lg p-3 space-y-1.5 bg-card">
                    <div className="text-xs font-medium truncate" title={h}>{h}</div>
                    <Select value={mapping[h] || 'skip'} onValueChange={(v) => setMapping((m) => ({ ...m, [h]: v }))}>
                      <SelectTrigger className="h-8 text-xs" data-testid={`import-mapping-${h.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {['skip', ...preview.target_fields].map((f) => (
                          <SelectItem key={f} value={f} disabled={f !== 'skip' && f !== mapping[h] && Object.values(mapping).includes(f)}>
                            {FIELD_LABELS[f] || f}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Import Options</CardTitle></CardHeader>
            <CardContent className="grid sm:grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">{jobMapped ? 'Fallback job (when title not matched)' : 'Default job (no Job column mapped) *'}</Label>
                <Select value={defaultJob} onValueChange={setDefaultJob}>
                  <SelectTrigger className="h-9" data-testid="import-default-job-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Default source (when blank)</Label>
                <Select value={defaultSource} onValueChange={setDefaultSource}>
                  <SelectTrigger className="h-9" data-testid="import-default-source-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="career_site">Career Site</SelectItem>
                    <SelectItem value="job_board">Job Board</SelectItem>
                    <SelectItem value="referral">Referral</SelectItem>
                    <SelectItem value="linkedin">LinkedIn</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Duplicates (same email)</Label>
                <Select value={dupStrategy} onValueChange={setDupStrategy}>
                  <SelectTrigger className="h-9" data-testid="import-duplicate-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip">Skip duplicates</SelectItem>
                    <SelectItem value="create">Import anyway</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Preview table */}
          <Card className="shadow-none">
            <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Data Preview (first 5 rows)</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto thin-scroll">
              <Table>
                <TableHeader>
                  <TableRow className="bg-secondary/50 hover:bg-secondary/50">
                    {preview.headers.map((h) => (
                      <TableHead key={h} className="whitespace-nowrap">
                        <div className="text-xs">{h}</div>
                        {mapping[h] !== 'skip' && <Badge variant="secondary" className="text-[10px] mt-0.5">{FIELD_LABELS[mapping[h]]}</Badge>}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.sample_rows.map((row, i) => (
                    <TableRow key={i}>
                      {row.map((c, j) => <TableCell key={j} className="text-xs whitespace-nowrap max-w-[180px] truncate">{c}</TableCell>)}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <div className="flex justify-between">
            <Button variant="outline" onClick={() => { setStep(0); setPreview(null); }}>Back</Button>
            <Button onClick={commit} disabled={busy || nameMissing} data-testid="import-commit-button">
              {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ArrowRight className="h-4 w-4 mr-1" />}
              Import {preview.total_rows} Rows
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Results */}
      {step === 2 && result && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-3 gap-4">
            <Card className="shadow-none" data-testid="import-result-created">
              <CardContent className="pt-5 text-center">
                <CheckCircle2 className="h-6 w-6 text-primary mx-auto" />
                <div className="font-display text-3xl font-semibold tabular-nums mt-1">{result.created}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Imported</div>
              </CardContent>
            </Card>
            <Card className="shadow-none">
              <CardContent className="pt-5 text-center">
                <div className="h-6" />
                <div className="font-display text-3xl font-semibold tabular-nums mt-1">{result.skipped_duplicates}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Duplicates Skipped</div>
              </CardContent>
            </Card>
            <Card className="shadow-none">
              <CardContent className="pt-5 text-center">
                <div className="h-6" />
                <div className="font-display text-3xl font-semibold tabular-nums mt-1">{result.errors.length}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Warnings / Issues</div>
              </CardContent>
            </Card>
          </div>

          {result.errors.length > 0 && (
            <Card className="shadow-none">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Warnings & Skipped Rows</CardTitle></CardHeader>
              <CardContent className="space-y-1.5 max-h-64 overflow-y-auto thin-scroll" data-testid="import-errors-list">
                {result.errors.map((e, i) => (
                  <div key={i} className="text-xs flex gap-2 items-start bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
                    <span className="font-mono shrink-0">Row {e.row}:</span> {e.reason}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <div className="flex gap-2">
            <Button onClick={() => navigate('/candidates')} data-testid="import-view-candidates-button">View Candidates</Button>
            <Button variant="outline" onClick={() => { setStep(0); setPreview(null); setResult(null); }}>Import Another File</Button>
          </div>
        </div>
      )}
    </div>
  );
}
