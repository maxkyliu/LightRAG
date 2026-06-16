## 1. LightRAG workspace-routing patch (fork)

- [x] 1.1 Wire `get_workspace_from_request` into the document router handlers (insert/upload/scan/delete/clear/status) in `lightrag/api/routers/document_routes.py` — added `rag=Depends(get_rag_for_request)` to all 14 handlers
- [x] 1.2 Wire per-request workspace into the query router in `lightrag/api/routers/query_routes.py`
- [x] 1.3 Ensure header value sanitization and empty-header fallback to default workspace are applied consistently — `extract_workspace_from_request` in `utils_api.py`
- [ ] 1.4 (Optional, deferred) Bind API key → workspace for defense-in-depth — gateway is the trust boundary; see `docs/MultiTenancyWorkspaceRouting.md`
- [x] 1.5 Add isolation tests: two workspaces, verify no cross-tenant read/delete leakage; verify no-header path is unchanged — `tests/api/test_workspace_routing.py` (15 tests)
- [x] 1.6 Document the patch and re-apply procedure (same playbook as the llama-swap binding patch) — `docs/MultiTenancyWorkspaceRouting.md`

## 2. Gateway scaffold & datastore

- [ ] 2.1 Create the gateway service skeleton (separate process) with config for LightRAG base URL, bot token, provider keys
- [ ] 2.2 Define datastore schema: `teams`, `memberships`, `invites`, `sessions`, `talk_events`
- [ ] 2.3 Implement a LightRAG HTTP client that injects `LIGHTRAG-WORKSPACE: <team_id>` on every call
- [ ] 2.4 Wire Telegram Bot API inbound webhook/long-poll loop

## 3. Team tenancy & onboarding

- [ ] 3.1 Implement `/createteam` (creates team + workspace binding, sets owner)
- [ ] 3.2 Implement invite code generation (reusable + optional expiry), owner-only
- [ ] 3.3 Implement `/join <code>` (adds member, rejects invalid/expired)
- [ ] 3.4 Implement identity resolution: Telegram account → team → workspace on every message
- [ ] 3.5 Prompt unaffiliated users to onboard; block LightRAG calls until affiliated
- [ ] 3.6 Enforce owner-only destructive/membership actions; member ingest+query allowed

## 4. Intent routing & query path

- [ ] 4.1 Implement default-query routing and `/ingest` detection (same-message payload or arm-next-message)
- [ ] 4.2 Implement query execution against the resolved workspace and reply formatting
- [ ] 4.3 Append query turns to the active session buffer

## 5. Ingest path & media pipeline

- [ ] 5.1 File attachment → LightRAG `/upload` under the team workspace
- [ ] 5.2 Voice → STT → text; route to query or ingest per active intent
- [ ] 5.3 Image → caption/OCR/vision for query, or upload-as-file for ingest
- [ ] 5.4 Public URL fetch (`/ingest <url>`): http(s) only, block private/link-local IPs, size/time caps, then upload
- [ ] 5.5 Error handling for unreachable/non-public URLs and unsupported media

## 6. Conversation memory (talk-events)

- [ ] 6.1 Session tracking with 30-min idle timeout, `/end`, and token-cap flush
- [ ] 6.2 Default-deny LLM summarizer (team-knowledge-only) producing the talk-event
- [ ] 6.3 Deterministic regex/NER post-scrub of the summary before ingest
- [ ] 6.4 Ingest talk-event into the team workspace using the `talk-events/...` `file_path` convention; record the doc id in `talk_events`
- [ ] 6.5 `/private` (skip session) and `/forget` (delete most recent talk-event by doc id, with confirmation)
- [ ] 6.6 Skip empty/trivial sessions

## 7. Validation & rollout

- [ ] 7.1 End-to-end test: two teams, isolated KBs, full onboarding → query → ingest → talk-event cycle
- [ ] 7.2 Redaction tests: seeded PII/secret content excluded from ingested summaries
- [ ] 7.3 SSRF tests for URL fetch (private IPs, redirects, oversized payloads)
- [ ] 7.4 Deploy patched LightRAG first (verify no-header behavior), then gateway
