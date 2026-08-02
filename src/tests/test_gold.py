from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from src.etl.config import ETLConfig
from src.etl.gold import silver_to_gold


# ── Helpers ────────────────────────────────────────────────────────────────


def _write_silver(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(data)
    df.write_parquet(path)


def _event(event_type: str, **fields) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": "2026-07-29T12:00:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "1.0",
        **fields,
    }


def _login(**kw) -> dict:
    return _event("user_login", **kw)


def _prompt(**kw) -> dict:
    return _event("prompt_submitted", **kw)


def _response(**kw) -> dict:
    return _event("model_response", **kw)


def _feedback(**kw) -> dict:
    return _event("feedback", **kw)


def _conv_closed(**kw) -> dict:
    return _event("conversation_closed", **kw)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def silver(tmp_path: Path) -> Path:
    return tmp_path / "silver"


@pytest.fixture
def gold(tmp_path: Path) -> Path:
    return tmp_path / "gold"


@pytest.fixture
def quarantine(tmp_path: Path) -> Path:
    return tmp_path / "quarantine"


@pytest.fixture
def etl_config(silver: Path, gold: Path, quarantine: Path) -> ETLConfig:
    return ETLConfig(
        silver_root=silver,
        gold_root=gold,
        quarantine_root=quarantine,
    )


# ── Model Performance ──────────────────────────────────────────────────────


