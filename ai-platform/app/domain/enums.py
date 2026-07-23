from enum import Enum


class UserTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class Platform(str, Enum):
    WEB = "web"
    MOBILE = "mobile"
    API = "api"


class Provider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
    OLLAMA = "ollama"


class PromptCategory(str, Enum):
    CODING = "coding"
    WRITING = "writing"
    RESEARCH = "research"
    MATH = "math"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class FeedbackType(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    NONE = "none"
