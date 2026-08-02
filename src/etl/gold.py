"""Silver → Gold aggregation pipeline.

Gold produces pre-computed business metrics from clean Silver data.
Each gold table is designed for direct dashboard/API consumption —
no further joins, filters, or aggregations needed at query time.

Gold tables produced per date partition:
  1. model_perf        — Per model: request volume, success/error breakdown, latency percentiles
  2. user_activity      — Per subscription tier: login stats, unique users
  3. conversation_stats  — Global: conversation count, avg turns, avg duration
  4. prompt_analytics   — Per prompt category: volume, token usage
  5. feedback_summary   — Per feedback type: count, average rating

Key design decisions:
  - Each table is a standalone Parquet file, partitioned by date directory.
  - Idempotent: re-running overwrites existing files, never appends.
  - Graceful empty handling: if no events exist for a table, no file is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import polars as pl

from src.etl.config import ETLConfig


@dataclass
class GoldMetadata:
    """Tracks the outcome of a single gold aggregation run."""

    run_timestamp: datetime
    target_date: Optional[date]
    silver_rows_read: int
    gold_tables_written: dict[str, int] = field(default_factory=dict)
    gold_files_written: int = 0
    duration_seconds: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Gold Aggregation Run @ {self.run_timestamp.isoformat()}",
            f"  Target date       : {self.target_date or 'all'}",
            f"  Silver rows read  : {self.silver_rows_read}",
            f"  Gold files written: {self.gold_files_written}",
            f"  Duration          : {self.duration_seconds:.3f}s",
        ]
        if self.gold_tables_written:
            lines.append("  Tables produced:")
            for table, rows in sorted(self.gold_tables_written.items()):
                lines.append(f"    {table:30s} {rows} rows")
        return "\n".join(lines)


# ── Model Performance ─────────────────────────────────────────────────────


def _build_model_perf(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate model_response events into per-model performance metrics."""
    resp = df.filter(pl.col("event_type") == "model_response")
    if resp.is_empty():
        return _empty_model_perf()

    return (
        resp.group_by("model_name", "model_provider")
        .agg(
            pl.len().alias("request_count"),
            pl.col("status")
            .eq("success")
            .sum()
            .cast(pl.UInt32)
            .alias("success_count"),
            pl.col("status")
            .eq("error")
            .sum()
            .cast(pl.UInt32)
            .alias("error_count"),
            pl.col("status")
            .eq("timeout")
            .sum()
            .cast(pl.UInt32)
            .alias("timeout_count"),
            pl.col("status")
            .eq("rate_limited")
            .sum()
            .cast(pl.UInt32)
            .alias("rate_limited_count"),
            pl.col("total_latency_ms").mean().round(2).alias("avg_latency_ms"),
            pl.col("total_latency_ms").quantile(0.5).alias("median_latency_ms"),
            pl.col("total_latency_ms").quantile(0.95).alias("p95_latency_ms"),
            pl.col("time_to_first_token_ms")
            .mean()
            .round(2)
            .alias("avg_ttft_ms"),
            pl.col("prompt_token_count").mean().round(2).alias("avg_input_tokens"),
            pl.col("response_token_count")
            .mean()
            .round(2)
            .alias("avg_output_tokens"),
        )
        .sort("request_count", descending=True)
    )


def _empty_model_perf() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "model_name": pl.Utf8,
            "model_provider": pl.Utf8,
            "request_count": pl.UInt32,
            "success_count": pl.UInt32,
            "error_count": pl.UInt32,
            "timeout_count": pl.UInt32,
            "rate_limited_count": pl.UInt32,
            "avg_latency_ms": pl.Float64,
            "median_latency_ms": pl.Float64,
            "p95_latency_ms": pl.Float64,
            "avg_ttft_ms": pl.Float64,
            "avg_input_tokens": pl.Float64,
            "avg_output_tokens": pl.Float64,
        }
    )


# ── User Activity ──────────────────────────────────────────────────────────


