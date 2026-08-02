"""Read-only queries against Gold and Silver Parquet files using DuckDB.

Why DuckDB instead of Polars for queries?
  - DuckDB speaks SQL — the universal data language.
  - Zero-copy reads on Parquet (reads column statistics, skips irrelevant rows).
  - Perfect for "SELECT ... WHERE date = X" pattern that an API serves.
  - We still use Polars for ETL (transformations, validation).
  - DuckDB for serving (ad-hoc SQL queries, predicate pushdown).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional

import duckdb
import polars as pl


class QueryService:
    """Read-only query layer over Gold and Silver Parquet files."""

    def __init__(self, gold_root: Path, silver_root: Path) -> None:
        self._gold_root = gold_root
        self._silver_root = silver_root
        self._con = duckdb.connect(":memory:")

    def close(self) -> None:
        self._con.close()

    # ── Model Performance ──────────────────────────────────────────────

    def get_model_perf(
        self, target_date: Optional[date] = None
    ) -> List[dict]:
        path = self._gold_table_path("model_perf", target_date)
        if path is None:
            return []
        return self._con.execute(
            f"SELECT * FROM read_parquet('{path}') ORDER BY request_count DESC"
        ).fetchall_asdict()

    # ── User Activity ───────────────────────────────────────────────────

    def get_user_activity(
        self, target_date: Optional[date] = None
    ) -> List[dict]:
        path = self._gold_table_path("user_activity", target_date)
        if path is None:
            return []
        return self._con.execute(
            f"SELECT * FROM read_parquet('{path}') ORDER BY subscription_tier"
        ).fetchall_asdict()

    # ── Conversation Stats ─────────────────────────────────────────────

    def get_conversation_stats(
        self, target_date: Optional[date] = None
    ) -> List[dict]:
        path = self._gold_table_path("conversation_stats", target_date)
        if path is None:
            return []
        return self._con.execute(
            f"SELECT * FROM read_parquet('{path}')"
        ).fetchall_asdict()

    # ── Prompt Analytics ──────────────────────────────────────────────

    def get_prompt_analytics(
        self, target_date: Optional[date] = None
    ) -> List[dict]:
        path = self._gold_table_path("prompt_analytics", target_date)
        if path is None:
            return []
        return self._con.execute(
            f"SELECT * FROM read_parquet('{path}') ORDER BY total_prompts DESC"
        ).fetchall_asdict()

    # ── Feedback Summary ───────────────────────────────────────────────

    def get_feedback_summary(
        self, target_date: Optional[date] = None
    ) -> List[dict]:
        path = self._gold_table_path("feedback_summary", target_date)
        if path is None:
            return []
        return self._con.execute(
            f"SELECT * FROM read_parquet('{path}') ORDER BY count DESC"
        ).fetchall_asdict()

    # ── Silver: Event detail query ────────────────────────────────────

    def get_events(
        self,
        target_date: date,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        path = self._silver_root / target_date.isoformat() / "events.parquet"
        if not path.exists():
            return []

        sql = f"SELECT * FROM read_parquet('{path}')"
        params: list = []

        if event_type:
            sql += " WHERE event_type = ?"
            params.append(event_type)

        sql += f" LIMIT {limit}"

        return self._con.execute(sql, params).fetchall_asdict()

    # ── Available dates ────────────────────────────────────────────────

    def get_available_dates(self) -> List[str]:
        if not self._gold_root.exists():
            return []
        return sorted(
            d.name
            for d in self._gold_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    def _gold_table_path(
        self, table_name: str, target_date: Optional[date] = None
    ) -> Optional[str]:
        if target_date:
            path = self._gold_root / target_date.isoformat() / f"{table_name}.parquet"
            return str(path) if path.exists() else None

        # Use latest date partition
        if not self._gold_root.exists():
            return None
        partitions = sorted(
            d for d in self._gold_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if not partitions:
            return None

        latest = partitions[-1]
        path = latest / f"{table_name}.parquet"
        return str(path) if path.exists() else None