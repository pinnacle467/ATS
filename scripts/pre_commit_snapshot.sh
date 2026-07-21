#!/usr/bin/env bash
# ============================================================================
# Sprout ATS — git pre-commit hook
#
# Runs a SYNCHRONOUS fresh dump of the live MongoDB `sprout_ats` database into
# backend/data_seed/snapshot.json and stages it, so that every commit — most
# importantly the one Emergent's "Save to GitHub" button creates — carries the
# very latest candidates, resumes (base64 in files coll), jobs, notes,
# interviews, scorecards, audit log, etc. exactly as they exist at the click.
#
# Behaviour:
#   - Skipped for merge / rebase / cherry-pick commits (GIT_MERGE_MSG_FILE etc.).
#   - Skipped when SPROUT_SKIP_SNAPSHOT_HOOK=1 (escape hatch for CI / debugging).
#   - Never fails the commit — a snapshot problem is logged loudly but does not
#     block the user's push. Corrupt DB or Mongo-down should not brick "Save to
#     GitHub".
#   - Emits a clear "[snapshot]" prefixed log block so the hook run is visible
#     in Emergent's Save-to-GitHub output.
# ============================================================================
set -u

# Bail out on merge/rebase/amend so we don't rewrite snapshots mid-history-rewrite
if [ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ] \
   || [ -f "$(git rev-parse --git-dir)/CHERRY_PICK_HEAD" ] \
   || [ -f "$(git rev-parse --git-dir)/REBASE_HEAD" ] \
   || [ -d "$(git rev-parse --git-dir)/rebase-merge" ] \
   || [ -d "$(git rev-parse --git-dir)/rebase-apply" ]; then
    echo "[snapshot] merge/rebase in progress — skipping DB snapshot"
    exit 0
fi

if [ "${SPROUT_SKIP_SNAPSHOT_HOOK:-0}" = "1" ]; then
    echo "[snapshot] SPROUT_SKIP_SNAPSHOT_HOOK=1 — skipping DB snapshot"
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
DUMP_SCRIPT="$REPO_ROOT/scripts/dump_snapshot.py"
SNAPSHOT_FILE="$REPO_ROOT/backend/data_seed/snapshot.json"

if [ ! -f "$DUMP_SCRIPT" ]; then
    echo "[snapshot] ⚠ dump_snapshot.py missing at $DUMP_SCRIPT — skipping"
    exit 0
fi

echo "[snapshot] ==================================================="
echo "[snapshot] Refreshing snapshot.json before commit ..."
START_TS=$(date +%s)

# Resolve python — prefer the venv used by the running backend, fall back to system
PYBIN="python3"
if [ -x "/root/.venv/bin/python" ]; then
    PYBIN="/root/.venv/bin/python"
fi

# Run the dump with a hard 60s timeout so a stuck Mongo can't hang "Save to GitHub"
DUMP_OUT="$(timeout 60 "$PYBIN" "$DUMP_SCRIPT" 2>&1)"
DUMP_RC=$?

if [ $DUMP_RC -ne 0 ]; then
    echo "[snapshot] ⚠ dump failed (rc=$DUMP_RC) — commit will proceed with the previous snapshot."
    echo "[snapshot]    fix ASAP: any data added since the last successful snapshot"
    echo "[snapshot]    will NOT be pushed to GitHub in this commit."
    echo "[snapshot] --- dump output ---"
    echo "$DUMP_OUT" | sed 's/^/[snapshot] /'
    echo "[snapshot] ==================================================="
    exit 0
fi

# Stage the refreshed snapshot so it goes into THIS commit
git add "$SNAPSHOT_FILE" 2>/dev/null || true

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
echo "[snapshot] ✓ fresh snapshot written in ${DURATION}s"
echo "[snapshot]   $DUMP_OUT" | sed 's/^/[snapshot] /'
echo "[snapshot] ==================================================="
exit 0
