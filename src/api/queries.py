"""Query service for reading Gold and Silver data via DuckDB.

DuckDB is NOT thread-safe. A threading.Lock is used to serialize all queries.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

from src.api.config import APIConfig


class QueryService:
    """Read-only query layer over Gold and Silver Parquet files."""

    def __init__(self, config: APIConfig) -> None:
        self._config = config
        self._con = duckdb.connect()
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                self._con.execute(sql, params)
                description = self._con.description
                if description is None:
                    return []
                cols = [desc[0] for desc in description]
                rows = self._con.fetchall()
                return [dict(zip(cols, row)) for row in rows]
            except Exception:
                return []

    def _gold_table_path(self, table_name: str, target_date: Optional[date] = None) -> str:
        gold_root = self._config.gold_root
        if target_date:
            path = gold_root / target_date.isoformat() / f"{table_name}.parquet"
            return str(path)
        if not gold_root.exists():
            return str(gold_root / "1970-01-01" / f"{table_name}.parquet")
        partitions = sorted(
            d for d in gold_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if not partitions:
            return str(gold_root / "1970-01-01" / f"{table_name}.parquet")
        latest = partitions[-1]
        return str(latest / f"{table_name}.parquet")

    def _collect_gold_paths(self, table_name: str, from_date: date, to_date: date) -> str:
        """Collect Gold Parquet paths for a date range. Works on ALL DuckDB versions."""
        paths = []
        current = from_date
        while current <= to_date:
            p = self._config.gold_root / current.isoformat() / f"{table_name}.parquet"
            if p.exists():
                paths.append(str(p))
            current += timedelta(days=1)
        if not paths:
            return "[]"
        return "[" + ", ".join(f"'{p}'" for p in paths) + "]"

    def _collect_silver_paths(self, from_date: date, to_date: date) -> str:
        """Collect Silver events.parquet paths for a date range."""
        paths = []
        current = from_date
        while current <= to_date:
            p = self._config.silver_root / current.isoformat() / "events.parquet"
            if p.exists():
                paths.append(str(p))
            current += timedelta(days=1)
        if not paths:
            return "[]"
        return "[" + ", ".join(f"'{p}'" for p in paths) + "]"

    # -- Single date queries --

    def get_model_perf(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("model_perf", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}') ORDER BY invocation_count DESC")

    def get_user_activity(self, target_date: Optional[date] = None, top_n: int = 20) -> List[Dict]:
        path = self._gold_table_path("user_activity", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}') ORDER BY total_cost_usd DESC NULLS LAST LIMIT {top_n}")

    def get_conversation_stats(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("conversation_stats", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}')")

    def get_prompt_analytics(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("prompt_analytics", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}') ORDER BY submission_count DESC")

    def get_feedback_summary(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("feedback_summary", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}') ORDER BY count DESC")

    def get_feedback_categories(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("feedback_categories", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}') ORDER BY count DESC")

    # -- Trend queries (date range) --

    def get_model_perf_trend(self, from_date: date, to_date: date) -> List[Dict]:
        paths = self._collect_gold_paths("model_perf", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(f"SELECT * FROM read_parquet({paths}) ORDER BY event_date, model_name")

    def get_user_activity_trend(self, from_date: date, to_date: date, top_n: int = 20) -> List[Dict]:
        paths = self._collect_gold_paths("user_activity", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(f"SELECT * FROM read_parquet({paths}) ORDER BY total_cost_usd DESC NULLS LAST LIMIT {top_n}")

    def get_feedback_trend(self, from_date: date, to_date: date) -> List[Dict]:
        paths = self._collect_gold_paths("feedback_summary", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(f"SELECT * FROM read_parquet({paths}) ORDER BY event_date, count DESC")

    def get_daily_kpis(self, from_date: date, to_date: date) -> List[Dict]:
        mp_paths = self._collect_gold_paths("model_perf", from_date, to_date)
        fb_paths = self._collect_gold_paths("feedback_summary", from_date, to_date)
        cs_paths = self._collect_gold_paths("conversation_stats", from_date, to_date)
        if mp_paths == "[]":
            return []

        feedback_join = (
            f"""
            LEFT JOIN (
                SELECT event_date, avg(avg_rating) as avg_rating, sum(count) as total_feedback
                FROM read_parquet({fb_paths})
                GROUP BY event_date
            ) fb ON mp_sum.event_date = fb.event_date
            """
            if fb_paths != "[]"
            else "LEFT JOIN (SELECT NULL::VARCHAR AS event_date, NULL::DOUBLE AS avg_rating, NULL::BIGINT AS total_feedback WHERE false) fb ON mp_sum.event_date = fb.event_date"
        )
        conversation_join = (
            f"""
            LEFT JOIN (
                SELECT event_date, total_conversations_started
                FROM read_parquet({cs_paths})
            ) cs ON mp_sum.event_date = cs.event_date
            """
            if cs_paths != "[]"
            else "LEFT JOIN (SELECT NULL::VARCHAR AS event_date, NULL::BIGINT AS total_conversations_started WHERE false) cs ON mp_sum.event_date = cs.event_date"
        )

        return self._query(f"""
            SELECT
                mp_sum.total_invocations,
                mp_sum.total_cost_usd,
                mp_sum.avg_latency,
                mp_sum.avg_success_rate,
                fb.avg_rating,
                fb.total_feedback,
                cs.total_conversations_started
            FROM (
                SELECT event_date,
                    sum(invocation_count) as total_invocations,
                    sum(total_cost_usd) as total_cost_usd,
                    avg(avg_latency_ms) as avg_latency,
                    avg(success_rate_pct) as avg_success_rate
                FROM read_parquet({mp_paths})
                GROUP BY event_date
            ) mp_sum
            {feedback_join}
            {conversation_join}
            ORDER BY mp_sum.event_date
        """)

    # -- Cross-table: heatmap & correlation (reads Silver) --

    def get_latency_heatmap(self, from_date: date, to_date: date) -> List[Dict]:
        """Q3: hour x day_of_week -> P95 latency."""
        paths = self._collect_silver_paths(from_date, to_date)
        if paths == "[]":
            return []
        return self._query(f"""
            SELECT
                extract('hour' from try_cast(event_timestamp AS TIMESTAMP))::int as hour,
                extract('dow' from try_cast(event_timestamp AS TIMESTAMP))::int as day_of_week,
                quantile(total_latency_ms, 0.95)::double as p95_latency,
                count(*)::int as sample_count
            FROM read_parquet({paths}, union_by_name=True)
            WHERE event_type = 'model_response'
              AND try_cast(event_timestamp AS TIMESTAMP) IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 2, 1
        """)

    def get_feedback_latency_correlation(self, from_date: date, to_date: date) -> List[Dict]:
        """Q5: avg rating by latency bucket."""
        paths = self._collect_silver_paths(from_date, to_date)
        if paths == "[]":
            return []
        return self._query(f"""
            WITH responses AS (
                SELECT conversation_id, total_latency_ms,
                    CASE
                        WHEN total_latency_ms < 500 THEN 'Fast (<500ms)'
                        WHEN total_latency_ms < 1500 THEN 'Medium (500ms-1.5s)'
                        ELSE 'Slow (>1.5s)'
                    END as latency_bucket
                FROM read_parquet({paths}, union_by_name=True)
                WHERE event_type = 'model_response'
            ),
            feedback AS (
                SELECT conversation_id, rating_value
                FROM read_parquet({paths}, union_by_name=True)
                WHERE event_type = 'feedback' AND rating_value IS NOT NULL
            )
            SELECT r.latency_bucket,
                round(avg(f.rating_value), 2)::double as avg_rating,
                count(*)::int as sample_count,
                round(avg(r.total_latency_ms), 1)::double as avg_latency_ms
            FROM responses r
            JOIN feedback f ON r.conversation_id = f.conversation_id
            GROUP BY r.latency_bucket
            ORDER BY avg_rating DESC
        """)

    # -- Silver detail --

    def get_events(self, target_date: Optional[date] = None, event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        silver_root = str(self._config.silver_root)
        if target_date:
            path = f"{silver_root}/{target_date.isoformat()}/events.parquet"
        else:
            path = f"{silver_root}/*/events.parquet"
        where = ""
        params: tuple = ()
        if event_type:
            where = " WHERE event_type = ?"
            params = (event_type,)
        union_clause = ", union_by_name=True" if not target_date else ""
        return self._query(
            f"SELECT * FROM read_parquet('{path}'{union_clause}){where} ORDER BY event_timestamp DESC LIMIT {limit}",
            params,
        )

    # -- Metadata --

    def get_available_dates(self) -> List[str]:
        gold_root = self._config.gold_root
        if not gold_root.exists():
            return []
        return sorted(d.name for d in gold_root.iterdir() if d.is_dir() and not d.name.startswith("."))

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "available_dates": self.get_available_dates()}