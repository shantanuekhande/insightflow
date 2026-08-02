"""Landing Zone → Bronze Layer ingestion pipeline.

Bronze validation is intentionally minimal. It checks only:
  1. The file is valid JSON.
  2. The JSON contains four required fields: event_id, event_type,
     event_timestamp, schema_version.

Deeper validation (enum values, field constraints, deduplication)
happens in the Silver layer. This separation keeps Bronze as a
reliable but permissive raw-data store.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.etl.config import ETLConfig
from src.etl.metadata import IngestMetadata

REQUIRED_FIELDS = {"event_id", "event_type", "event_timestamp", "schema_version"}


def ingest(config: ETLConfig) -> IngestMetadata:
    """Read landing zone JSON, validate minimally, write to Bronze (Parquet)."""
    start = datetime.now(timezone.utc)

    # Determine which date partitions to scan
    if config.target_date:
        partitions: list[Path] = [config.landing_root / config.target_date.isoformat()]
    elif config.landing_root.exists():
        partitions = sorted(
            d for d in config.landing_root.iterdir() if d.is_dir() and not d.name.startswith(".")
        )
    else:
        partitions = []

    scanned = 0
    bronze_rows = 0
    bronze_files = 0
    quarantined = 0
    errors_by_type: dict[str, int] = {}
    events_by_type: dict[str, int] = {}

    for partition in partitions:
        if not partition.exists():
            continue

        event_date = partition.name
        json_files = sorted(partition.glob("*.json"))

        # Accumulate good events grouped by event_type
        good_by_type: dict[str, list[dict]] = {}

        for jf in json_files:
            scanned += 1
            content = jf.read_text(encoding="utf-8")

            try:
                record = json.loads(content)
                # Minimal structural validation
                missing = REQUIRED_FIELDS - set(record.keys())
                if missing:
                    raise ValueError(f"Missing required fields: {sorted(missing)}")

                event_type = record["event_type"]
                good_by_type.setdefault(event_type, []).append(record)
                events_by_type[event_type] = events_by_type.get(event_type, 0) + 1

            except Exception as exc:
                quarantined += 1
                error_key = type(exc).__name__
                errors_by_type[error_key] = errors_by_type.get(error_key, 0) + 1
                _quarantine(config.quarantine_root, event_date, jf.name, content, str(exc))

        # Write each event_type as a separate Parquet file
        for event_type, records in good_by_type.items():
            df = pl.DataFrame(records)
            bronze_dir = config.bronze_root / event_date
            bronze_dir.mkdir(parents=True, exist_ok=True)
            bronze_path = bronze_dir / f"{event_type}.parquet"
            df.write_parquet(bronze_path)
            bronze_rows += len(records)
            bronze_files += 1

    end = datetime.now(timezone.utc)
    return IngestMetadata(
        run_timestamp=start,
        target_date=config.target_date,
        landing_files_scanned=scanned,
        bronze_rows_written=bronze_rows,
        bronze_files_written=bronze_files,
        quarantined_files=quarantined,
        errors_by_type=errors_by_type,
        events_by_type=events_by_type,
        duration_seconds=(end - start).total_seconds(),
    )


def _quarantine(
    root: Path,
    event_date: str,
    filename: str,
    original_content: str,
    reason: str,
) -> None:
    """Write a quarantined event with its original content and failure reason."""
    q_dir = root / event_date
    q_dir.mkdir(parents=True, exist_ok=True)

    envelope = {
        "original_filename": filename,
        "original_content": original_content,
        "quarantine_reason": reason,
        "quarantine_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (q_dir / filename).write_text(json.dumps(envelope, indent=2), encoding="utf-8")


def main() -> IngestMetadata:
    meta = ingest(ETLConfig())
    print(meta.summary())
    return meta


if __name__ == "__main__":
    main()
