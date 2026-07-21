"""Snapshot durability plumbing for the ATS.

The old design used a periodic background loop that dumped MongoDB into
`backend/data_seed/snapshot.json` every 5 minutes. That created a race window:
if the user clicked Emergent's "Save to GitHub" button between two ticks of the
loop, the pushed snapshot lagged the live DB by up to 5 minutes and any data
added in that window was lost on the next chat import.

New design (this module):
  * The periodic loop is gone.
  * A git `pre-commit` hook (scripts/pre_commit_snapshot.sh) runs the same
    `dump_snapshot.py` synchronously right before ANY commit — including the
    one Emergent's "Save to GitHub" produces — and stages the freshly-written
    snapshot.json into that commit. Every push therefore contains data as of
    the moment of the click.
  * On backend startup this module installs / refreshes that hook idempotently
    so a freshly-imported chat is protected from the first request onward.

If you're wondering why the hook lives in scripts/ but is *installed* here at
backend boot: `.git/hooks/*` is intentionally not tracked by git, so the hook
would not survive a fresh clone unless something re-installs it. Backend
startup is the earliest reliable point at which we know the working tree is
present, so we do it there.
"""
import logging
import os
import shutil
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOK_SRC = _REPO_ROOT / 'scripts' / 'pre_commit_snapshot.sh'
_GIT_DIR = _REPO_ROOT / '.git'
_HOOKS_DIR = _GIT_DIR / 'hooks'
_HOOK_DST = _HOOKS_DIR / 'pre-commit'


def install_pre_commit_hook() -> dict:
    """Copy scripts/pre_commit_snapshot.sh into .git/hooks/pre-commit and make
    it executable. Idempotent: safe to run on every backend boot.

    Returns a small dict describing what happened, suitable for logging.
    """
    result = {'installed': False, 'reason': None, 'path': str(_HOOK_DST)}

    if not _GIT_DIR.exists():
        result['reason'] = 'no .git directory — not a git repo, hook not installed'
        return result

    if not _HOOK_SRC.exists():
        result['reason'] = f'source hook missing at {_HOOK_SRC}'
        return result

    _HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    src_bytes = _HOOK_SRC.read_bytes()
    needs_write = True
    if _HOOK_DST.exists():
        try:
            if _HOOK_DST.read_bytes() == src_bytes:
                needs_write = False
        except OSError:
            needs_write = True

    if needs_write:
        # Preserve an existing hook (if it's not ours) so we don't clobber
        # something the user or another tool put there.
        if _HOOK_DST.exists() and b'Sprout ATS' not in _HOOK_DST.read_bytes():
            backup = _HOOK_DST.with_suffix('.pre-sprout-backup')
            try:
                shutil.copy2(_HOOK_DST, backup)
                logger.warning('backed up existing pre-commit hook to %s', backup)
            except OSError:
                logger.exception('could not back up existing pre-commit hook')
        _HOOK_DST.write_bytes(src_bytes)

    # Always ensure it's executable — chmod is cheap and previous chats may
    # have left it non-executable.
    current_mode = _HOOK_DST.stat().st_mode
    _HOOK_DST.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result['installed'] = True
    result['wrote_file'] = needs_write
    return result


# ---------------------------------------------------------------------------
# Back-compat shim: older code may still `from snapshot_scheduler import
# snapshot_loop`. We keep the name but make it a no-op so we can be sure the
# periodic loop is truly gone. Delete the import site in server.py once you're
# happy with the new hook-based design.
# ---------------------------------------------------------------------------

async def snapshot_loop():  # pragma: no cover — deliberate no-op
    """Deprecated. Periodic snapshotting is replaced by a git pre-commit hook
    (see install_pre_commit_hook above). This function is kept only to avoid
    an ImportError from stale callers and returns immediately."""
    logger.info(
        'snapshot_loop() is a deprecated no-op — snapshots now run '
        'synchronously via the .git/hooks/pre-commit hook.'
    )
    return


# Explicit environment override for tests / CI — the hook itself reads
# SPROUT_SKIP_SNAPSHOT_HOOK=1 to skip execution. Nothing to do here.
_ = os.environ  # touch to satisfy linters that flag the unused import above
