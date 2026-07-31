from src.schemas.enums import (
    DeviceOS,
    DeviceType,
    EventType,
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


def test_user_login_creation():
    login = UserLogin(
        user_id="user-123",
        subscription_tier=SubscriptionTier.FREE,
        device_type=DeviceType.DESKTOP,
        device_os=DeviceOS.LINUX,
        login_status=LoginStatus.SUCCESS,
        schema_version="1.0",
    )

    assert login.event_type == EventType.USER_LOGIN
    assert login.failure_reason is None


def test_user_login_serialization():
    login = UserLogin(
        user_id="user-123",
        subscription_tier=SubscriptionTier.FREE,
        device_type=DeviceType.DESKTOP,
        device_os=DeviceOS.LINUX,
        login_status=LoginStatus.SUCCESS,
        schema_version="1.0",
    )

    data = login.model_dump(mode="json")

    assert data["event_type"] == "user_login"
    assert data["user_id"] == "user-123"
    assert data["failure_reason"] is None


def test_conversation_started_creation():
    event = ConversationStarted(
        user_id="user-123",
        subscription_tier=SubscriptionTier.PRO,
        conversation_id="conversation-123",
        schema_version="1.0",
    )

    assert event.event_type == EventType.CONVERSATION_STARTED
    assert event.conversation_id == "conversation-123"


def test_conversation_started_serialization():
    event = ConversationStarted(
        user_id="user-123",
        subscription_tier=SubscriptionTier.PRO,
        conversation_id="conversation-123",
        schema_version="1.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "conversation_started"
    assert data["subscription_tier"] == "pro"
    assert data["conversation_id"] == "conversation-123"


def test_prompt_submitted_creation():
    event = PromptSubmitted(
        user_id="user-123",
        conversation_id="conversation-123",
        prompt_char_count=24,
        prompt_token_count=6,
        prompt_category=PromptCategory.CODING,
        schema_version="1.0",
    )

    assert event.event_type == EventType.PROMPT_SUBMITTED
    assert event.prompt_token_count == 6


def test_prompt_submitted_serialization():
    event = PromptSubmitted(
        user_id="user-123",
        conversation_id="conversation-123",
        prompt_char_count=24,
        prompt_token_count=6,
        prompt_category=PromptCategory.CODING,
        schema_version="1.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "prompt_submitted"
    assert data["prompt_char_count"] == 24
    assert data["prompt_category"] == "coding"


def test_model_response_creation():
    event = ModelResponse(
        user_id="user-123",
        conversation_id="conversation-123",
        model_provider=ModelProvider.LOCAL,
        model_name="qwen",
        status=ModelResponseStatus.SUCCESS,
        prompt_token_count=6,
        response_token_count=12,
        total_latency_ms=500,
        inference_latency_ms=400,
        queue_wait_ms=50,
        time_to_first_token_ms=100,
        schema_version="1.0",
    )

    assert event.event_type == EventType.MODEL_RESPONSE
    assert event.error_code is None


def test_model_response_serialization():
    event = ModelResponse(
        user_id="user-123",
        conversation_id="conversation-123",
        model_provider=ModelProvider.LOCAL,
        model_name="qwen",
        status=ModelResponseStatus.SUCCESS,
        prompt_token_count=6,
        response_token_count=12,
        total_latency_ms=500,
        inference_latency_ms=400,
        queue_wait_ms=50,
        time_to_first_token_ms=100,
        schema_version="1.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "model_response"
    assert data["model_provider"] == "local"
    assert data["total_latency_ms"] == 500


def test_feedback_creation():
    event = Feedback(
        user_id="user-123",
        conversation_id="conversation-123",
        response_id="response-123",
        feedback_type=FeedbackType.STAR_RATING,
        rating_value=5,
        schema_version="1.0",
    )

    assert event.event_type == EventType.FEEDBACK
    assert event.rating_value == 5


def test_feedback_serialization():
    event = Feedback(
        user_id="user-123",
        conversation_id="conversation-123",
        response_id="response-123",
        feedback_type=FeedbackType.THUMBS_UP,
        schema_version="1.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "feedback"
    assert data["feedback_type"] == "thumbs_up"
    assert data["rating_value"] is None


def test_conversation_closed_creation():
    event = ConversationClosed(
        user_id="user-123",
        conversation_id="conversation-123",
        turn_count=4,
        conversation_duration_seconds=240,
        schema_version="1.0",
    )

    assert event.event_type == EventType.CONVERSATION_CLOSED
    assert event.turn_count == 4


def test_conversation_closed_serialization():
    event = ConversationClosed(
        user_id="user-123",
        conversation_id="conversation-123",
        turn_count=4,
        conversation_duration_seconds=240,
        schema_version="1.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "conversation_closed"
    assert data["turn_count"] == 4
    assert data["conversation_duration_seconds"] == 240
