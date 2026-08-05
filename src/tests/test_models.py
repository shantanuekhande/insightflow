from src.schemas.enums import (
    CloseReason,
    DeviceOS,
    DeviceType,
    EventType,
    FeedbackCategory,
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
        session_id="sess-abc",
        subscription_tier=SubscriptionTier.FREE,
        device_type=DeviceType.DESKTOP,
        device_os=DeviceOS.LINUX,
        country_code="US",
        login_status=LoginStatus.SUCCESS,
        schema_version="2.0",
    )

    assert login.event_type == EventType.USER_LOGIN
    assert login.failure_reason is None
    assert login.session_id == "sess-abc"
    assert login.country_code == "US"


def test_user_login_failed_no_session():
    """Failed logins have null session_id (no session was created)."""
    login = UserLogin(
        user_id="user-123",
        session_id=None,
        subscription_tier=SubscriptionTier.FREE,
        device_type=DeviceType.DESKTOP,
        device_os=DeviceOS.LINUX,
        country_code="US",
        login_status=LoginStatus.FAILURE,
        failure_reason=None,
        schema_version="2.0",
    )

    assert login.session_id is None
    assert login.login_status == LoginStatus.FAILURE


def test_user_login_serialization():
    login = UserLogin(
        user_id="user-123",
        session_id="sess-abc",
        subscription_tier=SubscriptionTier.FREE,
        device_type=DeviceType.DESKTOP,
        device_os=DeviceOS.LINUX,
        country_code="IN",
        login_status=LoginStatus.SUCCESS,
        schema_version="2.0",
    )

    data = login.model_dump(mode="json")

    assert data["event_type"] == "user_login"
    assert data["user_id"] == "user-123"
    assert data["country_code"] == "IN"
    assert data["session_id"] == "sess-abc"
    assert data["failure_reason"] is None


def test_conversation_started_creation():
    event = ConversationStarted(
        user_id="user-123",
        session_id="sess-abc",
        subscription_tier=SubscriptionTier.PRO,
        conversation_id="conversation-123",
        schema_version="2.0",
    )

    assert event.event_type == EventType.CONVERSATION_STARTED
    assert event.session_id == "sess-abc"
    assert event.conversation_id == "conversation-123"


def test_conversation_started_serialization():
    event = ConversationStarted(
        user_id="user-123",
        session_id="sess-abc",
        subscription_tier=SubscriptionTier.PRO,
        conversation_id="conversation-123",
        schema_version="2.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "conversation_started"
    assert data["subscription_tier"] == "pro"
    assert data["session_id"] == "sess-abc"


def test_prompt_submitted_creation():
    event = PromptSubmitted(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        prompt_char_count=24,
        prompt_token_count=6,
        prompt_category=PromptCategory.CODING,
        schema_version="2.0",
    )

    assert event.event_type == EventType.PROMPT_SUBMITTED
    assert event.prompt_token_count == 6
    assert event.session_id == "sess-abc"


def test_prompt_submitted_serialization():
    event = PromptSubmitted(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        prompt_char_count=24,
        prompt_token_count=6,
        prompt_category=PromptCategory.CODING,
        schema_version="2.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "prompt_submitted"
    assert data["prompt_char_count"] == 24
    assert data["prompt_category"] == "coding"
    assert data["session_id"] == "sess-abc"


def test_model_response_creation():
    event = ModelResponse(
        user_id="user-123",
        session_id="sess-abc",
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
        estimated_cost_usd=0.0025,
        schema_version="2.0",
    )

    assert event.event_type == EventType.MODEL_RESPONSE
    assert event.error_code is None
    assert event.estimated_cost_usd == 0.0025
    assert event.server_id is None
    assert event.session_id == "sess-abc"


def test_model_response_with_server_info():
    """ModelResponse can carry server metadata for infrastructure analytics."""
    event = ModelResponse(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        model_provider=ModelProvider.API,
        model_name="gpt-4.1",
        status=ModelResponseStatus.SUCCESS,
        prompt_token_count=100,
        response_token_count=200,
        total_latency_ms=1200,
        inference_latency_ms=1000,
        queue_wait_ms=100,
        time_to_first_token_ms=150,
        estimated_cost_usd=0.045,
        server_id="srv-infra-003",
        server_region="us-east-1",
        server_instance_type="gpu-a100",
        schema_version="2.0",
    )

    assert event.server_id == "srv-infra-003"
    assert event.server_region == "us-east-1"
    assert event.server_instance_type == "gpu-a100"


def test_model_response_serialization():
    event = ModelResponse(
        user_id="user-123",
        session_id="sess-abc",
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
        estimated_cost_usd=0.0025,
        schema_version="2.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "model_response"
    assert data["model_provider"] == "local"
    assert data["total_latency_ms"] == 500
    assert data["estimated_cost_usd"] == 0.0025
    assert data["server_id"] is None


def test_feedback_creation():
    event = Feedback(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        response_id="response-123",
        feedback_type=FeedbackType.STAR_RATING,
        feedback_category=FeedbackCategory.ACCURACY,
        rating_value=5,
        schema_version="2.0",
    )

    assert event.event_type == EventType.FEEDBACK
    assert event.rating_value == 5
    assert event.feedback_category == FeedbackCategory.ACCURACY


def test_feedback_without_category():
    """Feedback category is optional — can be null."""
    event = Feedback(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        response_id="response-123",
        feedback_type=FeedbackType.THUMBS_UP,
        schema_version="2.0",
    )

    assert event.feedback_category is None
    assert event.rating_value is None


def test_feedback_serialization():
    event = Feedback(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        response_id="response-123",
        feedback_type=FeedbackType.THUMBS_UP,
        feedback_category=FeedbackCategory.RELEVANCE,
        schema_version="2.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "feedback"
    assert data["feedback_type"] == "thumbs_up"
    assert data["feedback_category"] == "relevance"
    assert data["rating_value"] is None


def test_conversation_closed_creation():
    event = ConversationClosed(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        close_reason=CloseReason.USER_CLOSED,
        turn_count=4,
        conversation_duration_seconds=240,
        schema_version="2.0",
    )

    assert event.event_type == EventType.CONVERSATION_CLOSED
    assert event.turn_count == 4
    assert event.close_reason == CloseReason.USER_CLOSED
    assert event.session_id == "sess-abc"


def test_conversation_closed_serialization():
    event = ConversationClosed(
        user_id="user-123",
        session_id="sess-abc",
        conversation_id="conversation-123",
        close_reason=CloseReason.TIMEOUT,
        turn_count=4,
        conversation_duration_seconds=240,
        schema_version="2.0",
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "conversation_closed"
    assert data["turn_count"] == 4
    assert data["conversation_duration_seconds"] == 240
    assert data["close_reason"] == "timeout"
    assert data["session_id"] == "sess-abc"
