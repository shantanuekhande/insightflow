from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ETLConfig(BaseModel):
    """Configuration for the ETL ingestion pipeline."""

    landing_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "landing")
    bronze_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "bronze")
    silver_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "silver")
    gold_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "gold")
    quarantine_root: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data" / "quarantine")
    target_date: Optional[date] = Field(default=None)
    batch_size: int = Field(default=10_000, ge=1)
