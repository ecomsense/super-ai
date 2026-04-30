# SPEC: super-ai

## Overview

Algorithmic trading platform with broker-agnostic architecture. Manages trading strategies via tmux sessions, controlled through a FastAPI web dashboard.

**Repo**: `git@github.com:ecomsense/super-ai`

## Architecture

```
super-ai/
├── src/                    # Core trading engine
│   ├── main.py             # Entry point - reads builders, runs engine loop
│   ├── constants.py        # Config loading, TradeSet singleton, global objects
│   ├── core/
│   │   ├── build.py        # Builder pattern - merges settings + symbols
│   │   ├── engine.py       # Trading loop - tick strategies, manage time
│   │   └── strategy.py     # Dynamic strategy loader via importlib
│   ├── strategies/         # 8 strategies (hilo, pivot, renko, ram, etc.)
│   ├── providers/          # Broker-agnostic managers (trade, position, risk, grid)
│   ├── sdk/                # Helper utilities, websocket server, paper trading
│   └── config/             # Trade interface definitions
├── server/                 # FastAPI web dashboard
│   └── main.py             # Start/stop tmux, view logs, edit config files
├── factory/                # User-configurable YAML/CSV templates
├── data/                   # Runtime data (copied from factory, not in git)
└── tests/                  # Unit + integration tests
```

## Key Design Decisions

1. **Broker agnostic**: `stock-brokers` library abstracts broker APIs
2. **Strategy loading**: Dynamic via `importlib` from `src/strategies/{name}.py`
3. **Process management**: tmux session (`tmux-session`) for trading loop
4. **Config system**: YAML files in `factory/` copied to `data/` at runtime
5. **Singleton**: `TradeSet` in `constants.py` for shared trade settings

## API Routes (server/main.py)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard - file list or tmux view |
| GET | `/status` | Check if tmux session is running |
| POST | `/start` | Start trading via tmux.sh |
| POST | `/stop` | Kill tmux session |
| GET | `/tmux-data` | Stream tmux pane output |
| GET | `/log-data` | Last 5000 chars of log.txt |
| GET | `/files` | List data/ directory files |
| GET | `/file/{filename}` | View/edit file content |
| POST | `/file/{filename}` | Save file content |
| POST | `/rename` | Toggle .yml/.txt extension |
| POST | `/delete` | Delete file from data/ |

## Known Issues

1. **renko.py**: Had syntax error (stray `:` on line 114) - fixed
2. **renko.py**: Wrong import paths (`src.helper` → `src.sdk.helper`) - fixed
3. **oblegacy.py**: `history` import broken - changed to `Helper.history()` - fixed
4. **renkodf**: External dependency not in requirements.txt
5. **Hardcoded credentials**: `server/main.py` has password in plaintext
6. **No systemd service**: FastAPI app not managed via systemd
7. **IPv6 forced off**: `constants.py` disables IPv6 globally

## Dependencies

- `stock-brokers` (git+https://github.com/ecomsense/stock-brokers)
- `toolkit` (git+https://github.com/pannet1/toolkit)
- `pendulum`, `renkodf`, `pandas`, `numpy`, `fastapi`, `uvicorn`, `libtmux`

## Server

- **Remote**: `65.20.88.130` (user: `harinath`, SSH alias: `harinath.r`)
- **Local**: `65.20.71.25` (user: `harinath.l`)
- **Venv**: `/home/pannet1/py/finvasia/`
