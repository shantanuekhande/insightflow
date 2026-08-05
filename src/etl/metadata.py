from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class IngestMetadata:
    """Tracks the outcome of a single ingestion run."""

    run_timestamp: datetime
    target_date: date | None
    landing_files_scanned: int
    bronze_rows_written: int
    bronze_files_written: int
    quarantined_files: int
    errors_by_type: dict[str, int] = field(default_factory=dict)
    events_by_type: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "run_timestamp": self.run_timestamp.isoformat(),
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "landing_files_scanned": self.landing_files_scanned,
            "bronze_rows_written": self.bronze_rows_written,
            "bronze_files_written": self.bronze_files_written,
            "quarantined_files": self.quarantined_files,
            "errors_by_type": self.errors_by_type,
            "events_by_type": self.events_by_type,
            "duration_seconds": round(self.duration_seconds, 3),
        }

    def summary(self) -> str:
        lines = [
            f"Ingest Run @ {self.run_timestamp.isoformat()}",
            f"  Target date     : {self.target_date or 'all'}",
            f"  Files scanned   : {self.landing_files_scanned}",
            f"  Bronze rows     : {self.bronze_rows_written}",
            f"  Bronze files    : {self.bronze_files_written}",
            f"  Quarantined     : {self.quarantined_files}",
            f"  Duration        : {self.duration_seconds:.3f}s",
        ]
        if self.events_by_type:
            lines.append("  Events by type:")
            for et, count in sorted(self.events_by_type.items()):
                lines.append(f"    {et:30s} {count}")
        if self.errors_by_type:
            lines.append("  Errors by type:")
            for err, count in sorted(self.errors_by_type.items()):
                lines.append(f"    {err:30s} {count}")
        return "\n".join(lines)
