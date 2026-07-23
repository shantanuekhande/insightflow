"""User domain entity."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Platform, UserTier


class User(BaseModel):
    """A user interacting with the AI platform."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=255)
    tier: UserTier
    country: str = Field(min_length=2, max_length=100)
    platform: Platform
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
