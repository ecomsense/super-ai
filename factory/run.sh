#!/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[$(date)] Creating venv..."
    python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt

echo "[$(date)] Pulling latest code..."
git fetch --all
git reset --hard origin/$(git rev-parse --abbrev-ref HEAD)
git pull

exec .venv/bin/python -m src.main
