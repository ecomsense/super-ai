#!/bin/env sh
find . -type d -name "__pycache__" -print0 | xargs -0 rm -rf
sess="tmux-session"

if tmux has-session -t "$sess" 2>/dev/null; then
	if [ -t 0 ]; then
		echo "Attaching to session $sess."
		tmux attach-session -t "$sess"
	else
		echo "Session $sess already exists."
	fi
else
	echo "updating"
	git reset --hard && git pull
	if [ -t 0 ]; then
		echo "Creating and attaching to session $sess."
		tmux new-session -s "$sess" ".venv/bin/python -m src.main && tmux kill-session -t $sess"
	else
		echo "Creating session $sess."
		tmux new-session -d -s "$sess"
		tmux send-keys -t "$sess" ".venv/bin/python -m src.main && tmux kill-session -t $sess" C-m
	fi
fi
