# Syncing data from Emergent preview to your VPS

Every commit made from the Emergent preview (including every "Save to
GitHub") refreshes `backend/data_seed/snapshot.json` with a full dump of the
live database (candidates, jobs, tenants, offers, AI settings, etc. — see
`scripts/dump_snapshot.py:COLLECTIONS` for the exact list).

Your VPS database only gets seeded from that file automatically on a
**completely fresh install** (empty `users` collection). Once your VPS has
run once, pulling new code will NOT update its data on its own — you need to
explicitly re-sync.

## To re-sync your VPS with the latest Emergent data (repeatable, run anytime)

**If your VPS was set up with `deploy/deploy.sh` (see `deploy/README.md`), just run:**

```bash
sudo RESTORE_DATA=1 bash /opt/ats/deploy/deploy.sh
```

This pulls the latest code AND force-overwrites the database from the latest `snapshot.json` in
one command, then restarts everything for you.

**Manual / other deployments:**

```bash
cd /path/to/your/app        # your VPS checkout of this repo
git pull

# Preview what would change (safe, read-only, no --yes flag):
python scripts/restore_snapshot.py

# Actually overwrite the VPS database with the snapshot from GitHub:
python scripts/restore_snapshot.py --yes

# Restart the app so it re-creates indexes on the fresh data
# (adjust to however you run this — docker compose, pm2, supervisor, etc.)
docker compose restart backend    # or: pm2 restart ats-backend / etc.
```

## Important

- This is a **full overwrite**: every collection listed in
  `scripts/dump_snapshot.py:COLLECTIONS` is cleared and replaced with what's
  in `snapshot.json`. Anything created directly on the VPS (not in Emergent)
  will be lost. Run the no-flag dry-run first if you're unsure.
- The script reads `MONGO_URL` / `DB_NAME` from `backend/.env` on the VPS
  itself, so it always targets your VPS's own database — never Emergent's.
- Do this any time you want the VPS to catch up with new candidates/data
  added in the Emergent preview: `git pull` -> `restore_snapshot.py --yes` ->
  restart.
