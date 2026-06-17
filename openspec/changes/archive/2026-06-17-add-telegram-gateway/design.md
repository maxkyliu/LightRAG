## Context

LightRAG is single-tenant in practice: a server process pins one `WORKSPACE`, and although `get_workspace_from_request` (`lightrag/api/lightrag_server.py:1395`) reads a `LIGHTRAG-WORKSPACE` header, that header is consumed **only** by the status endpoint (`lightrag_server.py:2257`). Document insert/upload/query routes all use the boot-time workspace. Ingestion accepts only local-dir scan, multipart upload, and raw text — no remote URL fetch.

We are building a Telegram-fronted client where **teams** (not individuals) own a shared knowledge base, members onboard over chat, ingest mixed media and public URLs, and conversations are distilled back into the KB. The cleanest separation keeps the gateway ignorant of LightRAG internals (it speaks HTTP + a workspace header) and keeps LightRAG ignorant of teams (it only sees a workspace string). One targeted fork patch makes that possible.

## Goals / Non-Goals

**Goals:**
- Single LightRAG instance serving many team workspaces via the existing header.
- A standalone Telegram gateway owning identity, sessions, media, and URL fetch.
- Team = workspace; many Telegram accounts per team; DM-only interaction.
- Conversations become recallable, redacted team knowledge.

**Non-Goals:**
- Google Drive / OAuth / authenticated cloud storage (fast-follow after v1).
- Group-chat-native interaction (DM-only for v1).
- Granular RBAC beyond owner/member.
- Per-instance-per-tenant deployment (rejected — see Decisions).

## Decisions

### D1 — Multi-tenancy via header patch, not instance-per-tenant
Patch the LightRAG fork to honor `LIGHTRAG-WORKSPACE` on the document and query routers (the plumbing already exists for status). `workspace = team_id`.
- **Why:** single instance keeps LLM/embedding memory loaded once; storage backends already namespace by workspace; the patch is small and the default path is unchanged.
- **Alternatives:** (B) one LightRAG process per team — rejected, doesn't scale past a handful of tenants (each pins model memory). (C) client-side ID prefixing in a shared namespace — rejected, leaks tenants into one graph, unsafe for shared queries.
- **Maintenance:** the patch must be re-applied by hand after upstream merges (ruff reformatting churns the fork), consistent with the existing llama-swap binding patch practice.

### D2 — Team as a logical grouping, DM-only
Each member DMs the bot 1:1; the team is maintained by the gateway via invite codes (`/createteam`, `/join <code>`). No Telegram group membership is required.
- **Why:** simplest bot model; clean per-member session boundaries; avoids group-message processing, @mention triggers, and group privacy concerns.
- **Trade-off:** members don't *see* each other's conversations — sharing happens only through the KB and talk-events.

### D3 — `/ingest` gates ingestion; everything else is a query
Default intent is query. `/ingest` routes the same-message payload (or the next single message) into the ingest pipeline. This collapses file/URL/voice/image ingest into one rule and removes query-vs-ingest ambiguity for every modality.

### D4 — Talk-events: default-deny summarization + deterministic post-scrub
On session end (30 min idle / `/end` / token cap) an LLM **constructs** a team-relevant summary that omits sensitive/personal content (default-deny, not redact-a-transcript), then a regex/NER pass scrubs residual PII/secrets before ingest. `/private` skips a session; `/forget` removes recent talk-events.
- **Why:** a member's private DM becomes retrievable by all teammates once ingested — default-deny is the safe posture for a shared KB.
- **Alternative:** ingest full transcript then redact — rejected, higher leakage risk and noisier KB.

### D5 — Media pipeline
Voice → STT → text (then query or ingest). Image → caption/OCR/vision → text for query, or upload-as-file for ingest. File → existing `/upload` endpoint. URL (public) → gateway fetches → upload. The LLM for summarization can reuse LightRAG's configured binding.

### D6 — Gateway owns its own datastore
Tables: `teams`, `memberships(tg_user, team, role)`, `invites(code, team, expiry)`, `sessions(member, state, buffer, last_activity)`, `talk_events(member, team, doc_id, created_at)`. Plus transient media/temp storage. LightRAG storage is untouched beyond workspace namespacing.

### D7 — Invite codes are reusable with optional expiry; revoke = rotate
An invite code is reusable and MAY carry an optional expiry. The owner revokes access to the team's onboarding link by **rotating** the code (the old code stops resolving). No single-use codes in v1.
- **Why:** the common path is an owner sharing one code with the team; rotation covers "stop letting people in" without a per-invite issuance/tracking table.
- **Alternative:** single-use / per-recipient codes — rejected for v1 (more state, more friction) but compatible as a later addition.

### D8 — Tag talk-events from day one via `file_path` convention
Every ingested talk-event is tagged as such from the start, realized through a `file_path`/`file_source` naming convention (e.g. `talk-events/<member>/<session_id>.md`) rather than a new LightRAG metadata field.
- **Why:** the cost is near-zero now, but retrofitting later means re-ingesting/migrating existing talk-events to separate them from authored docs; the same convention also gives `/forget` and any future retrieval-weighting a clean handle — all without a further LightRAG patch.
- **Alternative:** add a first-class `source_type` field to LightRAG ingest — rejected for v1 (widens the carried fork patch for no v1 benefit).

### D9 — `/forget` removes the most recent talk-event, with confirmation
`/forget` targets the requesting member's **most recent** talk-event and prompts for confirmation before deleting it from the team workspace by doc id (looked up in the gateway's `talk_events` table).
- **Why:** predictable and safe; a confirmation guard fits a destructive, shared-KB action; doc-id lookup avoids fuzzy matching.
- **Alternative:** time-window or interactive multi-select deletion — rejected for v1 (more machinery); compatible as a later `/forget <n>` extension.

## Risks / Trade-offs

- **Redaction is imperfect** → default-deny summarizer + regex/NER post-scrub + `/private`/`/forget` escape hatches; document that talk-events are best-effort, not a guarantee.
- **Fork drift on the LightRAG patch** → keep the patch minimal and documented; re-apply after upstream merges (same playbook as llama-swap binding).
- **Talk-events polluting retrieval quality** → tag talk-events with a `source_type` so they can be weighted/filtered; revisit if answer quality degrades.
- **Public URL fetch = SSRF surface** → restrict to http(s), block private/link-local IP ranges, cap size/time.
- **STT/vision cost & latency** → make providers configurable; consider size limits on voice/images.
- **No per-request auth→workspace binding yet** → gateway is the trust boundary; LightRAG should not be exposed publicly without the optional API-key→workspace binding.

## Migration Plan

1. Apply and validate the LightRAG router patch (default-no-header behavior unchanged → safe to deploy first).
2. Stand up the gateway service + datastore against the patched LightRAG.
3. Roll out onboarding (`/createteam`, `/join`), then query, then ingest, then talk-events.
4. Rollback: gateway is additive; disabling it leaves LightRAG fully functional. The header patch is backward-compatible and can remain.

## Open Questions

_None outstanding for v1 — the three prior open questions are resolved in Decisions D7 (invite codes), D8 (talk-event tagging), and D9 (`/forget` scope)._
