# Sprout ATS — PRD & Implementation Status

## Product
Lightweight Greenhouse-style ATS for internal use. React + FastAPI + MongoDB, Tailwind + shadcn/ui.

## Core proven in POC
AI resume parsing (PDF/DOCX → OpenAI gpt-5.4-mini via Emergent LLM key → structured JSON + confidence flags).
POC script: /app/tests/poc_resume_parse.py (all tests passed).

---

## Import log
- **Sep 2026 — imported full build from GitHub `pinnacle467/ATS` (commit `85f021a`) into a fresh chat.** Followed the runbook below: recreated `backend/.env` (fresh `JWT_SECRET` + fresh `CREDENTIALS_ENCRYPTION_KEY`; `XAI_API_KEY` left empty because the Context66 tenant's Grok key lives in `tenant_ai_settings` and was restored from the snapshot) and `frontend/.env` (preview URL `https://fcbac33a-c2b9-46d6-ae1c-a42119ff0f02.preview.emergentagent.com`), installed deps (`litellm` line stripped from requirements to avoid the resolver conflict), restarted supervisor. Verified: snapshot auto-restored (candidates=400, jobs=9, files=280, tenants=2 `context66`+`acme`, 399 candidates with fit_score), pre-commit hook installed, `admin@ats.com / Admin@123` login works via API + UI, dashboard renders real data. Credentials in `/app/memory/test_credentials.md`. Note: `job_board_integrations` was empty, so the new Fernet key caused no undecryptable rows.

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
  - `/app/backend/.env` must contain: `MONGO_URL="mongodb://localhost:27017"`, `DB_NAME="sprout_ats"`, `CORS_ORIGINS="*"`, `JWT_SECRET=<any strong value>`, `XAI_API_KEY=<user's Grok/xAI key>`, `APP_BASE_URL=<current preview URL>`. `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` and `RESEND_API_KEY` are NOT yet configured as of Aug 2026 — Google Calendar/Meet and candidate emails remain inactive until the user provides them (see Backlog).
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
- ❌ Never let `scripts/dump_snapshot.py`'s `COLLECTIONS` list drift from what the app actually writes to. This happened (Feb 2026): after the multi-tenancy conversion, the list was never updated and silently dropped `tenants`, `platform_admins`, `offers`, `tenant_ai_settings` from every snapshot, plus the `settings` collection only ever captured the `pipeline_stages` key (scheduling settings + the offer letter template were dropped too). Fixed by dumping/restoring the full `settings` collection generically and adding every missing collection — cross-check periodically with `grep -rEoh "db\.[a-zA-Z_]+\." backend/*.py backend/*/*.py | sed -E "s/db\.([a-zA-Z_]+)\..*/\1/" | sort -u`.

### VPS / self-hosted deployments do NOT auto-sync data from Emergent
`seed.seed_if_empty()` only restores `snapshot.json` when the `users` collection is completely empty (first boot). A VPS that already has data will NOT pick up new snapshot data just from a `git pull` + restart. To force an already-running deployment (e.g. a VPS) to match the latest snapshot from GitHub, run `python scripts/restore_snapshot.py --yes` there (full destructive overwrite of every collection from `snapshot.json`, reading `MONGO_URL`/`DB_NAME` from that deployment's own `backend/.env`) then restart the app. See `scripts/VPS_SYNC.md` for the exact runbook. Dry-run (no `--yes`) prints a before/after diff without touching data.

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
- `MONGO_URL`, `DB_NAME=sprout_ats`, `JWT_SECRET`, `XAI_API_KEY`, `APP_BASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (VPS only, not sandbox), `CORS_ORIGINS`

## Current live data (Aug 2026, after merging live production site `http://129.121.126.61`)
- 3 users (admin@ats.com/Admin@123 super_admin, kangabhijeet@gmail.com super_admin, abhi.kang@context66.com admin)
- 9 jobs, 379 candidates (up to CAND-0089), 80 interviews, 261 resume files
- 257 candidates now have an AI/manually-classified `industry` field (see Industry feature below); remaining 122 have no resume/no clear evidence and are correctly left untagged
- 151 notes, 1131+ activities, 11 scorecards, 16 analytics events, 4 career pages
- `counters` collection correctly seeded with `candidate_seq`/`job_seq` — fixes a latent bug where local builds lacked these keys and would have regenerated colliding CAND-0001/JOB-001 codes on next create.
- **Production VPS (`http://129.121.126.61`) and this sandbox are TWO SEPARATE MongoDB instances.** Deploying code via git never syncs data between them (by design). As of Aug 2026 both are in sync (379 candidates, same industry tags) because the main agent manually pushed the sandbox's new candidates + industry data to the VPS via SSH+pymongo — but any FUTURE data added in one will NOT automatically appear in the other. If the user reports "my data is missing" after a fresh VPS deploy, check this first.

## Changelog (Sep 2026 session — One-time candidate data sync from user's VPS)
- User's private VPS (129.121.126.61, SSH root) runs its own self-hosted deployment of this same app (`sprout_ats` DB, same tenant IDs — same origin snapshot). Did a ONE-TIME, data-only sync (no code touched) of `candidates` (400 docs) + `files` (283 docs, resume blobs referenced by `resume_file_id`) collections FROM the VPS INTO this sandbox, per user's explicit request: overwrite sandbox with VPS's live/edited data (VPS had real usage — stage changes, notes — since original seed; sandbox still had unedited demo data).
- Method: `mongodump --gzip` on VPS → `scp` → `mongorestore --drop` locally. Took a pre-sync backup of the sandbox's old candidates+files first, saved at `/app/memory/backup_sandbox_{candidates,files}_pre_sync.dump` for rollback if ever needed.
- Verified: doc counts match (400/283), all resume_file_id links resolve, dashboard/candidates pages render correctly with the new live data (fit scores, stages, industries, recruiter assignments all reflect VPS production state).
- Scope explicitly limited to candidates+files only (per user's request) — activities/interviews/scorecards/offers were NOT synced.

## Changelog (Sep 2026 session — Per-tenant Google OAuth + AI-caching audit)
- **Per-tenant Google Calendar/Gmail OAuth** (new): `backend/google_oauth_settings.py` stores each tenant's own Google Cloud OAuth `client_id`/`client_secret` (Fernet-encrypted via existing `crypto_utils.py`, `CREDENTIALS_ENCRYPTION_KEY`) in global `tenant_google_settings` collection, falling back to env `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` when a tenant hasn't configured its own. `google_calendar.py`'s `authorization_url`/`exchange_code` now take explicit client_id/secret params; `get_credentials_for_user` resolves per-tenant creds internally. `routes_calendar.py`'s OAuth callback (public, no JWT) now looks up the user via `raw_db` and wraps the token-exchange/save in `tenant_scope(tenant_id)` — this also fixed a **pre-existing latent bug** where the callback had no tenant context set at all (would have raised `TenantScopeError`). Platform Control Panel (`/platform`) now has a "Google" badge + config dialog per tenant (GET/PUT/DELETE `/platform/tenants/{id}/google`), mirroring the existing per-tenant AI-settings UI.
- **AI-caching audit** (no code changes needed): confirmed fit score, resume parsing, and industry tagging are already compute-once-cache-in-Mongo — `GET /candidates/{id}` is a pure DB read with zero AI calls; `recompute_candidate_fit` only fires from explicit event triggers (resume upload, job (re)assign, JD change, new application) via `background_tasks.add_task`; `/backfill-industry` is idempotent (skips already-classified unless `force=true`).
- Verified by testing_agent (iteration_4.json): 100% pass (10/10 backend pytest + full frontend CRUD flow), Fernet encryption confirmed via direct Mongo inspection, AI-caching claim independently re-confirmed by re-reading the source.

## Changelog (Sep 2026 session — Dashboard + Candidate Profile major UI/UX refinement)
- User gave a detailed spec to restructure (not just restyle) Dashboard and Candidate Profile into "Candidate 360°"/"recruiter command center" style, explicitly preserving all existing data/APIs, no fabricated fields.
- **DashboardPage.jsx**: Upcoming Interviews card enriched with interviewer name(s) + duration_min (uses existing /interviews fields, no backend change).
- **CandidateProfilePage.jsx** major restructure: added a header contact-meta row (email mailto/phone tel/location/recruiter, only rendered if data exists) + tags moved into header badge row; Overview tab changed from 2-col to a true 3-column `lg:grid-cols-12` (3/6/3) layout — LEFT="About" card (job select, recruiter, notice period, expected comp admin-only, industries — email/phone/tags removed here since now in header), CENTER=new "Skills" card + enhanced "Job Fit Score" (added qualitative label Strong/Moderate/Low fit) + new split-out "Experience" card + new split-out "Education" card (previously combined "Background") + "Interview Feedback" scorecards, RIGHT="Pipeline Status" stepper + "Upcoming Interviews" + "Add Note/Log Email" + "Activity Timeline" (unchanged, just narrower). Added a new "Resume" tab (`candidate-tab-resume`) — moved the large Resume preview card (PDF iframe / docx-preview / mobile fallback / Expand+Download) out of Overview into its own TabsContent using Radix `forceMount` + `data-[state=inactive]:hidden` so the `docxContainerRef`-based render effect still works despite lazy tab mounting — verified working (docx renders ~21KB of content, PDF blob confirmed valid) via manual test with a real .docx-resume candidate (Himanshu Kumar, id `d8455825-65bb-44b5-b641-28acf51124b5`).
- Fixed minor React duplicate-key warning in Skills card (now keys by `${skill}-${index}`).
- Verified by testing_agent (iteration_3.json): ~95% pass, zero blocking issues; only loose end was DOCX-path which I then manually verified myself (see above) since no seeded Screening-stage candidate had one at test time.

## Changelog (Sep 2026 session — UI reskin to "HireFlow" design)
- User supplied 2 reference screenshots (dark navy sidebar, blue #2563EB accent, card dashboard, dense candidate table, tabbed profile) and asked for a full reskin, no new modules, light mode only, brand renamed "Pinnacle ATS" → "HireFlow".
- **Theme foundation**: `index.css` new blue HSL vars + new `--sidebar-*` vars (dark navy `222 47% 9%`); `tailwind.config.js` adds a `sidebar` color token group. `PinnacleLogo.jsx` redesigned (blue mark, same export signature — used in 10+ files, none broken).
- **AppShell.jsx** fully redone: dark navy sidebar (w-64), blue active nav state, topbar with pill search + ⌘K hint, user avatar+name+role block. All existing data-testids preserved.
- **DashboardPage.jsx** rewritten: KPI cards with colored icon boxes, Hiring Pipeline bar chart recolored to graduated blue with value labels, new "Recent Candidates" table (GET /candidates sort=created_at limit=5) and "Upcoming Interviews" card (GET /interviews status=scheduled), existing My Tasks/Activity Feed kept.
- **JobsPage.jsx** rewritten (2nd pass, after user flagged it wasn't updated enough): KPI cards (Open Roles/Total Applicants/Active in Pipeline/Hired), status pill-tabs with counts, search input, converted card-grid → real `<Table>` (Job Title+code+JD icon, Department, Location, Status, Applicants (clickable, hover-underline), Stages badges, row actions). All handlers (openCreate/openEdit/save/setStatus/deleteJob) unchanged; `JdIndicator` export preserved for JobDetailPage.
- **CandidatesPage.jsx**: added `initialsOf` export + avatar circle per row, stage-count quick-filter chips row (reuses GET /dashboard/stats pipeline breakdown), STAGE_BADGE Interview color tied to primary blue. All bulk-action/kanban/filter logic untouched.
- **CandidateProfilePage.jsx** (2nd pass): added avatar in header, underline-style Tabs, new `PipelineStepper` component moved into a right-sidebar "Pipeline Status" card + new "Upcoming Interviews" sidebar card (GET /interviews?candidate_id=&status=scheduled, future-dated only) placed above the pre-existing Notes/Timeline cards.
- Branding text "Pinnacle ATS" → "HireFlow" across Login/Forgot/Reset/WorkspacePicker/Account/CareerPublicLayout; emerald hero panels/avatars → blue. Tenant-level custom `branding.accent_color` (e.g. Context66's emerald) legitimately overrides the global blue — expected multi-tenant behavior, not a bug.
- Verified by testing_agent (iteration_2.json): 100% of tested flows passed, zero bugs, all new data-testids present (`candidates-stage-chips`, `stage-chip-*`, `candidate-pipeline-status`, `pipeline-step-*`, `candidate-upcoming-interviews`, `jobs-kpi-*`, `jobs-status-tab-*`, `job-row-*`).

## Changelog (Aug 2026 session, continued)
- **Industry indicator + industry-based search feature** (full build): candidates now have a normalized `industry: list[str]` + `industry_source: 'auto'|'manual'` field. New `industry_taxonomy.py` (21 canonical values + alias normalization e.g. Fintech→FinTech, "health care"→Healthcare). `resume_parser.py`'s single LLM call now also classifies industry from work-history evidence (never from job title alone, per explicit prompt rule). Standalone `industry_classifier.py` + `POST /candidates/backfill-industry` (admin-only, background task + polling status) migrates existing candidates. Manual edits via `PUT /candidates/{id}` set `industry_source='manual'`, which `merge-resume` respects (never overwritten by a later auto-parse). Search bar tokenizes `q` (AND across tokens, OR across name/email/title/company/skills/industry per token — e.g. "Python FinTech" now works). Dedicated `Industry` checkbox filter (OR semantics) + `Industry` table column + CSV export column. New shared frontend component `components/IndustryPicker.jsx` (chip editor, filter dropdown, read-only chips) used in `CandidatesPage`, `CandidateProfilePage`, `AddCandidatePage`. Admin Panel gained a "Data Tools" tab to run/monitor the backfill.
- **Bug fixes found by testing_agent, both fixed and re-verified**: (1) `GET /candidates/meta/industries` 500'd because `db.candidates.distinct('industry')` can return `None` entries that crashed `sorted()` — fixed by filtering non-empty strings first. (2) The Industry filter dropdown silently didn't filter anything — axios was sending `industry[]=X` (bracket notation) while FastAPI's `Query(List[str])` expects repeated `industry=X&industry=Y`; fixed globally via `paramsSerializer: { indexes: null }` on the shared axios instance in `frontend/src/lib/api.js`.
- **VPS production data restore**: user reported candidates + industry tags added during this session were missing after deploying the new code to their VPS. Root cause: the VPS's MongoDB is fully independent from the sandbox's — code deploys never carry data. Fixed by running the industry backfill to completion in the sandbox (257/379 tagged) then pushing new/changed data (industry fields for 257 candidates + 4 sandbox-only candidates + their resume files) directly into the VPS's MongoDB via SSH. Verified by testing_agent directly against `http://129.121.126.61`: candidate count now 379, all 4 previously-missing candidates present with correct industry tags, pre-existing manually-tagged candidate (Arav Vyawahare) unaffected, no regressions.
- **Google Calendar/Meet activated on the VPS**: user provided `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`. Set directly in the VPS's `/opt/ats/backend/.env` via SSH (its `APP_BASE_URL` was already correctly `http://129.121.126.61`) and restarted the `ats-backend` systemd service. Verified via curl against the VPS: `/api/oauth/google/login` now returns a valid Google authorization URL with the correct client_id + `redirect_uri=http://129.121.126.61/api/oauth/calendar/callback` + all required scopes. NOT added to the sandbox's own `.env` (redirect URI is host-specific). Full OAuth consent needs the user's own Google login in-browser — cannot be automated further.
- **Isolated demo instance built for prospect/customer testing**: built `backend/demo_seed.py` — a standalone, idempotent script (fictional company, 3 users, 4 jobs, 15 candidates with AI-style fit scores + industry tags, 4 interviews, scorecard, notes, activities) that seeds ANY target database name without touching real data. Validated it in this sandbox first by seeding a scratch `sprout_ats_demo_test` db, temporarily pointing this sandbox's own `.env` at it, verifying login+data via curl through the real running app, then reverting `.env` back to `sprout_ats` (confirmed 379 real candidates intact afterward). Then deployed the same validated script to the user's VPS as a FULLY isolated instance: separate `ats-demo-backend` systemd service (port 8002, own `.env.demo`, own JWT secret), separate `sprout_ats_demo` Mongo database, separate frontend build (`/opt/ats-demo-frontend`, own `REACT_APP_BACKEND_URL`), separate nginx server block (port 8080), and opened port 8080 in `ufw` (was previously only 22/80/443). Verified externally: demo login/data work on port 8080, and the real production site on port 80 (379 candidates) is completely unaffected. This is the reusable pattern for future demo/prospect access — just re-run `demo_seed.py` against a fresh db name for a clean reset.
- **VPS page-load performance fix**: user reported the VPS site "taking way too long to load anything". RCA: nginx's `gzip on;` was active but `gzip_types` was commented out in `/etc/nginx/nginx.conf`, so only `text/html` was compressed — the React app's 1.72MB main JS bundle was served completely uncompressed to every visitor. Fixed by enabling `gzip_types` (js/css/json/svg/woff etc.), `gzip_comp_level 6`, `gzip_min_length 512`; also added a `location /static/ { expires 1y; add_header Cache-Control "public, immutable"; }` block to both the prod (port 80) and demo (port 8080) nginx site configs since CRA build filenames are content-hashed and safe to cache indefinitely. Verified by testing_agent: main.js now transfers gzip-compressed at 484,603 bytes (was 1,724,008 uncompressed, 3.6x smaller), cache headers present, ~0.9s networkidle page load on both instances, zero functional regressions. A minor unrelated pre-existing 400 console error was spotted on the prod Jobs page during testing (not reproduced by main agent directly hitting `/api/jobs` or `/api/departments`, both returned 200) — flagged in backlog for a future look, did not block anything.

## Changelog (Aug 2026 session)
- **Grok AI activated**: `XAI_API_KEY` added to `/app/backend/.env` (rotated key). Verified end-to-end: `resume_parser.parse_resume_text()` correctly extracts structured fields from a sample resume, and `fit_scorer._score_text()` returns a real 0-100 score + summary. Resume parsing, bulk import, and fit-score recompute are now live (previously blocked on missing key).
- **Live production data sync**: SSH'd into the user's live self-hosted deployment (`root@129.121.126.61`, native MongoDB `sprout_ats` db), ran `mongodump`, transferred the dump (53MB, 22 collections) into this build, and merged it into the local `sprout_ats` DB. Policy: upsert every live document by its business key (`id`/`key`/`_id` for `counters`) — live version overwrites on conflict, local-only records (from an older snapshot) are preserved untouched. Verified via `/api/auth/login` + `/api/candidates` (newest live candidate CAND-0082 present) and a UI login smoke test (redirect to `/` succeeded). One-off merge script left at `/app/backend/live_sync/merge.py` for reference; dump files cleaned up (local + remote) after the merge.

## Changelog (July 2026 session)
- **AI Parsing turned ON**: `EMERGENT_LLM_KEY` (universal) wired; verified via `parse_resume_text` smoke test.
- **Google Calendar OAuth wired**: real client id + secret in `.env`; `/api/oauth/google/login` returns valid auth URL with the correct redirect.
- **Login page brand refresh**: new warm hero image (`pexels.com/photos/9301835`), floating "AI resume parsing" / "Structured interview scorecards" chips, split tagline, trust element with brand-emerald avatars.
- **Bulk Resume Import — folder drop + chunked**: `AddCandidatePage.jsx` now supports `webkitGetAsEntry` folder drops and a dedicated **Upload Folder** button; up to 100 files per session, chunked into batches of 10 (matches backend cap of 25/request). Progress bar shows `Parsing X of Y`. A **Save All** action bar bulk-creates all clean drafts against a single chosen job in one click (skips drafts flagged with a "same person" match banner so recruiter reviews those individually).
- **Fit Score Column** on Candidates table: new `FitBadge` component with color tiers (emerald ≥80, amber 60–79, rose <60), tooltip shows the AI's `fit_score_summary`, sort dropdown adds "Best fit first" and "Name (A-Z)". Fit scorer now falls back to `job.description` when `jd_text` is absent (unblocks scoring for the 5 imported jobs that only have a description).
- **Data-durability chain**: imported all data from `https://ats-full-build-2.preview.emergentagent.com` via `scripts/import_from_remote.py`; wrote `scripts/dump_snapshot.py` (atomic write to `data_seed/snapshot.json` covering every collection); added `backend/snapshot_scheduler.py` running as an asyncio task from `server.py` startup that dumps every 5 minutes so all future edits also persist across chat imports. **See NON-NEGOTIABLE section above.**

## Changelog (Aug 2026 session, continued further)
- **Frontend page-navigation performance fix**: user asked "can the load time when i switch from different pages like from Candidates to Jobs or vice versa be reduced?". RCA: many pages independently re-fetched the same rarely-changing reference lists (jobs, users, tags, departments, pipeline stages, interview kits) on every single mount/route change, adding redundant round-trips to every page switch. Fixed with a new shared frontend cache module `frontend/src/lib/referenceCache.js` — a lightweight per-resource TTL cache (5 min) + pub/sub pattern exposing `useCachedJobs`/`useCachedUsers`/`useCachedTags`/`useCachedDepartments`/`useCachedPipelineStages`/`useCachedInterviewKits` hooks (first caller fetches, everyone else reuses in-flight promise or cached result) and `refreshJobs`/`refreshUsers`/`refreshTags`/`refreshDepartments`/`refreshPipelineStages`/`refreshInterviewKits` functions to call right after a mutation so already-mounted consumers update reactively instead of going stale. Converted `JobsPage`, `CandidatesPage`, `DashboardPage`, `AddCandidatePage`, `InterviewsPage`, `CandidateProfilePage`, `ImportCandidatesPage`, `ScheduleInterviewDialog`, `JobTeamPanel`, `ScorecardDialog` to read from the cache instead of calling `api.get()` on every mount; `AdminPage` intentionally keeps its own local `load()`/state for editing (source of truth for CRUD) while also calling the `refresh*()` invalidators after each mutation so other pages pick up the change. Public career page (`CareerJobsPage.jsx`, unauthenticated) intentionally left untouched — different auth context, not part of the internal navigation loop. Verified by testing_agent (`iteration_4.json`): zero regressions across all converted pages/dialogs, cache invalidation correctly propagates cross-page (new job → shows in Candidates' job filter immediately; new department/tag → shows in relevant dropdowns immediately), and network-level check confirmed repeat navigation to an already-visited page within the TTL window fires **zero** redundant `/jobs`, `/users`, `/tags`, `/departments`, `/settings/pipeline`, `/interview-kits` requests (only `/candidates` + unrelated polling endpoints fired) — confirming the actual performance fix works. Test data created during testing (1 job, 1 department, 1 tag, all `TEST`-prefixed) was cleaned up via API afterward.

## Deployment Log
- **Aug 9, 2026**: Deployed navigation-speed cache fix + Demo Reset Data feature to VPS production (`sudo bash /opt/ats/deploy/deploy.sh`, commit `3275816`) and to the isolated demo instance (synced frontend source into `/opt/ats-demo-frontend`, rebuilt, added `DEMO_MODE=true` to `/opt/ats/backend/.env.demo`, restarted `ats-demo-backend`). Verified live: production 379 candidates intact, demo reseed executed successfully (15 fresh candidates), production correctly 403s the reseed endpoint (safety gate confirmed on live infra, not just sandbox).
- **Feb 2026 (Naukri deploy)**: user asked to redeploy whatever is currently on GitHub. Ran `sudo bash /opt/ats/deploy/deploy.sh` on the VPS (commit `9fba41e` — Job Boards + Naukri) via SSH. **Found and fixed a real outage**: `ats-backend` crash-looped after the deploy (`KeyError: 'CREDENTIALS_ENCRYPTION_KEY'`) because that env var — required since the Job Board Integration feature shipped — was never present in this VPS's pre-existing `backend/.env` (it predates that feature and `install.sh` hadn't been re-run). Fixed live by generating a fresh Fernet key directly on the VPS (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and appending it to `/opt/ats/backend/.env`, then `systemctl restart ats-backend` → came up clean. **Hardened both scripts so this class of bug can't recur**: `deploy/install.sh` now provisions `CREDENTIALS_ENCRYPTION_KEY` on fresh installs (idempotent — never overwrites an existing key, same pattern as `JWT_SECRET`), and `deploy/deploy.sh` now self-heals it on every run — if `backend/.env` exists but is missing the key, it generates and appends one automatically before restarting the service, using only Python stdlib (no `cryptography` package dependency at that point in the script). Verified live end-to-end post-fix: `ats-backend`/`mongod`/`nginx` all `active`, live counts candidates=400/jobs=9/files=280, admin login (`admin@ats.com` / `context66`) returns 200 with a token, and `GET /api/job-boards/integrations` returns all 7 providers including `naukri` — confirming the Job Boards module (Naukri included) is genuinely live in production, not just deployed.

## Changelog (Feb 2026 session)
- **GitHub push protection block (secret scan) fixed**: `git push` (via Save to GitHub) was rejected because a real xAI/Grok API key was hardcoded in a comment in a stale one-off test script (`/app/test_ai_provider_config.py`, superseded, also had outdated owner credentials). Deleted the file. User was given the choice to rotate the key vs. use GitHub's "allow secret" bypass since the key was only ever committed locally (push had never previously succeeded) — resolved on the user's side.
- **Snapshot/durability gap fixed (see NON-NEGOTIABLE section above)**: `scripts/dump_snapshot.py`'s `COLLECTIONS` list had never been updated after the multi-tenancy conversion — every snapshot silently excluded `tenants`, `platform_admins`, `offers`, `tenant_ai_settings`, and most of `settings` (only `pipeline_stages` was special-cased; `scheduling` + `offer_letter_template` settings docs were dropped). This is the actual root cause behind "my VPS is missing data" reports going forward — a VPS pulling this repo would get a code update but a data snapshot that didn't even carry the tenant registry. Fixed `dump_snapshot.py` and `backend/seed.py::_restore_snapshot()` to cover every collection the app writes to (verified via `grep -rEoh "db\.[a-zA-Z_]+\." backend/*.py` against the live DB's actual collection list), and switched `settings` to a generic full-collection dump/restore instead of the old pipeline-only special case.
- **New `scripts/restore_snapshot.py`**: a repeatable, `--yes`-gated, full-overwrite restore script for already-running deployments (VPS). Unlike `seed.py`'s bootstrap-only restore, this always overwrites every collection in `COLLECTIONS` from the current `snapshot.json`. Dry-run by default (prints a before/after count diff per collection); reads `MONGO_URL`/`DB_NAME` from that deployment's own `backend/.env`. Validated by running it against a disposable scratch database (`scratch_restore_test`) — confirmed `tenants`, `platform_admins`, `candidates`, `offers`, `settings` all restore correctly — then dropped the scratch db; live/preview data was never touched. Runbook at `scripts/VPS_SYNC.md`.
- Re-ran `dump_snapshot.py` against the live preview DB to refresh `backend/data_seed/snapshot.json` immediately with the corrected collection list (tenants=2, platform_admins=1, offers=2, tenant_ai_settings=1, settings=3, candidates=397 — all now captured; previously 0 of those 5 keys existed in the snapshot at all).
- **VPS sync executed end-to-end**: user's VPS (`http://129.121.126.61`, `/opt/ats`, systemd `ats-backend`) had stale/independent data even after a deploy attempt (its `tenants`/`platform_admins` had different IDs than the snapshot — confirmed via public API calls before touching anything). Main agent was given root SSH access (`root@129.121.126.61`) directly by the user and ran `scripts/restore_snapshot.py --yes` there manually (the user's own deploy.sh run hadn't picked up the just-pushed fix in time), then `systemctl restart ats-backend`. Verified via curl against the live VPS: `context66` tenant id now `0d6ff40c-...` (matches snapshot), `admin@ats.com` login returns 397 candidates, platform owner id now `22470887-...` (matches snapshot) — VPS and Emergent preview are now fully in sync. No SSH key persisted; access was password-based (user-provided), one-off.
- **Delete Offer + Delete Scheduling Link (Feb 2026)**: `DELETE /api/offers/{offer_id}` (admin/recruiter/super_admin or the offer's creator; also removes the attached contract file from `db.files`) and `DELETE /api/scheduling/requests/{req_id}` (admin/recruiter/super_admin; best-effort deletes the linked Google Calendar event first if one exists) added. Frontend: trash icon next to the status badge on every offer card in `OfferPanel.jsx` (`offer-delete-button-{id}`), and a red "Delete" item at the bottom of the Actions dropdown on the `/scheduling` dashboard (`scheduling-delete-{id}`), both gated behind a `window.confirm()`. Verified via curl (create→delete→404) + `testing_agent_v4` frontend pass (100%, zero regressions on existing Approve/Reject/Cancel/Edit offer actions and Copy/Send/Disable/Regenerate/Timeline scheduling actions).

## Job Board Integration & Application Ingestion module (Feb 2026)
Full provider/adapter architecture for publishing jobs to external job boards and ingesting inbound applications, built on top of the existing candidate/resume-parser/fit-scorer/RBAC/audit-log infrastructure without modifying any of it.

**Architecture**: `backend/job_boards/` — `base.py` defines `JobBoardProvider` (connect/test_connection/publish_job/update_job/expire_job/get_job_status) + `ATS_JOB_FIELDS` (the subset of fields the existing Job model can populate: title, description, company, department, location, remote_type, employment_type, salary_range, application_url, requisition_id, job_reference_id — the Job model does NOT have separate country/state/city, structured salary_min/max, skills, qualifications or benefits fields yet, so those aren't sent; this was a deliberate scope decision, not an oversight, to avoid touching the core Job model). `mock_provider.py` (Sandbox — always succeeds, used for demoing/testing the whole pipeline with zero setup, has a "Simulate Application" action). `partner_providers.py` (Indeed/ZipRecruiter/LinkedIn — full adapter framework, but `test_connection`/`publish_job` always return `partner_approval_required`, NEVER a fake success, since all three require business-level partner approval this environment cannot obtain — see docstrings for the exact application process per board, current as of Feb 2026 web research). `generic_xml_provider.py` / `generic_webhook_provider.py` — fully functional, no external approval needed. `registry.py` — central catalogue; adding a new board later = one new file + one registry line, nothing else changes.

**Ingestion pipeline** (`backend/job_board_ingestion.py`): shared by the webhook endpoint today (email ingestion deferred per user's explicit choice — needs their own inbound-email DNS setup, out of scope for this environment). Dedup order: `provider`+`external_candidate_id` on `candidate.job_board_refs[]` → exact email → normalized phone. If a match is found for a **different** job than the one being applied to, the candidate's pipeline is **never silently moved** — an `applications` doc with `status='duplicate_review'` is created and the recruiter must resolve it (`add_to_pipeline` / `create_new_candidate` / `ignore`) via the new Applications tab. Reuses `resume_parser.parse_resume_text()` (unchanged) and `fit_scorer.recompute_candidate_fit()` (unchanged) — no second resume parser was built.

**DB collections added**: `job_board_integrations` (per-tenant, per-provider connection + Fernet-encrypted credentials via new `crypto_utils.py`, key in `CREDENTIALS_ENCRYPTION_KEY` env var), `job_board_publications` (one row per job×provider — Job Board Distribution UI), `job_board_sync_logs` (also mirrored into the existing `audit_log` via `log_audit()`), `job_board_webhook_events` (webhook delivery idempotency, unique on `webhook_id`+`idempotency_key`). The existing `applications` collection (already used by the career portal) was **extended**, not duplicated, with `source_type`, `provider`, `external_candidate_id/application_id/job_id`, `raw_payload`, `status`, `potential_duplicate_of`. All new collections are automatically tenant-isolated via the existing `TenantDatabase` proxy — no changes needed to `tenant_context.py`.

**API endpoints**: `GET/POST /api/job-boards/integrations[/{provider}/connect|test|disconnect]`, `POST /api/job-boards/jobs/{id}/publish[-preview]`, `PUT/POST/DELETE /api/job-boards/publications/{id}[/close|/retry]`, `GET /api/job-boards/jobs/{id}/publications` (incl. a virtual "Career Portal" row derived from the job's existing `published` flag), `GET/POST /api/job-boards/applications[/{id}][/resolve]`, `GET /api/job-boards/analytics/{job_id}`, `GET /api/job-boards/sync-logs`, `POST /api/job-boards/integrations/mock/simulate-application` (QA helper). Public (no auth, tenant resolved from URL/query): `GET /api/job-feeds/{slug}/jobs.xml`, `POST /api/integrations/job-boards/applications` (HMAC-SHA256 or bearer-token webhook auth, rate-limited via existing `rate_limiter.py`, idempotent).

**Frontend**: new Admin Panel tab "Job Boards" (`JobBoardsTab.jsx` — Connections/Applications/Activity Log sub-tabs) and a new "Job Board Distribution" card on the Job Detail page (`JobBoardDistributionCard.jsx` — Publish dialog with field-mapping preview + unsupported-field warnings, per-board Update/Close/Retry/Remove/View Posting, Simulate Application on Sandbox). `CandidatesPage.jsx` `SOURCES` extended with `indeed`/`ziprecruiter`/`generic_xml`/`generic_webhook`/`mock` for per-provider analytics.

**Tested**: backend fully curl-verified by main agent (all 6 providers connect/test/disconnect, publish/update/close/retry/remove, webhook auth+idempotency+resume-via-base64+AI-parsing, dedup same-job vs different-job, resolve actions, analytics, XML feed) + `testing_agent_v4` frontend pass (95%→100% after one fix: Job Detail page candidate list/kanban/sources chart weren't auto-refreshing after "Simulate Application" — fixed by passing `load` down as an `onApplicationIngested` callback). Zero regressions in existing Admin Panel tabs or Job Detail sections. RBAC confirmed: vendor role gets 403 on all integration-management endpoints; applications list is scoped (not blocked) for non-admins per spec.

**Limitations / what needs external action to go live**: Indeed/ZipRecruiter/LinkedIn/Naukri.com all need real business partner approval (see `backend/job_boards/partner_providers.py` docstrings for the current 2026 application process/URLs per board) — entering an API key alone will never connect these four. Naukri.com added Feb 2026 (no self-serve API; requires a paid Naukri subscription + integration key from a Naukri account manager) — appeared automatically in the Connections grid and Publish dialog with zero frontend changes, confirming the adapter architecture (one new provider file + one registry line = fully wired everywhere). Email application ingestion (Settings → Job Boards → Email Application Ingestion) was explicitly deferred — needs an inbound-email provider (e.g. SendGrid Inbound Parse) pointed at the user's own domain DNS.

## Deferred (explicitly, per user)
- External filesystem storage for resumes (moving off base64-in-MongoDB) — deferred, not started this session.

## Backlog / Not Started
- Resend email integration (candidate email templates) — needs user-provided `RESEND_API_KEY`.
- Full Gmail API scope/consent runtime validation (only OAuth URL generation verified so far).
- Full Google Calendar/Meet browser consent + interview scheduling end-to-end validation (only auth-URL generation verified on VPS so far).
- One-off 400 console error seen once on Jobs page during a previous nginx-performance test run — not reproduced since, low priority watch item.

---

## Feature: Candidate Self-Scheduling (added Aug 2026)

**Phase 1 (DONE, backend verified 15/15):** Recruiter opens "Schedule Interview" on a candidate → configures stage/title/type/duration/interviewers/attendees/date-range/timezone/instructions → generates a secure public scheduling link (`/schedule/interview/{token}`) → candidate (no login) picks timezone + slot → double-booking-safe booking → Google Calendar event + Meet auto-created (when a recruiter Google account is connected; degrades gracefully to book-without-event otherwise) → confirmation page with Add-to-Google-Calendar / Reschedule / Cancel. Candidate reschedule + cancel supported. Emails are QUEUED/LOGGED only (db.email_log status='queued') until an email channel key is provided.

Key modules: `scheduling_engine.py` (slot generation intersecting working hours + ATS conflicts + Google free/busy, DST-correct), `scheduling_emails.py` (queued templates), `routes_scheduling.py` (recruiter + public token endpoints). Settings in `db.settings key='scheduling'`.

**Phase 2 (DONE, tested 100%/100% — Aug 2026):** New `/scheduling` recruiter dashboard (nav item, admin/recruiter only) — stat cards (Total/Awaiting Candidate/Scheduled/Cancelled), status filter bar (all/draft/awaiting_candidate/scheduled/expired/cancelled), search by candidate/job, full requests table (candidate/job-stage/type/status/link-sent/opened/scheduled-for), row Actions dropdown (Copy link, Send/Resend link, Disable link, Regenerate link, View timeline). Backend added `display_status` (folds link_disabled/expired/scheduled/cancelled/draft/awaiting_candidate into one field) to `_enrich_request()` and a new `GET /scheduling/requests/{id}/timeline` endpoint (audit_log scoped to that interview) surfaced as a right-side Sheet with a chronological icon timeline (request created → link generated → sent → opened → booked/rescheduled/cancelled/reminder sent).

**Phase 3 (DONE, tested — Aug 2026):** New `backend/scheduling_reminders.py` background loop (`scheduling_reminder_loop`, runs every 5 min from `server.py` startup, mirrors the existing feedback `reminder_loop` pattern) sends 24h/1h reminders (configurable via `scheduling` settings `reminder_offsets_hours`) to the candidate + all interviewers for booked (`scheduling_status='scheduled'`) self-scheduled interviews. Uses its own `scheduling_reminders_sent: list[int]` field on the interview doc (deliberately separate from the feedback loop's per-interviewer `reminders_sent` dict to avoid a field-shape collision) with atomic `$addToSet` claim + rollback-on-failure, and — critically — never fires a stale larger threshold (e.g. "24h") after a smaller one (e.g. "1h") was already sent, even after scheduler downtime. Reminders are queued via the existing `scheduling_emails.queue_scheduling_email('interview_reminder', ...)` (logged to `db.email_log`, not live-delivered — same as all other scheduling emails). Working-hours/scheduling-settings admin UI (`PUT /scheduling/settings` already exists on the backend) was NOT built this round — still open, see Backlog.

**Pending external setup:** GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (+ register redirect URI) to enable real free/busy + Meet; an email channel key (Resend) to switch emails from queued to live.

**Backlog:** Scheduling settings admin UI (working hours/timezone/min notice/horizon/reminder offsets — backend `GET/PUT /api/scheduling/settings` already exists, just needs a screen, likely under Admin Panel).

---

## Feature: MULTI-TENANT SaaS conversion (June 2026 — built)

User goal: turn the single-tenant ATS into a multi-tenant SaaS — shared MongoDB with `tenant_id`
row-level isolation, a platform Super Admin panel for provisioning, slug-based tenant routing,
tenant-scoped auth, and per-tenant white-labeling.

### User decisions (confirmed in chat)
- Founding tenant = **"Context66 Data"**, slug **`context66`** → `/context66/login`. All pre-existing
  real data (388 candidates, 9 jobs, 82 interviews, 3 users) was migrated into it.
- Platform owner lives OUTSIDE all tenants (`platform_admins` collection), signs in at `/platform/login`,
  cannot read tenant data directly — only via explicit **impersonation**.
- Roles unchanged inside tenants (super_admin / admin / interview_panel / vendor) + `platform_owner` above them.
- New tenants start **completely empty** (no demo data) but get default pipeline stages + email templates.
- Branding = company name, logo upload, accent colour, tagline (login page + app sidebar).

### How isolation works (READ BEFORE TOUCHING DATA CODE)
- `backend/tenant_context.py` — ContextVar holding the current `tenant_id`, plus an `in_request` flag
  and `TenantScopeError`. `GLOBAL_COLLECTIONS = {tenants, platform_admins, password_resets, counters}`.
- `backend/tenant_db.py` — `TenantDatabase`/`TenantCollection` Motor proxy. Every read gets
  `tenant_id` merged into its filter, every insert gets it stamped, `aggregate()` gets a leading
  `$match`. **Fail-closed**: touching a tenant-owned collection during an HTTP request with no
  resolved tenant raises `TenantScopeError` → HTTP 400. Background loops (outside a request) may run
  unscoped on purpose and set the tenant per item.
- `backend/database.py` exports `raw_db` (unscoped, platform/migration only) and `db` (scoped proxy).
  Route code keeps using `from database import db` — nothing else changed in 10k lines of routes.
- Tenant resolution order: JWT `tid` (via `auth.get_current_user`) > `X-Tenant-Slug` header /
  `?tenant=` query (middleware in `server.py`) > public token records (offers/scheduling look the row
  up with `raw_db`, then `set_tenant_id(row['tenant_id'])`).
- `counters` are keyed `"<tenant_id>:candidate_seq"` / `"<tenant_id>:job_seq"` (see `utils.py`).
- `users` uniqueness is now the compound index `(tenant_id, email)` — the same person can exist in
  two workspaces. Legacy global `email_unique` index is dropped on boot.
- `migrate_tenancy.py` runs on every startup (idempotent): founding tenant → backfill `tenant_id`
  everywhere it's missing → seed the platform owner.

### API added
- `POST /api/platform/login`, `GET /api/platform/me|tenants|stats`,
  `POST /api/platform/tenants`, `PATCH/DELETE /api/platform/tenants/{id}`,
  `POST /api/platform/tenants/{id}/impersonate`
- `GET /api/tenants/by-slug/{slug}` (public, for the login page), `GET /api/tenant/me`,
  `PUT /api/tenant/branding`, `POST/DELETE /api/tenant/logo`
- `POST /api/auth/login` now REQUIRES a workspace (`tenant_slug` in body or `X-Tenant-Slug` header)
  and returns `{token, user, tenant}`. `POST /api/auth/forgot-password` also requires the workspace;
  reset records store `tenant_id` and the reset/verify endpoints re-scope from the record.

### Frontend
- `lib/tenant.js` (slug storage, `loginPath`, `careersPath`, hex→HSL `applyAccent`),
  `lib/api.js` (sends `X-Tenant-Slug`; separate `platformApi` using `ats_platform_token`),
  `components/TenantGate.jsx` (pins the slug before children mount).
- Routes: `/login` = workspace picker, `/:slug/login` = tenant login (branded),
  `/:slug/careers*` = public careers portal, `/platform/login` + `/platform` = control panel,
  `/workspace` = tenant branding page. Legacy `/careers*` redirects to `/<stored slug>/careers`.
- Public asset `<img>`/`<a>` URLs (career logo/hero/og-image/media, robots, sitemap) append
  `?tenant=<slug>` because raw image requests carry no headers.
- `AppShell` shows the tenant name/logo and, while impersonating, a "Platform view … Exit to control
  panel" banner.

### Testing status (June 2026)
- Testing agent iteration 2 + expanded pytest suite: **38/38 backend tests pass**; no cross-tenant
  leakage found on any module; platform provisioning/suspension/impersonation/branding verified;
  frontend flows for both tenants + platform panel + branding verified in iteration 2.
- Known PRE-EXISTING (not multi-tenancy) behaviours, intentionally unchanged: `/api/interviews`
  returns 80 of 82 rows because unbooked self-scheduling requests are filtered there (they appear on
  `/api/scheduling/requests`); `/api/interviews/{id}` has no GET/DELETE (405).
- User asked to self-test the final polish pass (plan selector, impersonation banner, slug-prefixed
  career links) manually.

### Backlog (multi-tenancy)
- P1: per-tenant billing/plan enforcement (limits per plan; `plan` field already exists).
- P1: tenant-aware background loops iterating tenants explicitly instead of per-row scoping.
- P2: invite-by-email flow for new workspace users (today the platform owner sets a temp password).
- P2: custom domain per tenant (career portal `custom_domain` field exists but is single-tenant logic).
- P2: platform-level audit trail of impersonation/suspension events in a dedicated collection.

### Added: platform owner self-service password change (June 2026)
- `POST /api/platform/change-password` (platform token) — verifies the current password, enforces the
  same strength rules as tenant users (8+, upper+lower, digit), and sets `self_managed: True` on the
  `platform_admins` doc.
- `migrate_tenancy.ensure_platform_owner()` now SKIPS password reconciliation when `self_managed` is
  set, so a UI-set password survives reboots and .env is only the bootstrap/rescue path (deleting the
  flag or the doc lets .env take over again).
- UI: key icon in the control-panel header opens the "Change owner password" dialog
  (`change-password-button`, `change-password-dialog`, `current-password-input`, `new-password-input`,
  `confirm-password-input`, `change-password-submit`).
- Verified by API: wrong current password → 400, weak password → 400, successful change + login with
  the new password, and a backend restart did NOT overwrite the self-managed password.
