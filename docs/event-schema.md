
# InsightFlow Event Schema

> **Version:** 1.0  
> **Last Updated:** 2026-07-28  
> **Status:** Milestone 0 — Design Phase  
> **Author:** InsightFlow Data Engineering Team

---

## 1. Overview

This document defines the telemetry event schema for InsightFlow — an analytics platform that captures, processes, and analyzes telemetry from an AI application.

### 1.1 What Is an Event?

An event is a **JSON record of something that happened at a specific moment in time**. When a user logs in, submits a prompt, receives a model response, or provides feedback, the AI application generates a small JSON payload describing what happened. InsightFlow receives these payloads and transforms them into actionable analytics.

### 1.2 Event Lifecycle

A single user interaction flows through multiple event types in sequence:

```
user_login
      │
      ▼
conversation_started
      │
      ▼
prompt_submitted ──────► model_response
      │                       │
      │                       ▼
      │                  feedback (optional, may repeat)
      │
      ▼
prompt_submitted ──────► model_response  (user asks follow-up)
      │                       │
      ▼                       ▼
conversation_closed
```

Each event captures **only what is new at that moment**. Data that already exists in other events is not duplicated — it is computed during aggregation in the Gold layer.

### 1.3 Design Principles

| Principle | Description |
|-----------|-------------|
| **Single Responsibility** | Each event captures data that does not exist in any other event |
| **No Aggregation** | Events do not contain computed/rolled-up values from other events |
| **Immutable** | Once written, an event is never modified |
| **Schema Versioned** | Every event carries a `schema_version` for evolution handling |
| **Minimal PII** | No raw user content (prompts, responses) is stored — only metadata and metrics |
| **Common Fields** | All events share a standard set of identity and temporal fields |

---

## 2. Event Types

### 2.1 Summary

| # | Event Type | When It Fires | Purpose |
|---|-----------|---------------|---------|
| 1 | `user_login` | User authenticates into the application | Track DAU, device distribution, regional usage, auth failures |
| 2 | `conversation_started` | User begins a new chat thread | Measure conversation frequency, new vs resumed chats |
| 3 | `prompt_submitted` | User sends a prompt to the AI | Track prompt volume, length distribution, user behavior |
| 4 | `model_response` | AI model returns a response (or fails) | Track latency, token consumption, model performance, errors |
| 5 | `feedback` | User rates or comments on a response | Track quality signals, satisfaction rates |
| 6 | `conversation_closed` | User ends a chat thread | Measure conversation length, close reasons |

---

## 3. Field Architecture

Every event follows a three-tier field structure:

```
┌─────────────────────────────────────────┐
│  COMMON FIELDS (every event)             │
│  Identity and temporal metadata           │
│  event_id, event_type, schema_version,   │
│  timestamp                               │
├─────────────────────────────────────────┤
│  CONTEXT FIELDS (most events)            │
│  Who and where                           │
│  user_id, session_id, conversation_id,    │
│  prompt_event_id, response_event_id       │
├─────────────────────────────────────────┤
│  EVENT-SPECIFIC FIELDS                   │
│  Unique to this event type               │
│  Varies per event                        │
└─────────────────────────────────────────┘
```

---

## 4. Event Definitions

### 4.1 user_login

Fires when a user authenticates (successfully or unsuccessfully) into the AI application.

**Why this event exists:** Login events are the primary source for calculating Daily Active Users (DAU). Without login events, we cannot measure how many unique users interact with the platform each day. The device, region, and subscription fields allow segmentation: "How many enterprise users logged in from mobile in India yesterday?"

