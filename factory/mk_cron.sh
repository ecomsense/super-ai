#!/bin/bash


#14 9 * * * /var/www/clients/client5/web8/home/harinath.l/no_venv/super-ai/data/cron.sh > /tmp/harinath_cron.txt 2>&1


# 1. Define variables
# Using absolute paths is critical for servers
PYTHON_BIN="/usr/bin/python3"
SCRIPT_PATH="/home/user/scripts/eod_analysis.py"
LOG_PATH="/home/user/logs/eod_market.log"

# The cron entry with redirection
NEW_JOB="30 15 * * 1-5 $PYTHON_BIN $SCRIPT_PATH >> $LOG_PATH 2>&1"

# 2. Ensure the log directory exists (common server oversight)
mkdir -p "$(dirname "$LOG_PATH")"

# 3. Add to crontab safely
# We redirect stderr (2>/dev/null) because if crontab is empty, 
# 'crontab -l' sends an error message to the pipe that we don't want to save.
if crontab -l 2>/dev/null | grep -qF "$SCRIPT_PATH"; then
    echo "Entry for $SCRIPT_PATH already exists. No changes made."
else
    (crontab -l 2>/dev/null; echo "$NEW_JOB") | crontab -
    echo "Successfully updated crontab via SSH."
fi
