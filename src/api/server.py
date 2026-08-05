"""FastAPI application for InsightFlow API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api.config import APIConfig
from src.api.queries import QueryService
from src.api.dashboard import router as dashboard_router

# ---------------------------------------------------------------------------
# Response models for OpenAPI docs
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    available_dates: List[str]


class DateListResponse(BaseModel):
    dates: List[str]


class EventResponse(BaseModel):
    events: List[Dict[str, Any]]
    count: int


class ModelPerfRow(BaseModel):
    model_name: str
    model_provider: str
    invocation_count: int
    success_count: int
    error_count: int
    timeout_count: int
    rate_limited_count: int
    avg_latency_ms: Optional[float]
    p50_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    p99_latency_ms: Optional[float]
    avg_ttft_ms: Optional[float]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_cost_usd: float
    success_rate_pct: float
    error_rate_pct: float


class KPISummary(BaseModel):
    total_conversations_started: Optional[int]
    total_conversations_closed: Optional[int]
    avg_turns: Optional[float]
    avg_duration_seconds: Optional[float]
    total_invocations: Optional[int]
    total_cost_usd: Optional[float]
    avg_latency: Optional[float]
    avg_success_rate: Optional[float]
    avg_rating: Optional[float]
    total_feedback: Optional[int]


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_query_service: Optional[QueryService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create QueryService on startup, close on shutdown."""
    global _query_service
    config = APIConfig()
    _query_service = QueryService(config)
    yield
    if _query_service:
        _query_service.close()


app = FastAPI(
    title="InsightFlow API",
    description="AI Application Observability Data Platform",
    version="2.0",
    lifespan=lifespan,
)

# Mount dashboard
app.include_router(dashboard_router)

# Serve static files
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ---------------------------------------------------------------------------
# Health & metadata
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health():
    qs = _get_qs()
    return qs.health()


@app.get("/api/dates", response_model=DateListResponse)
async def available_dates():
    qs = _get_qs()
    return DateListResponse(dates=qs.get_available_dates())


# ---------------------------------------------------------------------------
# Gold endpoints: single date
# ---------------------------------------------------------------------------


@app.get("/api/gold/model-perf")
async def get_model_perf(date: Optional[str] = Query(None, description="YYYY-MM-DD")):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_model_perf(d)


@app.get("/api/gold/user-activity")
async def get_user_activity(date: Optional[str] = Query(None), top_n: int = Query(20)):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_user_activity(d, top_n)


@app.get("/api/gold/conversation-stats")
async def get_conversation_stats(date: Optional[str] = Query(None)):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_conversation_stats(d)


@app.get("/api/gold/prompt-analytics")
async def get_prompt_analytics(date: Optional[str] = Query(None)):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_prompt_analytics(d)


@app.get("/api/gold/feedback-summary")
async def get_feedback_summary(date: Optional[str] = Query(None)):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_feedback_summary(d)


@app.get("/api/gold/feedback-categories")
async def get_feedback_categories(date: Optional[str] = Query(None)):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_feedback_categories(d)


# ---------------------------------------------------------------------------
# Gold endpoints: trend (date range)
# ---------------------------------------------------------------------------


@app.get("/api/gold/model-perf/trend")
async def get_model_perf_trend(from_date: str = Query(...), to_date: str = Query(...)):
    qs = _get_qs()
    return qs.get_model_perf_trend(_parse_date(from_date), _parse_date(to_date))


@app.get("/api/gold/user-activity/trend")
async def get_user_activity_trend(
    from_date: str = Query(...), to_date: str = Query(...), top_n: int = Query(20)
):
    qs = _get_qs()
    return qs.get_user_activity_trend(_parse_date(from_date), _parse_date(to_date), top_n)


@app.get("/api/gold/feedback/trend")
async def get_feedback_trend(from_date: str = Query(...), to_date: str = Query(...)):
    qs = _get_qs()
    return qs.get_feedback_trend(_parse_date(from_date), _parse_date(to_date))


@app.get("/api/gold/kpis")
async def get_daily_kpis(from_date: str = Query(...), to_date: str = Query(...)):
    qs = _get_qs()
    return qs.get_daily_kpis(_parse_date(from_date), _parse_date(to_date))


@app.get("/api/gold/latency-heatmap")
async def get_latency_heatmap(from_date: str = Query(...), to_date: str = Query(...)):
    """Q3: Latency heatmap — hour x day_of_week, color = P95 latency."""
    qs = _get_qs()
    return qs.get_latency_heatmap(_parse_date(from_date), _parse_date(to_date))


@app.get("/api/gold/feedback-correlation")
async def get_feedback_correlation(from_date: str = Query(...), to_date: str = Query(...)):
    """Q5: Feedback vs latency correlation — avg rating by latency bucket."""
    qs = _get_qs()
    return qs.get_feedback_latency_correlation(_parse_date(from_date), _parse_date(to_date))


# ---------------------------------------------------------------------------
# Silver endpoints (detail)
# ---------------------------------------------------------------------------


@app.get("/api/silver/events")
async def get_events(
    date: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100),
):
    qs = _get_qs()
    d = _parse_date(date)
    return qs.get_events(d, event_type, limit)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_qs() -> QueryService:
    if _query_service is None:
        raise RuntimeError("QueryService not initialized")
    return _query_service


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="127.0.0.1", port=8000, reload=True)
