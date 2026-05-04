# AGENTS.md - super-ai

## Project

- **Repo**: `git@github.com:ecomsense/super-ai`
- **Remote server**: `ssh harinath.r` (see ~/.ssh/config for IP)
- **Venv**: `/home/pannet1/py/finvasia/`
- **Python**: 3.13

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

```bash
# Install from requirements
/home/pannet1/py/finvasia/bin/pip install -r requirements.txt

# Install renkodf separately (not in requirements.txt)
/home/pannet1/py/finvasia/bin/pip install renkodf
```

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
