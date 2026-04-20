from __future__ import annotations

import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).parent.parent
TMUX_SESSION = "tmux-session"

app = FastAPI()

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/status")
async def status():
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    return {"status": "Running" if result.returncode == 0 else "Stopped"}


@app.post("/start")
async def start():
    subprocess.Popen([PROJECT_ROOT / "tmux.sh"], cwd=PROJECT_ROOT)
    return {"status": "started"}


@app.post("/stop")
async def stop():
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION])
    return {"status": "stopped"}


@app.get("/logs")
async def logs():
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p", "-S", "-100"],
        capture_output=True,
        text=True
    )
    return {"logs": result.stdout or "No logs"}
