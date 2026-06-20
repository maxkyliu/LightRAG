## 1. Quota store + config

- [x] 1.1 `lightrag/api/config.py`: add tier-limit env vars (storage MB, monthly queries, max docs, max upload MB) for `normal`/`advance`; `unlimited`/unset ⇒ no cap; `QUOTA_DB_PATH`
- [x] 1.2 `lightrag/api/quota.py`: SQLite store (WAL) with `workspace_tier` + `workspace_usage` (monthly query counters) tables; atomic UPSERT increment (`query_count += 1`); `set_tier`/`get_tier` (default `normal`); live `compute_storage(rag)` summing `content_length` + doc count
- [x] 1.3 Tier→limit resolver from config; period helper (`YYYY-MM`, UTC)

## 2. Enforcement (request chokepoint)

- [x] 2.1 `utils_api.py`: `resolve_effective_workspace(request)` (same rule as `get_rag_for_request`); returns `None` for default/exempt
- [x] 2.2 `require_storage_quota` dependency → 413 when `used_bytes + incoming > cap`, or doc-count / single-upload caps exceeded; admin not blocked but usage still applies
- [x] 2.3 `require_query_quota` dependency → 429 when monthly `query_count >= cap`; admin not blocked
- [x] 2.4 Wire `require_storage_quota` onto ingest/upload/text routes (`document_routes.py`); enforce per-tier single-upload cap in the upload route
- [x] 2.5 Wire `require_query_quota` onto `/query`, `/query/stream`, and Ollama chat/generate routes; increment on a gate-passing serve

## 3. Lifespan

- [x] 3.1 Initialize the quota store in the server lifespan (storage is live-computed; no backfill)

## 4. Usage + super-admin tier management (API)

- [x] 4.1 `GET /usage`: tier, used/limit storage, used/limit monthly queries for the requesting workspace
- [x] 4.2 `GET /admin/quotas` (admin-guarded): list workspaces with tier + live usage
- [x] 4.3 `POST /admin/quotas/{workspace}` (admin-guarded): assign tier; audited like other admin mutations

## 5. WebUI

- [x] 5.1 Super-admin tier-management panel (list workspaces, show usage, assign tier)
- [x] 5.2 Usage indicator for the active workspace (storage + monthly queries)
- [x] 5.3 `bun run build` clean; `tsc --noEmit` + eslint clean; assets rebuilt to `lightrag/api/webui`

## 6. Gateway

- [x] 6.1 Render 413 (storage) and 429 (monthly enquiries) from LightRAG into clear Telegram messages incl. monthly reset date

## 7. Verify

- [x] 7.1 Storage: ingest blocked at 413 when over cap; query still works when storage-full; usage drops after delete/clear
- [x] 7.2 Enquiries: 429 at the monthly cap; counter resets on a new UTC month
- [x] 7.3 Default workspace exempt; named workspace metered (incl. gateway api-key + header path); admin may exceed
- [x] 7.4 Unknown workspace defaults to `normal`; live storage correct for a pre-existing workspace
- [x] 7.5 Multi-worker: concurrent queries across workers increment exactly once each (no lost updates)
