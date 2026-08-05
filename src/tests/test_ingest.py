from __future__ import annotations

import json
from datetime import date, timezone
from pathlib import Path

import pytest

from src.etl.ingest import ingest
from src.etl.config import ETLConfig
from src.etl.metadata import IngestMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_json(dirpath: Path, filename: str, data: dict | str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / filename
    content = data if isinstance(data, str) else json.dumps(data)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def landing(tmp_path: Path) -> Path:
    return tmp_path / "landing"


@pytest.fixture
def bronze(tmp_path: Path) -> Path:
    return tmp_path / "bronze"


@pytest.fixture
def quarantine(tmp_path: Path) -> Path:
    return tmp_path / "quarantine"


@pytest.fixture
def etl_config(landing: Path, bronze: Path, quarantine: Path) -> ETLConfig:
    return ETLConfig(
        landing_root=landing,
        bronze_root=bronze,
        quarantine_root=quarantine,
    )


def _valid_event() -> dict:
    return {
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


# ---------------------------------------------------------------------------
# Tests: valid events reach Bronze
# ---------------------------------------------------------------------------


def test_valid_event_ingested_to_bronze(landing: Path, bronze: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    _write_json(landing / target.isoformat(), "evt_001.json", _valid_event())

    meta = ingest(etl_config)

    assert meta.landing_files_scanned == 1
    assert meta.bronze_rows_written == 1
    assert meta.bronze_files_written == 1
    assert meta.quarantined_files == 0

    # Verify Parquet file exists and is readable
    parquet_file = bronze / "2026-07-29" / "user_login.parquet"
    assert parquet_file.exists()


def test_multiple_event_types_separate_files(landing: Path, bronze: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    partition = landing / target.isoformat()

    login = _valid_event()
    _write_json(partition, "evt_001.json", login)

    response = _valid_event()
    response["event_id"] = "22222222-2222-2222-2222-222222222222"
    response["event_type"] = "model_response"
    response["user_id"] = "u-1"
    response["session_id"] = "sess-1"
    response["conversation_id"] = "c-1"
    response["model_provider"] = "local"
    response["model_name"] = "qwen"
    response["status"] = "success"
    response["prompt_token_count"] = 10
    response["response_token_count"] = 20
    response["total_latency_ms"] = 500
    response["inference_latency_ms"] = 400
    response["queue_wait_ms"] = 50
    response["time_to_first_token_ms"] = 100
    response["estimated_cost_usd"] = 0.0025
    response["server_id"] = "srv-001"
    response["server_region"] = "us-east-1"
    response["server_instance_type"] = "gpu-a100"
    response["error_code"] = None
    _write_json(partition, "evt_002.json", response)

    meta = ingest(etl_config)

    assert meta.bronze_rows_written == 2
    assert meta.bronze_files_written == 2
    assert (bronze / "2026-07-29" / "user_login.parquet").exists()
    assert (bronze / "2026-07-29" / "model_response.parquet").exists()


# ---------------------------------------------------------------------------
# Tests: malformed events go to quarantine
# ---------------------------------------------------------------------------


def test_malformed_json_quarantined(landing: Path, quarantine: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    _write_json(landing / target.isoformat(), "bad_001.json", "{not valid json!!!")

    meta = ingest(etl_config)

    assert meta.landing_files_scanned == 1
    assert meta.bronze_rows_written == 0
    assert meta.quarantined_files == 1
    assert "JSONDecodeError" in meta.errors_by_type

    # Quarantine file should exist with original content + reason
    q_file = quarantine / "2026-07-29" / "bad_001.json"
    assert q_file.exists()
    q_record = json.loads(q_file.read_text(encoding="utf-8"))
    assert "quarantine_reason" in q_record
    assert "original_content" in q_record


def test_missing_required_fields_quarantined(landing: Path, quarantine: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    incomplete = {"event_id": "aaa", "event_type": "user_login"}
    _write_json(landing / target.isoformat(), "incomplete.json", incomplete)

    meta = ingest(etl_config)

    assert meta.quarantined_files == 1
    assert meta.bronze_rows_written == 0
    assert "ValueError" in meta.errors_by_type


def test_garbage_suffix_quarantined(landing: Path, quarantine: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    event = _valid_event()
    payload = json.dumps(event) + "<<<garbage>>>"
    _write_json(landing / target.isoformat(), "garbage.json", payload)

    meta = ingest(etl_config)

    assert meta.quarantined_files == 1


# ---------------------------------------------------------------------------
# Tests: metadata tracking
# ---------------------------------------------------------------------------


def test_metadata_tracks_event_breakdown(landing: Path, etl_config: ETLConfig):
    target = date(2026, 7, 29)
    partition = landing / target.isoformat()

    for i in range(3):
        evt = _valid_event()
        evt["event_id"] = f"id-{i}"
        _write_json(partition, f"evt_{i:03d}.json", evt)

    meta = ingest(etl_config)

    assert meta.events_by_type == {"user_login": 3}
    assert meta.duration_seconds >= 0
    assert meta.summary()  # just ensure it doesn't crash
    d = meta.to_dict()
    assert d["landing_files_scanned"] == 3
    assert d["bronze_rows_written"] == 3


def test_target_date_filters_partitions(landing: Path, bronze: Path, etl_config: ETLConfig):
    _write_json(landing / "2026-07-28", "old.json", _valid_event())
    _write_json(landing / "2026-07-29", "new.json", _valid_event())

    config = ETLConfig(
        landing_root=landing,
        bronze_root=bronze,
        quarantine_root=etl_config.quarantine_root,
        target_date=date(2026, 7, 29),
    )
    meta = ingest(config)

    assert meta.landing_files_scanned == 1
    assert meta.bronze_rows_written == 1
    assert not (bronze / "2026-07-28").exists()


def test_empty_landing_zone(landing: Path, etl_config: ETLConfig):
    meta = ingest(etl_config)

    assert meta.landing_files_scanned == 0
    assert meta.bronze_rows_written == 0
    assert meta.quarantined_files == 0
