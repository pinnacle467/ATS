#!/usr/bin/env bash
# =============================================================================
# Pinnacle ATS — in-place update / redeploy script
#
# Run on the server (as root or via sudo) after you have committed + pushed
# changes to the main branch on GitHub.
#
#   sudo /opt/ats/deploy/deploy.sh
#
# It does:
#   1. git pull (fast-forward or hard reset if you set FORCE=1)
#   2. reinstall Python backend deps into the venv
#   3. reinstall Node deps and rebuild the frontend
#   4. restart the ats-backend systemd service and reload Nginx
#
# Environment overrides (same defaults as install.sh):
#   APP_DIR    (default /opt/ats)
#   APP_USER   (default ats)
#   BRANCH     (default main)
#   FORCE      (set to 1 to hard-reset local changes)
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ats}"
APP_USER="${APP_USER:-ats}"
BRANCH="${BRANCH:-main}"
FORCE="${FORCE:-0}"

log()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run with sudo:  sudo bash $0"
[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR does not look like a git checkout — run deploy/install.sh first"

# ---------- 1. Pull latest ---------------------------------------------------
log "Pulling latest from origin/$BRANCH …"
if [[ "$FORCE" == "1" ]]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch --all
  sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch --all
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
fi

CURRENT_SHA="$(git -C "$APP_DIR" rev-parse --short HEAD)"
log "At commit $CURRENT_SHA"

# ---------- 2. Backend deps --------------------------------------------------
log "Refreshing Python backend deps…"
PYBIN="$(command -v python3.11 || command -v python3.12 || command -v python3)"
sudo -u "$APP_USER" bash -c "
  set -e
  cd '$APP_DIR'
  [[ -d .venv ]] || $PYBIN -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip wheel
  .venv/bin/pip install --quiet --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r backend/requirements.txt
"

# ---------- 3. Frontend build ------------------------------------------------
log "Rebuilding frontend…"
sudo -u "$APP_USER" bash -c "
  set -e
  cd '$APP_DIR/frontend'
  yarn install --frozen-lockfile --silent
  yarn build
"

# ---------- 4. Restart services ---------------------------------------------
log "Restarting ats-backend + reloading Nginx…"
systemctl daemon-reload
systemctl restart ats-backend.service
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx
fi

sleep 2
BACKEND_STATUS=$(systemctl is-active ats-backend.service || true)

cat <<EOF

============================================================
 ✅  Redeploy complete
 Commit          : $CURRENT_SHA
 Backend status  : $BACKEND_STATUS
 Live logs       : journalctl -u ats-backend -f
============================================================
EOF
