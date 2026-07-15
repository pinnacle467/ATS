# plan.md

## 1. Objectives
- Deliver a lightweight, modern internal ATS (Dashboard, Candidate Tracker, Interview Scheduling, Admin Panel) on React + FastAPI + MongoDB with Tailwind + shadcn/ui.
- Prove the **core failure-prone workflow** first: **PDF/DOCX resume → text extraction → OpenAI GPT structured JSON → reviewable fields**.
- Implement RBAC (Admin/Recruiter/Interviewer) that gates navigation, data access, and actions.
- Ship a clean V1 with manual interviewer availability + scheduling, designed to plug in Google/Microsoft calendar sync later.

## 2. Implementation Steps

### Phase 1 — Core POC: Resume Parsing in Isolation (must pass before app work)
**User stories**
1. As a recruiter, I can run a script on a PDF resume and get structured JSON fields.
2. As a recruiter, I can run the same script on a DOCX resume and get structured JSON fields.
3. As a recruiter, I can see which fields are low-confidence and need manual review.
4. As a recruiter, I can parse multiple resumes in a folder and get one JSON per file.
5. As a developer, I can re-run the script reliably without manual environment fiddling.

**Steps**
- Web research: best practices for PDF/DOCX text extraction + LLM structured extraction/JSON schema validation.
- Build `poc_resume_parse.py`:
  - Extract text: `pdfplumber` (PDF) + `python-docx` (DOCX); normalize whitespace.
  - Call OpenAI via `emergentintegrations` with a strict JSON schema prompt.
  - Output: `{candidate:{...}, experience:[...], education:[...], skills:[...], confidence:{field:0-1}, low_confidence_fields:[...]}`.
  - Add guards: empty text, token truncation, invalid JSON → retry once with stricter instructions.
- Run against 5–10 varied sample resumes; iterate prompt + extraction until:
  - JSON always parses
  - key fields extracted reasonably
  - low-confidence fields are blanked/flagged

**Exit criteria**
- 90%+ runs produce valid JSON (no manual fixes), and low-confidence logic works.

---

### Phase 2 — V1 App Development (no auth yet; build around proven parsing)
**User stories**
1. As a recruiter, I can upload a resume and review/edit parsed fields before saving the candidate.
2. As a recruiter, I can bulk upload resumes and get multiple draft candidates to review.
3. As a recruiter, I can manage jobs and move candidates through stages via kanban drag-drop.
4. As an interviewer, I can view my upcoming interviews and submit scorecards.
5. As a manager, I can see a dashboard snapshot of pipeline health and my tasks.

**Backend (FastAPI + MongoDB)**
- Core models/collections: users (stub for now), departments, jobs, stages/templates, candidates, applications (candidate↔job), interviews, scorecards, notes/activity, notifications, audit_log.
- Resume endpoints:
  - `POST /resumes/parse` (single) + `POST /resumes/parse/bulk` (multi) using the Phase-1 proven parser.
  - Store original file in object storage (or Mongo GridFS) + text snapshot + parsed JSON + confidence metadata.
- ATS CRUD endpoints (minimal but complete):
  - Jobs: create/edit/open-close, per-job pipeline.
  - Candidates: create from parsed draft, list/search/filter, profile view, stage move, bulk actions.
  - Interviews: schedule, update status, list/calendar feed.
  - Scorecards: create/update per interview per interviewer.
  - Dashboard aggregations: overview cards, pipeline counts per stage, my-tasks, recent activity.
  - CSV export: candidates list with filters.
- Authorization placeholder: pass `X-User-Id` header for development to simulate roles and test flows end-to-end.

**Frontend (React + Tailwind + shadcn/ui)**
- App shell: left nav (role-aware later), top filters (job/department), responsive desktop-first layout.
- Module pages:
  - Dashboard: cards + pipeline chart + my tasks + activity feed.
  - Candidate Tracker:
    - List table + filters + bulk actions
    - Kanban by stage with drag-drop
    - Candidate profile (resume preview/download, notes timeline)
    - Resume upload: single + bulk → review form (flag low-confidence)
  - Interview Scheduling:
    - Calendar (week view) + list view
    - Schedule form with manual interviewer availability slots
    - Scorecard form + feedback status
  - Admin (V1-lite): departments/tags + stage template editor (basic)

**Phase 2 testing checkpoint**
- Run one full E2E test pass (upload→parse→review→save→move stage→schedule interview→submit scorecard→dashboard updates). Fix all breakages.

---

### Phase 3 — Add Auth + RBAC + Admin Hardening
**User stories**
1. As an admin, I can log in and manage users (create/invite/deactivate) and assign roles.
2. As a recruiter, I can only see candidates/jobs I’m permitted to manage (per org rules).
3. As an interviewer, I only see candidates and interviews I’m assigned to.
4. As an admin, I can configure pipeline stages and required scorecard fields per stage.
5. As an admin, I can see an audit log of key system actions.

**Steps**
- Implement email/password auth + JWT (access + refresh) and password hashing.
- Seed demo accounts (Admin/Recruiter/Interviewer) + demo dataset.
- Enforce RBAC at API layer + UI routing/nav gating:
  - Interviewers: restricted candidate visibility, only assigned interviews/scorecards.
  - Recruiters: job/candidate/scheduling management.
  - Admin: full access.
- Admin panel expansion:
  - User management + role assignment
  - Stage templates (global + per job) + interview kits + scorecard schema per stage
  - Audit log viewer
- Notifications: in-app reminders for upcoming interviews + pending feedback.

**Phase 3 testing checkpoint**
- E2E tests per role (Admin/Recruiter/Interviewer) verifying gated actions, data visibility, and no broken flows.

---

### Phase 4 — Calendar Sync (Deferred; start only when credentials exist)
**User stories**
1. As a recruiter, I can see interviewer free/busy to pick a valid time.
2. As a recruiter, scheduling an interview automatically creates a calendar event for all participants.
3. As an interviewer, updates/cancellations reflect on my calendar.
4. As an admin, I can connect/disconnect Google/Microsoft integrations securely.
5. As a system, failures gracefully fall back to manual scheduling without data loss.

**Steps (when credentials provided)**
- OAuth apps + token storage + scopes.
- Implement provider-agnostic interface: `CalendarProvider.freeBusy()` + `CalendarProvider.createEvent()`.
- Google Calendar API + Microsoft Graph adapters.
- UI: connect accounts, choose provider per user, conflict warnings.
- Testing with real tenant credentials + rollback/fallback.

## 3. Next Actions
1. Run web research and draft the POC extraction + prompt schema.
2. Implement and run `poc_resume_parse.py` on sample PDF/DOCX; iterate until exit criteria met.
3. Once POC is stable, scaffold FastAPI + React app and wire `/resumes/parse` into the upload→review→save flow.
4. Build Candidate Tracker + Scheduling core flows, then do the Phase 2 E2E test.

## 4. Success Criteria
- Resume parsing works reliably for PDF and DOCX, produces valid structured JSON, and flags low-confidence fields.
- Recruiter can: create jobs, upload/bulk-upload resumes, review parsed data, manage pipeline/kanban, schedule interviews, collect scorecards.
- Interviewer can: view assigned interviews/candidates and submit feedback; cannot access unassigned candidates.
- Admin can: manage users/roles and configure pipeline/scorecards; audit log captures key actions.
- Dashboard metrics update correctly from real data; search/filter works with a few thousand candidates.
- Manual availability-based scheduling works end-to-end; calendar sync is cleanly pluggable later.