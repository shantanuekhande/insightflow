from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from src.api.config import APIConfig
from src.api.queries import QueryService


def _write_parquet(root: Path, event_date: str, name: str, rows: list[dict]) -> None:
    partition = root / event_date
    partition.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(partition / name)


def _response_row(**overrides) -> dict:
    row = {
        "event_id": "mr-1",
        "event_type": "model_response",
        "event_timestamp": "2026-04-09T12:00:00Z",
        "event_date": "2026-04-09",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "s-1",
        "conversation_id": "c-1",
        "model_provider": "openai",
        "model_name": "gpt-4.1",
        "status": "success",
        "error_code": None,
        "prompt_token_count": 40,
        "response_token_count": 80,
        "total_latency_ms": 600,
        "inference_latency_ms": 500,
        "queue_wait_ms": 50,
        "time_to_first_token_ms": 120,
        "estimated_cost_usd": 0.02,
    }
    row.update(overrides)
    return row


def _feedback_row(**overrides) -> dict:
    row = {
        "event_id": "fb-1",
        "event_type": "feedback",
        "event_timestamp": "2026-04-09T12:05:00Z",
        "event_date": "2026-04-09",
        "schema_version": "2.0",
        "user_id": "u-1",
        "session_id": "s-1",
        "conversation_id": "c-1",
        "response_id": "r-1",
        "feedback_type": "star_rating",
        "feedback_category": "accuracy",
        "rating_value": 4,
    }
    row.update(overrides)
    return row


def _gold_row(**overrides) -> dict:
    row = {
        "event_date": "2026-04-09",
        "invocation_count": 10,
        "total_cost_usd": 1.5,
        "avg_latency_ms": 250.0,
        "success_rate_pct": 90.0,
    }
    row.update(overrides)
    return row


def test_daily_kpis_reads_multiple_dates(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"
    silver_root = tmp_path / "silver"
    for event_date, cost, rating, started in [
        ("2026-04-09", 1.5, 4.0, 10),
        ("2026-04-10", 2.5, 3.0, 12),
    ]:
        _write_parquet(gold_root, event_date, "model_perf.parquet", [_gold_row(event_date=event_date, total_cost_usd=cost)])
        _write_parquet(
            gold_root,
            event_date,
            "feedback_summary.parquet",
            [{"event_date": event_date, "avg_rating": rating, "count": 5}],
        )
        _write_parquet(
            gold_root,
            event_date,
            "conversation_stats.parquet",
            [{"event_date": event_date, "total_conversations_started": started}],
        )

    service = QueryService(APIConfig(gold_root=gold_root, silver_root=silver_root))
    rows = service.get_daily_kpis(date.fromisoformat("2026-04-09"), date.fromisoformat("2026-04-10"))
    service.close()

    assert len(rows) == 2
    assert rows[0]["total_invocations"] == 10
    assert rows[1]["total_feedback"] == 5


def test_daily_kpis_handles_missing_supporting_tables(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"
    silver_root = tmp_path / "silver"

    _write_parquet(
        gold_root,
        "2026-04-09",
        "model_perf.parquet",
        [_gold_row(event_date="2026-04-09", total_cost_usd=2.0, invocation_count=4)],
    )

    service = QueryService(APIConfig(gold_root=gold_root, silver_root=silver_root))
    rows = service.get_daily_kpis(date.fromisoformat("2026-04-09"), date.fromisoformat("2026-04-09"))
    service.close()

    assert len(rows) == 1
    assert rows[0]["total_invocations"] == 4
    assert rows[0]["avg_rating"] is None
    assert rows[0]["total_conversations_started"] is None


def test_heatmap_and_correlation_handle_mixed_silver_schemas(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"
    silver_root = tmp_path / "silver"

    _write_parquet(silver_root, "2026-04-09", "events.parquet", [_response_row(conversation_id="c-1")])
    _write_parquet(silver_root, "2026-04-10", "events.parquet", [
        {
            "event_id": "fb-1",
            "event_type": "feedback",
            "event_timestamp": "2026-04-10T12:05:00Z",
            "event_date": "2026-04-10",
            "schema_version": "2.0",
            "user_id": "u-1",
            "session_id": "s-1",
            "conversation_id": "c-1",
            "response_id": "r-1",
            "feedback_type": "star_rating",
            "feedback_category": "accuracy",
            "rating_value": 4,
        },
        {
            "event_id": "login-1",
            "event_type": "user_login",
            "event_timestamp": "2026-04-10T08:00:00Z",
            "event_date": "2026-04-10",
            "schema_version": "2.0",
            "user_id": "u-2",
            "session_id": "s-2",
            "subscription_tier": "free",
            "device_type": "desktop",
            "device_os": "linux",
            "country_code": "US",
            "login_status": "success",
            "failure_reason": None,
        },
    ])

    service = QueryService(APIConfig(gold_root=gold_root, silver_root=silver_root))
    heatmap = service.get_latency_heatmap(date.fromisoformat("2026-04-09"), date.fromisoformat("2026-04-10"))
    correlation = service.get_feedback_latency_correlation(date.fromisoformat("2026-04-09"), date.fromisoformat("2026-04-10"))
    service.close()

    assert len(heatmap) == 1
    assert heatmap[0]["sample_count"] == 1
    assert len(correlation) == 1
    assert correlation[0]["avg_rating"] == 4.0