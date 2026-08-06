#!/usr/bin/env bash
# =============================================================================
# Pinnacle ATS — one-shot installer for a fresh Ubuntu 22.04 VPS
# Repo: https://github.com/pinnacle467/ATS
#
# USAGE (paste this on your VPS as root):
#   curl -fsSL https://raw.githubusercontent.com/pinnacle467/ATS/main/deploy/install.sh | sudo bash
#
# Or download first (so you can tweak the defaults below), then run:
#   curl -fsSL https://raw.githubusercontent.com/pinnacle467/ATS/main/deploy/install.sh -o install.sh
#   sudo bash install.sh
#
# Requirements: Ubuntu 22.04+ on a VPS/dedicated server with root/sudo access.
# WILL NOT WORK on Bluehost SHARED hosting (no daemons allowed).
# =============================================================================
set -euo pipefail

# ---------- Config (override with env vars before running) -------------------
APP_DIR="${APP_DIR:-/opt/ats}"
APP_USER="${APP_USER:-ats}"
REPO_URL="${REPO_URL:-https://github.com/pinnacle467/ATS.git}"
BRANCH="${BRANCH:-main}"
PUBLIC_URL="${PUBLIC_URL:-http://129.121.126.61}"      # change to https://yourdomain.com if you have DNS + TLS
BIND_HOST="${BIND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_NAME_VAR="${DB_NAME_VAR:-sprout_ats}"
JWT_SECRET_VAL="${JWT_SECRET_VAL:-$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)}"
EMERGENT_LLM_KEY_VAL="${EMERGENT_LLM_KEY_VAL:-}"        # paste your Emergent LLM key here (or export before running)
GOOGLE_CLIENT_ID_VAL="${GOOGLE_CLIENT_ID_VAL:-}"        # optional — for Google Calendar/Meet
GOOGLE_CLIENT_SECRET_VAL="${GOOGLE_CLIENT_SECRET_VAL:-}"
RESEND_API_KEY_VAL="${RESEND_API_KEY_VAL:-}"            # optional — for outbound emails

log()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m⚠ %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root:  sudo bash install.sh"
grep -qi 'ubuntu' /etc/os-release || warn "Tested on Ubuntu 22.04 — proceed at your own risk on other distros"

export DEBIAN_FRONTEND=noninteractive

# ---------- 1. System packages ------------------------------------------------
log "Installing system packages (git, python, nginx, curl, build-essential)…"
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg lsb-release git build-essential \
  nginx ufw software-properties-common

# Pick the newest Python 3.11+ available (Ubuntu 22.04 → 3.11, Ubuntu 24.04 → 3.12)
if command -v python3.11 >/dev/null 2>&1; then
  PYBIN=python3.11
elif command -v python3.12 >/dev/null 2>&1; then
  PYBIN=python3.12
else
  # Try installing 3.11 via deadsnakes PPA (Jammy). On Noble the default python3 is already 3.12.
  add-apt-repository -y ppa:deadsnakes/ppa || true
  apt-get update -y || true
  apt-get install -y python3.11 python3.11-venv python3.11-dev || apt-get install -y python3 python3-venv python3-dev
  PYBIN=$(command -v python3.11 || command -v python3.12 || command -v python3)
