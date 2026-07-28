# InsightFlow — Architectural Tradeoffs

> **Version:** 1.0  
> **Last Updated:** 2026-07-28

This document records every major architectural decision, the alternatives considered, and the rationale for the chosen approach. Every decision here was made intentionally — and every decision can be revisited as the project evolves.

---

## T1: Polars vs PySpark for ETL

| Aspect | Detail |
|--------|--------|
| **Decision** | Use Polars for V1 ETL processing |
| **Alternative** | PySpark (Apache Spark with Python bindings) |
| **Why Polars** | Rust-based, single-process, no JVM overhead. At V1 scale (~100MB/day), Spark's distributed compute adds complexity without benefit. Polars teaches the same concepts (lazy evaluation, projection pushdown, join strategies) with transparent execution. |
| **Tradeoff** | Polars is single-machine. When data exceeds single-machine capacity, we must migrate to Spark — which requires rewriting ETL logic. |
| **Revisit trigger** | Daily data volume exceeds 10 GB or streaming becomes a requirement |

---

## T2: DuckDB vs PostgreSQL as Analytics Engine

| Aspect | Detail |
|--------|--------|
| **Decision** | Use DuckDB to query Parquet files directly |
| **Alternative** | PostgreSQL (load Parquet data into relational tables) |
| **Why DuckDB** | DuckDB is a columnar OLAP engine that reads Parquet natively — zero data copying. PostgreSQL is an OLTP database optimized for transactional workloads. Loading data into PostgreSQL creates an unnecessary ETL step and loses Parquet's columnar advantages (predicate pushdown, compression). |
| **Tradeoff** | DuckDB is an embedded database (no standalone server). It cannot serve multiple concurrent clients like PostgreSQL. For V1 (single API server), this is fine. |
| **Revisit trigger** | Multiple consumers need concurrent access to analytics, or external BI tools need JDBC/ODBC connectivity |

---

## T3: No Prompt/Response Text in Telemetry

| Aspect | Detail |
|--------|--------|
| **Decision** | Store only length metrics (chars, tokens), not full text |
| **Alternative** | Store full prompt_text and response_text (with encryption at rest) |
| **Why no text** | Three reasons: (1) PII risk — users type personal information in prompts. Under GDPR, this is personally identifiable data. (2) Storage cost — 350K events/day × 200 chars average = 70MB/day just for text, growing to GB/month. (3) The full text already lives in the AI application's OLTP database and can be looked up via conversation_id. |
| **Tradeoff** | We lose the ability to analyze prompt content directly. Content analytics (e.g., "what topics are trending") require cross-referencing the OLTP database. |
| **Revisit trigger** | If content analytics becomes a business requirement, add prompt_hash for deduplication and prompt_preview for debugging |

---

## T4: Date-First Partitioning

| Aspect | Detail |
|--------|--------|
| **Decision** | Partition all data layers by event_date (YYYY-MM-DD) |
| **Alternative** | Partition by country_code, event_type, or subscription_tier |
| **Why date** | 90%+ of analytics queries are time-bounded ("yesterday's data", "last 7 days", "July trend"). Date partitioning optimizes the most common access pattern. Alternative partition keys would require scanning many partitions for time-based queries. |
| **Tradeoff** | Queries like "all data for India across all time" scan all date partitions. However, Parquet predicate pushdown mitigates this by filtering within files without full scans. |
| **Revisit trigger** | If query patterns shift to region-first or type-first access AND data volume per partition exceeds 1 GB |

---

## T5: FastAPI vs Django for API Layer

| Aspect | Detail |
|--------|--------|
| **Decision** | Use FastAPI for the analytics API |
| **Alternative** | Django with Django REST Framework |
| **Why FastAPI** | FastAPI is purpose-built for JSON APIs. It is async-native, generates OpenAPI documentation automatically, integrates with Pydantic for request/response validation, and has minimal boilerplate. Django is a full-stack web framework designed for building websites with HTML templates, user authentication, admin panels, and ORM — none of which we need for a data API. |
| **Tradeoff** | Django's ORM and admin panel would be useful if we needed a web-based management interface. FastAPI doesn't provide these. |
| **Revisit trigger** | If the project evolves to include user-facing web pages with authentication |

