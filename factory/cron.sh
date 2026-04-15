#!/bin/env bash
set -e

PROJECT="$(dirname "$0")"
cd "$PROJECT" || exit 1

sess="tmux-session"
if tmux has-session -t "$sess" 2>/dev/null; then
  echo "[$(date)] Session '$sess' already running. Skipping start."
  exit 0
fi

exec ./factory/run.sh
