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


@app.get("/tmux", response_class=HTMLResponse)
async def tmux_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("tmux.html", {"request": request})


@app.get("/tmux-data")
async def tmux_data(user: str = Depends(get_current_user)):
    try:
        import libtmux
        server = libtmux.Server()
        session = server.find_where({"session_name": TMUX_SESSION})
        if session:
            pane = session.attached_pane
            if pane:
                pane.capture_pane()
                return {"tmux": pane.content}
    except Exception:
        pass
    return {"tmux": "Session not running"}


@app.get("/log", response_class=HTMLResponse)
async def log_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("log.html", {"request": request})


@app.get("/log-data")
async def log_data(user: str = Depends(get_current_user)):
    log_file = PROJECT_ROOT / "data" / "log.txt"
    if log_file.exists():
        return {"log": log_file.read_text()[-5000:]}
    return {"log": "No log file"}
