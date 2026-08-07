"""Query service for reading Gold and Silver data via DuckDB.

DuckDB is NOT thread-safe. A threading.Lock is used to serialize all queries.
This is the pattern for concurrent FastAPI requests hitting the same connection.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

from src.api.config import APIConfig

logger = logging.getLogger(__name__)


class QueryService:
    """Read-only query layer over Gold and Silver Parquet files."""

    def __init__(self, config: APIConfig) -> None:
        self._config = config
        self._con = duckdb.connect()
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a read-only SQL query and return list of dicts.

        Uses self._con.description for column names (works on older DuckDB).
        Uses dict(zip(...)) pattern to avoid numpy/pandas dependency.
        """
        with self._lock:
            try:
                self._con.execute(sql, params)
                description = self._con.description
                if description is None:
                    return []
                cols = [desc[0] for desc in description]
                rows = self._con.fetchall()
                return [dict(zip(cols, row)) for row in rows]
            except Exception as e:
                logger.error(f"DuckDB query failed: {e}\nSQL: {sql}\nParams: {params}")
                return []

    def _gold_table_path(self, table_name: str, target_date: Optional[date] = None) -> str:
        """Build the path to a Gold Parquet table, defaulting to latest partition."""
        gold_root = self._config.gold_root

        if target_date:
            path = gold_root / target_date.isoformat() / f"{table_name}.parquet"
            return str(path)

        # Find latest partition
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
        """Collect Gold Parquet file paths for a date range.

        Returns a DuckDB list expression like ['path1', 'path2', ...].
        Works on ALL DuckDB versions — no from..to or hive_partitioning needed.
        """
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
        """Collect Silver events.parquet paths for a date range.

        Returns a DuckDB list expression.
        """
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

    # ------------------------------------------------------------------
    # Gold queries: single date
    # ------------------------------------------------------------------

    def get_model_perf(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("model_perf", target_date)
        return self._query(
            f"SELECT * FROM read_parquet('{path}') ORDER BY invocation_count DESC"
        )

    def get_user_activity(self, target_date: Optional[date] = None, top_n: int = 20) -> List[Dict]:
        path = self._gold_table_path("user_activity", target_date)
        return self._query(
            f"SELECT * FROM read_parquet('{path}') ORDER BY total_cost_usd DESC NULLS LAST LIMIT {top_n}"
        )

    def get_conversation_stats(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("conversation_stats", target_date)
        return self._query(f"SELECT * FROM read_parquet('{path}')")

    def get_prompt_analytics(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("prompt_analytics", target_date)
        return self._query(
            f"SELECT * FROM read_parquet('{path}') ORDER BY submission_count DESC"
        )

    def get_feedback_summary(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("feedback_summary", target_date)
        return self._query(
            f"SELECT * FROM read_parquet('{path}') ORDER BY count DESC"
        )

    def get_feedback_categories(self, target_date: Optional[date] = None) -> List[Dict]:
        path = self._gold_table_path("feedback_categories", target_date)
        return self._query(
            f"SELECT * FROM read_parquet('{path}') ORDER BY count DESC"
        )

    # ------------------------------------------------------------------
    # Gold queries: trend (date range) — uses _collect_gold_paths
    # ------------------------------------------------------------------

    def get_model_perf_trend(self, from_date: date, to_date: date) -> List[Dict]:
        """Q1: model performance trend over a date range."""
        paths = self._collect_gold_paths("model_perf", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(
            f"""
            SELECT * FROM read_parquet({paths})
            ORDER BY event_date, model_name, invocation_count DESC
            """,
        )

    def get_model_reliability(self, from_date: date, to_date: date) -> List[Dict]:
        """Q2: Model reliability — aggregated success rate, errors, timeouts per model.

        Groups all model_perf rows in the date range by model, computing
        average success rate, total errors/timeouts/rate-limits, and
        average latency. Ordered by success rate ASC so the least reliable
        model appears at the top of the horizontal bar chart.
        """
        paths = self._collect_gold_paths("model_perf", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(
            f"""
            SELECT
                model_name,
                model_provider,
                sum(invocation_count)::int   AS total_invocations,
                round(avg(success_rate_pct), 1)::double AS avg_success_rate,
                sum(error_count)::int        AS total_errors,
                sum(timeout_count)::int      AS total_timeouts,
                sum(rate_limited_count)::int AS total_rate_limited,
                round(avg(avg_latency_ms), 0)::double  AS avg_latency_ms,
                round(avg(p95_latency_ms), 0)::double   AS avg_p95_latency_ms,
                sum(total_cost_usd)::double   AS total_cost_usd
            FROM read_parquet({paths})
            GROUP BY model_name, model_provider
            ORDER BY avg_success_rate ASC
            """,
        )

    def get_user_activity_trend(self, from_date: date, to_date: date, top_n: int = 20) -> List[Dict]:
        """Q4: user activity trend over a date range."""
        paths = self._collect_gold_paths("user_activity", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(
            f"""
            SELECT * FROM read_parquet({paths})
            ORDER BY total_cost_usd DESC NULLS LAST
            LIMIT {top_n}
            """,
        )

    def get_feedback_trend(self, from_date: date, to_date: date) -> List[Dict]:
        """Q5: feedback trend over a date range."""
        paths = self._collect_gold_paths("feedback_summary", from_date, to_date)
        if paths == "[]":
            return []
        return self._query(
            f"""
            SELECT * FROM read_parquet({paths})
            ORDER BY event_date, count DESC
            """,
        )

    def get_daily_kpis(self, from_date: date, to_date: date) -> List[Dict]:
        """Daily KPI summary. Uses event_date from gold tables."""
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

        return self._query(
            f"""
            SELECT
                mp_sum.event_date,
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
            """,
        )

    # ------------------------------------------------------------------
    # Cross-table queries: heatmap & correlation (reads Silver)
    # ------------------------------------------------------------------

    def get_latency_heatmap(self, from_date: date, to_date: date) -> List[Dict]:
        """Q3: Latency heatmap — hour x day_of_week → P95 latency.

        Reads Silver model_response events, extracts hour and day_of_week
        from the timestamp, then computes P95 latency per cell.
        """
        paths = self._collect_silver_paths(from_date, to_date)
        if paths == "[]":
            return []
        return self._query(
            f"""
            SELECT
                extract('hour' from try_cast(event_timestamp AS TIMESTAMP))::int as hour,
                extract('dow' from try_cast(event_timestamp AS TIMESTAMP))::int as day_of_week,
                quantile(total_latency_ms, 0.95)::double as p95_latency,
                count(*)::int as sample_count
            FROM read_parquet({paths}, union_by_name=True)
            WHERE event_type = 'model_response'
            GROUP BY 1, 2
            ORDER BY 2, 1
            """,
        )

    def get_feedback_latency_correlation(self, from_date: date, to_date: date) -> List[Dict]:
        """Q5: Feedback vs latency correlation.

        Joins model_response (latency) with feedback (rating) on conversation_id.
        Buckets latency into Fast / Medium / Slow and computes avg rating per bucket.
        """
        paths = self._collect_silver_paths(from_date, to_date)
        if paths == "[]":
            return []

        logger.info(f"paths are {paths}")

        query = f"""
            WITH responses AS (
                SELECT
                    conversation_id,
                    event_id as response_event_id,
                    total_latency_ms,
                    CASE
                        WHEN total_latency_ms < 500 THEN 'Fast (<500ms)'
                        WHEN total_latency_ms < 1500 THEN 'Medium (500ms-1.5s)'
                        ELSE 'Slow (>1.5s)'
                    END as latency_bucket
                FROM read_parquet({paths}, union_by_name=True)
                WHERE event_type = 'model_response'
            ),
            feedback AS (
                SELECT
                    response_id,
                    -- Convert thumbs to numeric ratings to increase sample size
                    COALESCE(
                        rating_value,
                        CASE
                            WHEN feedback_type = 'thumbs_up' THEN 5.0
                            WHEN feedback_type = 'thumbs_down' THEN 1.0
                        END
                    ) as normalized_rating
                FROM read_parquet({paths}, union_by_name=True)
                WHERE event_type = 'feedback'
            )
            SELECT
                r.latency_bucket,
                -- Filter out rows that still have no rating (e.g. text/report)
                COALESCE(round(avg(f.normalized_rating), 2)::double, 0) as avg_rating,
                count(f.normalized_rating)::int as sample_count,
                round(avg(r.total_latency_ms), 1)::double as avg_latency_ms
            FROM responses r
            LEFT JOIN feedback f ON r.response_event_id = f.response_id
            GROUP BY r.latency_bucket
            ORDER BY 2 DESC
            """

        logger.info(f"query is: {query}")
        result = self._query(query)
        logger.info(f"result is: {result}")
        return result

    # ------------------------------------------------------------------
    # Data Quality Scorecard
    # ------------------------------------------------------------------

    _GOLD_TABLE_NAMES = [
        "model_perf", "user_activity", "conversation_stats",
        "prompt_analytics", "feedback_summary", "feedback_categories",
    ]

    def get_data_quality(self, from_date: date, to_date: date) -> List[Dict]:
        """Data quality scorecard: quarantine rate, completeness, volume per day.

        Scans landing, quarantine, silver, and gold folders to compute
        per-day quality metrics. This is the 'data health' endpoint
        that demonstrates data engineering operational awareness.
        """
        # Batch-read silver row counts
        silver_row_map: Dict[str, int] = {}
        current_tmp = from_date
        while current_tmp <= to_date:
            ds = current_tmp.isoformat()
            sp = self._config.silver_root / ds / "events.parquet"
            if sp.exists():
                try:
                    rows = self._query(
                        f"SELECT count(*)::int as cnt FROM read_parquet('{sp}')"
                    )
                    silver_row_map[ds] = rows[0]["cnt"] if rows else 0
                except Exception:
                    silver_row_map[ds] = 0
            current_tmp += timedelta(days=1)

        results: List[Dict] = []
        current = from_date
        while current <= to_date:
            date_str = current.isoformat()

            # Landing file count
            landing_dir = self._config.landing_root / date_str
            landing_count = len(list(landing_dir.glob("*.json"))) if landing_dir.exists() else 0

            # Quarantine file count
            quarantine_dir = self._config.quarantine_root / date_str
            quarantine_count = len(list(quarantine_dir.glob("*"))) if quarantine_dir.exists() else 0

            # Silver row count from batch query
            silver_rows = silver_row_map.get(date_str, 0)

            # Gold completeness: how many of 6 expected tables exist
            gold_dir = self._config.gold_root / date_str
            gold_found = 0
            for t in self._GOLD_TABLE_NAMES:
                if gold_dir.exists() and (gold_dir / f"{t}.parquet").exists():
                    gold_found += 1

            quarantine_rate = round(quarantine_count / max(landing_count, 1) * 100, 2)
            completeness = round(gold_found / len(self._GOLD_TABLE_NAMES) * 100, 1)
            validity_rate = round(
                (landing_count - quarantine_count) / max(landing_count, 1) * 100, 1
            )

            results.append({
                "event_date": date_str,
                "landing_files": landing_count,
                "quarantine_files": quarantine_count,
                "quarantine_rate": quarantine_rate,
                "validity_rate": validity_rate,
                "silver_rows": silver_rows,
                "gold_completeness": completeness,
                "gold_tables_found": gold_found,
                "gold_tables_expected": len(self._GOLD_TABLE_NAMES),
            })
            current += timedelta(days=1)

        return results

    # ------------------------------------------------------------------
    # Silver queries (detail/debug)
    # ------------------------------------------------------------------

    def get_events(
        self,
        target_date: Optional[date] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        silver_root = str(self._config.silver_root)

        if target_date:
            path = f"{silver_root}/{target_date.isoformat()}/events.parquet"
        else:
            path = f"{silver_root}/*/events.parquet"

        union_clause = ", union_by_name=True" if not target_date else ""
        where = ""
        params: tuple = ()
        if event_type:
            where = " WHERE event_type = ?"
            params = (event_type,)

        return self._query(
            f"SELECT * FROM read_parquet('{path}'{union_clause}){where} ORDER BY event_timestamp DESC LIMIT {limit}",
            params,
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_available_dates(self) -> List[str]:
        """List available date partitions in Gold."""
        gold_root = self._config.gold_root
        if not gold_root.exists():
            return []
        return sorted(
            d.name for d in gold_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def health(self) -> Dict[str, Any]:
        """Return health status and available dates."""
        return {
            "status": "ok",
            "available_dates": self.get_available_dates(),
        }
