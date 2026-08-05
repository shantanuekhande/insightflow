from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from src.etl.config import ETLConfig
from src.etl.gold import silver_to_gold


# ---------------------------------------------------------------------------
# Helpers — all fields explicit, no defaults
# ---------------------------------------------------------------------------


def _write_silver(silver_root: Path, event_date: str, events: list) -> None:
    """Write a Silver parquet file for testing."""
    partition = silver_root / event_date
    partition.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(events)
    df.write_parquet(partition / "events.parquet")


def _login(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "l-001"),
        "event_type": "user_login",
        "event_timestamp": "2026-07-29T09:00:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "subscription_tier": kw.get("subscription_tier", "free"),
        "device_type": kw.get("device_type", "desktop"),
        "device_os": kw.get("device_os", "linux"),
        "country_code": kw.get("country_code", "US"),
        "login_status": kw.get("login_status", "success"),
        "failure_reason": kw.get("failure_reason"),
    }


def _conv_start(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "cs-001"),
        "event_type": "conversation_started",
        "event_timestamp": "2026-07-29T09:01:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "subscription_tier": kw.get("subscription_tier", "free"),
        "conversation_id": kw.get("conversation_id", "conv-1"),
    }


def _prompt(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "ps-001"),
        "event_type": "prompt_submitted",
        "event_timestamp": "2026-07-29T09:02:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "conversation_id": kw.get("conversation_id", "conv-1"),
        "prompt_char_count": kw.get("prompt_char_count", 100),
        "prompt_token_count": kw.get("prompt_token_count", 25),
        "prompt_category": kw.get("prompt_category", "coding"),
    }


def _response(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "mr-001"),
        "event_type": "model_response",
        "event_timestamp": "2026-07-29T09:03:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "conversation_id": kw.get("conversation_id", "conv-1"),
        "model_provider": kw.get("model_provider", "local"),
        "model_name": kw.get("model_name", "qwen"),
        "status": kw.get("status", "success"),
        "error_code": kw.get("error_code"),
        "prompt_token_count": kw.get("prompt_token_count", 25),
        "response_token_count": kw.get("response_token_count", 150),
        "total_latency_ms": kw.get("total_latency_ms", 500),
        "inference_latency_ms": kw.get("inference_latency_ms", 400),
        "queue_wait_ms": kw.get("queue_wait_ms", 50),
        "time_to_first_token_ms": kw.get("time_to_first_token_ms", 100),
        "estimated_cost_usd": kw.get("estimated_cost_usd", 0.005),
        "server_id": kw.get("server_id", "srv-001"),
        "server_region": kw.get("server_region", "us-east-1"),
        "server_instance_type": kw.get("server_instance_type", "gpu-a100"),
    }


def _feedback(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "fb-001"),
        "event_type": "feedback",
        "event_timestamp": "2026-07-29T09:04:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "conversation_id": kw.get("conversation_id", "conv-1"),
        "response_id": kw.get("response_id", "resp-001"),
        "feedback_type": kw.get("feedback_type", "star_rating"),
        "feedback_category": kw.get("feedback_category", "accuracy"),
        "rating_value": kw.get("rating_value", 4),
    }


