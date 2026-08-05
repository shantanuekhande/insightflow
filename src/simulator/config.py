from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class SimulatorConfig(BaseModel):
    """Configuration knobs for synthetic event generation."""

    target_date: date = Field(default_factory=date.today)
    date_range_days: int = Field(default=45, ge=1, le=90)
    total_events: int = Field(default=1000, ge=1)
    malformed_rate: float = Field(default=0.05, ge=0, le=1)
    duplicate_rate: float = Field(default=0.03, ge=0, le=1)
    late_arrival_rate: float = Field(default=0.02, ge=0, le=1)
    schema_version: str = Field(default="2.0")