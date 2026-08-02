"""FastAPI analytics server for InsightFlow.

Serves pre-computed Gold metrics and Silver event detail over HTTP.
Each endpoint reads Parquet files — no database required.

Run:
    python -m src.api.server
    uvicorn src.api.server:app --reload
"""

from __future__ import annotations

from datetime import date
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.config import APIConfig
from src.api.queries import QueryService


# ── Shared state ──────────────────────────────────────────────────────────

_query_service: Optional[QueryService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create QueryService. Shutdown: close DuckDB connection."""
    global _query_service
    config = APIConfig()
    _query_service = QueryService(
        gold_root=config.gold_root,
        silver_root=config.silver_root,
    )
    yield
    if _query_service:
        _query_service.close()
        _query_service = None


app = FastAPI(
    title="InsightFlow Analytics API",
    description="AI Application Observability — Gold/Silver layer queries",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Response schemas ──────────────────────────────────────────────────────


class ModelPerf(BaseModel):
    model_name: str
    model_provider: str
    request_count: int
    success_count: int
    error_count: int
    timeout_count: int
    rate_limited_count: int
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    avg_ttft_ms: float
    avg_input_tokens: float
    avg_output_tokens: float


class UserActivity(BaseModel):
    subscription_tier: str
    unique_users: int
    total_logins: int
    successful_logins: int
    failed_logins: int


class ConversationStats(BaseModel):
    total_conversations: int
    avg_turns: float
    max_turns: int
    avg_duration_seconds: float


class PromptAnalytics(BaseModel):
    prompt_category: str
    total_prompts: int
    total_input_tokens: int
    avg_input_tokens: float
    avg_char_count: float


class FeedbackSummary(BaseModel):
    feedback_type: str
    count: int
    avg_rating: Optional[float] = None


class AvailableDates(BaseModel):
    dates: List[str]


# ── Gold Endpoints ────────────────────────────────────────────────────────


@app.get("/api/gold/model-perf", response_model=List[ModelPerf])
def get_model_perf(
    date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-29"),
):
    target = _parse_date(date) if date else None
    rows = _query_service.get_model_perf(target)
    if not rows:
        return []
    return rows


@app.get("/api/gold/user-activity", response_model=List[UserActivity])
def get_user_activity(
    date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-29"),
):
    target = _parse_date(date) if date else None
    rows = _query_service.get_user_activity(target)
    if not rows:
        return []
    return rows


@app.get("/api/gold/conversation-stats", response_model=List[ConversationStats])
def get_conversation_stats(
    date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-29"),
):
    target = _parse_date(date) if date else None
    rows = _query_service.get_conversation_stats(target)
    if not rows:
        return []
    return rows


@app.get("/api/gold/prompt-analytics", response_model=List[PromptAnalytics])
def get_prompt_analytics(
    date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-29"),
):
    target = _parse_date(date) if date else None
    rows = _query_service.get_prompt_analytics(target)
    if not rows:
        return []
    return rows


@app.get("/api/gold/feedback-summary", response_model=List[FeedbackSummary])
def get_feedback_summary(
    date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-29"),
):
    target = _parse_date(date) if date else None
    rows = _query_service.get_feedback_summary(target)
    if not rows:
        return []
    return rows


# ── Silver Endpoints ─────────────────────────────────────────────────────


@app.get("/api/silver/events")
def get_events(
    date: str = Query(..., description="ISO date, e.g. 2026-07-29"),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    target = _parse_date(date)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid date format")
    rows = _query_service.get_events(target, event_type, limit)
    return JSONResponse(content={"date": date, "events": rows, "count": len(rows)})


# ── Utility ──────────────────────────────────────────────────────────────


@app.get("/api/dates", response_model=AvailableDates)
def get_available_dates():
    dates = _query_service.get_available_dates()
    return AvailableDates(dates=dates)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insightflow-analytics"}


def _parse_date(date_str: str) -> Optional[date]:
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None



if __name__ == "__main__":
    import uvicorn
    config = APIConfig()
    uvicorn.run(
        "src.api.server:app",
        host=config.host,
        port=config.port,
        reload=True,
    )