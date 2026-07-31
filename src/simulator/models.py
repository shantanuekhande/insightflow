"""Re-exports event models and enums for the simulator.

The simulator acts as an external system (the AI application).
It imports from src.schemas but through its own module boundary,
mirroring how a real AI application would consume the schema.
"""

from src.schemas.enums import (
    CloseReason,
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
from src.schemas.events import (
    ConversationClosed,
    ConversationStarted,
    Feedback,
    ModelResponse,
    PromptSubmitted,
    UserLogin,
)

__all__ = [
    "CloseReason",
    "ConversationClosed",
    "ConversationStarted",
    "DeviceOS",
    "DeviceType",
    "ErrorCode",
    "EventType",
    "FailureReason",
    "Feedback",
    "FeedbackType",
    "LoginStatus",
    "ModelProvider",
    "ModelResponse",
    "ModelResponseStatus",
    "PromptCategory",
    "PromptSubmitted",
    "SubscriptionTier",
    "UserLogin",
]
