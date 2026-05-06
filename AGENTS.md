# AGENTS.md - super-ai

## CRITICAL: Start Button vs tmux.sh

- **Start button** (POST /start): Creates HTTP request, but may NOT create tmux session
- **tmux.sh via shell**: This is what actually creates the trading session
- If no POST /start in journalctl but trading running → started via shell manually

## Session Diagnosis Method

To check what user did after a specific time:

```bash
# 1. Find POST /start in journalctl (start button clicks)
ssh harinath.r "journalctl --user -u fastapi_app.service --since '2026-05-05 15:30' --no-pager | grep 'POST /start'"

# 2. Find trading sessions in log (all starts - button OR tmux.sh)
ssh harinath.r "grep -E '2026-05-05 1[6-7]:' /home/harinath/no_venv/super-ai/data/log.txt | grep -E 'WAITING|Live trading'"

# 3. Compare: entries WITH POST /start = button, WITHOUT = tmux.sh
```

**Session Running Check:**
```bash
# Check if tmux session exists
ssh harinath.r "tmux ls"

# Check button response after clicking
ssh harinath.r "journalctl --user -u fastapi_app.service -n 3 | grep POST /start"
# - If "already_running" returned → session existed, button worked correctly
# - If "started" returned → new session created
```

## Project

- **Repo**: `git@github.com:ecomsense/super-ai`
- **Remote server**: `ssh harinath.r` (see ~/.ssh/config for IP)

## Troubleshooting Checklist

### Trading Engine Not Starting

```bash
# Check tmux session
ssh harinath.r "tmux ls"

# Check logs
ssh harinath.r "tail -50 /home/harinath/super-ai/data/log.txt"

# Check if process is running
ssh harinath.r "ps aux | grep python"
```

### FastAPI Dashboard Down

```bash
# Check service status
ssh harinath.r "systemctl --user status fastapi_app.service"

# Restart service
ssh harinath.r "systemctl --user restart fastapi_app.service"

# Check journal logs
ssh harinath.r "journalctl --user -u fastapi_app.service -n 50"
```

### Strategy Import Errors

```bash
# Test imports
cd /home/pannet1/py/github.com/ecomsense/super-ai
/home/pannet1/py/finvasia/bin/python -c "
import sys; sys.path.insert(0, '.')
from src.strategies import hilo, pivot, ram
print('OK')
"
```

### Missing Dependencies

**Note**: See rules.md for Python/uv setup - use pyproject.toml as source of truth for dependencies.

### Git Sync

```bash
# Pull latest on server
ssh harinath.r "cd /home/harinath/super-ai && git pull"

# Restart after pull
ssh harinath.r "systemctl --user restart fastapi_app.service"
```

## Issue Tracking

### renko.py syntax error
- **Root cause**: Stray `:` colon on line 114 after `return` statement
- **Fix**: Removed colon, fixed import paths (`src.helper` → `src.sdk.helper`, `src.trade` → `src.config.interface`)
- **Status**: Fixed
- **pre**: `scripts/pre-renko-fix.sh`
- **commit**: `fix renko.py syntax error`
- **post**: `scripts/post-renko-fix.sh`

### oblegacy.py history import
- **Root cause**: `history` was imported from `src.sdk.helper` but it's a method on `Helper` class
- **Fix**: Changed `from src.sdk.helper import Helper, history` → `from src.sdk.helper import Helper`, call as `Helper.history()`
- **Status**: Fixed

### renkodf missing from requirements.txt
- **Root cause**: External dependency not listed
- **Fix**: Installed manually, should be added to requirements.txt
- **Status**: Installed, needs requirements.txt update

### Hardcoded credentials in server/main.py
- **Root cause**: Password stored in plaintext
- **Fix**: Should use environment variables or .env file
- **Status**: Known issue, not fixed

### Broker Position Format
- **Finding**: Helper.positions() returns broker position dicts with keys: `symbol`, `quantity`
- **Note**: No `id` field in broker response - RiskManager generates id from symbol
- **Fixtures**: Added broker_position_book, broker_order_book, broker_trades fixtures in tests/conftest.py
- **Status**: Done

