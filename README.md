# Pinnacle ATS

An opinionated, batteries-included Applicant Tracking System built with **FastAPI**, **React**, and **MongoDB**. Designed for mid-market recruiting teams that want an ATS they can self-host and extend.

![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20MongoDB-16A34A) ![License](https://img.shields.io/badge/license-Proprietary-blue)

---

## Features

### Pipeline & workflow
- **Drag-and-drop Kanban** per job — Applied → Screening → Interview 1/2/3 → Offer → Hired / Rejected
- **Grid view** toggle for compact overviews of long pipelines
- **Sort by AI fit score** so top matches float to the top of every stage
- **Quick-filter search** across name / email / title / company / skill / tag
- **Rejection dialog** with reason categories (Not Fit / No Response / Offer Declined / Out of Budget)

### AI-powered
- Resume parsing (PDF / DOCX) and structured extraction
- **AI fit score** per (candidate × job) with a color-coded 0–100 badge (green/amber/red) + AI summary tooltip
- LLM-based reply parsing on inbound email threads

### Interview management
- Google Calendar + Google Meet integration (OAuth)
- Availability windows per interviewer
- Interview kits with structured scorecards
- **3-round feedback tab** per candidate — free-text notes, date, interviewer, duration, and a **Recommend / Neutral / Reject verdict chip** that also appears on Kanban cards

### Roles & auth
- **super_admin / admin / recruiter / interviewer / vendor** — every route respects the role hierarchy
- JWT session auth, invitation flow, password reset, per-job team access
- Vendor + interviewer users only see candidates on jobs they're added to

### Comms
- Outbound email via **Resend** (templates + variable substitution)
- Inbound reply parsing via a mail webhook
- Per-candidate activity timeline + admin change log with full diff audit

### Career portal
- Public jobs board rendered from the same DB
- Application form with file upload, custom questions, and instant fit-score preview

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · Motor (async Mongo) · Pydantic · Uvicorn |
| Frontend | React 18 · React Router 7 · shadcn/ui · Tailwind CSS · dnd-kit |
| Database | MongoDB 7 |
| AI / LLM | Emergent Integrations (OpenAI · Anthropic · Gemini) |
| Email | Resend |
| Auth | Custom JWT + Google OAuth (for Calendar/Meet) |
| Deploy | systemd + Nginx (bare-metal / VPS) or Emergent managed |

---

## Quick start

### Option 1 — one-shot install on a fresh Ubuntu 22.04 VPS

```bash
curl -fsSL https://raw.githubusercontent.com/pinnacle467/ATS/main/deploy/install.sh | sudo bash
```

Full details, env-var overrides, HTTPS, and update flow in [`deploy/README.md`](deploy/README.md).

### Option 2 — local development

Prerequisites: Python 3.11+, Node 20+, yarn, and a running MongoDB.

```bash
git clone https://github.com/pinnacle467/ATS.git
cd ATS

# ---- Backend ----
python3.11 -m venv .venv
.venv/bin/pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r backend/requirements.txt

cat > backend/.env <<'EOF'
MONGO_URL=mongodb://localhost:27017
DB_NAME=sprout_ats
CORS_ORIGINS=*
JWT_SECRET=change-me
APP_BASE_URL=http://localhost:3000
EMERGENT_LLM_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
RESEND_API_KEY=
EOF

.venv/bin/uvicorn server:app --reload --host 0.0.0.0 --port 8001 --app-dir backend

# ---- Frontend (in a second terminal) ----
cd frontend
echo 'REACT_APP_BACKEND_URL=http://localhost:8001' > .env
yarn install
yarn start
```

Open http://localhost:3000 and sign in with the seeded admin:

- **Email:** `admin@ats.com`
- **Password:** `Admin@123`

The DB is auto-seeded from `backend/data_seed/snapshot.json` on first launch when empty.

### Option 3 — restore a MongoDB dump

If you have a mongodump you want to load:

```bash
mongorestore --drop --nsFrom='sprout_ats.*' --nsTo='sprout_ats.*' /path/to/mongodump/
```

---

## Repository layout

```
.
├── backend/               FastAPI app (server.py, routes_*.py, seed.py)
│   ├── data_seed/         Bootstrap data used on first empty-DB launch
│   ├── requirements.txt
│   └── .env               (git-ignored)
├── frontend/              React app (Create React App + shadcn/ui)
│   ├── src/
│   │   ├── pages/         Route components
│   │   ├── components/    Reusable UI (KanbanBoard, RoundFeedbackSection, …)
│   │   ├── context/       AuthContext + hooks
│   │   └── lib/           api client, roles helpers
│   └── .env               (git-ignored)
├── deploy/
│   ├── install.sh         One-shot Ubuntu 22.04 VPS installer
│   ├── deploy.sh          In-place git-pull + rebuild + restart
│   └── README.md          Deploy docs, HTTPS, override vars
├── scripts/               Utility scripts (import from remote build, …)
└── backups/               Optional mongodump snapshots (see .gitignore)
```

---

## Environment variables

### `backend/.env`

| Var | Required | Example / Purpose |
|---|---|---|
| `MONGO_URL` | ✅ | `mongodb://localhost:27017` |
| `DB_NAME` | ✅ | `sprout_ats` |
| `APP_BASE_URL` | ✅ | Public URL used to build OAuth redirect + email links |
| `CORS_ORIGINS` | ✅ | `*` for dev, comma-list for prod |
| `JWT_SECRET` | ✅ | 32+ random chars — regenerate per env |
| `XAI_API_KEY` | ✅ | Powers all LLM features (resume parsing, fit scoring, reply parsing, career-portal preview) via Grok 4.3 |
| `GROK_MODEL` | optional | Defaults to `grok-4.3`. Override if xAI ships a newer model |
| `EMERGENT_LLM_KEY` | optional | Legacy — kept for future rollback. Not called on the hot path anymore |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | optional | Enables Google Calendar + Meet |
| `RESEND_API_KEY` | optional | Enables outbound email |
| `SENDER_EMAIL` | optional | e.g. `Pinnacle ATS <hi@yourdomain.com>` |

### `frontend/.env`

| Var | Required | Example |
|---|---|---|
| `REACT_APP_BACKEND_URL` | ✅ | Same origin as `APP_BASE_URL` (Nginx routes `/api` → backend) |
| `WDS_SOCKET_PORT` | dev only | `443` when behind HTTPS proxy |

---

## Deploy update flow

After committing changes to `main` and pushing to GitHub:

```bash
# on the server
sudo /opt/ats/deploy/deploy.sh
```

That runs `git pull`, reinstalls Python + Node deps, rebuilds the frontend, and restarts `ats-backend` + reloads Nginx.

---

## Third-party integrations

| Provider | Purpose | Where to plug in |
|---|---|---|
| **Emergent Integrations** | LLM calls across OpenAI · Anthropic · Gemini through one key | `EMERGENT_LLM_KEY` in `backend/.env` |
| **Google Cloud OAuth** | Calendar events + Meet auto-links | `GOOGLE_CLIENT_ID/SECRET` in `backend/.env`; add redirect `${APP_BASE_URL}/api/oauth/calendar/callback` in the Google Cloud Console |
| **Resend** | Transactional email | `RESEND_API_KEY` in `backend/.env`; verify sender domain in the Resend dashboard |

---

## Default admin

On first empty-DB launch, `backend/seed.py` creates:

- `admin@ats.com` / `Admin@123` — super_admin

**Change this password immediately** in Admin → Users after logging in.

---

## License

Proprietary — © Pinnacle. All rights reserved.
