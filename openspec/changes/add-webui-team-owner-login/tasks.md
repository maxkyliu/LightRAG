## 1. Server: token roles + scoped-token minting

- [x] 1.1 `auth.py`/`utils_api.py`: token carries `role` + (viewer) `metadata.workspace`; `get_request_principal` reads it back (lazily validates the bearer token, order-independent)
- [x] 1.2 `lightrag_server.py`: `AUTH_ACCOUNTS` logins minted as `role=admin`
- [x] 1.3 `POST /auth/mint-viewer-token` (admin-guarded via combined_auth + write-guard) → short-lived viewer token scoped to a workspace; JWT secret stays in LightRAG

## 2. Server: role × workspace enforcement

- [x] 2.1 `utils_api.get_rag_for_request`: viewer token forced to `token.workspace` (header ignored); admin/no-token keep header/default behavior
- [x] 2.2 `require_write_access` dependency added to all mutating document routes (scan/upload/text/texts/clear/delete/clear_cache/reprocess/cancel) → 403 for viewers
- [x] 2.3 Tests in `tests/api/test_workspace_routing.py`: viewer header-spoof locked, viewer mutation 403, admin any-workspace, no-token unchanged (20 pass; 26 path-prefix regression pass)

## 3. Audit log

- [ ] 3.1 Record `{actor, action, workspace, doc_ids?, ts}` on every admin ingest/delete/clear
- [ ] 3.2 Choose + wire the audit sink (table vs append-only file)

## 4. Gateway: /webui magic link

- [ ] 4.1 `bot.py`: `/webui` command — owner-only; call LightRAG to mint a viewer token for the owner's workspace
- [ ] 4.2 Reply with a one-tap WebUI URL that establishes the session; short TTL
- [ ] 4.3 Decline non-owners

## 5. WebUI

- [ ] 5.1 Send `LIGHTRAG-WORKSPACE` from the session token (viewer: token workspace; admin: switcher)
- [ ] 5.2 Accept the magic-link token and establish a session
- [ ] 5.3 Hide/disable write controls for viewer sessions
- [ ] 5.4 Admin-only workspace switcher
- [ ] 5.5 `bun run build`; serve rebuilt assets (carried fork patch)

## 6. Verify

- [ ] 6.1 E2E: owner `/webui` → read-only, own-workspace session; cannot mutate or switch
- [ ] 6.2 E2E: admin logs in → switches to a team workspace → ingest/delete works → audit entry written
- [ ] 6.3 Confirm no-token / default-workspace behavior is unchanged (backward compatible)
