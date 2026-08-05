"""Dashboard router — serves the HTML dashboard at /."""
from __future__ import annotations

import pathlib
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()

_STATIC_DIR = pathlib.Path(__file__).parent / "static"


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard HTML."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return HTMLResponse("<h1>InsightFlow Dashboard</h1><p>index.html not found in static/</p>")