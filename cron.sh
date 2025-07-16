#!/bin/bash

# Source user profile (adjust to your shell: .bashrc, .zshrc, etc.)
source "$HOME/.bashrc"

# OR if you use virtualenvs or conda:
# source "$HOME/miniconda3/etc/profile.d/conda.sh"
# conda activate myenv

# Your tmux logic
sess="tmux-session"

if tmux has-session -t "$sess" 2>/dev/null; then
  echo "[$(date)] Session '$sess' already running. Skipping start."
  exit 0
fi

cd "$HOME/no_venv/super-ai" || exit 1

tmux new-session -d -s "$sess"
tmux send-keys -t "$sess" "python3 -m src.main && tmux kill-session -t $sess" C-m
