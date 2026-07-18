# Sprout ATS — PRD & Implementation Status

## Product
Lightweight Greenhouse-style ATS for internal use. React + FastAPI + MongoDB, Tailwind + shadcn/ui.
Preview: https://ats-import-build.preview.emergentagent.com

## Core proven in POC
AI resume parsing (PDF/DOCX → OpenAI gpt-5.4-mini via Emergent LLM key → structured JSON + confidence flags).
POC script: /app/tests/poc_resume_parse.py (all tests passed).

## Modules (V1 — built)
1. **Dashboard**: KPI cards (open roles, active candidates, interviews this week, offers, avg time-to-hire), pipeline bar chart, My Tasks, activity feed, filters (job/department/recruiter).
2. **Candidate Tracker**: AI resume parse (single + bulk up to 10) → editable review form with low-confidence flags → save candidate. Table + kanban (dnd-kit drag-drop) views, search/filters/sort, bulk actions (move stage/reject/tag/assign), candidate profile (resume preview/download, notes + email log, timeline, scorecards), CSV export.
3. **Interviews**: week calendar + list views, schedule dialog (type, multiple interviewers, date/time/duration, location/video), manual availability slots + availability/conflict check, status flow scheduled→feedback_pending→feedback_submitted, scorecards (per-stage attributes from pipeline settings), interview kits, in-app notifications.
4. **Admin Panel**: user management (invite/role/deactivate/delete, last login), global pipeline stage editor (order + scorecard attrs), departments & tags, interview kits CRUD, audit log with filter.

## RBAC
- admin: everything
- recruiter: jobs, candidates, scheduling, no admin panel
- interviewer: only assigned candidates/interviews, submit scorecards, no add/edit candidates

## Architecture notes
- Backend: /app/backend, modular routers (routes_*.py), JWT auth (auth.py), resume_parser.py, seed.py (auto-seeds when users collection empty).
- Files stored as base64 in Mongo `files` collection; served via /api/files/{id} (auth required; frontend fetches blob for iframe preview).
- All dates stored as ISO strings. IDs are uuid4 strings.
- Calendar sync (Google Workspace / Microsoft Graph) DEFERRED — planned Phase 4 when user provides OAuth credentials. Availability is manual slots (availability collection, seeded Mon-Fri 9-17 for interviewers).

## Env
- EMERGENT_LLM_KEY and JWT_SECRET in /app/backend/.env

## Changelog (this session — Feb 2026)
- **DOCX compression enhanced**: `resume_compressor.py` now also downsamples/re-encodes embedded images (word/media/*) inside DOCX files via Pillow (max 1600px dim, JPEG q=85 or optimized PNG), on top of the pre-existing max-level zip re-compression. Falls back safely to original bytes on any error. Verified byte-safe (zip integrity + identical extracted text) via direct script test and via live UI screenshot (embedded photo in a real resume still renders correctly post-compression).
- **Rejection sub-reason ("Not Fit") verified working end-to-end**: confirmed via direct API test (`move-stage` with reason `"Not Fit: <detail>"` persists correctly to `rejection_reason`/`status`/`stage`) and code review of all 3 entry points (CandidateProfilePage reject dialog, CandidatesPage bulk-reject dialog, Kanban drag-to-Rejected dialog) — all correctly gate "Not Fit" behind a required text detail field.
- **Resume attachment indicators verified working**: visually confirmed on Candidates table (colored vs dimmed file icon per row) via screenshot.
- **Resume preview enlarged + made expandable** (`CandidateProfilePage.jsx`): default preview height increased from 480px to 720px; added an "Expand" button (`data-testid=candidate-resume-expand-button`) that opens a large full-screen modal (`data-testid=candidate-resume-expand-modal`, ~95vw x 92vh) rendering the same PDF iframe / DOCX preview at full readable size. Fixed a docx-preview rendering race (blank/gray result) by adding a 200ms delay before calling `renderAsync` in the modal so the Dialog's open-transition finishes and the container has real width before docx-preview measures it. Verified visually: DOCX renders crisp, large, fully readable (including embedded photo); PDF iframe blob URL wiring confirmed correct (blank rendering when screenshotted is a known headless-Chromium limitation — no native PDF viewer plugin in Playwright's Chromium build — not an app bug; renders fine in real user browsers, consistent with the pre-existing default PDF preview behavior).

## Deferred (explicitly, per user)
- External filesystem storage for resumes (moving off base64-in-MongoDB) — deferred, not started this session.