fi
# Ensure the venv module for the picked python is installed
PYVER=$("$PYBIN" -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')")
apt-get install -y "python${PYVER}-venv" "python${PYVER}-dev" || true
log "Using Python: $PYBIN ($PYVER)"

# ---------- 2. MongoDB (auto-picks 7 for Jammy, 8 for Noble) -----------------
if ! command -v mongod >/dev/null 2>&1; then
  UBUNTU_CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  case "$UBUNTU_CODENAME" in
    noble)  MONGO_VERSION=8.0 ;;
    jammy)  MONGO_VERSION=7.0 ;;
    focal)  MONGO_VERSION=7.0 ;;
    *)      warn "Unknown Ubuntu codename '$UBUNTU_CODENAME' — defaulting to MongoDB 7.0 on jammy repo"
            UBUNTU_CODENAME=jammy
            MONGO_VERSION=7.0 ;;
  esac
  log "Installing MongoDB $MONGO_VERSION for Ubuntu $UBUNTU_CODENAME…"
  # Clean any stale mongo apt files from previous failed runs
  rm -f /etc/apt/sources.list.d/mongodb-org-*.list /usr/share/keyrings/mongodb-server-*.gpg

  curl -fsSL "https://pgp.mongodb.com/server-${MONGO_VERSION}.asc" \
    | gpg -o "/usr/share/keyrings/mongodb-server-${MONGO_VERSION}.gpg" --dearmor --yes
  echo "deb [signed-by=/usr/share/keyrings/mongodb-server-${MONGO_VERSION}.gpg] https://repo.mongodb.org/apt/ubuntu ${UBUNTU_CODENAME}/mongodb-org/${MONGO_VERSION} multiverse" \
    > "/etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list"
  apt-get update -y
  apt-get install -y mongodb-org
else
  log "MongoDB already installed — skipping"
fi
systemctl enable --now mongod

# ---------- 3. Node 20 + Yarn -------------------------------------------------
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v)" != v20* ]]; then
  log "Installing Node.js 20…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
if ! command -v yarn >/dev/null 2>&1; then
  npm install -g yarn
fi

# ---------- 4. App user + directories -----------------------------------------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Creating system user '$APP_USER'…"
  useradd --system --create-home --home-dir "/home/$APP_USER" --shell /bin/bash "$APP_USER"
fi

log "Cloning repo into $APP_DIR…"
# Tell git the repo is trustworthy regardless of ownership (installer may run as root
# on a repo cloned/chowned by a previous run)
git config --global --add safe.directory "$APP_DIR" || true
if [[ ! -d "$APP_DIR/.git" ]]; then
  mkdir -p "$APP_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --all
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
# Also mark the dir safe for the app user so subsequent deploy.sh runs don't trip
sudo -u "$APP_USER" git config --global --add safe.directory "$APP_DIR" || true

# ---------- 5. Backend .env ---------------------------------------------------
log "Writing backend/.env…"
cat > "$APP_DIR/backend/.env" <<EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=${DB_NAME_VAR}
CORS_ORIGINS=*
JWT_SECRET=${JWT_SECRET_VAL}
APP_BASE_URL=${PUBLIC_URL}
EMERGENT_LLM_KEY=${EMERGENT_LLM_KEY_VAL}
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID_VAL}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET_VAL}
RESEND_API_KEY=${RESEND_API_KEY_VAL}
SENDER_EMAIL=Pinnacle ATS <onboarding@resend.dev>
SENDER_REPLY_TO=
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/backend/.env"
chmod 600 "$APP_DIR/backend/.env"

# ---------- 6. Frontend .env --------------------------------------------------
log "Writing frontend/.env…"
cat > "$APP_DIR/frontend/.env" <<EOF
REACT_APP_BACKEND_URL=${PUBLIC_URL}
WDS_SOCKET_PORT=443
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/frontend/.env"

# ---------- 7. Backend virtualenv + Python deps -------------------------------
log "Creating Python virtualenv + installing backend deps…"
# NOTE: emergentintegrations 0.2.0 and the URL-pinned litellm wheel in
# requirements.txt cause pip's resolver to conflict when installed in one shot.
# Three-step workaround (verified working):
#   1. install emergentintegrations first (pulls a compatible litellm)
#   2. install the rest of requirements.txt with those two lines stripped out
#   3. force-install the exact litellm wheel URL with --no-deps
sudo -u "$APP_USER" bash -c "
  set -e
  cd '$APP_DIR'
  $PYBIN -m venv .venv
  .venv/bin/pip install --upgrade pip wheel

  .venv/bin/pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ 'emergentintegrations==0.2.0'

  grep -vE '^(emergentintegrations|litellm[[:space:]@])' backend/requirements.txt > /tmp/ats-reqs-noconflict.txt
  .venv/bin/pip install -r /tmp/ats-reqs-noconflict.txt
  rm -f /tmp/ats-reqs-noconflict.txt

  .venv/bin/pip install --no-deps 'https://customer-assets.emergentagent.com/internal-asset/library/litellm-1.80.0-py3-none-any.whl'
