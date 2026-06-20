## Why

Each team is bound 1:1 to a LightRAG workspace, but a workspace can ingest and query without
bound. One team can fill the knowledge base or run unlimited LLM queries, driving cost and
starving other tenants. We need per-team resource limits that a super admin can assign, with
sensible defaults, enforced where every request already resolves to a workspace.

## What Changes

- **Three tiers** — `normal`, `advance`, `unlimited` — each defining a **storage** cap and a
  **monthly enquiry** (query) cap. Tier→limit numbers come from server config; `unlimited`
  means no enforcement.
- **Storage metered as accumulated source bytes** per workspace (not raw disk/DB footprint,
  which is backend-specific and unpredictable for users). Gated at ingest time by the incoming
  file/text size; recomputed on delete/clear so it never drifts.
- **Enquiries metered per calendar month (UTC)** per workspace, resetting on the first request
  of a new month.
- **New API-side SQLite store** (`quota.db`) with two dedicated tables —
  `workspace_tier(workspace, tier)` and `workspace_usage(workspace, period, query_count,
  used_bytes)`. Counters are DB-authoritative (atomic increments, WAL) so they are correct
  across gunicorn workers. (The gateway's `teams.db` lives in a different process and cannot be
  reused.)
- **Enforcement at the request chokepoint**: two FastAPI dependencies modeled on the existing
  `require_write_access` — `require_storage_quota` on ingest routes (→ **413** when over) and
  `require_query_quota` on query/Ollama routes (→ **429** when over). Metering is keyed on the
  **resolved workspace**; the server's **default workspace is exempt**.
- **Super-admin tier management in the WebUI**: list workspaces with their tier + live usage,
  and assign a tier. Unknown/unassigned workspaces default to `normal`.
- **Usage visibility**: `GET /usage` returns the requesting workspace's tier, used/limit
  storage, and used/limit monthly queries, so owners (and the WebUI) can see consumption.
- **Non-destructive**: hitting a cap only blocks the *new* action — never deletes data, and a
  storage-full team can still query. An admin may exceed a team's block for support, but the
  usage still increments.
- **Gateway surfaces quota errors** (413/429) to Telegram users with a clear message and the
  monthly reset date.

## Capabilities

### New Capabilities
- `team-resource-quotas`: per-workspace storage + monthly-enquiry limits across three tiers,
  with a SQLite-backed usage store, request-path enforcement, a usage endpoint, and a one-time
  backfill of existing storage usage.

### Modified Capabilities
- `lightrag-workspace-routing`: add quota enforcement at the per-request workspace chokepoint
  (storage on ingest, enquiries on query), keyed on the resolved workspace, default exempt.
- `webui-super-admin`: admins can view per-workspace usage and assign a team's tier.
- `team-tenancy`: the gateway surfaces over-quota responses to Telegram users.

## Impact

- **LightRAG (new)**: `lightrag/api/quota.py` — SQLite store (tier + usage tables), tier→limit
  config loading, atomic counters, backfill.
- **LightRAG (modified)**: `lightrag/api/utils_api.py` (quota dependencies + resolved-workspace
  helper), `lightrag/api/routers/document_routes.py` (storage guard on ingest/upload/text),
  `lightrag/api/routers/query_routes.py` + `ollama_api.py` (enquiry guard + increment),
  `lightrag/api/lightrag_server.py` (`GET /usage`, super-admin tier list/set endpoints, store
  init + backfill on lifespan), `lightrag/api/config.py` (tier limit env vars).
- **WebUI**: a super-admin tier-management panel and a usage indicator → requires `bun run
  build` (carried fork patch).
- **Gateway**: `telegram_gateway/bot.py` / client — render 413/429 quota errors.
- **Config/secrets**: new `quota.db` path (default alongside other API data); new tier-limit env
  vars with the defaults below.
- Depends on `lightrag-workspace-routing` (per-request workspace) and `webui-super-admin`
  (admin role) already shipped.

## Default tier limits

| Tier | Storage (source bytes) | Enquiries / month | Max documents | Max single upload |
|---|---|---|---|---|
| `normal` | 100 MB | 1,000 | 500 | 20 MB |
| `advance` | 2 GB | 20,000 | 10,000 | 200 MB |
| `unlimited` | ∞ (no enforcement) | ∞ | ∞ | ∞ |
