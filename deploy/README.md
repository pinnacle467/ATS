# Pinnacle ATS — VPS installer

One-shot installer for a **fresh Ubuntu 22.04 VPS** with root/sudo access.
Not compatible with shared hosting (needs to run MongoDB + a Python daemon + Nginx).

## 🚀 One-shot install (paste on your VPS as root)

```bash
curl -fsSL https://raw.githubusercontent.com/pinnacle467/ATS/main/deploy/install.sh | sudo bash
```

That single command will:

1. Install **git, Python 3.11, Node 20, yarn, MongoDB 7, Nginx, ufw**
2. Create a system user `ats` and clone the repo to `/opt/ats`
3. Write sensible `backend/.env` + `frontend/.env` (with a random JWT secret)
4. `pip install` the FastAPI backend into a venv, `yarn build` the React frontend
5. Restore the bundled MongoDB dump if present (`backups/pre-remote-sync-*/mongodump/`)
6. Install a **systemd unit** `ats-backend.service` (auto-start, auto-restart)
7. Configure **Nginx** to serve the built frontend on port 80 and reverse-proxy `/api/*` to the backend on `127.0.0.1:8001`
8. Open ports 22 / 80 / 443 in `ufw`
9. Print a summary with service statuses and next steps

## 🎛 Override defaults with env vars

```bash
# Example — install with a real domain and your Emergent LLM key
curl -fsSL https://raw.githubusercontent.com/pinnacle467/ATS/main/deploy/install.sh -o install.sh

sudo PUBLIC_URL="https://ats.yourdomain.com" \
     EMERGENT_LLM_KEY_VAL="sk-emergent-xxxxxxxx" \
     GOOGLE_CLIENT_ID_VAL="45396856275-....apps.googleusercontent.com" \
     GOOGLE_CLIENT_SECRET_VAL="GOCSPX-...." \
     bash install.sh
```

All overridable vars (see top of `install.sh`):

| Variable | Default | Purpose |
|---|---|---|
| `APP_DIR` | `/opt/ats` | Where the repo is cloned |
| `APP_USER` | `ats` | System user the app runs as |
| `PUBLIC_URL` | `http://129.121.126.61` | Base URL used by CORS, `APP_BASE_URL`, `REACT_APP_BACKEND_URL` |
| `BRANCH` | `main` | Git branch to check out |
| `BACKEND_PORT` | `8001` | Uvicorn port (Nginx proxies `/api/*` to this) |
| `DB_NAME_VAR` | `sprout_ats` | Mongo DB name |
| `JWT_SECRET_VAL` | random 40-char | Set explicitly to keep sessions across redeploys |
| `EMERGENT_LLM_KEY_VAL` | (empty) | Enables AI features |
| `GOOGLE_CLIENT_ID_VAL` / `GOOGLE_CLIENT_SECRET_VAL` | (empty) | Enables Calendar/Meet |
| `RESEND_API_KEY_VAL` | (empty) | Enables outbound emails |

## 🔒 After install — add HTTPS

Google OAuth **requires** HTTPS. Once DNS points at your server:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ats.yourdomain.com
# Then re-run the installer with PUBLIC_URL=https://ats.yourdomain.com
# to rebuild the frontend with the correct backend URL.
```

Also add this to your Google Cloud OAuth client:
- **Authorized JavaScript origin**: `https://ats.yourdomain.com`
- **Authorized redirect URI**: `https://ats.yourdomain.com/api/oauth/calendar/callback`

## 🔄 Update flow (after code changes)

```bash
sudo -u ats bash -c '
  cd /opt/ats &&
  git pull &&
  .venv/bin/pip install -r backend/requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ &&
  cd frontend && yarn install --frozen-lockfile && yarn build
'
sudo systemctl restart ats-backend
sudo systemctl reload nginx
```

## 🩺 Troubleshoot

```bash
systemctl status ats-backend       # is the backend up?
journalctl -u ats-backend -f       # live backend logs
systemctl status mongod            # is Mongo up?
sudo nginx -t && systemctl reload nginx
sudo -u ats mongosh sprout_ats --eval 'db.candidates.countDocuments()'
```

## 👤 Default admin login

Seeded by `backend/seed.py` (only on first empty-DB launch):

- **Email:** `admin@ats.com`
- **Password:** `Admin@123`

Change it immediately in Admin → Users after logging in.