def _conv_closed(**kw) -> dict:
    return {
        "event_id": kw.get("event_id", "cc-001"),
        "event_type": "conversation_closed",
        "event_timestamp": "2026-07-29T09:10:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": kw.get("user_id", "u-1"),
        "session_id": kw.get("session_id", "sess-1"),
        "conversation_id": kw.get("conversation_id", "conv-1"),
        "close_reason": kw.get("close_reason", "user_closed"),
        "turn_count": kw.get("turn_count", 3),
        "conversation_duration_seconds": kw.get("conversation_duration_seconds", 600),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def silver(tmp_path: Path) -> Path:
    return tmp_path / "silver"


@pytest.fixture
def gold(tmp_path: Path) -> Path:
    return tmp_path / "gold"


@pytest.fixture
def etl_config(silver: Path, gold: Path) -> ETLConfig:
    return ETLConfig(silver_root=silver, gold_root=gold)


# ---------------------------------------------------------------------------
# Tests: model_perf (Q1 cost, Q2 errors, Q3 latency)
# ---------------------------------------------------------------------------


def test_model_perf_success_and_error_counts(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q2: error counts per model."""
    _write_silver(silver, "2026-07-29", [
        _response(model_name="qwen", status="success", event_id="mr-1"),
        _response(model_name="qwen", status="success", event_id="mr-2"),
        _response(model_name="qwen", status="error", event_id="mr-3"),
        _response(model_name="gpt-4.1", status="success", event_id="mr-4"),
        _response(model_name="gpt-4.1", status="timeout", event_id="mr-5"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "model_perf.parquet")

    assert len(df) == 2
    qwen = df.filter(pl.col("model_name") == "qwen").row(0, named=True)
    gpt = df.filter(pl.col("model_name") == "gpt-4.1").row(0, named=True)

    assert qwen["invocation_count"] == 3
    assert qwen["success_count"] == 2
    assert qwen["error_count"] == 1
    assert gpt["timeout_count"] == 1


def test_model_perf_cost_tracking(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q1: cost tracking per model."""
    _write_silver(silver, "2026-07-29", [
        _response(model_name="qwen", estimated_cost_usd=0.01, prompt_token_count=100, response_token_count=200, event_id="mr-1"),
        _response(model_name="gpt-4.1", estimated_cost_usd=0.05, prompt_token_count=50, response_token_count=100, event_id="mr-2"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "model_perf.parquet")

    qwen = df.filter(pl.col("model_name") == "qwen").row(0, named=True)
    gpt = df.filter(pl.col("model_name") == "gpt-4.1").row(0, named=True)

    assert qwen["total_cost_usd"] == 0.01
    assert qwen["total_input_tokens"] == 100
    assert qwen["total_output_tokens"] == 200
    assert gpt["total_cost_usd"] == 0.05


def test_model_perf_latency_percentiles(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q3: latency percentiles are computed."""
    # Create 10 responses with different latencies
    events = []
    for i in range(10):
        events.append(_response(
            event_id=f"mr-{i}",
            model_name="qwen",
            total_latency_ms=100 * (i + 1),  # 100, 200, ..., 1000
        ))

    _write_silver(silver, "2026-07-29", events)
    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "model_perf.parquet")

    row = df.row(0, named=True)
    assert row["avg_latency_ms"] == 550.0  # mean of 100..1000
    assert row["p50_latency_ms"] is not None
    assert row["p95_latency_ms"] is not None
    assert row["p99_latency_ms"] is not None


# ---------------------------------------------------------------------------
# Tests: user_activity (Q4 resource consumption)
# ---------------------------------------------------------------------------


def test_user_activity_tracks_tokens_and_cost(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q4: per-user token usage and cost."""
    _write_silver(silver, "2026-07-29", [
        _login(user_id="u-1"),
        _response(user_id="u-1", prompt_token_count=50, response_token_count=200, estimated_cost_usd=0.02, event_id="mr-1"),
        _response(user_id="u-1", prompt_token_count=30, response_token_count=100, estimated_cost_usd=0.01, event_id="mr-2"),
        _response(user_id="u-1", prompt_token_count=20, response_token_count=50, estimated_cost_usd=0.005, event_id="mr-3"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "user_activity.parquet")

    row = df.row(0, named=True)
    assert row["user_id"] == "u-1"
    assert row["total_input_tokens"] == 100
    assert row["total_output_tokens"] == 350
    assert row["total_cost_usd"] == 0.035
    assert row["total_requests"] == 3


def test_user_activity_multiple_users_sorted_by_cost(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q4: users sorted by cost descending."""
    _write_silver(silver, "2026-07-29", [
        _login(user_id="u-1", event_id="l-1"),
        _login(user_id="u-2", event_id="l-2"),
        _response(user_id="u-1", estimated_cost_usd=0.01, event_id="mr-1"),
        _response(user_id="u-2", estimated_cost_usd=0.05, event_id="mr-2"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "user_activity.parquet")

    assert len(df) == 2
    first_user = df.row(0, named=True)
    assert first_user["user_id"] == "u-2"  # higher cost first


# ---------------------------------------------------------------------------
# Tests: feedback_summary (Q5 satisfaction)
# ---------------------------------------------------------------------------


def test_feedback_summary_rating_distribution(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q5: rating distribution (1-5 breakdown)."""
    _write_silver(silver, "2026-07-29", [
        _feedback(rating_value=5, event_id="fb-1"),
        _feedback(rating_value=5, event_id="fb-2"),
        _feedback(rating_value=4, event_id="fb-3"),
        _feedback(rating_value=3, event_id="fb-4"),
        _feedback(rating_value=1, event_id="fb-5"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "feedback_summary.parquet")

    row = df.row(0, named=True)
    assert row["count"] == 5
    assert row["rating_5"] == 2
    assert row["rating_4"] == 1
    assert row["rating_3"] == 1
    assert row["rating_1"] == 1
    assert row["rating_2"] == 0
    assert row["avg_rating"] == 3.6  # (5+5+4+3+1)/5


def test_feedback_categories_broken_down(silver: Path, gold: Path, etl_config: ETLConfig):
    """Q5: feedback categories are tracked separately."""
    _write_silver(silver, "2026-07-29", [
        _feedback(feedback_category="accuracy", rating_value=3, event_id="fb-1"),
        _feedback(feedback_category="speed", rating_value=5, event_id="fb-2"),
        _feedback(feedback_category="accuracy", rating_value=4, event_id="fb-3"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "feedback_categories.parquet")

    assert len(df) == 2
    accuracy = df.filter(pl.col("feedback_category") == "accuracy").row(0, named=True)
    assert accuracy["count"] == 2
    speed = df.filter(pl.col("feedback_category") == "speed").row(0, named=True)
    assert speed["count"] == 1


# ---------------------------------------------------------------------------
# Tests: conversation_stats
# ---------------------------------------------------------------------------


def test_conversation_stats_global(silver: Path, gold: Path, etl_config: ETLConfig):
    """Conversation stats are global (one row per day)."""
    _write_silver(silver, "2026-07-29", [
        _conv_start(conversation_id="c-1", event_id="cs-1"),
        _conv_start(conversation_id="c-2", event_id="cs-2"),
        _conv_closed(conversation_id="c-1", turn_count=3, conversation_duration_seconds=300, event_id="cc-1"),
        _conv_closed(conversation_id="c-2", turn_count=5, conversation_duration_seconds=600, event_id="cc-2"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "conversation_stats.parquet")

    assert len(df) == 1
    row = df.row(0, named=True)
    assert row["total_conversations_started"] == 2
    assert row["total_conversations_closed"] == 2
    assert row["avg_turns"] == 4.0
    assert row["max_turns"] == 5
    assert row["avg_duration_seconds"] == 450.0
    assert row["user_closed_pct"] == 100.0


# ---------------------------------------------------------------------------
# Tests: prompt_analytics
# ---------------------------------------------------------------------------


def test_prompt_analytics_by_category(silver: Path, gold: Path, etl_config: ETLConfig):
    """Prompt analytics grouped by category."""
    _write_silver(silver, "2026-07-29", [
        _prompt(prompt_category="coding", prompt_char_count=200, prompt_token_count=50, event_id="ps-1"),
        _prompt(prompt_category="coding", prompt_char_count=100, prompt_token_count=25, event_id="ps-2"),
        _prompt(prompt_category="writing", prompt_char_count=300, prompt_token_count=75, event_id="ps-3"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "prompt_analytics.parquet")

    assert len(df) == 2
    coding = df.filter(pl.col("prompt_category") == "coding").row(0, named=True)
    assert coding["submission_count"] == 2
    assert coding["avg_prompt_length"] == 150.0
    writing = df.filter(pl.col("prompt_category") == "writing").row(0, named=True)
    assert writing["submission_count"] == 1


# ---------------------------------------------------------------------------
# Tests: empty and edge cases
# ---------------------------------------------------------------------------


def test_empty_silver_writes_empty_tables(silver: Path, gold: Path, etl_config: ETLConfig):
    """Empty Silver still writes all Gold tables with correct schemas."""
    _write_silver(silver, "2026-07-29", [])
    # Write an empty DataFrame manually
    partition = silver / "2026-07-29"
    partition.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(schema={"event_type": pl.Utf8}).write_parquet(
        partition / "events.parquet"
    )

    silver_to_gold(etl_config)

    assert (gold / "2026-07-29" / "model_perf.parquet").exists()
    assert (gold / "2026-07-29" / "user_activity.parquet").exists()
    assert (gold / "2026-07-29" / "conversation_stats.parquet").exists()
    assert (gold / "2026-07-29" / "prompt_analytics.parquet").exists()
    assert (gold / "2026-07-29" / "feedback_summary.parquet").exists()


def test_target_date_filter(silver: Path, gold: Path, etl_config: ETLConfig):
    """Only processes the target date partition."""
    _write_silver(silver, "2026-07-28", [_response(event_id="mr-old")])
    _write_silver(silver, "2026-07-29", [_response(event_id="mr-new")])

    config = ETLConfig(
        silver_root=silver,
        gold_root=gold,
        target_date=date(2026, 7, 29),
    )
    silver_to_gold(config)

    assert (gold / "2026-07-29" / "model_perf.parquet").exists()
    assert not (gold / "2026-07-28").exists()


def test_no_response_events_no_model_perf_rows(silver: Path, gold: Path, etl_config: ETLConfig):
    """If no model_response events, model_perf should be empty schema."""
    _write_silver(silver, "2026-07-29", [
        _login(event_id="l-1"),
        _prompt(event_id="ps-1"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "model_perf.parquet")
    assert len(df) == 0


def test_no_feedback_events_empty_feedback(silver: Path, gold: Path, etl_config: ETLConfig):
    """If no feedback events, feedback tables should be empty schema."""
    _write_silver(silver, "2026-07-29", [
        _login(event_id="l-1"),
        _response(event_id="mr-1"),
    ])

    silver_to_gold(etl_config)
    df = pl.read_parquet(gold / "2026-07-29" / "feedback_summary.parquet")
    assert len(df) == 0
    assert (gold / "2026-07-29" / "feedback_categories.parquet").exists()
