#!/bin/env sh
export TZ=Asia/Kolkata
find . -type d -name "__pycache__" -print0 | xargs -0 rm -rf
sess="tmux-session"

if tmux has-session -t "$sess" 2>/dev/null; then
	echo "Session $sess already exists."
else
	echo "updating"
	git reset --hard && git pull
	echo "Creating session $sess."
	tmux new-session -d -s "$sess"
	tmux send-keys -t "$sess" ".venv/bin/python -m src.main && tmux kill-session -t $sess" C-m
fi
