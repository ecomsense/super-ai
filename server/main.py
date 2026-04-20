from __future__ import annotations

import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

PROJECT_ROOT = Path(__file__).parent.parent
TMUX_SESSION = "tmux-session"

app = FastAPI()
security = HTTPBasic()


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "harinath" or credentials.password != "Nifty@9999":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/status")
async def status(user: str = Depends(get_current_user)):
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    return {"status": "Running" if result.returncode == 0 else "Stopped"}


@app.post("/start")
async def start(user: str = Depends(get_current_user)):
    subprocess.Popen([str(PROJECT_ROOT / "tmux.sh")], cwd=PROJECT_ROOT)
    return {"status": "started"}


@app.post("/stop")
async def stop(user: str = Depends(get_current_user)):
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION])
    return {"status": "stopped"}


@app.get("/logs")
async def logs(user: str = Depends(get_current_user)):
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p", "-S", "-100"],
        capture_output=True,
        text=True
    )
    return {"logs": result.stdout or "No logs"}


@app.get("/live-logs", response_class=HTMLResponse)
async def live_logs(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("live_logs.html", {"request": request})
