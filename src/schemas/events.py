from typing import Literal, Optional

from pydantic import Field

from .common import BaseEvent
from .enums import (
    DeviceOS,
    DeviceType,
    ErrorCode,
    EventType,
    FailureReason,
    FeedbackType,
    LoginStatus,
    ModelProvider,
    ModelResponseStatus,
    PromptCategory,
    SubscriptionTier,
)


class UserLogin(BaseEvent):
    """Captures a user login attempt."""

    event_type: Literal[EventType.USER_LOGIN] = Field(default=EventType.USER_LOGIN)
    user_id: str
    subscription_tier: SubscriptionTier
    device_type: DeviceType
    device_os: DeviceOS
    login_status: LoginStatus
    failure_reason: Optional[FailureReason] = Field(default=None)


class ConversationStarted(BaseEvent):
    """Captures the start of a conversation."""

    event_type: Literal[EventType.CONVERSATION_STARTED] = Field(
        default=EventType.CONVERSATION_STARTED
    )
    user_id: str
    subscription_tier: SubscriptionTier
    conversation_id: str


class PromptSubmitted(BaseEvent):
    """Captures a prompt submitted by a user."""

    event_type: Literal[EventType.PROMPT_SUBMITTED] = Field(
        default=EventType.PROMPT_SUBMITTED
    )
    user_id: str
    conversation_id: str
    prompt_char_count: int
    prompt_token_count: int
    prompt_category: PromptCategory


class ModelResponse(BaseEvent):
    """Captures a model response or inference failure."""

    event_type: Literal[EventType.MODEL_RESPONSE] = Field(
        default=EventType.MODEL_RESPONSE
    )
    user_id: str
    conversation_id: str
    model_provider: ModelProvider
    model_name: str
    status: ModelResponseStatus
    error_code: Optional[ErrorCode] = Field(default=None)
    prompt_token_count: int
    response_token_count: int
    total_latency_ms: int
    inference_latency_ms: int
    queue_wait_ms: int
    time_to_first_token_ms: int


class Feedback(BaseEvent):
    """Captures user feedback on a model response."""

    event_type: Literal[EventType.FEEDBACK] = Field(default=EventType.FEEDBACK)
    user_id: str
    conversation_id: str
    response_id: str
    feedback_type: FeedbackType
    rating_value: Optional[int] = Field(default=None, ge=1, le=5)


class ConversationClosed(BaseEvent):
    """Captures the closing of a conversation."""

    event_type: Literal[EventType.CONVERSATION_CLOSED] = Field(
        default=EventType.CONVERSATION_CLOSED
    )
    user_id: str
    conversation_id: str
    turn_count: int
    conversation_duration_seconds: int
