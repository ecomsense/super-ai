#!/bin/bash
# Run backtest and copy results to local

cd "$(dirname "$0")/.."

echo "Running backtest on server..."
ssh harinath.r "cd /home/harinath/no_venv/super-ai && .venv/bin/python backtest.py"

echo "Copying results to local..."
scp harinath.r:/home/harinath/no_venv/super-ai/data/*.csv data/

echo "Done! Backtest files in data/ folder"