## 1. Server: token roles + scoped-token minting

- [x] 1.1 `auth.py`/`utils_api.py`: token carries `role` + (viewer) `metadata.workspace`; `get_request_principal` reads it back (lazily validates the bearer token, order-independent)
- [x] 1.2 `lightrag_server.py`: `AUTH_ACCOUNTS` logins minted as `role=admin`
- [x] 1.3 `POST /auth/mint-viewer-token` (admin-guarded via combined_auth + write-guard) → short-lived viewer token scoped to a workspace; JWT secret stays in LightRAG

## 2. Server: role × workspace enforcement

- [x] 2.1 `utils_api.get_rag_for_request`: viewer token forced to `token.workspace` (header ignored); admin/no-token keep header/default behavior
- [x] 2.2 `require_write_access` dependency added to all mutating document routes (scan/upload/text/texts/clear/delete/clear_cache/reprocess/cancel) → 403 for viewers
- [x] 2.3 Tests in `tests/api/test_workspace_routing.py`: viewer header-spoof locked, viewer mutation 403, admin any-workspace, no-token unchanged (20 pass; 26 path-prefix regression pass)

## 3. Audit log

- [x] 3.1 Audit middleware records `{actor, role, action, workspace, status, ts}` for every mutating document route (admin writes + denied 403 viewer attempts). Per-doc-id granularity is a fast-follow (endpoint-level for v1).
- [x] 3.2 Audit sink: always to the logger; also appends JSONL to `AUDIT_LOG_PATH` when set — `lightrag/api/audit.py`

## 4. Gateway: /webui magic link

- [x] 4.1 `bot.py`: `/webui` — owner-only; calls `client.mint_viewer_token(workspace, ttl)` (admin-auth via X-API-Key)
- [x] 4.2 Replies with `${webui_url}/webui#token=…`; short TTL (`GATEWAY_WEBUI_TOKEN_TTL_MINUTES`, default 15). (WebUI consuming the token = group 5.)
- [x] 4.3 Declines non-owners and unaffiliated users

## 5. WebUI

- [x] 5.1 API client (axios interceptor + stream-fetch headers) sends `LIGHTRAG-WORKSPACE` from `localStorage` (viewer: token workspace; admin: switcher)
- [x] 5.2 `main.tsx` consumes a `?token=` query param (HashRouter owns the hash), logs in via the auth store, strips it from the URL; store decodes role + workspace
- [x] 5.3 `DocumentManager` hides upload/clear/delete for viewer sessions (server still enforces 403)
- [x] 5.4 Admin-only workspace switcher in `SiteHeader` (sets active workspace + reloads)
- [x] 5.5 `bun run build` clean; `tsc --noEmit` + eslint clean (caught/fixed a token-payload type). Assets rebuilt to `lightrag/api/webui` (gitignored; baked into the image on deploy)

## 6. Verify

- [~] 6.1 E2E owner `/webui` read-only: mint endpoint verified live (returns role=viewer + metadata.workspace); enforcement (lock + 403) covered by 20 unit tests. Full live owner flow blocked in this deployment — see "Deployment requirement" below.
- [~] 6.2 E2E admin RW + audit: **audit verified live** (denied 401 viewer attempt AND 200 anon write both logged). Admin login + switcher need `AUTH_ACCOUNTS` configured to test live.
- [x] 6.3 Backward compatible: confirmed live — anonymous write under a header workspace → 200, default behavior unchanged.

## Deployment requirement (found during e2e)

The viewer/admin feature needs LightRAG **out of guest mode**, otherwise
`combined_auth` rejects non-guest bearer tokens (viewer/admin) with 401 *before*
enforcement runs. To make the magic-link + admin flow work end-to-end, set on
LightRAG: `AUTH_ACCOUNTS=<admin:pass>`, `TOKEN_SECRET=<random>`, and a
`LIGHTRAG_API_KEY` so the gateway can authenticate to `/auth/mint-viewer-token`;
set the same `LIGHTRAG_API_KEY` in the gateway `.env`. (Guest mode confirmed:
mint works, audit works, backward-compat holds; viewer tokens 401 at the auth
layer.)
