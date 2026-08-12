#!/usr/bin/env bash
# =============================================================================
# Pinnacle ATS — bulletproof redeploy script (idempotent, run as often as you like)
#
# USAGE:
#   sudo bash /opt/ats/deploy/deploy.sh                 # deploy latest code (safe, keeps live data)
#   sudo RESTORE_DATA=1 bash /opt/ats/deploy/deploy.sh  # ALSO force-overwrite the DB from the
#                                                        # repo's backend/data_seed/snapshot.json
#                                                        # (the latest data pushed from Emergent)
#
# What it always does (in order):
#   1. Configure git safe.directory (survives chown to `ats`)
#   2. Stop ats-backend (Mongo won't be written to during install)
#   3. git fetch + hard-reset to origin/main (blows away local drift)
#   4. Repair file ownership -> ats:ats
#   5. Reinstall Python backend deps (3-step workaround for emergentintegrations+litellm)
#   6. Rebuild frontend (yarn install --frozen-lockfile && yarn build)
#   7. [Optional, if RESTORE_DATA=1] scripts/restore_snapshot.py --yes — full overwrite of every
#      collection from backend/data_seed/snapshot.json (the snapshot just pulled from GitHub)
#   8. daemon-reload, restart ats-backend, nginx -t + reload
#   9. Print live status + candidate/job/file counts
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ats}"
APP_USER="${APP_USER:-ats}"
BRANCH="${BRANCH:-main}"
DB_NAME_VAR="${DB_NAME_VAR:-sprout_ats}"

log()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m⚠ %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run with sudo:  sudo bash $0"
[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR does not look like a git checkout — run deploy/install.sh first"

# 1. Git safe.directory (works whether the repo is owned by root or ats)
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
sudo -u "$APP_USER" -H git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# 2. Stop backend so Mongo isn't being written to during the deploy
systemctl stop ats-backend 2>/dev/null || true

# 3. Fetch + hard reset to origin/BRANCH
log "Fetching latest from origin/$BRANCH …"
git -C "$APP_DIR" fetch --all --tags --prune
git -C "$APP_DIR" reset --hard "origin/$BRANCH"
CURRENT_SHA="$(git -C "$APP_DIR" rev-parse --short HEAD)"
log "At commit $CURRENT_SHA"

# 4. Repair ownership
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 4b. Self-heal required backend/.env keys that may not exist yet on this VPS
#     (e.g. CREDENTIALS_ENCRYPTION_KEY, added when Job Board integrations shipped).
#     Never overwrites an existing value — only appends if the key is fully absent.
ENV_FILE="$APP_DIR/backend/.env"
if [[ -f "$ENV_FILE" ]] && ! grep -q '^CREDENTIALS_ENCRYPTION_KEY=' "$ENV_FILE"; then
  warn "CREDENTIALS_ENCRYPTION_KEY missing from backend/.env — generating one now (required since Job Board integrations)"
  NEW_CRED_KEY="$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")"
  echo "CREDENTIALS_ENCRYPTION_KEY=${NEW_CRED_KEY}" >> "$ENV_FILE"
  chown "$APP_USER:$APP_USER" "$ENV_FILE"
fi

# 5. Backend deps — 3-step install to work around litellm/emergentintegrations pip resolver conflict
log "Refreshing Python backend deps…"
PYBIN="$(command -v python3.11 || command -v python3.12 || command -v python3)"
sudo -u "$APP_USER" -H bash -lc "
  set -e
  cd '$APP_DIR'
  [[ -d .venv ]] || $PYBIN -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip wheel
  .venv/bin/pip install --quiet --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ 'emergentintegrations==0.2.0'
  grep -vE '^(emergentintegrations|litellm[[:space:]@])' backend/requirements.txt > /tmp/ats-reqs-noconflict.txt
  .venv/bin/pip install --quiet -r /tmp/ats-reqs-noconflict.txt
  rm -f /tmp/ats-reqs-noconflict.txt
  .venv/bin/pip install --quiet --no-deps 'https://customer-assets.emergentagent.com/internal-asset/library/litellm-1.80.0-py3-none-any.whl'
"

# 6. Frontend build
log "Rebuilding frontend…"
sudo -u "$APP_USER" -H bash -lc "
  set -e
  cd '$APP_DIR/frontend'
  yarn install --frozen-lockfile --silent
  yarn build
"

# 7. Optional data restore — full overwrite from the snapshot just pulled from GitHub
if [[ "${RESTORE_DATA:-0}" == "1" ]]; then
  log "Restoring database from backend/data_seed/snapshot.json (full overwrite)…"
  sudo -u "$APP_USER" -H bash -lc "
    cd '$APP_DIR' && .venv/bin/python scripts/restore_snapshot.py --yes
  "
else
  log "Skipping data restore (set RESTORE_DATA=1 to force-sync from the latest snapshot.json)"
fi

# 8. Restart services
log "Restarting ats-backend + reloading Nginx…"
systemctl daemon-reload
systemctl restart ats-backend.service
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx
fi

# 9. Summary
sleep 3
BACKEND_STATUS=$(systemctl is-active ats-backend.service || true)
MONGO_STATUS=$(systemctl is-active mongod || true)
NGINX_STATUS=$(systemctl is-active nginx || true)

CAND_COUNT=$(mongosh --quiet "$DB_NAME_VAR" --eval "print(db.candidates.countDocuments())" 2>/dev/null || echo "?")
JOB_COUNT=$(mongosh --quiet "$DB_NAME_VAR" --eval "print(db.jobs.countDocuments())" 2>/dev/null || echo "?")
FILE_COUNT=$(mongosh --quiet "$DB_NAME_VAR" --eval "print(db.files.countDocuments())" 2>/dev/null || echo "?")

cat <<EOF

============================================================
 ✅  Deploy complete
------------------------------------------------------------
 Commit          : $CURRENT_SHA
 Backend         : $BACKEND_STATUS
 MongoDB         : $MONGO_STATUS
 Nginx           : $NGINX_STATUS
 Live counts     : candidates=$CAND_COUNT  jobs=$JOB_COUNT  files=$FILE_COUNT
 Live logs       : journalctl -u ats-backend -f
============================================================
EOF
