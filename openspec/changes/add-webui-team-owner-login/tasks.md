## 1. Server: token roles + scoped-token minting

- [ ] 1.1 `auth.py`: include `role` and (for viewers) `workspace` in the JWT metadata; helper to read them back
- [ ] 1.2 `lightrag_server.py`: mint `AUTH_ACCOUNTS` logins as `role=admin`
- [ ] 1.3 Add an authenticated admin-only endpoint to mint a short-lived viewer token for a given workspace (gateway calls this; JWT secret stays in LightRAG)

## 2. Server: role × workspace enforcement

- [ ] 2.1 `utils_api.get_rag_for_request`: for a viewer token, force the workspace to `token.workspace` (ignore the header); admin/no-token keep current behavior
- [ ] 2.2 Add a write-guard dependency on ingest/upload/delete/clear that returns 403 for viewer tokens
- [ ] 2.3 Isolation tests: viewer header-spoof denied; viewer mutation 403; admin any-workspace RW; no-token unchanged

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
