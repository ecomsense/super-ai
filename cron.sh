#!/bin/env bash
env > /tmp/cron_log.txt

python3 -c "import sys; print(sys.path)" > /tmp/sys_path_from_cron.txt 2>&1

# Source user profile (adjust to your shell: .bashrc, .zshrc, etc.)
new_home="$HOME/home/konkakurnool/"
source "$new_home/.bashrc"

# OR if you use virtualenvs or conda:
# source "$HOME/miniconda3/etc/profile.d/conda.sh"
# conda activate myenv

# Your tmux logic
sess="tmux-session"

if tmux has-session -t "$sess" 2>/dev/null; then
  echo "[$(date)] Session '$sess' already running. Skipping start."
  exit 0
fi

cd "$new_home/no_venv/super-ai" || exit 1


tmux new-session -d -s "$sess"
tmux send-keys -t "$sess" "/usr/bin/python3 -m src.main && tmux kill-session -t $sess" C-m