def _build_user_activity(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate user_login events into per-tier login statistics."""
    logins = df.filter(pl.col("event_type") == "user_login")
    if logins.is_empty():
        return _empty_user_activity()

    return (
        logins.group_by("subscription_tier")
        .agg(
            pl.col("user_id").n_unique().alias("unique_users"),
            pl.len().alias("total_logins"),
            pl.col("login_status")
            .eq("success")
            .sum()
            .cast(pl.UInt32)
            .alias("successful_logins"),
            pl.col("login_status")
            .eq("failure")
            .sum()
            .cast(pl.UInt32)
            .alias("failed_logins"),
        )
        .sort("subscription_tier")
    )


def _empty_user_activity() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "subscription_tier": pl.Utf8,
            "unique_users": pl.UInt32,
            "total_logins": pl.UInt32,
            "successful_logins": pl.UInt32,
            "failed_logins": pl.UInt32,
        }
    )


# ── Conversation Stats ─────────────────────────────────────────────────────


def _build_conversation_stats(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate conversation_closed events into global conversation metrics."""
    closed = df.filter(pl.col("event_type") == "conversation_closed")
    if closed.is_empty():
        return _empty_conversation_stats()

    return closed.select(
        pl.len().alias("total_conversations"),
        pl.col("turn_count").mean().round(2).alias("avg_turns"),
        pl.col("turn_count").max().alias("max_turns"),
        pl.col("conversation_duration_seconds")
        .mean()
        .round(2)
        .alias("avg_duration_seconds"),
    )


def _empty_conversation_stats() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "total_conversations": pl.UInt32,
            "avg_turns": pl.Float64,
            "max_turns": pl.Int64,
            "avg_duration_seconds": pl.Float64,
        }
    )


# ── Prompt Analytics ───────────────────────────────────────────────────────


def _build_prompt_analytics(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate prompt_submitted events into per-category metrics."""
    prompts = df.filter(pl.col("event_type") == "prompt_submitted")
    if prompts.is_empty():
        return _empty_prompt_analytics()

    return (
        prompts.group_by("prompt_category")
        .agg(
            pl.len().alias("total_prompts"),
            pl.col("prompt_token_count")
            .sum()
            .cast(pl.UInt32)
            .alias("total_input_tokens"),
            pl.col("prompt_token_count").mean().round(2).alias("avg_input_tokens"),
            pl.col("prompt_char_count").mean().round(2).alias("avg_char_count"),
        )
        .sort("total_prompts", descending=True)
    )


def _empty_prompt_analytics() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "prompt_category": pl.Utf8,
            "total_prompts": pl.UInt32,
            "total_input_tokens": pl.UInt32,
            "avg_input_tokens": pl.Float64,
            "avg_char_count": pl.Float64,
        }
    )


# ── Feedback Summary ──────────────────────────────────────────────────────


def _build_feedback_summary(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate feedback events into per-type summary."""
    fb = df.filter(pl.col("event_type") == "feedback")
    if fb.is_empty():
        return _empty_feedback_summary()

    return (
        fb.group_by("feedback_type")
        .agg(
            pl.len().alias("count"),
            pl.col("rating_value").cast(pl.Float64).mean().round(2).alias("avg_rating"),
        )
        .sort("count", descending=True)
    )


def _empty_feedback_summary() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "feedback_type": pl.Utf8,
            "count": pl.UInt32,
            "avg_rating": pl.Float64,
        }
    )


# ── Main Pipeline ─────────────────────────────────────────────────────────

_GOLD_BUILDERS = [
    ("model_perf", _build_model_perf),
    ("user_activity", _build_user_activity),
    ("conversation_stats", _build_conversation_stats),
    ("prompt_analytics", _build_prompt_analytics),
    ("feedback_summary", _build_feedback_summary),
]


def _write_gold(path: Path, df: pl.DataFrame) -> None:
    """Write a gold Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def silver_to_gold(config: ETLConfig) -> GoldMetadata:
    """Read Silver Parquet, compute business aggregations, write to Gold."""
    start = datetime.now(timezone.utc)

    # Determine which date partitions to scan
    if config.target_date:
        partitions: list[Path] = [config.silver_root / config.target_date.isoformat()]
    elif config.silver_root.exists():
        partitions = sorted(
            d
            for d in config.silver_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    else:
        partitions = []

    silver_rows = 0
    gold_tables: dict[str, int] = {}
    gold_files = 0

    for partition in partitions:
        if not partition.exists():
            continue

        event_date = partition.name
        silver_path = partition / "events.parquet"
        if not silver_path.exists():
            continue

        df = pl.read_parquet(silver_path)
        silver_rows += len(df)

        gold_dir = config.gold_root / event_date
        gold_dir.mkdir(parents=True, exist_ok=True)

        for table_name, builder in _GOLD_BUILDERS:
            result = builder(df)
            if result.is_empty():
                continue
            path = gold_dir / f"{table_name}.parquet"
            _write_gold(path, result)
            gold_files += 1
            gold_tables[table_name] = gold_tables.get(table_name, 0) + len(result)

    end = datetime.now(timezone.utc)
    return GoldMetadata(
        run_timestamp=start,
        target_date=config.target_date,
        silver_rows_read=silver_rows,
        gold_tables_written=gold_tables,
        gold_files_written=gold_files,
        duration_seconds=(end - start).total_seconds(),
    )


def main() -> GoldMetadata:
    meta = silver_to_gold(ETLConfig())
    print(meta.summary())
    return meta


if __name__ == "__main__":
    main()