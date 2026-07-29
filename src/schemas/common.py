from datetime import date as Date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from .enums import EventType


class BaseEvent(BaseModel):
    """Defines fields shared by every event."""

    event_id: UUID = Field(default_factory=uuid4)
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_date: Date = Field(default=None, validate_default=True)
    event_type: EventType = Field(...)
    schema_version: str = Field(...)

    @field_validator("event_date", mode="before")
    @classmethod
    def set_event_date(cls, value, info) -> Date:
        """Derives the event date from its timestamp."""
        return info.data["event_timestamp"].date()
