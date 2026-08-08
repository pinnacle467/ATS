# Sprout ATS — PRD & Implementation Status

## Product
Lightweight Greenhouse-style ATS for internal use. React + FastAPI + MongoDB, Tailwind + shadcn/ui.

## Core proven in POC
AI resume parsing (PDF/DOCX → OpenAI gpt-5.4-mini via Emergent LLM key → structured JSON + confidence flags).
POC script: /app/tests/poc_resume_parse.py (all tests passed).

---

## 🚨 NON-NEGOTIABLE DATA DURABILITY — READ FIRST WHEN IMPORTING TO A NEW CHAT

The user's real data (candidates, resumes, jobs, JDs, fit scores, notes, activities, audit log, users) MUST survive every chat import. If any of the steps below are skipped, the new chat will boot with only the synthetic demo seed and every real record will be lost.

### How the durability chain works (as of July 2026 — hook-based, no periodic timer)
1. A git `pre-commit` hook at `.git/hooks/pre-commit` (source of truth: `/app/scripts/pre_commit_snapshot.sh`) runs `python /app/scripts/dump_snapshot.py` **synchronously** before every commit. The dump writes the full live MongoDB `sprout_ats` database to `/app/backend/data_seed/snapshot.json` atomically (tmp file + rename) and the hook then `git add`s that file so it lands in the same commit.
2. When the user commits + pushes via Emergent's **Save to GitHub** feature, the hook fires, `snapshot.json` is refreshed against the live DB, and the commit that goes out contains data exactly as it was at the moment of the click (no 5-minute-stale-snapshot race). `snapshot.json` is NOT in `.gitignore`.
3. On the next chat import, the fresh chat pulls the repo (including the freshly-written snapshot). MongoDB starts empty. Backend startup calls `seed.seed_if_empty()` which sees the empty `users` collection and calls `_restore_snapshot()`, which reads `backend/data_seed/snapshot.json` and re-inserts every collection.
4. Backend startup ALSO calls `snapshot_scheduler.install_pre_commit_hook()`, which copies `scripts/pre_commit_snapshot.sh` into `.git/hooks/pre-commit` and marks it executable. `.git/hooks/*` is not tracked by git, so this re-install on every boot is what makes the durability chain survive fresh chat imports.

### Non-negotiable steps for any main agent working on this build in a new chat

The following MUST be done, in order, at the very start of every new chat import — before touching any feature:

- **Step 1 — Recreate `.env` files** (they are gitignored). Values are protected but standard:
  - `/app/backend/.env` must contain: `MONGO_URL="mongodb://localhost:27017"`, `DB_NAME="sprout_ats"`, `CORS_ORIGINS="*"`, `JWT_SECRET=<any strong value>`, `EMERGENT_LLM_KEY=<universal key from emergent_integrations_manager>`, `APP_BASE_URL=<current preview URL>`, `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` (currently `45396856275-...apps.googleusercontent.com` / `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` — ask user to reconfirm).
  - `/app/frontend/.env` must contain: `REACT_APP_BACKEND_URL=<current preview URL>`, `WDS_SOCKET_PORT=443`.
- **Step 2 — Install deps**: `pip install -r /app/backend/requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` and `cd /app/frontend && yarn install`. Note: `emergentintegrations` and `litellm` both resolve to the same wheel; if pip complains about a conflict, install with `grep -v "^litellm" requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt --extra-index-url ...`
- **Step 3 — DO NOT run `mongorestore` or delete/overwrite the `sprout_ats` database.** The backend's startup will auto-restore from `/app/backend/data_seed/snapshot.json` via `seed.seed_if_empty()`. If MongoDB already has data from a prior boot in this chat, seed does nothing and the data stays.
- **Step 4 — Restart supervisor**: `sudo supervisorctl restart backend frontend`. Confirm the log contains `pre-commit snapshot hook installed at /app/.git/hooks/pre-commit`. It must NOT contain `snapshot_loop scheduled` — that log line belonged to the old periodic-timer design and was removed in July 2026.
- **Step 5 — Verify data restored**: `mongosh sprout_ats --quiet --eval 'print(db.candidates.countDocuments({}))'` — expect ≥ 150 (as of July 2026). Also verify at least one candidate has a `fit_score` and one job has `jd_text`.
- **Step 6 — Verify the hook is armed**: `ls -la /app/.git/hooks/pre-commit` — it must exist, be executable, and contain the string `Sprout ATS` in its header. To smoke-test end-to-end: `cd /app && echo "# smoke" >> README.md && git add README.md && git commit -m "hook smoke"` — the commit output must contain `[snapshot] ✓ fresh snapshot written`, and `git show --stat HEAD` must list `backend/data_seed/snapshot.json`. Then `git reset --soft HEAD~1 && git restore --staged README.md && git checkout -- README.md` to undo the smoke commit.

