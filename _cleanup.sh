#!/usr/bin/env bash
set -euo pipefail
SYNC_REPO_DIR="$HOME/.openclaw/workspace/openclaw-sync-repo"
cd "$SYNC_REPO_DIR"
git rm -r -q --cached --ignore-unmatch '*__pycache__*' '*.pyc' 2>/dev/null || true
find . -path ./.git -prune -o -type d -name '__pycache__' -print -exec rm -rf {} + 2>/dev/null || true
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -q -m "chore: remove python cache artifacts from sync" -m "$(date -u +%F\ %T) UTC"
  git push -q origin main
  echo "pushed cleanup commit"
else
  echo "nothing to clean"
fi
echo "== remote HEAD =="
git ls-remote origin main | cut -f1
git rev-parse HEAD