**JSON Example:**

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "user_login",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T09:00:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",

  "subscription_tier": "free",
  "device_type": "mobile",
  "device_os": "android",
  "country_code": "IN",
  "login_status": "success",
  "failure_reason": null
}
```

**Failure example:**

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440001",
  "event_type": "user_login",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T09:01:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": null,

  "subscription_tier": "free",
  "device_type": "mobile",
  "device_os": "android",
  "country_code": "IN",
  "login_status": "failure",
  "failure_reason": "invalid_password"
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this specific event |
| `event_type` | enum | No | Always `"user_login"` for this event |
| `schema_version` | string | No | Schema version (e.g., `"1.0"`) |
| `timestamp` | ISO 8601 datetime | No | When the login attempt occurred |
| `user_id` | UUID (string) | No | The user attempting to log in |
| `session_id` | UUID (string) | Yes | Null if login failed (no session created) |
| `subscription_tier` | enum | No | User's subscription level at time of login |
| `device_type` | enum | No | Type of device used |
| `device_os` | enum | No | Operating system of the device |
| `country_code` | string (ISO 3166-1 alpha-2) | No | User's country, derived from IP geolocation |
| `login_status` | enum | No | Outcome of the login attempt |
| `failure_reason` | enum | Yes | Reason for failure; null if login succeeded |

---

### 4.2 conversation_started

Fires when a user begins a new chat thread. This includes both brand new conversations and resumed (reopened) ones.

**Why this event exists:** This event measures conversation frequency — how many chats users start per day. The `is_continuation` flag distinguishes between new conversations and reopened ones, which is a retention signal. A user who resumes old conversations is more engaged than one who only starts new ones.

**JSON Example:**

```json
{
  "event_id": "660f9500-d3ac-52e5-b827-557766550001",
  "event_type": "conversation_started",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:30:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",

  "title": "Help with Python sorting",
  "is_continuation": false
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this event |
| `event_type` | enum | No | Always `"conversation_started"` |
| `schema_version` | string | No | Schema version |
| `timestamp` | ISO 8601 datetime | No | When the conversation was started |
| `user_id` | UUID (string) | No | The user who started the conversation |
| `session_id` | UUID (string) | No | The session in which this happened |
| `conversation_id` | UUID (string) | No | Unique identifier for this conversation thread |
| `title` | string | Yes | User-assigned or auto-generated title; null if not yet set |
| `is_continuation` | boolean | No | `true` if reopening an existing conversation, `false` if new |

**Why no redundant fields:** The conversation start time is already captured by `timestamp`. The conversation ID is already in `conversation_id`. We do not create separate fields for data that already exists in common or context fields. Redundancy creates confusion: "Which field do I use? What if they disagree?"

---

### 4.3 prompt_submitted

Fires when a user sends a prompt to the AI application. This event captures metadata about the prompt — NOT the prompt text itself.

**Why this event exists:** This is the primary event for measuring user engagement volume. It captures how many prompts are submitted, their length (which correlates with inference cost), and the user's context. The prompt text itself is NOT stored here because: (a) it is PII risk at scale, (b) it would create massive storage costs (millions of long strings), and (c) the OLTP database already stores it for operational use. We store only length metrics, which are sufficient for analytics.

**Why no `model` field:** At the moment a user submits a prompt, the system has not yet selected a model. Model selection happens AFTER submission. The model identifier belongs in `model_response`, not here. Placing fields in the wrong event based on "what we want to query" rather than "what actually happened at this moment" is a common data engineering mistake that creates confusing, unreliable telemetry.

**Why no `prompt_category`:** Users do not self-report categories. When you type into ChatGPT, nobody asks "is this coding or research?" Categories are assigned by a classifier after submission, which is captured in the `model_response` event's `prompt_category` field.

**JSON Example:**

```json
{
  "event_id": "770fa600-e4bd-63f6-c938-668877660002",
  "event_type": "prompt_submitted",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:30:15.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",

  "prompt_length_chars": 42,
  "prompt_length_tokens": 12,

  "subscription_tier": "free",
  "device_type": "mobile",
  "device_os": "android",
  "country_code": "IN"
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this event |
| `event_type` | enum | No | Always `"prompt_submitted"` |
| `schema_version` | string | No | Schema version |
| `timestamp` | ISO 8601 datetime | No | When the prompt was submitted |
| `user_id` | UUID (string) | No | The user who submitted the prompt |
| `session_id` | UUID (string) | No | The active session |
| `conversation_id` | UUID (string) | No | The conversation this prompt belongs to |
| `prompt_length_chars` | integer | No | Character count of the prompt (computed server-side) |
| `prompt_length_tokens` | integer | No | Token count of the prompt (computed by the model's tokenizer on the server) |
| `subscription_tier` | enum | No | User's subscription tier (included for segmentation without joins) |
| `device_type` | enum | No | Device used to submit the prompt |
| `device_os` | enum | No | OS of the device |
| `country_code` | string (ISO 3166-1 alpha-2) | No | User's country |

**Why `prompt_length_tokens` is computed server-side:** Tokenization requires the model's specific tokenizer. The browser cannot tokenize because it doesn't have the tokenizer. The AI application's backend tokenizes the prompt before sending it to the model, and includes the token count in the telemetry event. InsightFlow simply receives and stores this value.

---

### 4.4 model_response

Fires when the AI model returns a response, or when the inference pipeline fails. This is the **most data-rich event** in the schema.

**Why this event exists:** This event captures the complete picture of AI inference: which model handled the request, how fast it responded, how many tokens it consumed, and whether it succeeded or failed. This is the primary source for cost analytics, performance monitoring, model comparison, and error tracking.

**Why latency is broken into multiple fields:** A single `latency` number cannot diagnose problems. If a user reports "slow response," a single number can't tell you whether the bottleneck is the GPU, the network, the queue, or the safety filter. Breaking latency into stages enables targeted diagnostics:

```
total_latency_ms (520ms) = queue_wait_ms (45ms)
                           + model_inference_ms (380ms)
                           + post_processing_ms (15ms)
                           + time_to_first_token_ms (120ms, overlaps with above)
                           + network overhead
```

**Why token counts are separate (input vs output):** Different models have different pricing for input vs output tokens. Input tokens are cheaper; output tokens are more expensive. To calculate cost accurately, we need both. Total cost = (input_tokens × input_price) + (output_tokens × output_price).

**JSON Example (Success):**

```json
{
  "event_id": "880gb7100-f5ce-74g7-d049-779988770003",
  "event_type": "model_response",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:30:15.520Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",
  "prompt_event_id": "770fa600-e4bd-63f6-c938-668877660002",

  "model_id": "qwen",
  "model_version": "qwen-2.5-72b",
  "model_provider": "local",

  "status": "success",
  "error_code": null,
  "error_message": null,

  "response_length_chars": 312,
  "response_length_tokens": 78,
  "input_tokens": 12,
  "output_tokens": 78,
  "total_tokens": 90,

  "total_latency_ms": 520,
  "time_to_first_token_ms": 120,
  "model_inference_ms": 380,
  "queue_wait_ms": 45,
  "post_processing_ms": 15,

  "prompt_category": "coding",

  "server_id": "srv-infra-003",
  "server_region": "us-east-1",
  "server_instance_type": "gpu-a100"
}
```

**JSON Example (Error):**

```json
{
  "event_id": "880gb7100-f5ce-74g7-d049-779988770004",
  "event_type": "model_response",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:35:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",
  "prompt_event_id": "770fa600-e4bd-63f6-c938-668877660005",

  "model_id": "qwen",
  "model_version": "qwen-2.5-72b",
  "model_provider": "local",

  "status": "timeout",
  "error_code": "MODEL_TIMEOUT",
  "error_message": "Model inference exceeded 30000ms timeout",

  "response_length_chars": 0,
  "response_length_tokens": 0,
  "input_tokens": 12,
  "output_tokens": 0,
  "total_tokens": 12,

  "total_latency_ms": 30045,
  "time_to_first_token_ms": null,
  "model_inference_ms": null,
  "queue_wait_ms": 45,
  "post_processing_ms": 0,

  "prompt_category": null,

  "server_id": "srv-infra-003",
  "server_region": "us-east-1",
  "server_instance_type": "gpu-a100"
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this event |
| `event_type` | enum | No | Always `"model_response"` |
| `schema_version` | string | No | Schema version |
| `timestamp` | ISO 8601 datetime | No | When the response was received (or error occurred) |
| `user_id` | UUID (string) | No | The user who received this response |
| `session_id` | UUID (string) | No | The active session |
| `conversation_id` | UUID (string) | No | The conversation this response belongs to |
| `prompt_event_id` | UUID (string) | No | Links to the specific `prompt_submitted` event that triggered this response |
| `model_id` | string | No | Short identifier for the model (e.g., `"qwen"`, `"phi"`, `"smollm"`) |
| `model_version` | string | No | Full model version string (e.g., `"qwen-2.5-72b"`) for tracking upgrades |
| `model_provider` | enum | No | Where the model runs: `"local"` for self-hosted, `"api"` for external API |
| `status` | enum | No | Outcome: success, error, timeout, or rate_limited |
| `error_code` | enum | Yes | Machine-readable error code; null if status is `"success"` |
| `error_message` | string | Yes | Human-readable error description; null if status is `"success"` |
| `response_length_chars` | integer | No | Character count of the response (even if error, this is 0 not null) |
| `response_length_tokens` | integer | No | Token count of the response (0 if error or empty response) |
| `input_tokens` | integer | No | Tokens in the prompt (sent to the model). Used for cost calculation. |
| `output_tokens` | integer | No | Tokens generated by the model. Used for cost calculation. |
| `total_tokens` | integer | No | `input_tokens + output_tokens`. Convenience field for quick queries. |
| `total_latency_ms` | integer | No | End-to-end latency: from prompt submission to response delivery. User-perceived. |
| `time_to_first_token_ms` | integer | Yes | Time before first token streamed to user; null if error (no tokens generated) |
| `model_inference_ms` | integer | Yes | Actual GPU compute time; null if error occurred before inference |
| `queue_wait_ms` | integer | No | Time the request spent waiting in a queue before processing |
| `post_processing_ms` | integer | No | Time spent on safety filter, formatting, logging after inference |
| `prompt_category` | enum | Yes | System-classified category of the prompt; null if classification failed or error |
| `server_id` | string | No | Identifier of the server that processed this request |
| `server_region` | string | No | Cloud region or data center location (e.g., `"us-east-1"`) |
| `server_instance_type` | string | No | Hardware type (e.g., `"gpu-a100"`, `"gpu-t4"`, `"cpu"`) |

**Why `prompt_event_id` (not just `conversation_id`):** A conversation can have many prompt-response pairs. `conversation_id` tells you which conversation, but `prompt_event_id` tells you which specific prompt within that conversation triggered this response. This enables precise pairing of prompts and responses.

**Why response text is not stored:** Same reasoning as prompts — PII risk, GDPR liability, and storage cost at scale. We store `response_length_chars` and `response_length_tokens` for analytics, and the full response text lives in the OLTP database accessible via `conversation_id`.

---

### 4.5 feedback

Fires when a user provides feedback on a model response. This includes thumbs up/down, star ratings, text comments, and content reports.

**Why this event exists:** Feedback is the **primary quality signal** for the AI application. It answers: "Are users satisfied with the responses?" Without this event, we have no way to measure whether the AI is doing a good job from the user's perspective. All other events measure system behavior (latency, tokens, errors); this event measures user satisfaction.

**Why `response_event_id` (not `conversation_id`):** Feedback is given on a specific response, not on an entire conversation. A conversation might have 10 responses, some good and some bad. Linking feedback to a specific response enables: "Which response in this conversation was bad?" Without this precision, feedback is useless for diagnostics.

**JSON Example (Thumbs Up):**

```json
{
  "event_id": "990hc8200-g6df-85h8-e150-881099880005",
  "event_type": "feedback",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:31:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",
  "response_event_id": "880gb7100-f5ce-74g7-d049-779988770003",

  "feedback_type": "thumbs_up",
  "feedback_rating": null,
  "feedback_text": null
}
```

**JSON Example (Star Rating with Text):**

```json
{
  "event_id": "990hc8200-g6df-85h8-e150-881099880006",
  "event_type": "feedback",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:32:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",
  "response_event_id": "880gb7100-f5ce-74g7-d049-779988770003",

  "feedback_type": "star_rating",
  "feedback_rating": 4,
  "feedback_text": null
}
```

**JSON Example (Report with Text):**

```json
{
  "event_id": "990hc8200-g6df-85h8-e150-881099880007",
  "event_type": "feedback",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:33:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",
  "response_event_id": "880gb7100-f5ce-74g7-d049-779988770004",

  "feedback_type": "report",
  "feedback_rating": null,
  "feedback_text": "The response contained factually incorrect information about Python 3.12 release date"
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this event |
| `event_type` | enum | No | Always `"feedback"` |
| `schema_version` | string | No | Schema version |
| `timestamp` | ISO 8601 datetime | No | When the feedback was given |
| `user_id` | UUID (string) | No | The user giving feedback |
| `session_id` | UUID (string) | No | The active session |
| `conversation_id` | UUID (string) | No | The conversation containing the rated response |
| `response_event_id` | UUID (string) | No | The specific `model_response` event being rated |
| `feedback_type` | enum | No | How the user expressed feedback |
| `feedback_rating` | integer | Yes | Star rating (1-5); null for thumbs up/down or report |
| `feedback_text` | string | Yes | User's written comment; null if not provided |

---

### 4.6 conversation_closed

Fires when a user ends a chat thread — either explicitly (closing the chat) or implicitly (timeout, system error).

**Why this event exists:** This event measures conversation completion. Combined with `conversation_started`, it enables: "What's the average conversation duration?" and "What percentage of conversations reach completion?" The `close_reason` field helps distinguish between natural endings and abandonment, which is a product quality signal.

**Why no aggregated metrics (token counts, latency totals):** Token counts and latency already exist in individual `model_response` events. Aggregating them here would create data duplication. If a conversation has 10 prompt-response pairs, the total tokens are computed in the Gold layer by summing the 10 `model_response` events. This event captures ONLY what doesn't exist anywhere else: the close reason, total turns, and duration.

**JSON Example:**

```json
{
  "event_id": "110id9300-h7eg-96i9-f261-992110991008",
  "event_type": "conversation_closed",
  "schema_version": "1.0",
  "timestamp": "2026-07-25T10:45:00.000Z",

  "user_id": "usr_a1b2c3d4",
  "session_id": "sess_x1y2z3",
  "conversation_id": "conv_p7q8r9",

  "close_reason": "user_closed",
  "total_turns": 8,
  "conversation_duration_seconds": 900
}
```

**Field Reference:**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `event_id` | UUID (string) | No | Unique identifier for this event |
| `event_type` | enum | No | Always `"conversation_closed"` |
| `schema_version` | string | No | Schema version |
| `timestamp` | ISO 8601 datetime | No | When the conversation was closed |
| `user_id` | UUID (string) | No | The user who closed the conversation |
| `session_id` | UUID (string) | No | The session in which the conversation ended |
| `conversation_id` | UUID (string) | No | The conversation being closed |
| `close_reason` | enum | No | Why the conversation ended |
| `total_turns` | integer | No | Number of prompt-response exchanges in this conversation |
| `conversation_duration_seconds` | integer | No | Duration from `conversation_started` timestamp to now |

**Why `total_turns` is here:** The total number of turns cannot be derived from any single event. It requires counting across all `prompt_submitted` events for this conversation. Including it here avoids a costly aggregation query and provides a reliable count at conversation end.

**Why `conversation_duration_seconds` is here:** Similar to `total_turns` — the duration requires comparing `conversation_started.timestamp` with `conversation_closed.timestamp`. Computing it here at close time is more reliable than computing it later (what if the start event is missing or corrupted?).

---

## 5. Enum Definitions

### 5.1 event_type

| Value | Description |
|-------|-------------|
| `user_login` | User authentication attempt |
| `conversation_started` | New or resumed chat thread |
| `prompt_submitted` | User sent a prompt |
| `model_response` | Model returned a response or error |
| `feedback` | User rated or commented on a response |
| `conversation_closed` | Chat thread was ended |

### 5.2 subscription_tier

| Value | Description |
|-------|-------------|
| `free` | Free tier user — limited requests, no premium features |
| `pro` | Pro tier user — higher limits, basic premium features |
| `enterprise` | Enterprise tier user — unlimited, all features, SLA-backed |

### 5.3 device_type

| Value | Description |
|-------|-------------|
| `mobile` | Smartphone or tablet running a mobile browser/app |
| `desktop` | Laptop or desktop computer |
| `tablet` | Tablet device (distinct from mobile for UX analytics) |
| `api` | Programmatic access via API (no UI) |

### 5.4 device_os

| Value | Description |
|-------|-------------|
| `android` | Android operating system |
| `ios` | Apple iOS |
| `windows` | Microsoft Windows |
| `macos` | Apple macOS |
| `linux` | Linux distribution |
| `other` | Any other OS |

### 5.5 login_status

| Value | Description |
|-------|-------------|
| `success` | Authentication succeeded, session created |
| `failure` | Authentication failed (see `failure_reason`) |
| `locked` | Account is locked (too many failed attempts) |
| `mfa_timeout` | Multi-factor authentication timed out |
| `server_error` | Internal server error during authentication |

### 5.6 failure_reason

| Value | Description |
|-------|-------------|
| `invalid_password` | Incorrect password provided |
| `account_not_found` | No account with the provided identifier |
| `account_locked` | Account locked due to too many failed attempts |
| `mfa_timeout` | User did not complete MFA within timeout |
| `mfa_invalid` | MFA code was incorrect |
| `session_expired` | Existing session expired, re-auth required |
| `server_error` | Internal server error |
| `unknown` | Failure reason could not be determined |

### 5.7 status (model_response)

| Value | Description |
|-------|-------------|
| `success` | Model returned a valid response |
| `error` | Model encountered an error (see `error_code`) |
| `timeout` | Model inference exceeded the timeout threshold |
| `rate_limited` | Request was rate-limited (too many requests) |

### 5.8 error_code

| Value | Description |
|-------|-------------|
| `MODEL_TIMEOUT` | Inference exceeded timeout |
| `MODEL_OVERLOADED` | Model server is at capacity |
| `GPU_OOM` | GPU ran out of memory |
| `INVALID_PROMPT` | Prompt was empty or malformed |
| `SAFETY_FILTER` | Response blocked by safety filter |
| `CONTEXT_LENGTH_EXCEEDED` | Prompt + context exceeded model's max token limit |
| `NETWORK_ERROR` | Network failure between server and model |
| `INTERNAL_ERROR` | Unhandled internal error |

### 5.9 model_provider

| Value | Description |
|-------|-------------|
| `local` | Self-hosted model running on own infrastructure |
| `api` | External model API (e.g., OpenAI, Anthropic, HuggingFace) |

### 5.10 feedback_type

| Value | Description |
|-------|-------------|
| `thumbs_up` | User clicked thumbs up (positive) |
| `thumbs_down` | User clicked thumbs down (negative) |
| `star_rating` | User provided a star rating (1-5) |
| `text` | User provided only text feedback |
| `report` | User reported the response as problematic |

### 5.11 prompt_category

| Value | Description |
|-------|-------------|
| `coding` | Programming and software development questions |
| `writing` | Content creation, editing, copywriting |
| `math` | Mathematical problems and calculations |
| `research` | Information gathering and fact-finding |
| `summarization` | Condensing longer content |
| `translation` | Language translation |
| `reasoning` | Logic, puzzles, analytical thinking |
| `conversation` | General chat, small talk |
| `unknown` | Classifier could not determine category |

### 5.12 close_reason

| Value | Description |
|-------|-------------|
| `user_closed` | User explicitly closed the conversation |
| `timeout` | Conversation ended due to inactivity timeout |
| `system_error` | Conversation ended due to an unrecoverable error |
| `max_turns_reached` | Conversation hit the maximum allowed turns |

---

## 6. Field Reference Table (All Events)

### 6.1 Common Fields

| Field | Type | Nullable | Events |
|-------|------|----------|--------|
| `event_id` | UUID (string) | No | ALL |
| `event_type` | enum | No | ALL |
| `schema_version` | string | No | ALL |
| `timestamp` | ISO 8601 datetime | No | ALL |

### 6.2 Context Fields

| Field | Type | Nullable | Events |
|-------|------|----------|--------|
| `user_id` | UUID (string) | No | ALL |
| `session_id` | UUID (string) | No | ALL |
| `conversation_id` | UUID (string) | No | conversation_started, prompt_submitted, model_response, feedback, conversation_closed |
| `prompt_event_id` | UUID (string) | No | model_response |
| `response_event_id` | UUID (string) | No | feedback |

### 6.3 Event-Specific Fields

| Field | Type | Nullable | Events |
|-------|------|----------|--------|
| `subscription_tier` | enum | No | user_login, prompt_submitted |
| `device_type` | enum | No | user_login, prompt_submitted |
| `device_os` | enum | No | user_login, prompt_submitted |
| `country_code` | string (ISO 3166-1 alpha-2) | No | user_login, prompt_submitted |
| `login_status` | enum | No | user_login |
| `failure_reason` | enum | Yes | user_login |
| `title` | string | Yes | conversation_started |
| `is_continuation` | boolean | No | conversation_started |
| `prompt_length_chars` | integer | No | prompt_submitted |
| `prompt_length_tokens` | integer | No | prompt_submitted |
| `model_id` | string | No | model_response |
| `model_version` | string | No | model_response |
| `model_provider` | enum | No | model_response |
| `status` | enum | No | model_response |
| `error_code` | enum | Yes | model_response |
| `error_message` | string | Yes | model_response |
| `response_length_chars` | integer | No | model_response |
| `response_length_tokens` | integer | No | model_response |
| `input_tokens` | integer | No | model_response |
| `output_tokens` | integer | No | model_response |
| `total_tokens` | integer | No | model_response |
| `total_latency_ms` | integer | No | model_response |
| `time_to_first_token_ms` | integer | Yes | model_response |
| `model_inference_ms` | integer | Yes | model_response |
| `queue_wait_ms` | integer | No | model_response |
| `post_processing_ms` | integer | No | model_response |
| `prompt_category` | enum | Yes | model_response |
| `server_id` | string | No | model_response |
| `server_region` | string | No | model_response |
| `server_instance_type` | string | No | model_response |
| `feedback_type` | enum | No | feedback |
| `feedback_rating` | integer | Yes | feedback |
| `feedback_text` | string | Yes | feedback |
| `close_reason` | enum | No | conversation_closed |
| `total_turns` | integer | No | conversation_closed |
| `conversation_duration_seconds` | integer | No | conversation_closed |

---

## 7. Partition Strategy

### 7.1 Primary Partition Key: `event_date`

All events are partitioned by **date** (derived from `timestamp`, formatted as `YYYY-MM-DD`).

```
data/landing/
├── 2026-07-25/
│   ├── event_001.json
│   ├── event_002.json
│   └── ...
├── 2026-07-24/
│   ├── event_001.json
│   └── ...
└── 2026-07-23/
```

### 7.2 Why Date as Primary Partition

Over 90% of analytics queries are **time-bounded**:

| Query | Partition by Date | Partition by Region |
|-------|-------------------|-------------------|
| "Yesterday's total tokens" | Scan 1 partition | Scan ALL partitions |
| "Last 7 days cost by model" | Scan 7 partitions, filter model | Scan ALL partitions, filter date |
| "July 2026 DAU trend" | Scan 31 partitions | Scan ALL partitions |
| "India vs US today" | Scan 1 partition, filter country | Scan 2 partitions (also works) |

Partitioning by date makes the most common queries efficient. The alternative (partitioning by region, subscription tier, or event type) would require scanning many partitions for time-based queries.

### 7.3 Secondary Consideration: Event Type

In V1, all event types land in the same date partition. The `event_type` field is used as a **filter predicate** during ETL, not as a file-system partition.

In V2, if data volume grows significantly, we may introduce `event_type` as a sub-partition:

```
data/landing/
├── 2026-07-25/
│   ├── prompt_submitted/
│   ├── model_response/
│   ├── user_login/
│   └── feedback/
```

This decision will be driven by the **small file problem**: too many small files slows down reads. Introducing sub-partitions only when the number of files per date partition exceeds a threshold (e.g., 10,000 files).

---

## 8. Schema Versioning Rules

### 8.1 Why Versioning Matters

The AI application will evolve over time. New features will be added, fields will be renamed, and data structures will change. The `schema_version` field enables the ETL pipeline to handle multiple schema versions simultaneously, ensuring backward compatibility.

### 8.2 Version Numbering

We use **semantic versioning** for schema versions:

```
MAJOR.MINOR
│    │
│    └── MINOR: Additive changes (new optional fields added)
│         Example: v1.0 → v1.1 (added safety_score field)
│         Handling: Old events still valid; new field is null for old events
│
└── MAJOR: Breaking changes (fields renamed, removed, or type changed)
     Example: v1.x → v2.0 (renamed latency to model_latency_ms)
     Handling: ETL applies version-specific logic to map fields correctly
```

### 8.3 Version Handling Rules

| Change Type | Version Bump | ETL Behavior |
|-------------|-------------|--------------|
| New field added (optional) | MINOR (e.g., 1.0 → 1.1) | Fill new field with `null` for older events |
| New field added (required) | MINOR (e.g., 1.1 → 1.2) | Validate presence for events with this version; older events are quarantined |
| Field removed | MAJOR (e.g., 1.x → 2.0) | ETL v2 logic ignores the removed field; ETL v1 logic still reads it |
| Field renamed | MAJOR (e.g., 1.x → 2.0) | ETL v2 maps new name; ETL v1 maps old name |
| Field type changed | MAJOR (e.g., 1.x → 2.0) | ETL casts to new type with error handling |
| Enum value added | MINOR (e.g., 1.1 → 1.2) | Old events unaffected; new value recognized |

### 8.4 ETL Processing Logic

```python
# Pseudocode for version-aware ETL
def process_event(event):
    version = event["schema_version"]
    
    if version.startswith("1."):
        # v1.x processing
        validate_v1_schema(event)
        event = apply_v1_transformations(event)
    elif version.startswith("2."):
        # v2.x processing
        validate_v2_schema(event)
        event = apply_v2_transformations(event)
    else:
        # Unknown version — quarantine
        quarantine_event(event, reason="UNKNOWN_SCHEMA_VERSION")
    
    return event
```

---

## 9. Business Questions This Schema Answers

| Business Question | Primary Event(s) | Key Field(s) |
|-------------------|-----------------|--------------|
| How many DAU? | `user_login` | `user_id`, `timestamp` |
| What's the error rate? | `model_response` | `status` |
| Which model is fastest? | `model_response` | `model_id`, `total_latency_ms`, `model_inference_ms` |
| What's the daily cost? | `model_response` | `input_tokens`, `output_tokens`, `model_id` |
| Are users satisfied? | `feedback` | `feedback_type`, `feedback_rating` |
| What's the avg conversation length? | `conversation_started`, `conversation_closed` | `conversation_duration_seconds` |
| Do premium users behave differently? | `user_login`, `prompt_submitted` | `subscription_tier` |
| Which regions have most usage? | `user_login`, `prompt_submitted` | `country_code` |
| What categories get worst feedback? | `model_response`, `feedback` | `prompt_category`, `feedback_type` |
| Is latency increasing over time? | `model_response` | `timestamp`, `total_latency_ms` |
| Which server has issues? | `model_response` | `server_id`, `server_region`, `status` |

---

## 10. Design Decisions & Tradeoffs

### 10.1 Decision: No raw prompt/response text in telemetry

| Aspect | Detail |
|--------|--------|
| **Decision** | Store only length metrics and token counts, not full text |
| **Alternative considered** | Store full text with encryption at rest |
| **Why we chose this** | PII risk (GDPR), storage cost at scale (millions of events × long strings), legal liability |
| **Tradeoff** | We lose the ability to analyze prompt content without cross-referencing OLTP |
| **When to revisit** | If the product team requests content analytics as a feature (e.g., "what topics are trending") |

### 10.2 Decision: Date-first partitioning

| Aspect | Detail |
|--------|--------|
| **Decision** | Partition by `event_date` as the primary key |
| **Alternative considered** | Partition by `event_type` or `country_code` |
| **Why we chose this** | 90%+ of analytics queries are time-bounded; date partitioning optimizes the most common access pattern |
| **Tradeoff** | Queries like "all data for India across all time" scan all date partitions |
| **When to revisit** | If query patterns shift to region-first or type-first access |

### 10.3 Decision: UUID for event and entity identifiers

| Aspect | Detail |
|--------|--------|
| **Decision** | Use UUIDs (strings) for `event_id`, `user_id`, `session_id`, `conversation_id` |
| **Alternative considered** | Auto-incrementing integers (snowflake IDs) |
| **Why we chose this** | No coordination needed across distributed producers; guaranteed uniqueness without a central ID service |
| **Tradeoff** | Larger storage (36 chars vs 8-20 digits); slower to compare than integers |
| **When to revisit** | If storage becomes a concern at extreme scale |

### 10.4 Decision: `subscription_tier` instead of separate `user_type`

| Aspect | Detail |
|--------|--------|
| **Decision** | Single `subscription_tier` enum: free, pro, enterprise |
| **Alternative considered** | Separate `user_type` (client/enterprise) and `subscription_type` (free/pro/premium) |
| **Why we chose this** | Two overlapping dimensions create ambiguity: "Can a free user be enterprise?" One field eliminates confusion |
| **Tradeoff** | Less flexibility if user_type and subscription_tier diverge in the future |
| **When to revisit** | If the product introduces B2B accounts where company type differs from subscription level |
