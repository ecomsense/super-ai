from __future__ import annotations

import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

PROJECT_ROOT = Path(__file__).parent.parent
TMUX_SESSION = "tmux-session"

app = FastAPI()
security = HTTPBasic()

STATIC_DIR = Path(__file__).parent / "templates"


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "harinath" or credentials.password != "Nifty@9999":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


templates = Jinja2Templates(directory=STATIC_DIR)


@app.get("/style.css")
async def style_css():
    css_file = STATIC_DIR / "style.css"
    if css_file.exists():
        return FileResponse(str(css_file), media_type="text/css")
    return HTMLResponse("Not found", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: str = Depends(get_current_user)):
    data_dir = PROJECT_ROOT / "data"
    files = []
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.is_file() and f.suffix in [".txt", ".yml", ".yaml"]:
                files.append({"name": f.name, "size": f.stat().st_size})
    return templates.TemplateResponse("index.html", {"request": request, "files": files})


@app.get("/status")
async def status(user: str = Depends(get_current_user)):
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    return {"status": "Running" if result.returncode == 0 else "Stopped"}


@app.post("/start")
async def start(user: str = Depends(get_current_user)):
    subprocess.run(["bash", str(PROJECT_ROOT / "tmux.sh")], cwd=PROJECT_ROOT)
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
            pane = session.active_pane
            lines = pane.capture_pane()
            return {"tmux": "\n".join(lines)}
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


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request, user: str = Depends(get_current_user)):
    data_dir = PROJECT_ROOT / "data"
    files = []
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.is_file() and f.suffix in [".txt", ".yml", ".yaml"]:
                files.append({"name": f.name, "size": f.stat().st_size})
    return templates.TemplateResponse("files.html", {"request": request, "files": files})


@app.get("/file/{filename}")
async def view_file(filename: str, user: str = Depends(get_current_user)):
    file_path = PROJECT_ROOT / "data" / filename
    if file_path.exists() and file_path.is_file():
        content = file_path.read_text()
        return templates.TemplateResponse("file.html", {"request": None, "filename": filename, "content": content})
    return {"error": "File not found"}
