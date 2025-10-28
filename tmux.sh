#!/bin/env sh
find . -type d -name "__pycache__" -exec rm -rf {} +
# Define the session name
sess="tmux-session"

# Check if the session exists
if tmux has-session -t "$sess" 2>/dev/null; then
	echo "Session $sess already exists. Attaching to it."
	tmux attach -t "$sess"
else
	# If the session doesn't exist, create it
	echo "updating"
	git reset --hard && git pull
	echo "Creating and attaching to session $sess."
	tmux new-session -d -s "$sess"
	tmux send-keys -t "$sess" "python3 -m src.main && tmux kill-session -t $sess" C-m
	tmux attach -t "$sess"
fi