---

## T6: UUID vs Integer for Event IDs

| Aspect | Detail |
|--------|--------|
| **Decision** | Use UUIDs (string format) for event_id, user_id, session_id, conversation_id |
| **Alternative** | Auto-incrementing integers or Snowflake IDs |
| **Why UUID** | In a distributed system, multiple producers may generate events simultaneously. UUIDs guarantee uniqueness without requiring a central ID coordination service. Integers require either a central counter (single point of failure) or a Snowflake-like system (coordination overhead). |
| **Tradeoff** | UUIDs are 36 characters (vs 8-20 digits for integers), consuming more storage. UUID comparison is slightly slower than integer comparison. |
| **Revisit trigger** | If storage cost becomes a measurable concern at extreme scale (billions of events) |

---

## T7: Single Event-Responsibility Principle

| Aspect | Detail |
|--------|--------|
| **Decision** | Each event captures only data that does not exist in any other event |
| **Alternative** | Include redundant/aggregated fields in events for convenience |
| **Why single responsibility** | Aggregating data in events creates duplication. If a conversation has 10 prompt-response pairs, putting total tokens in conversation_closed duplicates data that already exists in 10 model_response events. Duplicated data can become inconsistent (what if one event is missing?). Aggregation belongs in the Gold layer, not in event schemas. |
| **Tradeoff** | Some queries require joining multiple event types. A denormalized approach would make single-event queries faster. |
| **Revisit trigger** | If specific single-event queries become performance bottlenecks |

---

## T8: Schema Version on Every Event

| Aspect | Detail |
|--------|--------|
| **Decision** | Every event includes a schema_version field |
| **Alternative** | Infer schema version from timestamp or use a separate metadata file |
| **Why explicit version** | Schema changes don't follow a calendar. The AI application may deploy schema changes at any time. During a transition period, events with different schemas coexist in the same data partition. An explicit schema_version on each event allows the ETL pipeline to apply version-specific validation and transformation logic per-event, not per-batch. |
| **Tradeoff** | Adds 4-6 bytes per event (e.g., "1.0"). Negligible. |
| **Revisit trigger** | Never — this is a permanent design decision |

---

## T9: Malformed Event Injection in Simulator

| Aspect | Detail |
|--------|--------|
| **Decision** | The simulator intentionally generates 5% malformed events, 3% duplicates, and 2% late arrivals |
| **Alternative** | Generate only clean, valid events |
| **Why noise injection** | Production data is messy. Real telemetry systems deal with malformed JSON, duplicate events from retries, and late-arriving data. A simulator that generates only clean data bypasses the hardest problems in data engineering: data quality, deduplication, and out-of-order processing. |
| **Tradeoff** | Makes the pipeline more complex (quarantine logic, deduplication, late arrival handling). But this complexity IS the learning objective. |
| **Revisit trigger** | Never — this is core to the educational value of the project |

---

## T10: Parquet for Bronze+ (JSON for Landing Zone Only)

| Aspect | Detail |
|--------|--------|
| **Decision** | Landing Zone stores raw JSON; Bronze, Silver, Gold store Parquet |
| **Alternative** | Use JSON throughout all layers, or use Parquet from landing zone |
| **Why JSON in Landing** | Landing Zone is for raw, unmodified data. JSON is the format events arrive in. Modifying the format (converting to Parquet) is a transformation — transformations belong in the ETL layer, not in ingestion. |
| **Why Parquet for Bronze+** | Parquet provides columnar storage (read only needed columns), compression (5-10x smaller than JSON), schema embedding (schema is part of the file), and predicate pushdown (skip irrelevant rows during reads). |
| **Tradeoff** | Two different file formats mean two different read/write codepaths. But the format change IS the Bronze layer's purpose — it's where raw data becomes structured data. |
| **Revisit trigger** | Never — this is the standard medallion architecture pattern |
