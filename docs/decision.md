# InsightFlow — Design Decisions

Conceptual decisions I made while building V1. No code errors, no bug fixes — just "why did I choose X and not Y?"

---

## Storage

### Why Parquet instead of CSV or JSON?

CSV is row-oriented. You read the whole file even if you need one column. No type information — 
everything is a string. No compression built-in.

JSON has the same row-oriented problem. Nested structures make column access slow. A 1GB 
JSON file with 10 columns? Want just 2 columns? You still parse the whole GB.

Parquet is **columnar**. Each column is stored separately, compressed, with statistics (min, max, 
null count) at the row group level. When you write `SELECT model_name FROM read_parquet('...')`, 
DuckDB reads ONLY the model_name column. It skips every other column entirely. The file might 
be 500MB but you read 2MB.

Parquet also embeds the schema — column names, types, nullable flags — inside the file itself. 
No separate schema file needed. You can drop a Parquet file from 6 months ago and it still 
knows its own structure.

**In InsightFlow:** Landing zone uses JSON (that's what applications emit). Everything after 
Bronze uses Parquet. This is standard — raw ingestion is flexible, then you convert to an 
efficient format immediately.

### What is a row group and why does it matter?

A Parquet file is split into horizontal slices called **row groups** (default ~128K rows each). 
Each row group stores column statistics: min, max, null count per column.

When DuckDB queries `WHERE event_date = '2026-07-29'`, it reads the statistics of each row 
group. If a row group's min/max for that column doesn't include '2026-07-29', it **skips 
the entire row group without reading it**. This is called **predicate pushdown**.

This is why Parquet queries are fast: you don't read data you don't need, at two levels — 
column level AND row group level.

---

## Query Engine

### What is DuckDB?

DuckDB is an embedded SQL database — no server, no config file, no network port. You call 
`duckdb.connect(":memory:")` and you have a full SQL engine running inside your Python 
process. When the process exits, the database is gone.

It can read Parquet files directly from disk. No import step. No ETL. You write:
```sql
SELECT model_name, avg(total_latency_ms) 
FROM read_parquet('data/gold/2026-07-29/model_perf.parquet')
GROUP BY model_name
```
And DuckDB reads the file, pushes down the GROUP BY, and returns the result. Zero data copying.

### Why DuckDB instead of pandas?

Pandas reads the ENTIRE file into memory as a DataFrame. A 2GB Parquet file → 2GB RAM used. 
Then you do `df.groupby("model_name").mean()` → pandas scans the whole DataFrame in Python. 
Slow, memory-heavy, single-threaded.

DuckDB reads only the columns and row groups it needs. It uses vectorized execution (process 
chunks of values at once, not row-by-row). It's written in C++ and uses LLVM for JIT 
compilation. The same query that takes pandas 5 seconds takes DuckDB 50 milliseconds.

Pandas is a data manipulation library. DuckDB is a query engine. Different tools for 
different jobs.

### Why DuckDB instead of SQLite?

SQLite is row-oriented. No predicate pushdown on Parquet. No columnar reads. You'd have to 
import Parquet data into SQLite tables first, then query. That's an extra step and extra 
storage.

DuckDB was designed specifically for analytical queries on columnar data. SQLite was designed 
for transactional (OLTP) workloads — point lookups, inserts, updates. Analytics needs 
scanning millions of rows and aggregating — that's DuckDB's strength.

### What is a DuckDB connection?

When you call `duckdb.connect(":memory:")`, DuckDB creates:
- A query parser (reads your SQL)
- A query planner (decides HOW to execute)
- An execution engine (runs the plan)
- A catalog (tracks tables, views, functions)

The connection is NOT a network socket. It's an in-process object. There's no server 
process, no port, no authentication. It's like a SQLite connection — lightweight and local.

But here's the critical difference from SQLite: a DuckDB connection is **not thread-safe**. 
Only one thread can use a connection at a time. If two threads call `.execute()` 
simultaneously on the same connection, you get corrupted internal state or a deadlock.

### Why does DuckDB hang with concurrent requests?

FastAPI serves each HTTP request in a separate thread (via `run_in_threadpool`). The 
dashboard fires 5 API calls simultaneously using `Promise.all()`. All 5 hit the same 
DuckDB connection at the same time. DuckDB's internal state (query parser, catalog, 
execution engine) gets corrupted by concurrent access. Result: hang or crash.

