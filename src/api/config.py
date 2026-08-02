"""Configuration for the analytics API."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class APIConfig(BaseModel):
    """Configuration for the FastAPI analytics server."""

    gold_root: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "data" / "gold"
    )
    silver_root: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "data" / "silver"
    )
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)