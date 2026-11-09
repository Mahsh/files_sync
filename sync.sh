#!/usr/bin/env bash
# Bidirectional sync for this folder: pull --rebase, commit local changes, push.
# Runs on any machine that cloned this repo into its workspace/sync_files.
set -euo pipefail
cd "$(dirname "$0")"
git pull --rebase -q origin main
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "Sync from $(hostname) at $(date -u '+%F %T') UTC"
  git push -q origin main
  echo "pushed: $(git log -1 --oneline)"
else
  echo "no local changes (remote merged)"
fi
