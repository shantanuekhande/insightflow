
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

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python | Primary language for data engineering ecosystem |
| ETL Processing | Polars (V1) | Rust-based, fast, teaches query optimization internals |
| Storage Format | Parquet | Columnar, compressed, predicate pushdown, schema-embedded |
| Query Engine | DuckDB | In-process OLAP, reads Parquet natively, zero-copy |
| API Framework | FastAPI | Async-native, auto-docs, Pydantic validation |
| Containers | Docker Compose | Reproducible, production-parallels, isolated services |
| Event Modeling | Pydantic | Type-safe event definitions, validation at write time |
| Testing | pytest | Industry standard, fixtures, parametrized tests |

**Future (V2+):** Apache Kafka, Apache Spark, Airflow, Delta Lake, AWS S3, Kubernetes

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

| Layer | Format | Description |
|-------|--------|-------------|
| Landing Zone | JSON (raw) | Raw events as received. Used for replay, audit, and reprocessing. |
| Bronze | Parquet | Raw data persisted in columnar format. Immutable. |
| Silver | Parquet | Validated, cleaned, deduplicated, standardized. |
| Gold | Parquet | Business-ready aggregations (daily usage, model stats, cost, feedback). |

**Partition Strategy:** All layers partitioned by `event_date` (YYYY-MM-DD). Date-first partitioning optimizes for the most common query pattern: time-bounded analytics.

---

## Project Structure

```
insightflow/
├── src/
│   ├── simulator/       # AI application simulator (event generation)
│   │   ├── models.py    # Pydantic event models
│   │   ├── generator.py # Event generation logic
│   │   ├── personas.py  # User persona definitions
│   │   └── config.py    # Configuration
│   ├── schemas/          # Event schema definitions and constants
│   ├── etl/             # Bronze → Silver → Gold transformations
│   ├── api/             # FastAPI analytics endpoints
│   └── tests/           # Unit and integration tests
├── data/
│   ├── landing/         # Raw JSON events (date-partitioned)
│   ├── bronze/          # Immutable Parquet copies
│   ├── silver/          # Clean, validated Parquet
│   ├── gold/            # Business-ready Parquet
│   └── quarantine/      # Failed/malformed events
├── docs/
│   ├── event-schema.md  # Complete event schema documentation
│   ├── HLD.md           # High-Level Design
│   └── diagrams/        # Architecture and data flow diagrams
├── docker/              # Dockerfile(s) per service
├── docker-compose.yml   # Local development environment
├── pyproject.toml       # Dependencies and project config
└── README.md            # This file
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

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/<your-username>/insightflow.git
cd insightflow

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
# Start all services
docker-compose up --build

# Generate sample events
python -m src.simulator.generator

# Run ETL pipeline
python -m src.etl.ingest

# Start the API
python -m src.api.main

# View dashboard
open http://localhost:8000/docs  # FastAPI auto-docs
```

---

## Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Event schema design and documentation | ✅ Complete |
| 1 | Project scaffold and event simulator | 🔄 In Progress |
| 2 | Bronze layer and ingestion pipeline | ⏳ Pending |
| 3 | Silver layer and ETL with Polars | ⏳ Pending |
| 4 | Gold layer and business aggregations | ⏳ Pending |
| 5 | FastAPI analytics API | ⏳ Pending |
| 6 | Dashboard and visualization | ⏳ Pending |

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
