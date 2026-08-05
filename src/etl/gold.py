"""Silver → Gold transformation pipeline.

Gold tables are the analytics-ready layer. Each table has a specific "grain"
(the primary key grouping) and answers specific business questions:

  Q1: Why did yesterday's inference cost increase by 27%?
      → model_perf (cost, tokens, per-model trend)
  Q2: Which model has the highest error rate?
      → model_perf (error counts, success_rate, per-model)
  Q3: Why is latency spiking every evening?
      → model_perf (p50/p95/p99 latency per model)
  Q4: Which users consume the most resources?
      → user_activity (tokens, sessions, prompts per user)
  Q5: Are users actually satisfied with the responses?
      → feedback_summary (ratings, categories, per-day trend)

Plus two supporting tables:
  - conversation_stats: global daily conversation metrics
  - prompt_analytics: prompt volume and complexity by category
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import polars as pl

from src.etl.config import ETLConfig

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def silver_to_gold(config: ETLConfig) -> dict:
    """Read Silver Parquet, build all Gold tables, write to Gold layer.

    Returns a dict mapping table_name → row_count.
    """
    start = datetime.now(timezone.utc)

    if config.target_date:
        partitions: list[Path] = [config.silver_root / config.target_date.isoformat()]
    elif config.silver_root.exists():
        partitions = sorted(
            d for d in config.silver_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    else:
        partitions = []

    results: dict[str, int] = {}

    for partition in partitions:
        if not partition.exists():
            continue
        event_date = partition.name
        silver_path = partition / "events.parquet"
        if not silver_path.exists():
            continue

        df = pl.read_parquet(silver_path)

        if df.is_empty():
            _write_empty_gold_tables(config.gold_root, event_date)
            continue

        gold_dir = config.gold_root / event_date
        gold_dir.mkdir(parents=True, exist_ok=True)

        results[f"model_perf_{event_date}"] = _build_model_perf(df, gold_dir, event_date)
        results[f"user_activity_{event_date}"] = _build_user_activity(df, gold_dir, event_date)
        results[f"conversation_stats_{event_date}"] = _build_conversation_stats(df, gold_dir, event_date)
        results[f"prompt_analytics_{event_date}"] = _build_prompt_analytics(df, gold_dir, event_date)
        results[f"feedback_summary_{event_date}"] = _build_feedback_summary(df, gold_dir, event_date)

    end = datetime.now(timezone.utc)
    duration = (end - start).total_seconds()
    print(f"Gold pipeline completed in {duration:.2f}s")
    return results


# ---------------------------------------------------------------------------
# Gold Table 1: model_perf
# Grain: (model_name, model_provider, date)
# Answers: Q1 (cost), Q2 (error rate), Q3 (latency spikes)
# ---------------------------------------------------------------------------


def _build_model_perf(df: pl.DataFrame, gold_dir: Path, event_date: str) -> int:
    """Build model performance table with cost, error rate, and latency percentiles."""
    responses = df.filter(pl.col("event_type") == "model_response")

    if responses.is_empty() or "status" not in responses.columns:
        _empty_model_perf(gold_dir)
        return 0

    agg = (
        responses
        .group_by("model_name", "model_provider")
        .agg(
            # Volume
            invocation_count=pl.len(),
            success_count=pl.col("status").eq("success").sum(),
            error_count=pl.col("status").eq("error").sum(),
            timeout_count=pl.col("status").eq("timeout").sum(),
            rate_limited_count=pl.col("status").eq("rate_limited").sum(),
            # Latency (P50, P95, P99 via quantile)
            avg_latency_ms=pl.col("total_latency_ms").mean().round(1),
            p50_latency_ms=pl.col("total_latency_ms").quantile(0.5).round(1),
            p95_latency_ms=pl.col("total_latency_ms").quantile(0.95).round(1),
            p99_latency_ms=pl.col("total_latency_ms").quantile(0.99).round(1),
            avg_ttft_ms=pl.col("time_to_first_token_ms").mean().round(1),
            # Token consumption
            total_input_tokens=pl.col("prompt_token_count").sum(),
            total_output_tokens=pl.col("response_token_count").sum(),
            # Cost
            total_cost_usd=pl.col("estimated_cost_usd").sum().round(4),
            avg_cost_usd=pl.col("estimated_cost_usd").mean().round(6),
        )
        .with_columns(
            success_rate_pct=(pl.col("success_count") / pl.col("invocation_count") * 100).round(2),
            error_rate_pct=(pl.col("error_count") / pl.col("invocation_count") * 100).round(2),
        )
        .sort("invocation_count", descending=True)
        .with_columns(event_date=pl.lit(event_date))
    )

    out_path = gold_dir / "model_perf.parquet"
    agg.write_parquet(out_path)
    return len(agg)


def _empty_model_perf(gold_dir: Path) -> None:
    """Write empty model_perf with correct schema."""
    schema = {
        "model_name": pl.Utf8,
        "model_provider": pl.Utf8,
        "invocation_count": pl.UInt32,
        "success_count": pl.UInt32,
        "error_count": pl.UInt32,
        "timeout_count": pl.UInt32,
        "rate_limited_count": pl.UInt32,
        "avg_latency_ms": pl.Float64,
        "p50_latency_ms": pl.Float64,
        "p95_latency_ms": pl.Float64,
        "p99_latency_ms": pl.Float64,
        "avg_ttft_ms": pl.Float64,
        "total_input_tokens": pl.UInt64,
        "total_output_tokens": pl.UInt64,
        "total_cost_usd": pl.Float64,
        "avg_cost_usd": pl.Float64,
        "success_rate_pct": pl.Float64,
        "error_rate_pct": pl.Float64,
        "event_date": pl.Utf8,
    }
    pl.DataFrame(schema=schema).write_parquet(gold_dir / "model_perf.parquet")


# ---------------------------------------------------------------------------
# Gold Table 2: user_activity
# Grain: (user_id, date)
# Answers: Q4 (which users consume the most resources?)
# ---------------------------------------------------------------------------


def _build_user_activity(df: pl.DataFrame, gold_dir: Path, event_date: str) -> int:
    """Build per-user activity metrics."""

    # Keep only events that have a user_id
    all_events = df.filter(pl.col("user_id").is_not_null())

    if all_events.is_empty():
        _empty_user_activity(gold_dir)
        return 0

    # --------------------------------------------------
    # Login metrics
    # --------------------------------------------------
    logins = df.filter(pl.col("event_type") == "user_login")

    if logins.is_empty() or "login_status" not in logins.columns:
        login_agg = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "login_count": pl.UInt32,
            "successful_logins": pl.UInt32,
        })
    else:
        login_agg = (
            logins
            .group_by("user_id")
            .agg(
                login_count=pl.len(),
                successful_logins=pl.col("login_status").eq("success").sum(),
            )
        )

    # --------------------------------------------------
    # Model response metrics
    # --------------------------------------------------
    responses = df.filter(pl.col("event_type") == "model_response")

    if responses.is_empty() or "prompt_token_count" not in responses.columns:
        response_agg = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "total_requests": pl.UInt32,
            "total_input_tokens": pl.UInt64,
            "total_output_tokens": pl.UInt64,
            "total_cost_usd": pl.Float64,
            "avg_latency_ms": pl.Float64,
        })
    else:
        response_agg = (
            responses
            .group_by("user_id")
            .agg(
                total_requests=pl.len(),
                total_input_tokens=pl.col("prompt_token_count").sum(),
                total_output_tokens=pl.col("response_token_count").sum(),
                total_cost_usd=pl.col("estimated_cost_usd").sum().round(4),
                avg_latency_ms=pl.col("total_latency_ms").mean().round(1),
            )
        )

    # --------------------------------------------------
    # Prompt metrics
    # --------------------------------------------------
    prompts = df.filter(pl.col("event_type") == "prompt_submitted")

    if prompts.is_empty() or "prompt_char_count" not in prompts.columns:
        prompt_agg = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "prompt_count": pl.UInt32,
            "avg_prompt_length": pl.Float64,
        })
    else:
        prompt_agg = (
            prompts
            .group_by("user_id")
            .agg(
                prompt_count=pl.len(),
                avg_prompt_length=pl.col("prompt_char_count").mean().round(1),
            )
        )

    # --------------------------------------------------
    # Session metrics
    # --------------------------------------------------
    if "session_id" not in all_events.columns:
        session_agg = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "session_count": pl.UInt32,
        })
    else:
        session_agg = (
            all_events
            .filter(pl.col("session_id").is_not_null())
            .group_by("user_id")
            .agg(session_count=pl.col("session_id").n_unique())
        )

    # --------------------------------------------------
    # Conversation metrics
    # --------------------------------------------------
    convs = df.filter(pl.col("event_type") == "conversation_started")

    if convs.is_empty():
        conv_agg = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "conversation_count": pl.UInt32,
        })
    else:
        conv_agg = (
            convs
            .group_by("user_id")
            .agg(conversation_count=pl.len())
        )

    # --------------------------------------------------
    # Latest subscription tier
    # --------------------------------------------------
    if logins.is_empty() or "login_status" not in logins.columns:
        tier_df = pl.DataFrame(schema={
            "user_id": pl.Utf8,
            "subscription_tier": pl.Utf8,
        })
    else:
        tier_df = (
            logins
            .filter(pl.col("login_status") == "success")
            .sort("event_timestamp", descending=True)
            .group_by("user_id")
            .first()
            .select("user_id", "subscription_tier")
        )

    # --------------------------------------------------
    # Final assembly
    # --------------------------------------------------
    all_user_ids = (
        all_events
        .select("user_id")
        .unique(maintain_order=False)
    )

    result = (
        all_user_ids
        .join(login_agg, on="user_id", how="left")
        .join(response_agg, on="user_id", how="left")
        .join(prompt_agg, on="user_id", how="left")
        .join(session_agg, on="user_id", how="left")
        .join(conv_agg, on="user_id", how="left")
        .join(tier_df, on="user_id", how="left")
    )

    # Ensure optional columns always exist
    required_cols = {
        "total_requests": pl.UInt32,
        "total_input_tokens": pl.UInt64,
        "total_output_tokens": pl.UInt64,
        "total_cost_usd": pl.Float64,
        "avg_latency_ms": pl.Float64,
        "prompt_count": pl.UInt32,
        "avg_prompt_length": pl.Float64,
        "conversation_count": pl.UInt32,
    }

    for col_name, dtype in required_cols.items():
        if col_name not in result.columns:
            result = result.with_columns(
                pl.lit(None).cast(dtype).alias(col_name)
            )

    result = (
        result
        .sort("total_cost_usd", descending=True, nulls_last=True)
        .with_columns(event_date=pl.lit(event_date))
    )

    out_path = gold_dir / "user_activity.parquet"
    result.write_parquet(out_path)

    return len(result)


def _empty_user_activity(gold_dir: Path) -> None:
    """Write empty user_activity with correct schema."""
    schema = {
        "user_id": pl.Utf8,
        "login_count": pl.UInt32,
        "successful_logins": pl.UInt32,
        "total_requests": pl.UInt32,
        "total_input_tokens": pl.UInt64,
        "total_output_tokens": pl.UInt64,
        "total_cost_usd": pl.Float64,
        "avg_latency_ms": pl.Float64,
        "prompt_count": pl.UInt32,
        "avg_prompt_length": pl.Float64,
        "session_count": pl.UInt32,
        "conversation_count": pl.UInt32,
        "subscription_tier": pl.Utf8,
        "event_date": pl.Utf8,
    }
    pl.DataFrame(schema=schema).write_parquet(gold_dir / "user_activity.parquet")


# ---------------------------------------------------------------------------
# Gold Table 3: conversation_stats
# Grain: date (global aggregation)
# ---------------------------------------------------------------------------


def _build_conversation_stats(df: pl.DataFrame, gold_dir: Path, event_date: str) -> int:
    """Build global conversation statistics for the day."""
    convs = df.filter(pl.col("event_type") == "conversation_started")
    closed = df.filter(pl.col("event_type") == "conversation_closed")

    total_started = len(convs)
    total_closed = len(closed)

    avg_turns = None
    max_turns = None
    avg_duration = None
    max_duration = None
    user_closed_pct = None

    if not closed.is_empty() and "turn_count" in closed.columns:
        avg_turns = closed["turn_count"].mean()
        max_turns = closed["turn_count"].max()
        avg_duration = closed["conversation_duration_seconds"].mean()
        max_duration = closed["conversation_duration_seconds"].max()
        if "close_reason" in closed.columns:
            user_closed_count = closed.filter(
                pl.col("close_reason") == "user_closed"
            ).height
            user_closed_pct = round(user_closed_count / total_closed * 100, 2) if total_closed > 0 else None

    result = pl.DataFrame({
        "total_conversations_started": [total_started],
        "total_conversations_closed": [total_closed],
        "avg_turns": [round(avg_turns, 1) if avg_turns is not None else None],
        "max_turns": [max_turns],
        "avg_duration_seconds": [round(avg_duration, 1) if avg_duration is not None else None],
        "max_duration_seconds": [max_duration],
        "user_closed_pct": [user_closed_pct],
        "event_date": [event_date],
    })

    out_path = gold_dir / "conversation_stats.parquet"
    result.write_parquet(out_path)
    return 1


# ---------------------------------------------------------------------------
# Gold Table 4: prompt_analytics
# Grain: (prompt_category, date)
# ---------------------------------------------------------------------------


def _build_prompt_analytics(df: pl.DataFrame, gold_dir: Path, event_date: str) -> int:
    """Build prompt analytics by category."""
    prompts = df.filter(pl.col("event_type") == "prompt_submitted")

    if prompts.is_empty() or "prompt_char_count" not in prompts.columns:
        _empty_prompt_analytics(gold_dir)
        return 0

    agg = (
        prompts
        .group_by("prompt_category")
        .agg(
            submission_count=pl.len(),
            avg_prompt_length=pl.col("prompt_char_count").mean().round(1),
            max_prompt_length=pl.col("prompt_char_count").max(),
            avg_tokens=pl.col("prompt_token_count").mean().round(1),
            total_tokens=pl.col("prompt_token_count").sum(),
        )
        .sort("submission_count", descending=True)
        .with_columns(event_date=pl.lit(event_date))
    )

    out_path = gold_dir / "prompt_analytics.parquet"
    agg.write_parquet(out_path)
    return len(agg)


def _empty_prompt_analytics(gold_dir: Path) -> None:
    """Write empty prompt_analytics with correct schema."""
    schema = {
        "prompt_category": pl.Utf8,
        "submission_count": pl.UInt32,
        "avg_prompt_length": pl.Float64,
        "max_prompt_length": pl.Int64,
        "avg_tokens": pl.Float64,
        "total_tokens": pl.UInt64,
        "event_date": pl.Utf8,
    }
    pl.DataFrame(schema=schema).write_parquet(gold_dir / "prompt_analytics.parquet")


# ---------------------------------------------------------------------------
# Gold Table 5: feedback_summary
# Grain: (feedback_type, date)
# Answers: Q5 (are users satisfied?)
# ---------------------------------------------------------------------------


def _build_feedback_summary(df: pl.DataFrame, gold_dir: Path, event_date: str) -> int:
    """Build feedback summary with rating distribution and category breakdown."""
    feedback = df.filter(pl.col("event_type") == "feedback")

    if feedback.is_empty() or "feedback_type" not in feedback.columns:
        _empty_feedback_summary(gold_dir)
        return 0

    # Overall summary per feedback_type
    agg = (
        feedback
        .group_by("feedback_type")
        .agg(
            count=pl.len(),
            avg_rating=pl.col("rating_value").cast(pl.Float64).mean().round(2),
            # Rating distribution (1-5)
            rating_1=pl.col("rating_value").eq(1).sum(),
            rating_2=pl.col("rating_value").eq(2).sum(),
            rating_3=pl.col("rating_value").eq(3).sum(),
            rating_4=pl.col("rating_value").eq(4).sum(),
            rating_5=pl.col("rating_value").eq(5).sum(),
        )
        .sort("count", descending=True)
        .with_columns(event_date=pl.lit(event_date))
    )

    out_path = gold_dir / "feedback_summary.parquet"
    agg.write_parquet(out_path)

    # Also write category breakdown
    _build_feedback_categories(feedback, gold_dir, event_date)

    return len(agg)


def _build_feedback_categories(feedback: pl.DataFrame, gold_dir: Path, event_date: str) -> None:
    """Build feedback breakdown by category."""
    with_category = feedback.filter(pl.col("feedback_category").is_not_null())

    if with_category.is_empty():
        _empty_feedback_categories(gold_dir)
        return

    agg = (
        with_category
        .group_by("feedback_category")
        .agg(
            count=pl.len(),
            avg_rating=pl.col("rating_value").cast(pl.Float64).mean().round(2),
        )
        .sort("count", descending=True)
        .with_columns(event_date=pl.lit(event_date))
    )

    agg.write_parquet(gold_dir / "feedback_categories.parquet")


def _empty_feedback_summary(gold_dir: Path) -> None:
    """Write empty feedback_summary with correct schema."""
    schema = {
        "feedback_type": pl.Utf8,
        "count": pl.UInt32,
        "avg_rating": pl.Float64,
        "rating_1": pl.UInt32,
        "rating_2": pl.UInt32,
        "rating_3": pl.UInt32,
        "rating_4": pl.UInt32,
        "rating_5": pl.UInt32,
        "event_date": pl.Utf8,
    }
    pl.DataFrame(schema=schema).write_parquet(gold_dir / "feedback_summary.parquet")
    _empty_feedback_categories(gold_dir)


def _empty_feedback_categories(gold_dir: Path) -> None:
    """Write empty feedback_categories with correct schema."""
    schema = {
        "feedback_category": pl.Utf8,
        "count": pl.UInt32,
        "avg_rating": pl.Float64,
        "event_date": pl.Utf8,
    }
    pl.DataFrame(schema=schema).write_parquet(gold_dir / "feedback_categories.parquet")


# ---------------------------------------------------------------------------
# Empty table writer
# ---------------------------------------------------------------------------


def _write_empty_gold_tables(gold_root: Path, event_date: str) -> None:
    """Write all empty gold tables for a date with no events."""
    gold_dir = gold_root / event_date
    gold_dir.mkdir(parents=True, exist_ok=True)
    _empty_model_perf(gold_dir)
    _empty_user_activity(gold_dir)
    _empty_prompt_analytics(gold_dir)
    _empty_feedback_summary(gold_dir)
    # conversation_stats is a single row, still write empty
    pl.DataFrame({
        "total_conversations_started": [0],
        "total_conversations_closed": [0],
        "avg_turns": [None],
        "max_turns": [None],
        "avg_duration_seconds": [None],
        "max_duration_seconds": [None],
        "user_closed_pct": [None],
        "event_date": [event_date],
    }).write_parquet(gold_dir / "conversation_stats.parquet")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def main() -> dict:
    from src.etl.config import ETLConfig
    results = silver_to_gold(ETLConfig())
    for name, count in results.items():
        print(f"  {name}: {count} rows")
    return results


if __name__ == "__main__":
    main()
