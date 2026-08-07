from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from src.simulator.config import SimulatorConfig
from src.simulator.models import (
    CloseReason,
    ConversationClosed,
    ConversationStarted,
    ErrorCode,
    Feedback,
    FeedbackCategory,
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
_DEFAULT_EVENTS_PER_SESSION = 4

# Model definitions: (name, cost_per_1k_input, cost_per_1k_output, avg_latency_ms)
_MODELS = {
    "gpt-4.1-mini": {"cost_input": 0.15, "cost_output": 0.60, "base_latency": 200},
    "gpt-4.1": {"cost_input": 2.00, "cost_output": 8.00, "base_latency": 800},
    "claude-3.7-sonnet": {"cost_input": 3.00, "cost_output": 15.00, "base_latency": 600},
    "mistral-large": {"cost_input": 2.00, "cost_output": 6.00, "base_latency": 450},
    "llama-3.1-70b": {"cost_input": 0.25, "cost_output": 0.80, "base_latency": 350},
}

_SERVER_IDS = ["srv-infra-001", "srv-infra-002", "srv-infra-003"]
_SERVER_REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
_SERVER_TYPES = ["gpu-a100", "gpu-t4", "cpu"]

_COUNTRY_CODES = [
    "US", "IN", "GB", "DE", "CA", "AU", "FR", "JP", "BR", "KR",
    "MX", "IT", "ES", "NL", "SE", "SG", "NZ", "IE", "CH", "PL",
]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Hourly traffic weights — mimics real SaaS patterns
# Low at night (0-6), ramps morning (7-10), peak midday (11-14), dips lunch (15),
# second peak evening (16-20), drops night (21-23)
_HOURLY_WEIGHTS = [
    1, 1, 1, 1, 1, 2,        # 00-05: dead hours
    4, 7, 12, 15, 18, 20,    # 06-11: morning ramp
    22, 24, 22, 20, 18, 16,  # 12-17: peak + afternoon dip
    14, 10, 7, 4, 3, 2,      # 18-23: evening drop
]
_WEEKDAY_MULTIPLIER = 1.0
_WEEKEND_MULTIPLIER = 0.55


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_events(config: SimulatorConfig) -> int:
    """Generate simulator events and write them to the landing zone.

    If date_range_days > 1, generates events across multiple days with
    realistic hourly and weekly traffic patterns.
    """
    landing_root = _PROJECT_ROOT / "data" / "landing"
    landing_root.mkdir(parents=True, exist_ok=True)

    user_pool_size = max(1, config.total_events // _DEFAULT_EVENTS_PER_SESSION)
    personas = create_user_pool(user_pool_size)

    written = 0
    sequence_number = 0

    for day_offset in range(config.date_range_days):
        target = config.target_date - timedelta(days=(config.date_range_days - 1 - day_offset))
        dow = target.weekday()  # 0=Monday, 6=Sunday
        is_weekend = dow >= 5
        day_multiplier = _WEEKEND_MULTIPLIER if is_weekend else _WEEKDAY_MULTIPLIER

        # Calculate how many sessions we need for this day.
        # Each session produces ~5-11 events (login + started + turns*2 + closed).
        # Use a realistic estimate of ~6 events per session to avoid burning
        # the total_events budget too fast.
        _EVENTS_PER_SESSION_ESTIMATE = 6
        day_total = max(1, int(config.total_events * day_multiplier / config.date_range_days))
        sessions_today = max(1, day_total // _EVENTS_PER_SESSION_ESTIMATE)

        for session_idx in range(sessions_today):
            # After budget is exhausted, still guarantee 1 session per remaining day
            if written >= config.total_events and session_idx > 0:
                break

            persona = personas[sequence_number % len(personas)]
            session_events = _build_session(persona, config, target, day_multiplier)

            for event in session_events:
                written += _write_event_record(
                    landing_root,
                    sequence_number,
                    event,
                    malformed_rate=config.malformed_rate,
                    duplicate_rate=config.duplicate_rate,
                    late_arrival_rate=config.late_arrival_rate,
                )
                sequence_number += 1

    return written


def main() -> int:
    count = generate_events(SimulatorConfig())
    print(f"Generated {count} events")
    return count


# ---------------------------------------------------------------------------
# Session builder
# ---------------------------------------------------------------------------


def _build_session(
    persona: UserPersona,
    config: SimulatorConfig,
    target_date: date,
    day_multiplier: float,
) -> list:
    """Build a realistic session of events for one user on one day."""
    turn_count = random.randint(_MIN_TURNS, _MAX_TURNS)
    session_id = str(uuid4())

    # Pick a realistic time within the day based on hourly weights
    session_start = _weighted_session_start(target_date)

    events: list = []
    current_timestamp = session_start

    # 1) User Login
    session_id_for_login = session_id
    login_status = _pick_login_status(persona)
    login = UserLogin(
        event_timestamp=current_timestamp,
        schema_version=config.schema_version,
        user_id=persona.user_id,
        session_id=session_id_for_login,
        subscription_tier=persona.subscription_tier,
        device_type=persona.device_type,
        device_os=persona.device_os,
        country_code=random.choice(_COUNTRY_CODES),
        login_status=login_status,
        failure_reason=None,
    )
    if login_status != LoginStatus.SUCCESS:
        # Failed login — no session created, session_id is null
        login = login.model_copy(update={"session_id": None})
        login = login.model_copy(
            update={"failure_reason": _pick_failure_reason(login_status)}
        )
        events.append(login)
        # Failed login → no conversation follows
        return events

    events.append(login)

    # 2) Conversation Started
    current_timestamp += timedelta(seconds=random.randint(5, 60))
    events.append(
        ConversationStarted(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            session_id=session_id,
            subscription_tier=persona.subscription_tier,
            conversation_id=session_id,
        )
    )

    # 3-4) Prompt → Response turns
    for _ in range(turn_count):
        current_timestamp += timedelta(seconds=random.randint(10, 180))
        prompt_char_count = _pick_prompt_length(persona)
        prompt_token_count = max(1, prompt_char_count // random.randint(3, 5))
        prompt_category = _pick_prompt_category(persona)
        events.append(
            PromptSubmitted(
                event_timestamp=current_timestamp,
                schema_version=config.schema_version,
                user_id=persona.user_id,
                session_id=session_id,
                conversation_id=session_id,
                prompt_char_count=prompt_char_count,
                prompt_token_count=prompt_token_count,
                prompt_category=prompt_category,
            )
        )

        current_timestamp += timedelta(seconds=random.randint(1, 30))
        model_name = _pick_model_name(persona)
        model_info = _MODELS[model_name]
        response_status = _pick_model_response_status(persona)

        # Generate latency with model-appropriate distribution + evening spike
        latency = _pick_latency(model_info, current_timestamp)

        response_token_count = (
            0 if response_status != ModelResponseStatus.SUCCESS
            else random.randint(10, 350)
        )

        # Calculate cost: (input_tokens / 1000 * cost_per_1k_input) + (output_tokens / 1000 * cost_per_1k_output)
        cost_input = (prompt_token_count / 1000.0) * model_info["cost_input"]
        cost_output = (response_token_count / 1000.0) * model_info["cost_output"]
        estimated_cost = round(cost_input + cost_output, 6)

        queue_wait_ms = random.randint(0, 900)
        inference_latency = max(50, latency - queue_wait_ms)
        ttft = random.randint(10, max(10, inference_latency // 3)) if response_status == ModelResponseStatus.SUCCESS else 0

        response = ModelResponse(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            session_id=session_id,
            conversation_id=session_id,
            model_provider=_pick_model_provider(persona),
            model_name=model_name,
            status=response_status,
            error_code=_pick_error_code(response_status),
            prompt_token_count=prompt_token_count,
            response_token_count=response_token_count,
            total_latency_ms=latency,
            inference_latency_ms=inference_latency,
            queue_wait_ms=queue_wait_ms,
            time_to_first_token_ms=ttft,
            estimated_cost_usd=estimated_cost,
            server_id=random.choice(_SERVER_IDS),
            server_region=random.choice(_SERVER_REGIONS),
            server_instance_type=random.choice(_SERVER_TYPES),
        )
        events.append(response)

        # 5) Optional Feedback
        if random.random() < _FEEDBACK_PROBABILITY:
            current_timestamp += timedelta(seconds=random.randint(5, 120))
            feedback_type = _pick_feedback_type(persona)
            feedback_category = _pick_feedback_category()
            # The response_id must link to the event_id of the ModelResponse
            events.append(
                Feedback(
                    event_timestamp=current_timestamp,
                    schema_version=config.schema_version,
                    user_id=persona.user_id,
                    session_id=session_id,
                    conversation_id=session_id,
                    response_id=str(response.event_id),
                    feedback_type=feedback_type,
                    feedback_category=feedback_category,
                    rating_value=_pick_rating_value(feedback_type),
                )
            )

    # 6) Conversation Closed
    current_timestamp += timedelta(seconds=random.randint(5, 180))
    events.append(
        ConversationClosed(
            event_timestamp=current_timestamp,
            schema_version=config.schema_version,
            user_id=persona.user_id,
            session_id=session_id,
            conversation_id=session_id,
            close_reason=_pick_close_reason(),
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
) -> int:
    if random.random() < late_arrival_rate:
        late_date = event.event_date - timedelta(days=random.randint(1, 3))
        late_ts = _session_start_for_date(late_date)
        event = event.model_copy(update={"event_timestamp": late_ts})

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


def _weighted_session_start(target_date: date) -> datetime:
    """Pick a session start time weighted by hour-of-day traffic patterns."""
    hour = random.choices(
        population=list(range(24)),
        weights=_HOURLY_WEIGHTS,
        k=1,
    )[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    start_time = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start_time + timedelta(hours=hour, minutes=minute, seconds=second)


def _session_start_for_date(target_date: date) -> datetime:
    start_seconds = random.randint(0, 86_399)
    start_time = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start_time + timedelta(seconds=start_seconds)


# ---------------------------------------------------------------------------
# Latency generator with evening spike pattern
# ---------------------------------------------------------------------------


def _pick_latency(model_info: dict, timestamp: datetime) -> int:
    """Generate realistic latency with evening spike pattern.

    Q3 (question: "Why is latency spiking every evening?") is answered
    by injecting higher latency during evening hours (16-22 UTC).
    """
    hour = timestamp.hour
    base = model_info["base_latency"]

    # Evening spike: 16-22 UTC, peak at 19-20
    if 16 <= hour <= 22:
        spike_factor = 1.0 + 2.5 * math.sin(math.pi * (hour - 16) / 6)
    else:
        spike_factor = 1.0

    # Random jitter (log-normal distribution)
    jitter = random.gauss(1.0, 0.3)
    jitter = max(0.5, min(jitter, 3.0))  # clamp to [0.5, 3.0]

    latency = int(base * spike_factor * jitter)

    # Occasional very high latency outliers (5% chance)
    if random.random() < 0.05:
        latency = int(latency * random.uniform(3.0, 8.0))

    return max(50, latency)


def _pick_prompt_length(persona: UserPersona) -> int:
    """Generate realistic prompt lengths. Power users write longer prompts."""
    if persona.subscription_tier == SubscriptionTier.ENTERPRISE:
        return int(random.lognormvariate(5.0, 0.8))
    if persona.subscription_tier == SubscriptionTier.PRO:
        return int(random.lognormvariate(4.5, 0.9))
    return int(random.lognormvariate(4.0, 1.0))


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
            FailureReason.ACCOUNT_LOCKED,
            FailureReason.MFA_TIMEOUT,
            FailureReason.MFA_INVALID,
            FailureReason.SESSION_EXPIRED,
            FailureReason.SERVER_ERROR,
            FailureReason.UNKNOWN,
        ],
        weights=(50, 15, 10, 8, 7, 5, 3, 2),
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


def _pick_model_name(persona: UserPersona) -> str:
    """Pick model based on subscription tier — enterprise gets better models."""
    if persona.subscription_tier == SubscriptionTier.ENTERPRISE:
        return random.choices(
            population=list(_MODELS.keys()),
            weights=(10, 30, 30, 20, 10),
            k=1,
        )[0]
    if persona.subscription_tier == SubscriptionTier.PRO:
        return random.choices(
            population=list(_MODELS.keys()),
            weights=(25, 20, 20, 20, 15),
            k=1,
        )[0]
    return random.choices(
        population=list(_MODELS.keys()),
        weights=(50, 5, 5, 10, 30),
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


def _pick_feedback_category() -> Optional[FeedbackCategory]:
    """Pick a feedback category. Returns None ~15% of the time."""
    if random.random() < 0.15:
        return None
    return random.choices(
        population=[
            FeedbackCategory.ACCURACY,
            FeedbackCategory.TONE,
            FeedbackCategory.SPEED,
            FeedbackCategory.RELEVANCE,
            FeedbackCategory.HELPFULNESS,
        ],
        weights=(30, 15, 15, 25, 15),
        k=1,
    )[0]


def _pick_rating_value(feedback_type: FeedbackType) -> Optional[int]:
    if feedback_type != FeedbackType.STAR_RATING:
        return None
    return random.choices(
        population=[1, 2, 3, 4, 5], weights=(10, 10, 20, 25, 35), k=1
    )[0]


def _pick_close_reason() -> CloseReason:
    return random.choices(
        population=[
            CloseReason.USER_CLOSED,
            CloseReason.TIMEOUT,
            CloseReason.SYSTEM_ERROR,
            CloseReason.MAX_TURNS_REACHED,
        ],
        weights=(70, 12, 8, 10),
        k=1,
    )[0]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