def test_model_perf_success_and_error_counts(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _response(
            user_id="u-1", conversation_id="c-1",
            model_provider="local", model_name="qwen",
            status="success", error_code=None,
            prompt_token_count=25, response_token_count=200,
            total_latency_ms=500, inference_latency_ms=400,
            queue_wait_ms=50, time_to_first_token_ms=100,
        ),
        _response(
            user_id="u-1", conversation_id="c-1",
            model_provider="local", model_name="qwen",
            status="success", error_code=None,
            prompt_token_count=25, response_token_count=200,
            total_latency_ms=300, inference_latency_ms=250,
            queue_wait_ms=30, time_to_first_token_ms=80,
        ),
        _response(
            user_id="u-1", conversation_id="c-1",
            model_provider="local", model_name="qwen",
            status="error", error_code="MODEL_TIMEOUT",
            prompt_token_count=25, response_token_count=0,
            total_latency_ms=800, inference_latency_ms=750,
            queue_wait_ms=20, time_to_first_token_ms=0,
        ),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    perf = pl.read_parquet(gold / target.isoformat() / "model_perf.parquet")

    assert len(perf) == 1
    assert perf["request_count"][0] == 3
    assert perf["success_count"][0] == 2
    assert perf["error_count"][0] == 1
    assert perf["avg_latency_ms"][0] == 533.33


def test_model_perf_multiple_models(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _response(
            model_name="qwen", model_provider="local", total_latency_ms=500,
            user_id="u-1", conversation_id="c-1", status="success",
            error_code=None, prompt_token_count=25, response_token_count=200,
            inference_latency_ms=400, queue_wait_ms=50, time_to_first_token_ms=100,
        ),
        _response(
            model_name="qwen", model_provider="local", total_latency_ms=300,
            user_id="u-2", conversation_id="c-2", status="success",
            error_code=None, prompt_token_count=30, response_token_count=150,
            inference_latency_ms=250, queue_wait_ms=30, time_to_first_token_ms=80,
        ),
        _response(
            model_name="gpt-4", model_provider="api", total_latency_ms=200,
            user_id="u-3", conversation_id="c-3", status="success",
            error_code=None, prompt_token_count=20, response_token_count=100,
            inference_latency_ms=150, queue_wait_ms=20, time_to_first_token_ms=60,
        ),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    perf = pl.read_parquet(gold / target.isoformat() / "model_perf.parquet")

    assert len(perf) == 2
    qwen = perf.filter(pl.col("model_name") == "qwen")
    assert qwen["request_count"][0] == 2
    assert qwen["avg_latency_ms"][0] == 400.0
    gpt = perf.filter(pl.col("model_name") == "gpt-4")
    assert gpt["request_count"][0] == 1


# ── User Activity ───────────────────────────────────────────────────────────


def test_user_activity_by_tier(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _login(
            user_id="u-1", subscription_tier="free",
            device_type="desktop", device_os="linux",
            login_status="success", failure_reason=None,
        ),
        _login(
            user_id="u-2", subscription_tier="free",
            device_type="mobile", device_os="android",
            login_status="success", failure_reason=None,
        ),
        _login(
            user_id="u-3", subscription_tier="pro",
            device_type="desktop", device_os="windows",
            login_status="failure", failure_reason="invalid_password",
        ),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    activity = pl.read_parquet(gold / target.isoformat() / "user_activity.parquet")

    assert len(activity) == 2
    free_row = activity.filter(pl.col("subscription_tier") == "free")
    assert free_row["unique_users"][0] == 2
    assert free_row["successful_logins"][0] == 2
    pro_row = activity.filter(pl.col("subscription_tier") == "pro")
    assert pro_row["failed_logins"][0] == 1


# ── Conversation Stats ─────────────────────────────────────────────────────


def test_conversation_stats_global(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _conv_closed(user_id="u-1", conversation_id="c-1", turn_count=5, conversation_duration_seconds=120),
        _conv_closed(user_id="u-2", conversation_id="c-2", turn_count=10, conversation_duration_seconds=300),
        _conv_closed(user_id="u-3", conversation_id="c-3", turn_count=3, conversation_duration_seconds=60),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    stats = pl.read_parquet(gold / target.isoformat() / "conversation_stats.parquet")

    assert len(stats) == 1
    assert stats["total_conversations"][0] == 3
    assert stats["avg_turns"][0] == 6.0
    assert stats["max_turns"][0] == 10


# ── Prompt Analytics ─────────────────────────────────────────────────────


def test_prompt_analytics_by_category(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _prompt(
            user_id="u-1", conversation_id="c-1",
            prompt_category="coding", prompt_char_count=100, prompt_token_count=20,
        ),
        _prompt(
            user_id="u-1", conversation_id="c-1",
            prompt_category="coding", prompt_char_count=150, prompt_token_count=30,
        ),
        _prompt(
            user_id="u-2", conversation_id="c-2",
            prompt_category="writing", prompt_char_count=80, prompt_token_count=15,
        ),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    analytics = pl.read_parquet(gold / target.isoformat() / "prompt_analytics.parquet")

    assert len(analytics) == 2
    coding = analytics.filter(pl.col("prompt_category") == "coding")
    assert coding["total_prompts"][0] == 2
    assert coding["total_input_tokens"][0] == 50


# ── Feedback Summary ─────────────────────────────────────────────────────


def test_feedback_summary_with_ratings(silver, gold, etl_config):
    target = date(2026, 7, 29)
    data = [
        _feedback(
            user_id="u-1", conversation_id="c-1", response_id="r-1",
            feedback_type="star_rating", rating_value=4,
        ),
        _feedback(
            user_id="u-2", conversation_id="c-2", response_id="r-2",
            feedback_type="star_rating", rating_value=5,
        ),
        _feedback(
            user_id="u-3", conversation_id="c-3", response_id="r-3",
            feedback_type="thumbs_up", rating_value=None,
        ),
    ]
    _write_silver(silver / target.isoformat() / "events.parquet", data)

    meta = silver_to_gold(etl_config)
    fb = pl.read_parquet(gold / target.isoformat() / "feedback_summary.parquet")

    assert len(fb) == 2
    stars = fb.filter(pl.col("feedback_type") == "star_rating")
    assert stars["count"][0] == 2
    assert stars["avg_rating"][0] == 4.5
    thumbs = fb.filter(pl.col("feedback_type") == "thumbs_up")
    assert thumbs["avg_rating"][0] is None


# ── Edge Cases ────────────────────────────────────────────────────────────


def test_empty_silver_no_gold_files(silver, etl_config):
    meta = silver_to_gold(etl_config)

    assert meta.silver_rows_read == 0
    assert meta.gold_files_written == 0


def test_target_date_filter(silver, gold, etl_config):
    _write_silver(
        silver / "2026-07-28" / "events.parquet",
        [
            _login(
                user_id="u-1", subscription_tier="free",
                device_type="desktop", device_os="linux",
                login_status="success", failure_reason=None,
            )
        ],
    )
    _write_silver(
        silver / "2026-07-29" / "events.parquet",
        [
            _login(
                user_id="u-2", subscription_tier="pro",
                device_type="mobile", device_os="ios",
                login_status="success", failure_reason=None,
            )
        ],
    )

    config = ETLConfig(
        silver_root=silver,
        gold_root=gold,
        quarantine_root=etl_config.quarantine_root,
        target_date=date(2026, 7, 29),
    )
    meta = silver_to_gold(config)

    assert meta.silver_rows_read == 1
    assert not (gold / "2026-07-28").exists()
    assert (gold / "2026-07-29" / "user_activity.parquet").exists()


def test_no_file_for_missing_event_type(silver, gold, etl_config):
    """If a date has only logins, there should be no model_perf file."""
    target = date(2026, 7, 29)
    _write_silver(
        silver / target.isoformat() / "events.parquet",
        [
            _login(
                user_id="u-1", subscription_tier="free",
                device_type="desktop", device_os="linux",
                login_status="success", failure_reason=None,
            )
        ],
    )

    meta = silver_to_gold(etl_config)

    assert (gold / target.isoformat() / "user_activity.parquet").exists()
    assert not (gold / target.isoformat() / "model_perf.parquet").exists()