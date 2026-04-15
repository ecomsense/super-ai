#!/bin/env bash
set -e
cd "$(dirname "$0")"

find . -type d -name "__pycache__" -print0 | xargs -0 rm -rf

sess="tmux-session"

if tmux has-session -t "$sess" 2>/dev/null; then
    echo "Session $sess already exists. Attaching to it."
    tmux attach -t "$sess"
else
    echo "Updating and creating session $sess."
    tmux new-session -d -s "$sess"
    tmux send-keys -t "$sess" "./factory/run.sh && tmux kill-session -t $sess" C-m
    tmux attach -t "$sess"
fi
