#!/bin/bash
tmux kill-session -t tmux-session 2>/dev/null && echo "Session stopped" || echo "No session running"