The fix is `threading.Lock()` — a mutex that ensures only one thread touches DuckDB at a 
time. Thread 1 acquires the lock, executes, releases. Thread 2 was waiting, now acquires, 
executes, releases. Sequential, not parallel. But for 5 small queries on local data, 
the total time is still under 50ms.

This is a **local development limitation**, not a DuckDB bug. In production:
- You'd create one connection per request (DuckDB connects in ~5ms)
- Or use a connection pool
- Or switch to a client-server database (Postgres, ClickHouse) that handles 
  concurrent connections natively

---

## ETL Engine

### What is Polars?

Polars is a DataFrame library written in Rust, exposed through Python. Like pandas, it 
manages tabular data. Unlike pandas, it's:
- **Columnar-native**: Data stored in Apache Arrow column format, not Python objects
- **Lazy by default**: You build a computation graph, then call `.collect()` to execute 
  once — Polars optimizes the entire plan before running it
- **Multi-threaded**: Operations automatically parallelize across CPU cores
- **Memory-efficient**: Uses Arrow's zero-copy memory format, no Python object overhead

A DataFrame in pandas is a collection of Python objects. Each cell is a Python object 
with reference counting, type checking, and garbage collection overhead. A 1M-row DataFrame 
in pandas might use 200MB. The same data in Polars uses ~40MB because it's raw Arrow 
arrays, not Python objects.

### Why Polars for the WRITE path (ETL)?

The ETL pipeline does transformations: filter, validate, deduplicate, group, aggregate, 
write. These are **batch operations** — process all rows, produce a result.

Polars' expression API is designed for this:
```python
pl.col("status").eq("success").sum()
```
This is a single expression that Polars compiles into an optimized plan. It processes 
the entire column in one pass, using SIMD instructions (processes 4-8 values per CPU cycle). 
No Python loops, no intermediate allocations.

DuckDB can do transformations too, but Polars is better at:
- Schema enforcement and type casting
- `how="diagonal"` concat (merge DataFrames with different columns, fill missing with null)
- Complex validation chains (`is_null() | is_in()`)
- Writing to Parquet with specific partitioning

**The pattern:** Polars builds data products (transform, validate, write). DuckDB serves 
data products (query, filter, aggregate). Write engine vs read engine.

### What is "how=diagonal" concat and why does it matter?

Different event types have different schemas:
```
user_login:     has device_type, device_os, login_status
model_response: has total_latency_ms, inference_latency_ms, prompt_token_count
```

These are incompatible DataFrames — you can't stack them with pandas (it would crash or 
create a mess). Polars' `how="diagonal"` handles this:
- Columns present in both → aligned and stacked
- Columns only in one → filled with null in the other
- Result: one unified DataFrame with all columns

This is how Silver merges 6 different event types into one `events.parquet` file.

### Why not use Polars for the READ path (API queries) too?

You could. `pl.read_parquet().filter().groupby().agg()` works. But:
- SQL is universal — any analyst, PM, or stakeholder can write a query without knowing Python
- DuckDB's predicate pushdown on Parquet is more mature — it can skip row groups before 
  reading them into memory
- SQL naturally expresses ad-hoc questions: "show me models where error rate > 5% and 
  p95 latency > 1000ms" — this is one SQL line vs a multi-step Polars expression chain

Polars for **planned, repeated transformations** (pipeline). DuckDB for **ad-hoc, 
unpredictable queries** (API). This separation is the industry standard in modern 
lakehouse architectures.

---

## Architecture

### Why Medallion Architecture?

A single data store means you're mixing raw, unvalidated data with clean, aggregated 
metrics. One bad row can corrupt your analytics. One schema change can break your queries.

