# Sprout ATS — PRD & Implementation Status

## Product
Lightweight Greenhouse-style ATS for internal use. React + FastAPI + MongoDB, Tailwind + shadcn/ui.
Preview: https://ats-import-flow.preview.emergentagent.com

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
