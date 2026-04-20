#!/bin/bash
if tmux has-session -t tmux-session 2>/dev/null; then
    echo "Running"
else
    echo "Stopped"
fi