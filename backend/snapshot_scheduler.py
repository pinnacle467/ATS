"""Background loop that dumps the live MongoDB snapshot to
backend/data_seed/snapshot.json every SNAPSHOT_INTERVAL_SEC so the current data
state survives a future chat import (where a fresh chat pulls the repo, sees
Mongo empty, and calls seed._restore_snapshot() which reads exactly this file).

This is the non-negotiable "data-durability" guarantee. It runs as a fire-and-
forget asyncio task from server.py's startup handler.
"""
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SEC = 300  # 5 minutes
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / 'scripts'
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


async def _dump_once():
    # Import inside the function so a subprocess-crash / missing-module doesn't
    # kill the whole loop at boot. Runs in a worker thread because pymongo is sync.
    from dump_snapshot import dump_snapshot  # type: ignore
    result = await asyncio.to_thread(dump_snapshot)
    logger.info('snapshot_dump ok: bytes=%s counts=%s', result['bytes'], result['counts'])


async def snapshot_loop():
    # Small initial delay so we don't race with seed._restore_snapshot on cold start
    await asyncio.sleep(60)
    while True:
        try:
            await _dump_once()
        except Exception:
            logger.exception('snapshot loop iteration failed')
        await asyncio.sleep(SNAPSHOT_INTERVAL_SEC)
