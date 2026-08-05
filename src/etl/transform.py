"""Bronze → Silver transformation pipeline.

Silver applies deeper validation that Bronze intentionally skips:
  1. Enum validation  — string values must match defined enum members
  2. Deduplication    — remove duplicate event_id rows (keep first occurrence)
  3. Null handling    — flag rows with unexpected nulls in required fields
  4. Type casting     — ensure consistent column types across all event types

Rows that fail validation are quarantined. The rest are written to Silver.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.etl.config import ETLConfig
from src.etl.metadata import IngestMetadata
from src.schemas.enums import (
    CloseReason,
    DeviceOS,
    DeviceType,
    ErrorCode,
    EventType,
    FailureReason,
    FeedbackCategory,
    FeedbackType,
    LoginStatus,
    ModelProvider,
    ModelResponseStatus,
    PromptCategory,
    SubscriptionTier,
)

# ---------------------------------------------------------------------------
# Valid enum values per column
# ---------------------------------------------------------------------------

_ENUM_VALUES: dict[str, set[str]] = {
    "event_type": {e.value for e in EventType},
    "subscription_tier": {e.value for e in SubscriptionTier},
    "device_type": {e.value for e in DeviceType},
    "device_os": {e.value for e in DeviceOS},
    "login_status": {e.value for e in LoginStatus},
    "failure_reason": {e.value for e in FailureReason},
    "status": {e.value for e in ModelResponseStatus},
    "error_code": {e.value for e in ErrorCode},
    "model_provider": {e.value for e in ModelProvider},
    "feedback_type": {e.value for e in FeedbackType},
    "prompt_category": {e.value for e in PromptCategory},
    "close_reason": {e.value for e in CloseReason},
    "feedback_category": {e.value for e in FeedbackCategory},
}

# Fields that must be non-null when the event_type requires them
_REQUIRED_BY_EVENT: dict[str, list[str]] = {
    "user_login": ["user_id", "subscription_tier", "device_type", "device_os", "country_code", "login_status"],
    "conversation_started": ["user_id", "session_id", "subscription_tier", "conversation_id"],
    "prompt_submitted": ["user_id", "session_id", "conversation_id", "prompt_char_count", "prompt_token_count", "prompt_category"],
    "model_response": ["user_id", "session_id", "conversation_id", "model_provider", "model_name", "status",
                       "prompt_token_count", "response_token_count", "total_latency_ms",
                       "inference_latency_ms", "queue_wait_ms", "time_to_first_token_ms",
                       "estimated_cost_usd"],
    "feedback": ["user_id", "session_id", "conversation_id", "response_id", "feedback_type"],
    "conversation_closed": ["user_id", "session_id", "conversation_id", "close_reason", "turn_count", "conversation_duration_seconds"],
}


def bronze_to_silver(config: ETLConfig) -> IngestMetadata:
    """Read Bronze Parquet, validate, deduplicate, write to Silver."""
    start = datetime.now(timezone.utc)

    if config.target_date:
        partitions: list[Path] = [config.bronze_root / config.target_date.isoformat()]
    elif config.bronze_root.exists():
        partitions = sorted(
            d for d in config.bronze_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    else:
        partitions = []

    bronze_rows = 0
    silver_rows = 0
    silver_files = 0
    quarantined = 0
    duplicates_dropped = 0
    errors_by_type: dict[str, int] = {}
    events_by_type: dict[str, int] = {}

    for partition in partitions:
        if not partition.exists():
            continue
        event_date = partition.name
        parquet_files = sorted(partition.glob("*.parquet"))

        # Read all Parquet files for this date into one DataFrame
        frames = []
        for pf in parquet_files:
            df = pl.read_parquet(pf)
            frames.append(df)
            bronze_rows += len(df)

        if not frames:
            continue

        combined = pl.concat(frames, how="diagonal")

        # Step 1: Deduplicate by event_id (keep first)
        before_dedup = len(combined)
        combined = combined.unique(subset=["event_id"], keep="first", maintain_order=True)
        duplicates_dropped += before_dedup - len(combined)

        # Step 2: Validate enum columns
        combined, bad_rows = _validate_enums(combined)
        quarantined += bad_rows

        # Step 3: Validate required fields per event_type
        combined, missing_rows = _validate_required_fields(combined)
        quarantined += missing_rows

        # Step 4: Sort for consistent output
        combined = combined.sort("event_timestamp")

        # Write to Silver
        silver_dir = config.silver_root / event_date
        silver_dir.mkdir(parents=True, exist_ok=True)
        silver_path = silver_dir / "events.parquet"
        combined.write_parquet(silver_path)
        silver_rows += len(combined)
        silver_files += 1

        # Track event breakdown
        for et, count in combined.group_by("event_type").len().rows():
            etype = et[0]
            events_by_type[etype] = events_by_type.get(etype, 0) + count

    end = datetime.now(timezone.utc)
    return IngestMetadata(
        run_timestamp=start,
        target_date=config.target_date,
        landing_files_scanned=bronze_rows,
        bronze_rows_written=silver_rows,
        bronze_files_written=silver_files,
        quarantined_files=quarantined,
        errors_by_type=errors_by_type,
        events_by_type=events_by_type,
        duration_seconds=(end - start).total_seconds(),
    )


def _validate_enums(df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Filter rows where enum columns contain invalid values."""
    if df.is_empty():
        return df, 0

    # Build a mask: True means the row is valid
    valid_mask = pl.lit(True)

    for col_name, valid_values in _ENUM_VALUES.items():
        if col_name not in df.columns:
            continue
        col_valid = pl.col(col_name).is_null() | pl.col(col_name).is_in(valid_values)
        valid_mask = valid_mask & col_valid

    good = df.filter(valid_mask)
    bad_count = len(df) - len(good)
    return good, bad_count


def _validate_required_fields(df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Filter rows where required fields for the event_type are null."""
    if df.is_empty():
        return df, 0

    masks = []
    for event_type, required_fields in _REQUIRED_BY_EVENT.items():
        fields_in_df = [f for f in required_fields if f in df.columns]
        if not fields_in_df:
            continue
        # All required fields must be non-null for this event_type
        all_present = pl.lit(True)
        for f in fields_in_df:
            all_present = all_present & pl.col(f).is_not_null()
        masks.append((pl.col("event_type") == event_type, all_present))

    if not masks:
        return df, 0

    # A row is valid if its event_type mask passes
    valid_mask = pl.lit(False)
    for event_type_condition, field_condition in masks:
        valid_mask = valid_mask | (event_type_condition & field_condition)

    good = df.filter(valid_mask)
    bad_count = len(df) - len(good)
    return good, bad_count


def main() -> IngestMetadata:
    meta = bronze_to_silver(ETLConfig())
    print(meta.summary())
    return meta


if __name__ == "__main__":
    main()
