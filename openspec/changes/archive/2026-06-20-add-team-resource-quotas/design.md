# Design — team-resource-quotas

## Context

Tenancy today: one API process, many workspaces; every data request resolves to a workspace in
`get_rag_for_request` (`lightrag/api/utils_api.py`). `require_write_access` already shows the
pattern for a per-request, role-aware gate. There is **no** API-side SQLite — the only durable
API artifact is the JSONL audit log; the gateway's `teams.db` is in a separate process and is
not reachable from the API. The API may run under gunicorn with >1 worker (separate processes,
no shared memory).

## Goals / Non-goals

- **Goals**: enforce a storage cap and a monthly enquiry cap per team workspace; let a super
  admin assign one of three tiers; predictable, backend-agnostic metering; correct under
  multiple workers; non-destructive enforcement; visible usage.
- **Non-goals**: billing/invoicing; real disk-footprint accounting; rate limiting (this is a
  monthly *quota*, not a per-second limiter); per-user (sub-team) quotas.

## Key decisions

### D1 — Storage = live sum of source-text length, not a stored counter
Real disk footprint is backend-specific (JSON/Nano/Postgres/Neo4j/Milvus), racy, and
unpredictable (embeddings + graph inflate a source 4–10×). We meter the **source content size**
of a workspace, defined as the sum of `DocProcessingStatus.content_length` (extracted text
length) across its documents — backend-agnostic and the only reliable per-doc size.

Because ingestion is **asynchronous** (the uploaded file's extracted length is unknown at upload
time), a stored `used_bytes` counter would drift (file-bytes at ingest vs extracted-length on
recompute). Instead storage is **computed live from the doc-status store** at check time:

- `require_storage_quota` sums `content_length` (and counts docs) for the resolved workspace and
  rejects with **413** when the sum is at/over the tier's storage cap, the doc count is at/over
  the doc cap, or a single upload exceeds the per-tier upload cap.
- No `used_bytes` column and **no backfill** — live computation is always correct, including for
  pre-existing workspaces. Ingest is infrequent relative to queries, so the O(docs) scan is
  acceptable; queries never touch storage.

### D2 — Enquiries = monthly, calendar UTC
`period` key is `YYYY-MM` (UTC). On the first request of a new month the counter row for the new
period is created at 0; old rows are retained for history. One **successful** call to `/query`,
`/query/stream`, or the Ollama chat/generate endpoints increments by 1; retrieval-only counts;
requests that fail before serving (4xx/5xx) do not count; a streamed answer counts once.

### D3 — New API-side SQLite (`quota.db`), DB-authoritative
A new SQLite file (path via env, default alongside other API data), WAL mode, two tables:

```
workspace_tier(workspace TEXT PRIMARY KEY, tier TEXT NOT NULL)        -- super-admin managed
workspace_usage(workspace TEXT, period TEXT, query_count INT,         -- request-path managed
                PRIMARY KEY (workspace, period))                      -- monthly query counters
```

Only the monthly query counter is durable (storage is live-computed, D1). Counters are never
cached in process memory — every increment is an atomic UPSERT
(`… ON CONFLICT … SET query_count = query_count + 1`), so N gunicorn workers stay consistent.
Tier limits are read from config, not the DB (the DB only stores the *assignment*).

### D4 — Metering keyed on resolved workspace; default exempt
A helper resolves the effective workspace exactly as `get_rag_for_request` does (viewer →
token workspace; otherwise header; else default). Metering applies **iff** the resolved
workspace is a named, non-default workspace. This correctly meters gateway-on-behalf-of-team
traffic (API-key caller + team header) while leaving the admin's own/default workspace
unmetered. Tier lookup: `workspace_tier` row, else `normal`.

### D5 — Enforcement points (mirror require_write_access)
- `require_storage_quota` on ingest/upload/text routes → **413** with a clear detail when
  `used_bytes + incoming > limit`, or doc-count / single-upload caps exceeded.
- `require_query_quota` on query + Ollama routes → **429** when `query_count >= limit`; on a
  served query, increment after success.
- **Admin override**: an `admin`-role principal is not *blocked* by either guard (support
  access), but the operation still increments the team's usage.

### D6 — No backfill needed
Storage is live-computed from the doc-status store (D1), so pre-existing workspaces are metered
correctly with no startup seeding. Query counters start fresh for the current month. An
already-over-line workspace keeps its data but cannot ingest more.

## Flow

```
Upload/text ─▶ require_storage_quota ─▶ resolve ws (named? else exempt)
                  │                       └─ tier→limits; live Σcontent_length < storage cap?
                  │                          doc_count < cap? upload size ≤ max_upload?
                  └─ no ─▶ 413           └─ yes ─▶ accept (ingest)

Query/Ollama ─▶ require_query_quota ─▶ resolve ws (named? else exempt)
                  │                       └─ tier→limit; query_count(period) < cap?
                  └─ no ─▶ 429           └─ yes ─▶ serve ; atomic count += 1
```

## Config (defaults)

```
QUOTA_DB_PATH=./data/quota.db
QUOTA_TIER_NORMAL_STORAGE_MB=100      QUOTA_TIER_NORMAL_QUERIES=1000
QUOTA_TIER_NORMAL_MAX_DOCS=500        QUOTA_TIER_NORMAL_MAX_UPLOAD_MB=20
QUOTA_TIER_ADVANCE_STORAGE_MB=2048    QUOTA_TIER_ADVANCE_QUERIES=20000
QUOTA_TIER_ADVANCE_MAX_DOCS=10000     QUOTA_TIER_ADVANCE_MAX_UPLOAD_MB=200
# unlimited: no enforcement (any cap unset/0 ⇒ unlimited)
```

## Risks / open items

- **Backfill cost** on very large existing workspaces (one-time scan); acceptable, runs at boot.
- **Multi-write recompute races** on delete are bounded by per-workspace serialization in
  SQLite; the recompute is idempotent.
- **Ollama endpoint surface** — confirm the exact set of generate/chat routes that should count
  during implementation.
- **Tier downgrade** leaving a team over the storage line: by design they keep data, lose
  ingest — surfaced via `/usage`.
