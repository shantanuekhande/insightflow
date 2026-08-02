from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from src.simulator.config import SimulatorConfig
from src.simulator.models import (
    ConversationClosed,
    ConversationStarted,
    ErrorCode,
    Feedback,
    FeedbackType,
    FailureReason,
    LoginStatus,
    ModelProvider,
    ModelResponse,
    ModelResponseStatus,
    PromptCategory,
    PromptSubmitted,
    SubscriptionTier,
    UserLogin,
)
from src.simulator.personas import UserPersona, create_user_pool


_MIN_TURNS = 2
_MAX_TURNS = 8
_FEEDBACK_PROBABILITY = 0.30
_DEFAULT_EVENTS_PER_USER = 4
_MODEL_NAMES = (
    "gpt-4.1-mini",
    "gpt-4.1",
    "claude-3.7-sonnet",
    "mistral-large",
    "llama-3.1-70b",
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_events(config: SimulatorConfig) -> int:
    """Generate simulator events and write them to the landing zone."""

    landing_root = _PROJECT_ROOT / "data" / "landing"
    landing_root.mkdir(parents=True, exist_ok=True)

    user_pool_size = max(1, config.total_events // _DEFAULT_EVENTS_PER_USER)
    personas = create_user_pool(user_pool_size)

    written = 0
    sequence_number = 0

    while written < config.total_events:
        persona = personas[sequence_number % len(personas)]
        session_events = _build_session(persona, config)

        for event in session_events:
            written += _write_event_record(
                landing_root,
                sequence_number,
                event,
                malformed_rate=config.malformed_rate,
                duplicate_rate=config.duplicate_rate,
                late_arrival_rate=config.late_arrival_rate,
                target_date=config.target_date,
            )
            sequence_number += 1
            if written >= config.total_events:
                break

    return written


def main() -> int:
    count = generate_events(SimulatorConfig())
    print(f"Generated {count} events")
    return count


# ---------------------------------------------------------------------------
# Session builder
# ---------------------------------------------------------------------------


def _build_session(persona: UserPersona, config: SimulatorConfig) -> list[Any]:
    turn_count = random.randint(_MIN_TURNS, _MAX_TURNS)
    session_id = str(uuid4())
    session_start = _session_start(config.target_date)

    events: list[Any] = []
    current_timestamp = session_start

    login = UserLogin(
        event_timestamp=current_timestamp,
        schema_version=config.schema_version,
        user_id=persona.user_id,
        subscription_tier=persona.subscription_tier,
        device_type=persona.device_type,
        device_os=persona.device_os,
        login_status=_pick_login_status(persona),
        failure_reason=None,
    )
    if login.login_status != LoginStatus.SUCCESS:
        login = login.model_copy(
            update={"failure_reason": _pick_failure_reason(login.login_status)}
        )
    events.append(login)

    current_timestamp += timedelta(seconds=random.randint(20, 180))
    events.append(
        ConversationStarted(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            subscription_tier=persona.subscription_tier,
            conversation_id=session_id,
        )
    )

    for turn_index in range(turn_count):
        current_timestamp += timedelta(seconds=random.randint(20, 180))
        prompt_char_count = random.randint(20, 500)
        prompt_token_count = max(1, prompt_char_count // random.randint(3, 5))
        prompt_category = _pick_prompt_category(persona)
        events.append(
            PromptSubmitted(
                event_timestamp=current_timestamp,
                schema_version=config.schema_version,
                user_id=persona.user_id,
                conversation_id=session_id,
                prompt_char_count=prompt_char_count,
                prompt_token_count=prompt_token_count,
                prompt_category=prompt_category,
            )
        )

        current_timestamp += timedelta(seconds=random.randint(2, 45))
        response_status = _pick_model_response_status(persona)
        response_token_count = (
            0
            if response_status != ModelResponseStatus.SUCCESS
            else random.randint(10, 350)
        )
        inference_latency_ms = random.randint(80, 6000)
        queue_wait_ms = random.randint(0, 900)
        time_to_first_token_ms = random.randint(
            10, max(10, inference_latency_ms // 3)
        )

        response = ModelResponse(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            conversation_id=session_id,
            model_provider=_pick_model_provider(persona),
            model_name=random.choice(_MODEL_NAMES),
            status=response_status,
            error_code=_pick_error_code(response_status),
            prompt_token_count=prompt_token_count,
            response_token_count=response_token_count,
            total_latency_ms=inference_latency_ms + queue_wait_ms,
            inference_latency_ms=inference_latency_ms,
            queue_wait_ms=queue_wait_ms,
            time_to_first_token_ms=time_to_first_token_ms,
        )
        events.append(response)

        if random.random() < _FEEDBACK_PROBABILITY:
            current_timestamp += timedelta(seconds=random.randint(5, 120))
            feedback_type = _pick_feedback_type(persona)
            feedback_kwargs = {
                "event_timestamp": current_timestamp,
                "schema_version": config.schema_version,
                "user_id": persona.user_id,
                "conversation_id": session_id,
                "response_id": str(uuid4()),
                "feedback_type": feedback_type,
                "rating_value": _pick_rating_value(feedback_type),
            }
            events.append(Feedback(**feedback_kwargs))

    current_timestamp += timedelta(seconds=random.randint(10, 180))
    events.append(
        ConversationClosed(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            conversation_id=session_id,
            turn_count=turn_count,
            conversation_duration_seconds=max(
                1, int((current_timestamp - session_start).total_seconds())
            ),
        )
    )

    return events


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _write_event_record(
    landing_root: Path,
    sequence_number: int,
    event: Any,
    *,
    malformed_rate: float,
    duplicate_rate: float,
    late_arrival_rate: float,
    target_date: date,
) -> int:
    if random.random() < late_arrival_rate:
        event = _with_timestamp(event, _late_arrival_timestamp(target_date))

    event_payload = _serialize_event(event)

    if random.random() < malformed_rate:
        event_payload = _corrupt_json(event_payload)

    event_path = _event_path(landing_root, sequence_number, event, duplicate=False)
    _write_text(event_path, event_payload)

    written = 1
    if random.random() < duplicate_rate:
        duplicate_path = _event_path(
            landing_root, sequence_number, event, duplicate=True
        )
        _write_text(duplicate_path, event_payload)
        written += 1

    return written


def _serialize_event(event: Any) -> str:
    return json.dumps(
        event.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
    )


def _event_path(
    landing_root: Path, sequence_number: int, event: Any, *, duplicate: bool
) -> Path:
    event_date = event.event_date.isoformat()
    partition_dir = landing_root / event_date
    partition_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_dup" if duplicate else ""
    file_name = (
        f"{sequence_number:06d}_{event.event_type.value}_{event.event_id}{suffix}.json"
    )
    return partition_dir / file_name


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def _session_start(target_date: date) -> datetime:
    start_seconds = random.randint(0, 86_399)
    start_time = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start_time + timedelta(seconds=start_seconds)


def _late_arrival_timestamp(target_date: date) -> datetime:
    late_date = target_date - timedelta(days=random.randint(1, 3))
    return _session_start(late_date)


def _with_timestamp(event: Any, timestamp: datetime) -> Any:
    payload = event.model_dump(mode="python")
    payload["event_timestamp"] = timestamp
    return event.__class__(**payload)


# ---------------------------------------------------------------------------
# Noise injection
# ---------------------------------------------------------------------------


def _corrupt_json(payload: str) -> str:
    corruption = random.choice(("missing_field", "truncate", "garbage"))
    if corruption == "truncate":
        return payload[:-1] if payload else payload
    if corruption == "garbage":
        return payload + "<<<garbage>>>"

    parsed = json.loads(payload)
    removable_keys = [
        key
        for key in parsed
        if key not in {"event_id", "event_timestamp", "event_type", "schema_version"}
    ]
    if removable_keys:
        parsed.pop(random.choice(removable_keys), None)
    return json.dumps(parsed, separators=(",", ":"), sort_keys=True)


# ---------------------------------------------------------------------------
# Random pickers (weighted distributions)
# ---------------------------------------------------------------------------


def _pick_login_status(persona: UserPersona) -> LoginStatus:
    if persona.subscription_tier == SubscriptionTier.FREE:
        return random.choices(
            population=[LoginStatus.SUCCESS, LoginStatus.FAILURE, LoginStatus.LOCKED],
            weights=(88, 9, 3),
            k=1,
        )[0]
    if persona.subscription_tier == SubscriptionTier.PRO:
        return random.choices(
            population=[LoginStatus.SUCCESS, LoginStatus.FAILURE, LoginStatus.LOCKED],
            weights=(93, 5, 2),
            k=1,
        )[0]
    return random.choices(
        population=[LoginStatus.SUCCESS, LoginStatus.FAILURE, LoginStatus.LOCKED],
        weights=(96, 3, 1),
        k=1,
    )[0]


def _pick_failure_reason(status: LoginStatus) -> FailureReason:
    if status == LoginStatus.LOCKED:
        return FailureReason.ACCOUNT_LOCKED
    return random.choices(
        population=[
            FailureReason.INVALID_PASSWORD,
            FailureReason.ACCOUNT_NOT_FOUND,
            FailureReason.MFA_TIMEOUT,
            FailureReason.MFA_INVALID,
            FailureReason.SESSION_EXPIRED,
            FailureReason.SERVER_ERROR,
            FailureReason.UNKNOWN,
        ],
        weights=(50, 15, 10, 8, 7, 5, 5),
        k=1,
    )[0]


def _pick_prompt_category(persona: UserPersona) -> PromptCategory:
    if persona.subscription_tier == SubscriptionTier.FREE:
        return random.choices(
            population=[
                PromptCategory.CONVERSATION,
                PromptCategory.WRITING,
                PromptCategory.SUMMARIZATION,
                PromptCategory.UNKNOWN,
            ],
            weights=(40, 25, 20, 15),
            k=1,
        )[0]
    if persona.subscription_tier == SubscriptionTier.PRO:
        return random.choices(
            population=[
                PromptCategory.CODING,
                PromptCategory.REASONING,
                PromptCategory.RESEARCH,
                PromptCategory.WRITING,
            ],
            weights=(35, 30, 20, 15),
            k=1,
        )[0]
    return random.choices(
        population=[
            PromptCategory.CODING,
            PromptCategory.RESEARCH,
            PromptCategory.MATH,
            PromptCategory.SUMMARIZATION,
        ],
        weights=(25, 30, 20, 25),
        k=1,
    )[0]


def _pick_model_provider(persona: UserPersona) -> ModelProvider:
    if persona.subscription_tier == SubscriptionTier.FREE:
        return random.choices(
            population=[ModelProvider.LOCAL, ModelProvider.API],
            weights=(65, 35),
            k=1,
        )[0]
    if persona.subscription_tier == SubscriptionTier.PRO:
        return random.choices(
            population=[ModelProvider.LOCAL, ModelProvider.API],
            weights=(30, 70),
            k=1,
        )[0]
    return random.choices(
        population=[ModelProvider.LOCAL, ModelProvider.API],
        weights=(10, 90),
        k=1,
    )[0]


def _pick_model_response_status(persona: UserPersona) -> ModelResponseStatus:
    return random.choices(
        population=[
            ModelResponseStatus.SUCCESS,
            ModelResponseStatus.ERROR,
            ModelResponseStatus.TIMEOUT,
            ModelResponseStatus.RATE_LIMITED,
        ],
        weights=(88, 5, 4, 3),
        k=1,
    )[0]


def _pick_error_code(status: ModelResponseStatus) -> Optional[ErrorCode]:
    if status == ModelResponseStatus.SUCCESS:
        return None
    return random.choices(
        population=[
            ErrorCode.MODEL_TIMEOUT,
            ErrorCode.MODEL_OVERLOADED,
            ErrorCode.GPU_OOM,
            ErrorCode.INVALID_PROMPT,
            ErrorCode.SAFETY_FILTER,
            ErrorCode.CONTEXT_LENGTH_EXCEEDED,
            ErrorCode.NETWORK_ERROR,
            ErrorCode.INTERNAL_ERROR,
        ],
        weights=(28, 14, 6, 12, 8, 10, 12, 10),
        k=1,
    )[0]


def _pick_feedback_type(persona: UserPersona) -> FeedbackType:
    if persona.subscription_tier == SubscriptionTier.ENTERPRISE:
        return random.choices(
            population=[
                FeedbackType.THUMBS_UP,
                FeedbackType.THUMBS_DOWN,
                FeedbackType.STAR_RATING,
                FeedbackType.TEXT,
                FeedbackType.REPORT,
            ],
            weights=(45, 10, 25, 15, 5),
            k=1,
        )[0]
    return random.choices(
        population=[
            FeedbackType.THUMBS_UP,
            FeedbackType.THUMBS_DOWN,
            FeedbackType.STAR_RATING,
            FeedbackType.TEXT,
            FeedbackType.REPORT,
        ],
        weights=(40, 18, 25, 12, 5),
        k=1,
    )[0]


def _pick_rating_value(feedback_type: FeedbackType) -> Optional[int]:
    if feedback_type != FeedbackType.STAR_RATING:
        return None
    return random.choices(
        population=[1, 2, 3, 4, 5], weights=(10, 10, 20, 25, 35), k=1
    )[0]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
