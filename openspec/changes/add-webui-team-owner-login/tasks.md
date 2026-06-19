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

- [x] 6.1 E2E owner read-only — verified live on the secured stack: gateway mints a viewer token (X-API-Key); viewer **query 200**, viewer **write 403**; workspace bound to the token. Browser owner `/webui` click-through is the only non-automatable bit (APIs all verified).
- [x] 6.2 E2E admin RW + audit — verified live: `admin` login (role=admin) writes to any workspace (200); the **audit log** records `viewer→403` and `admin→200` with actor/role/workspace. Browser admin switcher click-through is the manual bit.
- [x] 6.3 Backward compatible: anonymous → 401 once auth is configured; default/no-token behavior unchanged in guest mode (both confirmed live).

## Deployment requirement (satisfied)

The viewer/admin feature needs LightRAG **out of guest mode** (in guest mode
`combined_auth` 401s non-guest bearer tokens before enforcement). Configured on
this stack and verified: `AUTH_ACCOUNTS`, `TOKEN_SECRET`, and `LIGHTRAG_API_KEY`
on LightRAG (the gateway uses the same `LIGHTRAG_API_KEY` to call
`/auth/mint-viewer-token`). Secrets live only in the gitignored `.env` files.
