from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TMUX_SESSION = "tmux-session"
LOG_SLICE_SIZE = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(PROJECT_ROOT / "data" / "server.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI()
security = HTTPBasic()

STATIC_DIR = Path(__file__).parent / "templates"
STATIC_FILES_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_FILES_DIR), name="static")


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.getenv("DASHBOARD_USER")
    expected_pass = os.getenv("DASHBOARD_PASS")
    if not expected_user or not expected_pass:
        logger.error("DASHBOARD_USER or DASHBOARD_PASS not set in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )
    if credentials.username != expected_user or credentials.password != expected_pass:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def is_tmux_running() -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True
    )
    return result.returncode == 0


templates = Jinja2Templates(directory=STATIC_DIR)


def list_data_files() -> list[dict]:
    """List data files from DATA_DIR, excluding log and run files."""
    files = []
    ignore = {"log.txt", "run.txt", "server.log"}
    if DATA_DIR.exists():
        for f in DATA_DIR.iterdir():
            if f.is_file() and f.suffix in {".txt", ".yml", ".yaml"} and f.name not in ignore:
                files.append({"name": f.name, "size": f.stat().st_size})
    return files


def get_valid_file_path(filename: str) -> Path | None:
    """Get valid file path if file exists and is a file, else None."""
    if ".." in filename or filename.startswith("/") or "/" in filename:
        return None
    file_path = DATA_DIR / filename
    if file_path.exists() and file_path.is_file():
        return file_path
    return None





@app.get("/", response_class=HTMLResponse)
async def home(request: Request, _: str = Depends(get_current_user)):
    is_running = is_tmux_running()

    if is_running:
        return templates.TemplateResponse(request, "tmux.html")

    files = list_data_files()
    return templates.TemplateResponse(request, "index.html", {"files": files})


@app.get("/status")
async def get_status(_: str = Depends(get_current_user)) -> dict[str, str]:
    return {"status": "Running" if is_tmux_running() else "Stopped"}


@app.post("/start")
async def start(_: str = Depends(get_current_user)) -> dict[str, str]:
    # Check if session already exists first
    if is_tmux_running():
        return {"status": "already_running"}
    
    run_file = DATA_DIR / "run.txt"
    if run_file.exists():
        run_file.unlink()
    subprocess.run(["bash", str(PROJECT_ROOT / "tmux.sh")], cwd=PROJECT_ROOT)
    return {"status": "started"}


@app.post("/stop")
async def stop(_: str = Depends(get_current_user)) -> dict[str, str]:
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION])
    return {"status": "stopped"}


@app.get("/tmux", response_class=HTMLResponse)
async def tmux_page(request: Request, _: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "tmux.html")


@app.get("/tmux-data")
async def tmux_data(_: str = Depends(get_current_user)) -> dict[str, str]:
    try:
        import libtmux

        server = libtmux.Server()
        session = server.find_where({"session_name": TMUX_SESSION})
        if session:
            pane = session.active_pane
            lines = pane.capture_pane()
            return {"tmux": "\n".join(lines)}
    except Exception as e:
        logger.warning(f"Failed to get tmux data: {e}")
    return {"tmux": "Session not running"}


@app.get("/log", response_class=HTMLResponse)
async def log_page(request: Request, _: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "log.html")


@app.get("/log-data")
async def log_data(_: str = Depends(get_current_user)) -> dict[str, str]:
    log_file = DATA_DIR / "log.txt"
    if log_file.exists():
        lines = log_file.read_text().splitlines()
        return {"log": "\n".join(lines[-LOG_SLICE_SIZE:])}
    return {"log": "No log file"}


"""
    file handler 
"""


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request, _: str = Depends(get_current_user)):
    files = list_data_files()
    return templates.TemplateResponse(request, "files.html", {"files": files})


@app.get("/file/{filename}")
async def view_file(
    request: Request, filename: str, _: str = Depends(get_current_user)
):
    file_path = get_valid_file_path(filename)
    if file_path:
        content = file_path.read_text()
        return templates.TemplateResponse(
            request, "file.html", {"filename": filename, "content": content}
        )
    return {"error": "File not found"}


@app.post("/file/{filename}")
async def save_file(
    filename: str, content: str = Form(...), _: str = Depends(get_current_user)
):
    file_path = get_valid_file_path(filename)
    if file_path:
        file_path.write_text(content)
        return RedirectResponse(url="/", status_code=303)
    return {"error": "File not found"}


class ToggleRequest(BaseModel):
    filename: str


@app.post("/rename")
async def rename_file(req: ToggleRequest, _: str = Depends(get_current_user)) -> dict[str, str]:
    file_path = get_valid_file_path(req.filename)
    if file_path:
        if file_path.suffix == ".yml":
            new_path = file_path.with_suffix(".txt")
        elif file_path.suffix == ".txt":
            new_path = file_path.with_suffix(".yml")
        else:
            return {"error": "Cannot toggle"}
        file_path.rename(new_path)
        return {"status": "renamed", "new": new_path.name}
    return {"error": "File not found"}


@app.post("/delete")
async def delete_file(req: ToggleRequest, _: str = Depends(get_current_user)) -> dict[str, str]:
    file_path = get_valid_file_path(req.filename)
    if file_path:
        file_path.unlink()
        return {"status": "deleted"}
    return {"error": "File not found"}
