
# InsightFlow

> **A Modern Data Platform for AI Application Observability**

*"Building the analytics platform behind an AI application — not the AI application itself."*

---

## The Problem

AI applications generate millions of telemetry events every day. User logins, prompt submissions, model inference, feedback, conversation lifecycle — each interaction produces data. But most teams can't answer basic questions:

- Why did yesterday's inference cost increase by 27%?
- Which model has the highest error rate?
- Why is latency spiking every evening?
- Which users consume the most resources?
- Are users satisfied with the responses?

The production database isn't designed for analytics. Application logs are scattered. Telemetry events are generated but never analyzed systematically.

**InsightFlow transforms raw telemetry events into actionable business insights.**

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Polars](https://img.shields.io/badge/Polars-columnar-orange)
![DuckDB](https://img.shields.io/badge/DuckDB-embedded-green)

---

## Architecture

```
AI Application Simulator          ← Generates realistic telemetry
          │
          ▼
Landing Zone (Raw JSON)          ← Immutable, date-partitioned
          │
          ▼
Bronze Layer (Parquet)           ← Raw data, schema-validated
          │
          ▼
Silver Layer (Parquet)           ← Clean, deduplicated, standardized
          │
          ▼
Gold Layer (Parquet)             ← Business-ready aggregations
          │
          ▼
DuckDB (Query Engine)             ← Reads Parquet directly, no copy
          │
          ▼
FastAPI (Analytics API)           ← Serves JSON via REST endpoints
          │
          ▼
Dashboard (Visualization)        ← Business-friendly charts
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Schemas | Pydantic v2 | Runtime validation, JSON serialization |
| ETL | Polars | Rust-based, columnar, fast transformations |
| Queries | DuckDB | SQL on Parquet, zero-copy reads, predicate pushdown |
| API | FastAPI + Uvicorn | Async, auto-docs (Swagger), type-safe endpoints |
| Dashboard | Vanilla HTML/JS | Zero build step, API consumer pattern |
| Storage | Parquet | Compressed, schema-embedded, columnar reads |

---

## Event Schema

We capture 6 event types from the AI application lifecycle:

| Event | Purpose |
|-------|---------|
| `user_login` | Track DAU, device distribution, auth failures |
| `conversation_started` | Measure conversation frequency and engagement |
| `prompt_submitted` | Track prompt volume, length, user context |
| `model_response` | Track latency, tokens, cost, model performance, errors |
| `feedback` | Track quality signals and user satisfaction |
| `conversation_closed` | Measure conversation duration and completion |

Full schema documentation: [docs/event-schema.md](docs/event-schema.md)

---

## Data Layers

| Layer | Format | Validates | Produces |
|-------|--------|-----------|----------|
| **Landing** | JSON files (date-partitioned) | — | Raw events with noise (malformed, duplicates, late arrivals) |
| **Bronze** | Parquet (per event type) | Structure (4 required fields) | Structurally valid events, quarantined failures |
| **Silver** | Parquet (all events merged) | Semantics (enum values, nulls, dedup) | Clean, deduplicated, sorted events |
| **Gold** | Parquet (5 tables) | Aggregations | model_perf, user_activity, conversation_stats, prompt_analytics, feedback_summary |

**Partition Strategy:** All layers partitioned by `event_date` (YYYY-MM-DD). Date-first partitioning optimizes for the most common query pattern: time-bounded analytics.

---

## Project Structure

```
src/
├── schemas/          # Pydantic models + enums (6 event types)
├── simulator/        # Data generator with personas + noise injection
├── etl/
│   ├── config.py     # ETLConfig with path routing
│   ├── ingest.py     # Landing → Bronze
│   ├── transform.py  # Bronze → Silver
│   ├── gold.py       # Silver → Gold (5 aggregation tables)
│   └── metadata.py   # Pipeline run tracking
├── api/
│   ├── config.py     # APIConfig
│   ├── queries.py    # DuckDB query layer
│   ├── server.py     # FastAPI app + endpoints
│   ├── dashboard.py  # Dashboard router
│   └── static/       # index.html
└── tests/
    ├── test_models.py
    ├── test_silver.py
    └── test_gold.py
docs/
├── tradeoffs.md      # Design decisions and rationale
├── event-schema.md   # Event specifications with JSON examples
└── HLD.md            # High-level design document
data/
├── landing/          # Raw JSON events (date-partitioned)
├── bronze/           # Structurally valid Parquet
├── silver/           # Clean, deduplicated Parquet
├── gold/             # Pre-computed aggregations
└── quarantine/       # Failed events with reasons
```

---

## Engineering Principles

1. **Every component has one responsibility.**
2. **Every architectural decision is documented with tradeoffs.**
3. **Every transformation exists for a business reason.**
4. **The simulator and the data platform remain independent.**
5. **If a feature doesn't help answer a business question, we don't build it.**
6. **Schema design comes before code.**

---

## Quick Start

```bash
# 1. Install dependencies
pip install polars pydantic fastapi uvicorn duckdb pytest

# 2. Generate synthetic data
python -m src.simulator.generator

# 3. Run the full pipeline
python -m src.etl.ingest      # Landing → Bronze
python -m src.etl.transform   # Bronze → Silver
python -m src.etl.gold        # Silver → Gold

# 4. Start the API server
uvicorn src.api.server:app --reload --port 8000

# 5. Open the dashboard
#    http://127.0.0.1:8000
#    API docs: http://127.0.0.1:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/gold/model-perf` | Model performance metrics |
| GET | `/api/gold/model-perf/trend` | Model performance over a date range |
| GET | `/api/gold/user-activity` | User login stats by tier |
| GET | `/api/gold/user-activity/trend` | User activity over a date range |
| GET | `/api/gold/conversation-stats` | Global conversation aggregates |
| GET | `/api/gold/prompt-analytics` | Prompt category metrics |
| GET | `/api/gold/feedback-summary` | Feedback type breakdown |
| GET | `/api/gold/feedback/trend` | Feedback summary over a date range |
| GET | `/api/gold/feedback-categories` | Feedback category breakdown |
| GET | `/api/gold/kpis` | Daily KPI summary over a date range |
| GET | `/api/gold/latency-heatmap` | P95 latency heatmap over a date range |
| GET | `/api/gold/feedback-correlation` | Feedback vs. latency correlation over a date range |
| GET | `/api/silver/events?date=X` | Raw events with optional type filter |
| GET | `/api/dates` | Available date partitions |
| GET | `/api/health` | Health check |

Single-date gold endpoints accept optional `?date=YYYY-MM-DD` query parameter.
Trend and dashboard summary endpoints accept `?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`.

## Running Tests

```bash
python -m pytest src/tests/ -v
```

## Gold Tables

| Table | Grain | Key Metrics |
|-------|-------|-------------|
| `model_perf` | (model_name, model_provider) | request_count, success/error/timeout/rate_limited counts, avg/median/p95 latency, avg TTFT, token counts |
| `user_activity` | subscription_tier | unique_users, total_logins, successful/failed logins |
| `conversation_stats` | date (global) | total_conversations, avg/max turns, avg duration |
| `prompt_analytics` | prompt_category | total_prompts, total/avg input tokens, avg char count |
| `feedback_summary` | feedback_type | count, avg_rating |
| `feedback_categories` | feedback_category | count, avg_rating |

## What I Learned

1. **Medallion Architecture is graduated trust** — not "clean vs dirty" but three levels of data reliability, each independently rebuildable.
2. **Parquet + DuckDB is powerful** — zero infrastructure, predicate pushdown, schema-embedded, columnar reads.
3. **Polars for writes, DuckDB for reads** — different engines for different problems. Polars transforms, DuckDB queries.
4. **Type systems prevent bugs** — Pydantic enums catch bad data before it reaches analytics.
5. **Thread safety matters** — DuckDB access needs request serialization for safe concurrent API use.
6. **Separation of concerns** — ETL (build) vs queries (serve) vs dashboard (present) are different problems with different tools.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Event Schema](docs/event-schema.md) | Complete event definitions, field references, enums |
| [HLD](docs/HLD.md) | High-level architecture and component design |
| [Tradeoffs](docs/tradeoffs.md) | Architectural decisions and their rationale |

---

## License

This project is for educational and portfolio purposes.
