from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from src.etl.config import ETLConfig
from src.etl.transform import bronze_to_silver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_parquet(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(data)
    df.write_parquet(path)


def _valid_login_event(**overrides) -> dict:
    base = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "user_login",
        "event_timestamp": "2026-07-29T12:00:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "sess-1",
        "subscription_tier": "free",
        "device_type": "desktop",
        "device_os": "linux",
        "country_code": "US",
        "login_status": "success",
        "failure_reason": None,
    }
    base.update(overrides)
    return base


def _valid_response_event(**overrides) -> dict:
    base = {
        "event_id": "22222222-2222-2222-2222-222222222222",
        "event_type": "model_response",
        "event_timestamp": "2026-07-29T12:01:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "sess-1",
        "conversation_id": "c-1",
        "model_provider": "local",
        "model_name": "qwen",
        "status": "success",
        "error_code": None,
        "prompt_token_count": 10,
        "response_token_count": 20,
        "total_latency_ms": 500,
        "inference_latency_ms": 400,
        "queue_wait_ms": 50,
        "time_to_first_token_ms": 100,
        "estimated_cost_usd": 0.0025,
        "server_id": "srv-001",
        "server_region": "us-east-1",
        "server_instance_type": "gpu-a100",
    }
    base.update(overrides)
    return base


def _valid_feedback_event(**overrides) -> dict:
    base = {
        "event_id": "33333333-3333-3333-3333-333333333333",
        "event_type": "feedback",
        "event_timestamp": "2026-07-29T12:02:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "sess-1",
        "conversation_id": "c-1",
        "response_id": "resp-1",
        "feedback_type": "star_rating",
        "feedback_category": "accuracy",
        "rating_value": 4,
    }
    base.update(overrides)
    return base


def _valid_conv_closed_event(**overrides) -> dict:
    base = {
        "event_id": "44444444-4444-4444-4444-444444444444",
        "event_type": "conversation_closed",
        "event_timestamp": "2026-07-29T12:05:00+00:00",
        "event_date": "2026-07-29",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "sess-1",
        "conversation_id": "c-1",
        "close_reason": "user_closed",
        "turn_count": 3,
        "conversation_duration_seconds": 300,
    }
    base.update(overrides)
    return base


@pytest.fixture
def bronze(tmp_path: Path) -> Path:
    return tmp_path / "bronze"


@pytest.fixture
def silver(tmp_path: Path) -> Path:
    return tmp_path / "silver"


@pytest.fixture
def quarantine(tmp_path: Path) -> Path:
    return tmp_path / "quarantine"


@pytest.fixture
def etl_config(bronze: Path, silver: Path, quarantine: Path) -> ETLConfig:
    return ETLConfig(
        bronze_root=bronze,
        silver_root=silver,
        quarantine_root=quarantine,
    )


# ---------------------------------------------------------------------------
# Tests: deduplication
# ---------------------------------------------------------------------------


def test_duplicate_event_ids_removed(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    _write_parquet(
        bronze / target.isoformat() / "user_login.parquet",
        [_valid_login_event(), _valid_login_event()],  # same event_id twice
    )

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 1  # only 1 kept
    silver_df = pl.read_parquet(silver / "2026-07-29" / "events.parquet")
    assert len(silver_df) == 1


def test_different_event_ids_both_kept(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(event_id="id-1"),
        _valid_login_event(event_id="id-2"),
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 2
    silver_df = pl.read_parquet(silver / "2026-07-29" / "events.parquet")
    assert len(silver_df) == 2


# ---------------------------------------------------------------------------
# Tests: enum validation
# ---------------------------------------------------------------------------


def test_invalid_enum_value_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(subscription_tier="free"),
        _valid_login_event(event_id="bad-1", subscription_tier="platinum"),  # invalid
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 1  # only the valid one
    silver_df = pl.read_parquet(silver / "2026-07-29" / "events.parquet")
    assert len(silver_df) == 1
    assert silver_df["subscription_tier"][0] == "free"


def test_invalid_device_type_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(device_type="watch"),  # invalid
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


def test_null_enum_value_allowed(bronze: Path, silver: Path, etl_config: ETLConfig):
    """Null in an optional enum column should NOT be quarantined."""
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(failure_reason=None),  # null is valid for optional field
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 1


def test_invalid_feedback_category_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    """V2: feedback_category is now validated as an enum."""
    target = date(2026, 7, 29)
    events = [
        _valid_feedback_event(feedback_category="invalid_cat"),
    ]
    _write_parquet(bronze / target.isoformat() / "feedback.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


def test_invalid_close_reason_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    """V2: close_reason is now validated as an enum."""
    target = date(2026, 7, 29)
    events = [
        _valid_conv_closed_event(close_reason="deleted"),
    ]
    _write_parquet(bronze / target.isoformat() / "conversation_closed.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


# ---------------------------------------------------------------------------
# Tests: required field validation
# ---------------------------------------------------------------------------


def test_missing_required_field_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(user_id=None),  # required field is null
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


def test_missing_country_code_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    """V2: country_code is now a required field on user_login."""
    target = date(2026, 7, 29)
    events = [
        _valid_login_event(country_code=None),
    ]
    _write_parquet(bronze / target.isoformat() / "user_login.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


def test_missing_estimated_cost_quarantined(bronze: Path, silver: Path, etl_config: ETLConfig):
    """V2: estimated_cost_usd is now required on model_response."""
    target = date(2026, 7, 29)
    events = [
        _valid_response_event(estimated_cost_usd=None),
    ]
    _write_parquet(bronze / target.isoformat() / "model_response.parquet", events)

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


# ---------------------------------------------------------------------------
# Tests: multiple event types combined
# ---------------------------------------------------------------------------


def test_multiple_event_types_in_same_date(bronze: Path, silver: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    partition = bronze / target.isoformat()

    _write_parquet(partition / "user_login.parquet", [_valid_login_event()])
    _write_parquet(partition / "model_response.parquet", [_valid_response_event()])
    _write_parquet(partition / "feedback.parquet", [_valid_feedback_event()])
    _write_parquet(partition / "conversation_closed.parquet", [_valid_conv_closed_event()])

    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 4
    silver_df = pl.read_parquet(silver / "2026-07-29" / "events.parquet")
    assert len(silver_df) == 4
    event_types = sorted(silver_df["event_type"].to_list())
    assert event_types == ["conversation_closed", "feedback", "model_response", "user_login"]


# ---------------------------------------------------------------------------
# Tests: empty and edge cases
# ---------------------------------------------------------------------------


def test_empty_bronze(bronze: Path, etl_config: ETLConfig):
    meta = bronze_to_silver(etl_config)

    assert meta.bronze_rows_written == 0


def test_target_date_filter(bronze: Path, silver: Path, etl_config: ETLConfig):
    _write_parquet(
        bronze / "2026-07-28" / "user_login.parquet",
        [_valid_login_event(event_date="2026-07-28")],
    )
    _write_parquet(
        bronze / "2026-07-29" / "user_login.parquet",
        [_valid_login_event(event_date="2026-07-29", event_id="id-2")],
    )

    config = ETLConfig(
        bronze_root=bronze,
        silver_root=silver,
        quarantine_root=etl_config.quarantine_root,
        target_date=date(2026, 7, 29),
    )
    meta = bronze_to_silver(config)

    assert meta.bronze_rows_written == 1
    assert not (silver / "2026-07-28").exists()
