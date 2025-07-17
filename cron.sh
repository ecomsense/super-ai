#!/bin/env bash

ACTUAL_HOME="$HOME/home/konkakurnool"

export PATH="$ACTUAL_HOME/.local/bin:$PATH"
export PYTHONPATH="$ACTUAL_HOME/.local/lib/python3.11/site-packages"

PROJECT="$ACTUAL_HOME/no_venv/super-ai"
python3 -c "import sys; print(sys.path)" > /tmp/sys_path_from_cron.txt 2>&1

sess="tmux-session"
if tmux has-session -t "$sess" 2>/dev/null; then
  echo "[$(date)] Session '$sess' already running. Skipping start."
  exit 0
fi

cd "$PROJECT" || exit 1
git reset --hard
tmux new-session -d -s "$sess"
tmux send-keys -t "$sess" "python3 -m src.main && tmux kill-session -t $sess" C-m