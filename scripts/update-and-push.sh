#!/usr/bin/env bash
#
# Cron-friendly wrapper around scripts/update.py:
#   1. Pull any new remote commits (rebase, autostash safety net)
#   2. Run the Python updater to refresh the proxies/ tree
#   3. Commit + push only if anything actually changed
#
# Designed to be invoked from a crontab — see the "Server cron setup"
# section in README.md for installation steps.
#
# Exits non-zero on any failure so cron's MAILTO surfaces it.

set -euo pipefail

# Resolve the repo root from this script's location so the wrapper works no
# matter where you put the checkout. Override with REPO_DIR=... if you need
# to point at a different working tree.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

cd "$REPO_DIR"

# Author for the bot commits. Override at the cron call site if you want a
# different identity (e.g. a dedicated service account).
GIT_USER_NAME="${GIT_USER_NAME:-proxyscrape-mirror-bot}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-support@proxyscrape.com}"

# Lock to prevent overlapping runs. A long network stall on one tick should
# never collide with the next. flock returns 1 immediately when the lock is
# held; that's the correct behavior for a 5-min cron — skip this tick.
LOCKFILE="${TMPDIR:-/tmp}/free-proxy-list-mirror.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Another instance is running; skipping tick" >&2
    exit 0
fi

log() {
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

log "Starting update in $REPO_DIR"

# Pull remote updates first — anyone editing the repo (humans, other servers)
# stays compatible. --autostash protects against any stray local changes.
git pull --rebase --autostash --quiet origin main

# Run the updater. Failures here propagate (set -e).
python3 scripts/update.py

# Stage only the data we publish. The script also writes stats.json under
# proxies/, so a single `git add proxies/` covers everything we care about.
git add proxies/

if git diff --cached --quiet; then
    log "No changes — upstream list is unchanged this tick"
    exit 0
fi

TS=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
git -c user.name="$GIT_USER_NAME" -c user.email="$GIT_USER_EMAIL" \
    commit --quiet -m "chore(data): automatic update — $TS"

# `--quiet` suppresses progress; stderr still surfaces auth/network errors.
git push --quiet

log "Pushed update"