### Non-negotiable steps for the USER before starting a new chat
- **Click "Save to GitHub" in the Emergent chat input BEFORE starting the new chat.** The pre-commit hook guarantees the pushed snapshot is fresh at the moment of the click — but the click itself is still required. Without the push, the new chat pulls the older snapshot from the repo and any un-pushed data is lost.
- Unlike the old design, the user no longer has to worry about the 5-minute snapshot lag. Any data written up to the second before the click is in the push.

### Things that MUST NOT be done — silent data loss risks
- ❌ Never add `snapshot.json` to `.gitignore`.
- ❌ Never delete `/app/backend/data_seed/snapshot.json`.
- ❌ Never delete `/app/scripts/pre_commit_snapshot.sh`, and never remove the `install_pre_commit_hook()` call from `server.py`'s startup handler — without it, `.git/hooks/pre-commit` doesn't survive a fresh chat and pushes will contain a stale snapshot.
- ❌ Never re-introduce a periodic `snapshot_loop` — the whole point of the hook design is to guarantee freshness at click-time, not "at most 5 minutes stale".
- ❌ Never call `db.dropDatabase()` on `sprout_ats` without first taking a fresh snapshot (`python /app/scripts/dump_snapshot.py`).
- ❌ Never run `import_from_remote.py` on an already-populated db — it does a `delete_many({})` on every collection first (design assumption: it's a one-off migration from a remote build, not a refresh).

---

## Modules (V1 — built)
1. **Dashboard**: KPI cards (open roles, active candidates, interviews this week, offers, avg time-to-hire), pipeline bar chart, My Tasks, activity feed, filters (job/department/recruiter).
2. **Candidate Tracker**: AI resume parse (single + bulk + **folder drop up to 100 files, chunked in batches of 10**) → editable review form with low-confidence flags → save candidate (single) or **Save All** (bulk-assign remaining drafts to one job). Table + kanban (dnd-kit drag-drop) views, search/filters/**sort (Newest / Best fit / Name)**, **Fit column** with color-coded 0-100 AI score, bulk actions (move stage/reject/tag/assign/delete), candidate profile (resume preview/download, notes + email log, timeline, scorecards), CSV export.
3. **Interviews**: week calendar + list views, schedule dialog (type, multiple interviewers, date/time/duration, location/video), manual availability slots + availability/conflict check, status flow scheduled→feedback_pending→feedback_submitted, scorecards (per-stage attributes from pipeline settings), interview kits, in-app notifications. **Google Calendar connect button** (`/oauth/google/login` → callback) — creates events with Meet links + free-busy check.
4. **Admin Panel**: user management (invite/role/deactivate/delete, last login), global pipeline stage editor (order + scorecard attrs), departments & tags, interview kits CRUD, audit log with filter.

## RBAC
- admin: everything
- recruiter: jobs, candidates, scheduling, no admin panel
- interviewer: only assigned candidates/interviews, submit scorecards, no add/edit candidates

## Architecture notes
- Backend: /app/backend, modular routers (routes_*.py), JWT auth (auth.py), resume_parser.py, fit_scorer.py, seed.py (auto-seeds when users collection empty, restores from `data_seed/snapshot.json`), **snapshot_scheduler.py** (writes snapshot every 5 min).
- Files stored as base64 in Mongo `files` collection; served via /api/files/{id} (auth required; frontend fetches blob for iframe preview). Resume auto-compression (lossless PDF font-subset + DOCX max-zip + Pillow image downsample) in `resume_compressor.py`.
- Fit scoring: `fit_scorer.recompute_candidate_fit()` is called as a background task on candidate create + on job_id change + on JD upload. Falls back to `job.description` when `jd_text` is missing.
- All dates stored as ISO strings. IDs are uuid4 strings.
- **Data durability**: see the NON-NEGOTIABLE section above. `data_seed/snapshot.json` is the single source of truth for real data across chat imports.

## Env (in /app/backend/.env)
- `MONGO_URL`, `DB_NAME=sprout_ats`, `JWT_SECRET`, `EMERGENT_LLM_KEY`, `APP_BASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `CORS_ORIGINS`

## Current live data (Aug 2026, after merging live production site `http://129.121.126.61`)
- 3 users (admin@ats.com/Admin@123 super_admin, kangabhijeet@gmail.com super_admin, abhi.kang@context66.com admin)
- 9 jobs, 375 candidates (up to CAND-0082), 80 interviews, 261 resume files
- 151 notes, 1131 activities, 820 audit-log entries, 11 scorecards, 16 analytics events, 4 career pages
- `counters` collection now correctly seeded with `candidate_seq`(82) / `job_seq`(2) — fixes a latent bug where local builds lacked these keys and would have regenerated colliding CAND-0001/JOB-001 codes on next create.

## Changelog (Aug 2026 session)
- **Live production data sync**: SSH'd into the user's live self-hosted deployment (`root@129.121.126.61`, native MongoDB `sprout_ats` db), ran `mongodump`, transferred the dump (53MB, 22 collections) into this build, and merged it into the local `sprout_ats` DB. Policy: upsert every live document by its business key (`id`/`key`/`_id` for `counters`) — live version overwrites on conflict, local-only records (from an older snapshot) are preserved untouched. Verified via `/api/auth/login` + `/api/candidates` (newest live candidate CAND-0082 present) and a UI login smoke test (redirect to `/` succeeded). One-off merge script left at `/app/backend/live_sync/merge.py` for reference; dump files cleaned up (local + remote) after the merge.

## Changelog (July 2026 session)
- **AI Parsing turned ON**: `EMERGENT_LLM_KEY` (universal) wired; verified via `parse_resume_text` smoke test.
- **Google Calendar OAuth wired**: real client id + secret in `.env`; `/api/oauth/google/login` returns valid auth URL with the correct redirect.
- **Login page brand refresh**: new warm hero image (`pexels.com/photos/9301835`), floating "AI resume parsing" / "Structured interview scorecards" chips, split tagline, trust element with brand-emerald avatars.
- **Bulk Resume Import — folder drop + chunked**: `AddCandidatePage.jsx` now supports `webkitGetAsEntry` folder drops and a dedicated **Upload Folder** button; up to 100 files per session, chunked into batches of 10 (matches backend cap of 25/request). Progress bar shows `Parsing X of Y`. A **Save All** action bar bulk-creates all clean drafts against a single chosen job in one click (skips drafts flagged with a "same person" match banner so recruiter reviews those individually).
- **Fit Score Column** on Candidates table: new `FitBadge` component with color tiers (emerald ≥80, amber 60–79, rose <60), tooltip shows the AI's `fit_score_summary`, sort dropdown adds "Best fit first" and "Name (A-Z)". Fit scorer now falls back to `job.description` when `jd_text` is absent (unblocks scoring for the 5 imported jobs that only have a description).
- **Data-durability chain**: imported all data from `https://ats-full-build.preview.emergentagent.com` via `scripts/import_from_remote.py`; wrote `scripts/dump_snapshot.py` (atomic write to `data_seed/snapshot.json` covering every collection); added `backend/snapshot_scheduler.py` running as an asyncio task from `server.py` startup that dumps every 5 minutes so all future edits also persist across chat imports. **See NON-NEGOTIABLE section above.**

## Deferred (explicitly, per user)
- External filesystem storage for resumes (moving off base64-in-MongoDB) — deferred, not started this session.
