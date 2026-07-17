#!/bin/zsh
# Scheduled scrape run: snapshot all tracked products, export JSON, push to GitHub Pages.
set -e
cd "$(dirname "$0")"

./.venv/bin/python -m scraper.main >> data/run.log 2>&1 || echo "run finished with errors (see data/run.log)"

if [[ -n "$(git status --porcelain docs/data)" ]]; then
  git add docs/data
  git commit -m "data: scrape $(date '+%Y-%m-%d %H:%M')" --quiet
  git push --quiet origin main || echo "push failed (offline?) — will go out with next run"
fi
