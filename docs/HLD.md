
# InsightFlow — High-Level Design (HLD)

> **Version:** 1.0  
> **Status:** Draft  
> **Last Updated:** 2026-07-28

---

## 1. Introduction

### 1.1 Purpose

InsightFlow is a data platform that captures telemetry from an AI application, processes it through a medallion architecture (Bronze → Silver → Gold), and serves analytics through a REST API. The platform is designed to answer business-critical questions about AI application usage, performance, cost, and quality.

### 1.2 Scope

InsightFlow does NOT:
- Build an LLM or AI model
- Build a chatbot or user-facing application
- Serve as an operational database for the AI application

InsightFlow DOES:
- Receive telemetry events from an AI application (or simulator)
- Store, validate, clean, and aggregate that telemetry
- Serve analytics through a REST API
- Enable business decision-making through data

### 1.3 Stakeholders

| Stakeholder | Questions They Ask |
|-------------|-------------------|
| CTO | "What was yesterday's total inference cost?" |
| Data Engineer | "Are there schema mismatches in today's events?" |
| ML Engineer | "Which model has the best feedback rate?" |
| Product Manager | "What prompt categories are most popular?" |
| DevOps Engineer | "Which server region has the highest error rate?" |

---

## 2. Architecture Overview

### 2.1 System Context

```
┌─────────────────────────────────┐
│     AI Application (External)   │
│  (Simulated in V1 via Simulator)│
└───────────┬─────────────────────┘
            │
            │ Telemetry Events (JSON)
            │
            ▼
┌───────────────────────────────────────────────┐
│                  InsightFlow                    │
│                                                │
│  ┌─────────┐  ┌───────┐  ┌───────┐  ┌──────┐ │
│  │ Landing │→│Bronze │→│Silver │→│ Gold │ │
│  │  Zone   │  │ Layer │  │ Layer │  │Layer │ │
│  └─────────┘  └───────┘  └───────┘  └──┬───┘ │
│                                        │       │
│                                        ▼       │
│                                   ┌────────┐   │
│                                   │ DuckDB │   │
│                                   └───┬────┘   │
│                                       │        │
│                                       ▼        │
│                                   ┌────────┐   │
│                                   │FastAPI │   │
│                                   └───┬────┘   │
│                                       │        │
│                                       ▼        │
│                                   ┌────────┐   │
│                                   │Dashboard│   │
│                                   └────────┘   │
└───────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
1. AI Application generates a telemetry event (JSON)
       │
       ▼
2. Event lands in Landing Zone as a single JSON file
   (partitioned by event_date: data/landing/2026-07-25/event_001.json)
       │
       ▼
3. Ingestion reads Landing Zone → writes to Bronze (Parquet)
   (validates JSON structure, quarantines malformed events)
       │
       ▼
4. ETL reads Bronze → validates, cleans, deduplicates → writes Silver
   (schema validation against schema_version, timestamp standardization)
       │
       ▼
5. ETL reads Silver → aggregates by business dimensions → writes Gold
   (daily usage, model stats, cost analytics, feedback rates)
       │
       ▼
6. FastAPI reads Gold (via DuckDB over Parquet) → serves JSON
       │
       ▼
7. Dashboard consumes FastAPI endpoints → renders charts
```

---

## 3. Component Design

### 3.1 Simulator (src/simulator/)

**Responsibility:** Generate realistic telemetry events that mimic a production AI application.

**Key Design Decisions:**
- Uses Pydantic models for type-safe event generation
- Generates realistic distributions (70% free users, 25% pro, 5% enterprise)
- Injects realistic failure modes: malformed events (5%), duplicates (3%), late arrivals (2%)
- Each run generates events for a configurable date range and volume

**Files:**
| File | Purpose |
|------|---------|
| `models.py` | Pydantic models matching the event schema |
| `generator.py` | Event generation logic and orchestration |
| `personas.py` | User persona definitions and distributions |
| `config.py` | Configuration (event counts, date ranges, failure rates) |

### 3.2 Data Layers (data/)

**Landing Zone:** Raw JSON files, one event per file, partitioned by `event_date`. Purpose: replay, audit, reprocessing.

**Bronze Layer:** Parquet files, immutable copy of landing zone data. Purpose: persistent raw storage with columnar format benefits.

**Silver Layer:** Parquet files, validated and cleaned. Purpose: reliable source for downstream processing. Schema validation, deduplication, timestamp standardization, missing field handling.

**Gold Layer:** Parquet files, business-ready aggregations. Purpose: direct consumption by API and dashboard. Pre-computed tables for common queries.

**Quarantine:** JSON files for events that failed validation. Purpose: investigation and reprocessing.

### 3.3 ETL Pipeline (src/etl/)

**Responsibility:** Transform data through Bronze → Silver → Gold.

**Design Principles:**
- Idempotent: running the same pipeline twice produces the same result
- Metadata tracked: every run records row counts, error counts, duration
- Schema version aware: handles multiple schema versions in the same data

### 3.4 API Layer (src/api/)

**Responsibility:** Serve analytics via REST endpoints.

**Design Principles:**
- API-first: the API is the primary interface, not the dashboard
- DuckDB reads Parquet directly — no data copying to a database
- Pagination, date filtering, and query optimization built in
- Auto-documented via FastAPI's Swagger UI

### 3.5 Testing (src/tests/)

- Schema validation tests
- ETL correctness tests (Bronze → Silver row count consistency)
- Aggregation tests (Gold sums match Silver source)
- API response format tests

---

## 4. Technology Decisions

### 4.1 Polars Over Spark (V1)

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Tool | Polars | Rust-based, single-machine, teaches lazy evaluation and pushdown |
| Alternative | PySpark | Overkill at V1 scale (~100MB/day); JVM overhead not justified |
| When to switch | V2+ | When data volume exceeds single-machine capacity or streaming is needed |

### 4.2 DuckDB Over PostgreSQL

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Tool | DuckDB | Columnar, reads Parquet natively (zero-copy), teaches OLAP concepts |
| Alternative | PostgreSQL | OLTP database, not designed for analytics; creates unnecessary ETL step |
| When to switch | External users | If serving analytics to external consumers, add a caching layer |

### 4.3 FastAPI Over Django

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Tool | FastAPI | Purpose-built for JSON APIs; async-native; auto-docs; Pydantic integration |
| Alternative | Django | Full-stack web framework; unnecessary for a data API; adds bloat |
| When to switch | User-facing app | If building a web interface with auth, templates, and forms |

### 4.4 Parquet Over JSON for Bronze+

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Tool | Parquet | Columnar storage enables predicate pushdown, compression, schema embedding |
| Alternative | JSON | Human-readable but slow to query at scale; no compression; no pushdown |
| Exception | Landing Zone | JSON is kept in Landing Zone for raw audit/replay |

---

## 5. Scalability Considerations

| Scale | Bottleneck | Solution |
|-------|-----------|----------|
| 1 GB/day | Single machine handles it | Polars + DuckDB sufficient |
| 10 GB/day | Single machine may strain | Introduce Spark for ETL |
| 100 GB/day | Single machine insufficient | Distributed processing (Spark on cluster) |
| 1 TB/day | Storage and compute scaling | S3 + Spark (EMR/Databricks) |
| 1M events/day | File system limits | Kafka for ingestion, partition compaction |
| 100M events/day | End-to-end platform scaling | Kubernetes, S3, Spark Streaming, Airflow |

---

## 6. Security Considerations

- No PII stored in analytics pipeline (prompts and responses are not stored in full)
- Configuration secrets managed via environment variables, not hardcoded
- API authentication planned for V2
- Audit trail maintained via immutable Bronze layer
