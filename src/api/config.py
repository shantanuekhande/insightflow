"""API configuration for InsightFlow."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class APIConfig(BaseModel):
    """Configuration for the API layer."""

    landing_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "landing")
    bronze_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "bronze")
    quarantine_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "quarantine")
    gold_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "gold")
    silver_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "silver")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