### Running Tests Locally

**Note**: See rules.md for Python/uv setup and test running commands.

### Backtest Report

To generate backtest report:

```bash
# Run on server
ssh harinath.r "cd /home/harinath/no_venv/super-ai && /.venv/bin/python backtest.py call"
ssh harinath.r "cd /home/harinath/no_venv/super-ai && /.venv/bin/python backtest.py put"

# Copy to local
scp harinath.r:/home/harinath/no_venv/super-ai/data/backtest_NATURALGAS_CALL.csv /data/
scp harinath.r:/home/harinath/no_venv/super-ai/data/backtest_NATURALGAS_PUT.csv /data/
```

**IMPORTANT**: After copying, verify files exist in local data folder before completing.

### server/main.py refactoring
- **Changes**: Added logging, replaced hardcoded credentials with env vars (no defaults - must be set via environment), removed bare except, extracted duplicated file listing logic, removed unused import, added type hints, extracted magic number (LOG_SLICE_SIZE), extracted file validation into get_valid_file_path() helper (also adds security check for path traversal), moved style.css to static folder and using StaticFiles middleware, changed auth dependency parameter to _ to avoid linter warnings, renamed status() to get_status() to avoid conflict with imported status module, removed unused FileResponse import
- **Status**: Done
- **commit**: `refactor server/main.py - add logging, env vars, type hints, remove duplication`
- **Note**: Environment variables DASHBOARD_USER and DASHBOARD_PASS must be set on server (use `systemctl --user set-environment DASHBOARD_USER=... DASHBOARD_PASS=...`)
- **Fix**: Fixed RiskManager error - added property setter to convert dict-based positions to Position objects, fixed error handler referencing unassigned variable
- **Tests**: Added tests/unit/test_risk_manager.py with tests for status() method including dict-based positions

## Scripts

- `scripts/setup-ssh-key.sh` - Copy SSH key to remote server
- `tmux.sh` - Start trading engine in tmux session
- `stop.sh` - Stop trading engine
- `status.sh` - Check trading engine status

## Diagnosis Note - Identifying How Trading Session Started

**Rule:**
- POST /start in journalctl + trading session = **Started via Start button**
- No POST /start in journalctl + trading session = **Started via shell (tmux.sh)**

This distinction is critical for troubleshooting. Don't assume start button if there's no POST /start record.

---

## WebSocket 502 Errors Investigation (2026-05-05)

### What Happened
- Morning logs showed 502 Bad Gateway websocket errors at ~10:32
- We couldn't determine if session was started via start button or tmux.sh
- No logging to distinguish between the two start methods

### Key Finding
- WebSocket 502 errors occurred ~17-20 minutes AFTER session was already running
- They were NOT coinciding with the start button press
- This indicates broker connection issues mid-session, not at session start
- Root cause: Broker's websocket server went down, not at session initialization

### Why This Matters
- Without proper logging, we cannot retroactively determine:
  - When the session was started
  - Whether it was via start button or tmux.sh

### Fix - Logging Added
Now strategy logs "start_time: HH:MM" at session start, making it traceable:

| Start Method | journalctl | log.txt |
|-----------|-----------|--------|
| Start button (POST /start) | Has POST /start | Has start_time: |
| tmux.sh | No POST /start | Has start_time: |

### Diagnosis Commands
```bash
# Find start button clicks (with HTTP POST)
ssh harinath.r "journalctl --user -u fastapi_app.service | grep 'POST /start'"


# Find any session starts (strategy load time)
ssh harinath.r "grep 'start_time:' /home/harinath/no_venv/super-ai/data/log.txt"
```

### WebSocket Error Pattern
- Error: "Handshake status 502 Bad Gateway"
- Happens during trading when broker's WS server goes down
- Does NOT indicate start method - traceable only via journalctl + log comparison
