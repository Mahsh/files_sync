#!/usr/bin/env bash
# Bidirectional sync for this folder: commit local changes, pull --rebase, push.
# Runs on any machine that cloned this repo into its workspace/sync_files.
# Note: commit BEFORE pulling -- rebase pull refuses a dirty tree.
set -euo pipefail
cd "$(dirname "$0")"
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "Sync from $(hostname) at $(date -u '+%F %T') UTC" || true
fi
git pull --rebase -q origin main
git push -q origin main
echo "done: $(git log -1 --oneline)"
