from datetime import date

from pydantic import BaseModel, Field


class SimulatorConfig(BaseModel):
    """Configuration knobs for synthetic event generation."""

    target_date: date = Field(default_factory=date.today)
    total_events: int = Field(default=10000, ge=1)
    malformed_rate: float = Field(default=0.05, ge=0, le=1)
    duplicate_rate: float = Field(default=0.03, ge=0, le=1)
    late_arrival_rate: float = Field(default=0.02, ge=0, le=1)
    schema_version: str = Field(default="1.0")