"

# ---------- 8. Frontend build -------------------------------------------------
log "Installing frontend deps + building production bundle…"
sudo -u "$APP_USER" bash -c "
  cd '$APP_DIR/frontend' &&
  yarn install --frozen-lockfile &&
  yarn build
"

# ---------- 9. Restore MongoDB dump (if bundled) ------------------------------
DUMP_DIR="$APP_DIR/backups/pre-remote-sync-20260722-231124/mongodump"
if [[ -d "$DUMP_DIR/$DB_NAME_VAR" ]]; then
  log "Restoring MongoDB dump from $DUMP_DIR (drops existing $DB_NAME_VAR)…"
  mongorestore --drop --nsFrom="${DB_NAME_VAR}.*" --nsTo="${DB_NAME_VAR}.*" "$DUMP_DIR"
else
  warn "No bundled mongodump found — backend will bootstrap from backend/data_seed/snapshot.json on first launch if the DB is empty."
fi

# ---------- 10. systemd unit for the backend ---------------------------------
log "Installing systemd service ats-backend.service…"
cat > /etc/systemd/system/ats-backend.service <<EOF
[Unit]
Description=Pinnacle ATS FastAPI backend
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn server:app --host ${BIND_HOST} --port ${BACKEND_PORT} --proxy-headers
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ats-backend.service

# ---------- 11. Nginx reverse proxy + static frontend -------------------------
log "Configuring Nginx…"
SERVER_NAME_HOST="$(echo "$PUBLIC_URL" | sed -E 's~https?://~~; s~/.*~~')"
cat > /etc/nginx/sites-available/ats <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${SERVER_NAME_HOST} _;
    client_max_body_size 50m;

    root ${APP_DIR}/frontend/build;
    index index.html;

    # API + WebSocket → FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }

    # React Router — everything else falls back to index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/ats /etc/nginx/sites-enabled/ats
nginx -t
systemctl reload nginx

# ---------- 12. Firewall (ufw) ------------------------------------------------
if command -v ufw >/dev/null 2>&1; then
  log "Opening ports 22, 80, 443 in ufw (idempotent)…"
  ufw --force enable || true
  ufw allow 22/tcp || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
fi

# ---------- 13. Final summary -------------------------------------------------
sleep 2
BACKEND_STATUS=$(systemctl is-active ats-backend.service || true)
MONGO_STATUS=$(systemctl is-active mongod || true)
NGINX_STATUS=$(systemctl is-active nginx || true)

cat <<EOF

============================================================
 ✅  Pinnacle ATS installer finished
------------------------------------------------------------
 App URL         : ${PUBLIC_URL}
 App directory   : ${APP_DIR}
 App user        : ${APP_USER}
 Backend service : ats-backend.service   [$BACKEND_STATUS]
 MongoDB         : mongod                [$MONGO_STATUS]
 Nginx           : nginx                 [$NGINX_STATUS]

 Default admin login (from seed) :
   email    : admin@ats.com
   password : Admin@123

 Handy commands:
   systemctl status ats-backend
   journalctl -u ats-backend -f
   sudo -u ${APP_USER} bash -c 'cd ${APP_DIR} && git pull && cd frontend && yarn build'
   systemctl restart ats-backend
   systemctl reload nginx

 Next steps you MAY still need to do:
   1. If you have a domain, point DNS to this server, then update
      APP_BASE_URL / REACT_APP_BACKEND_URL in the two .env files to
      https://yourdomain.com and rebuild the frontend + restart backend.
   2. Add HTTPS:   apt install certbot python3-certbot-nginx
                   certbot --nginx -d yourdomain.com
   3. Add the Google OAuth redirect URI in your Google Cloud console:
      ${PUBLIC_URL}/api/oauth/calendar/callback
   4. Paste your EMERGENT_LLM_KEY / GOOGLE / RESEND keys into
      ${APP_DIR}/backend/.env  then:
         systemctl restart ats-backend
============================================================
EOF
