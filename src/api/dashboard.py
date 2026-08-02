"""Serve a single-page analytics dashboard from FastAPI.

Design philosophy:
  - Zero build step. No React/Vue/Svelte. One HTML file with inline JS.
  - Dashboard calls the same /api/* endpoints the external clients use.
  - This proves the API is the single source of truth — dashboard is just a consumer.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_DASHBOARD_DIR = Path(__file__).parent / "static"


@router.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return (_DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")