Medallion splits this into three trust levels:

**Bronze** — "Did this event arrive intact?"
- Valid JSON? 4 required fields present? Yes → store. No → quarantine.
- Nothing is transformed. Nothing is dropped. Every field preserved exactly as received.
- Bronze is immutable — you never modify it. It's your source of truth for raw data.

**Silver** — "Is this data correct?"
- Enum values valid? `subscription_tier = "platinum"` → quarantine (not a real tier).
- Required fields non-null? `user_id = null` → quarantine.
- Duplicate event_ids? Remove extras, keep first.
- Silver is where data becomes **trustworthy**. Gold layer never touches Bronze.

**Gold** — "What are the business metrics?"
- Pre-computed aggregations: model performance, user activity, prompt analytics.
- Dashboard queries read Gold and return instantly — no joins, no GROUP BY at query time.
- Gold tables have different "grains" (one row per model, one row per tier, etc.)

**Why three layers?** Because each layer solves a different problem. You can rebuild Silver 
from Bronze without re-running the simulator. You can rebuild Gold from Silver without 
re-processing raw events. Each layer is independently reproducible.

### Why 5 separate Gold tables instead of 1 big table?

Each table has a different **grain** — the thing that defines a unique row:

| Table | One row per... | Example |
|-------|---------------|---------|
| model_perf | (model_name, model_provider) | qwen/local, gpt-4/api |
| user_activity | subscription_tier | free, pro, enterprise |
| conversation_stats | date (global, no grouping) | one row per day |
| prompt_analytics | prompt_category | coding, writing, math |
| feedback_summary | feedback_type | thumbs_up, star_rating |

Mixing these into one table violates **first normal form** — each row would mean something 
different depending on which columns you look at. Separate tables = clear semantics, 
separate API endpoints, faster queries.

---

## Data Design

### Why `str, Enum` pattern for all enums?

An enum like `class EventType(str, Enum): USER_LOGIN = "user_login"` gives you:
- **In Python code**: Autocomplete, type checking, IDE support
- **In JSON/Parquet files**: The string value `"user_login"` — self-describing, no lookup 
  needed
- **In Pydantic validation**: Automatic — if someone sends `event_type = "user_loginn"`, 
  Pydantic rejects it

ErrorCode uses UPPERCASE values (`MODEL_TIMEOUT`, `GPU_OOM`) to distinguish machine-readable 
codes from lowercase user-facing values. This is a convention — the casing tells you whether 
a value is meant for systems or humans.

### Why quarantine bad events instead of dropping them?

In production, you WILL have bad events. Schema changes, upstream bugs, network errors. 
If you silently drop them:
- You can't debug what went wrong
- You can't re-process after fixing the issue
- You lose data permanently

The quarantine envelope preserves the original content, the failure reason, and the timestamp. 
You can look at `data/quarantine/2026-07-29/` and see exactly what failed and why. If you fix 
a schema bug, you can re-run quarantine events through the pipeline.

### Why `keep="first"` for deduplication?

A duplicate means the same event_id appeared twice. Which one is the "real" event?
- First occurrence = the original event as it arrived
- Second occurrence = likely a retry, reprocessing artifact, or duplicate delivery

Keeping first is deterministic and defensible. "Last" could be a corrupted copy or a 
partially processed event. First is the safer choice.

---

## Dashboard

### Why vanilla HTML/JS instead of React?

The dashboard's job is to prove the API works. It's a consumer of `/api/gold/*` 
endpoints — nothing more. A React app would need: npm, webpack/vite, node_modules, 
a build step, deployment config. For a local dev dashboard that shows 5 tables, 
that's overkill.

Vanilla HTML with `fetch()` calls the API directly. Zero build step. Zero dependencies. 
The dashboard proves a key architectural principle: **the API is the single source of 
truth**. Any frontend (React, mobile app, Slack bot) would use the same endpoints.

Production V2 would use a proper frontend framework with charting libraries.
