#!/usr/bin/env bash
# Starts backend (:8000) and frontend (:5173). Ctrl+C stops both.
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$root/backend" && . .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate; uvicorn app.main:app --reload --port 8000) &
(cd "$root/frontend" && npm run dev) &
trap 'kill 0' INT TERM
wait
