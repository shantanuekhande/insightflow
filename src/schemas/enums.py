from enum import Enum


class EventType(str, Enum):
    """Represents the type of event emitted by the application."""

    USER_LOGIN = "user_login"
    CONVERSATION_STARTED = "conversation_started"
    PROMPT_SUBMITTED = "prompt_submitted"
    MODEL_RESPONSE = "model_response"
    FEEDBACK = "feedback"
    CONVERSATION_CLOSED = "conversation_closed"


class SubscriptionTier(str, Enum):
    """Represents a user's subscription level."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class DeviceType(str, Enum):
    """Represents the device category used to access the application."""

    MOBILE = "mobile"
    DESKTOP = "desktop"
    TABLET = "tablet"
    API = "api"


class DeviceOS(str, Enum):
    """Represents the operating system of the device."""

    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"


class LoginStatus(str, Enum):
    """Represents the outcome of a login attempt."""

    SUCCESS = "success"
    FAILURE = "failure"
    LOCKED = "locked"
    MFA_TIMEOUT = "mfa_timeout"
    SERVER_ERROR = "server_error"


class FailureReason(str, Enum):
    """Represents the reason a login attempt failed."""

    INVALID_PASSWORD = "invalid_password"
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_LOCKED = "account_locked"
    MFA_TIMEOUT = "mfa_timeout"
    MFA_INVALID = "mfa_invalid"
    SESSION_EXPIRED = "session_expired"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class ModelResponseStatus(str, Enum):
    """Represents the outcome of a model response request."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class ErrorCode(str, Enum):
    """Represents a machine-readable model response error code."""

    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_OVERLOADED = "MODEL_OVERLOADED"
    GPU_OOM = "GPU_OOM"
    INVALID_PROMPT = "INVALID_PROMPT"
    SAFETY_FILTER = "SAFETY_FILTER"
    CONTEXT_LENGTH_EXCEEDED = "CONTEXT_LENGTH_EXCEEDED"
    NETWORK_ERROR = "NETWORK_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ModelProvider(str, Enum):
    """Represents where the model is hosted or accessed."""

    LOCAL = "local"
    API = "api"


class FeedbackType(str, Enum):
    """Represents how a user submitted response feedback."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    STAR_RATING = "star_rating"
    TEXT = "text"
    REPORT = "report"


class PromptCategory(str, Enum):
    """Represents the classified category of a prompt."""

    CODING = "coding"
    WRITING = "writing"
    MATH = "math"
    RESEARCH = "research"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    REASONING = "reasoning"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


class CloseReason(str, Enum):
    """Represents why a conversation was closed."""

    USER_CLOSED = "user_closed"
    TIMEOUT = "timeout"
    SYSTEM_ERROR = "system_error"
    MAX_TURNS_REACHED = "max_turns_reached"


class FeedbackCategory(str, Enum):
    """Represents the category of user feedback."""

    ACCURACY = "accuracy"
    TONE = "tone"
    SPEED = "speed"
    RELEVANCE = "relevance"
    HELPFULNESS = "helpfulness"
