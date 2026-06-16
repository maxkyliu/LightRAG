## 1. LightRAG workspace-routing patch (fork)

- [x] 1.1 Wire `get_workspace_from_request` into the document router handlers (insert/upload/scan/delete/clear/status) in `lightrag/api/routers/document_routes.py` — added `rag=Depends(get_rag_for_request)` to all 14 handlers
- [x] 1.2 Wire per-request workspace into the query router in `lightrag/api/routers/query_routes.py`
- [x] 1.3 Ensure header value sanitization and empty-header fallback to default workspace are applied consistently — `extract_workspace_from_request` in `utils_api.py`
- [ ] 1.4 (Optional, deferred) Bind API key → workspace for defense-in-depth — gateway is the trust boundary; see `docs/MultiTenancyWorkspaceRouting.md`
- [x] 1.5 Add isolation tests: two workspaces, verify no cross-tenant read/delete leakage; verify no-header path is unchanged — `tests/api/test_workspace_routing.py` (15 tests)
- [x] 1.6 Document the patch and re-apply procedure (same playbook as the llama-swap binding patch) — `docs/MultiTenancyWorkspaceRouting.md`

## 2. Gateway scaffold & datastore

- [x] 2.1 Create the gateway service skeleton (separate process) with config for LightRAG base URL, bot token, provider keys — `telegram_gateway/` package, `config.py`, `.env.example`, `README.md`
- [x] 2.2 Define datastore schema: `teams`, `memberships`, `invites`, `sessions`, `talk_events` — `db.py` (SQLite)
- [x] 2.3 Implement a LightRAG HTTP client that injects `LIGHTRAG-WORKSPACE: <team_id>` on every call — `lightrag_client.py`
- [x] 2.4 Wire Telegram Bot API inbound webhook/long-poll loop — `bot.py` + `__main__.py` (long-polling)

## 3. Team tenancy & onboarding

- [x] 3.1 Implement `/createteam` (creates team + workspace binding, sets owner) — `identity.create_team`
- [x] 3.2 Implement invite code generation (reusable + optional expiry), owner-only — `identity.new_invite` (rotate-to-revoke, D7)
- [x] 3.3 Implement `/join <code>` (adds member, rejects invalid/expired) — `identity.join_team`
- [x] 3.4 Implement identity resolution: Telegram account → team → workspace on every message — `identity.resolve` + `bot.on_message`
- [x] 3.5 Prompt unaffiliated users to onboard; block LightRAG calls until affiliated — `bot.on_message` guard
- [x] 3.6 Enforce owner-only destructive/membership actions; member ingest+query allowed — `require_owner`, owner-only rotate/leave-deletes-team

## 4. Intent routing & query path

- [x] 4.1 Implement default-query routing and `/ingest` detection (same-message payload or arm-next-message) — `intent.py` + `bot.on_message`
- [x] 4.2 Implement query execution against the resolved workspace and reply formatting — `bot._do_query` + `client.query`
- [x] 4.3 Append query turns to the active session buffer — `sessions.append_turn` in `_do_query`

## 5. Ingest path & media pipeline

- [x] 5.1 File attachment → LightRAG `/upload` under the team workspace — `bot._do_ingest` + `client.upload_file`
- [x] 5.2 Voice → STT → text; route to query or ingest per active intent — `media.transcribe`
- [x] 5.3 Image → caption/OCR/vision for query, or upload-as-file for ingest — `media.describe_image` (query) / upload (ingest)
- [x] 5.4 Public URL fetch (`/ingest <url>`): http(s) only, block private/link-local IPs, size/time caps, then upload — `fetcher.py`
- [x] 5.5 Error handling for unreachable/non-public URLs and unsupported media — `FetchError` / `MediaError` handled in `bot.on_message`

## 6. Conversation memory (talk-events)

- [x] 6.1 Session tracking with 30-min idle timeout, `/end`, and token-cap flush — `sessions.py` + `__main__` idle sweeper
- [x] 6.2 Default-deny LLM summarizer (team-knowledge-only) producing the talk-event — `summarizer.py`
- [x] 6.3 Deterministic regex/NER post-scrub of the summary before ingest — `redaction.py`
- [x] 6.4 Ingest talk-event into the team workspace using the `talk-events/...` `file_path` convention; record the doc id in `talk_events` — `talk_events.process_ended_session`
- [x] 6.5 `/private` (skip session) and `/forget` (delete most recent talk-event by doc id, with confirmation) — `bot._forget` + inline-button confirm
- [x] 6.6 Skip empty/trivial sessions — `talk_events` (private/empty/NO_KNOWLEDGE skip)

## 7. Validation & rollout

- [x] 7.1 End-to-end test: two teams, isolated KBs, full onboarding → query → ingest → talk-event cycle — service-level tests with fakes (`test_identity.py`, `test_talk_events.py`); note: live integration against a running LightRAG + Telegram is out of scope for the offline suite
- [x] 7.2 Redaction tests: seeded PII/secret content excluded from ingested summaries — `test_redaction.py` + `test_talk_events.py`
- [x] 7.3 SSRF tests for URL fetch (private IPs, redirects, oversized payloads) — `test_fetcher.py`
- [x] 7.4 Deploy patched LightRAG first (verify no-header behavior), then gateway — documented in `telegram_gateway/README.md` and `docs/MultiTenancyWorkspaceRouting.md` (operational step)
