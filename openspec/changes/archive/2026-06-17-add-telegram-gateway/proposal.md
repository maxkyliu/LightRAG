## Why

LightRAG today is effectively single-tenant (one `WORKSPACE` pinned per server process; the `LIGHTRAG-WORKSPACE` header is read but ignored by the document and query routers) and can only ingest from a local directory, multipart upload, or raw text — it cannot fetch remote URLs. We want a Telegram-fronted product where **teams** share a knowledge base, members register and ask questions over chat, ingest files/URLs/voice/images, and where conversations themselves become recallable team knowledge. This requires a thin gateway plus one targeted LightRAG patch.

## What Changes

- **Patch LightRAG** to honor the `LIGHTRAG-WORKSPACE` header on the **document and query routers** (today only the status endpoint honors it), so a single instance serves many workspaces. Optionally bind API key → workspace. **No breaking change** — default behavior (no header) is unchanged.
- **New Telegram gateway service** (separate process) that owns identity, sessions, and media, and talks to LightRAG over HTTP injecting `LIGHTRAG-WORKSPACE: <team_id>`.
- **Team-based multi-tenancy**: a team maps 1:1 to a LightRAG workspace; many Telegram accounts belong to a team and share its KB. `/createteam` (owner) and `/join <code>` (member). Roles: **owner** + **member**.
- **DM-only chat model**: each member DMs the bot 1:1; the team is a logical grouping maintained via invite codes.
- **Intent routing**: default is **query**; a `/ingest` prefix routes the input into the ingest pipeline.
- **Multimodal input**: text, image, voice (→ STT), and file attachments. Voice is transcribed; images are captioned/OCR'd for query or uploaded for ingest; files go through the upload pipeline.
- **Mass ingest by public URL** (v1): `/ingest <url>` — the gateway fetches the public URL and pushes the content to LightRAG. (Google Drive / OAuth is explicitly out of v1.)
- **Conversation talk-events**: on session end (30 min idle, `/end`, or token cap) the gateway produces a **default-deny, sensitive-info-omitting** LLM summary and ingests it into the team KB. `/private` skips a session; `/forget` removes recent memory.

## Capabilities

### New Capabilities
- `lightrag-workspace-routing`: honor `LIGHTRAG-WORKSPACE` header for per-request workspace selection on document and query routes in the LightRAG fork.
- `team-tenancy`: team/membership/invite/role model and Telegram-account → team → workspace resolution.
- `telegram-gateway`: the Telegram bot — intent routing (`/ingest` vs query), multimodal handling, query path, and ingest path (file / public URL / transcribed voice / image).
- `conversation-memory`: DM session lifecycle and redacted talk-event summarization + ingest into the team KB.

### Modified Capabilities
<!-- None — no existing OpenSpec specs to modify. The LightRAG router patch is captured as the new `lightrag-workspace-routing` capability. -->

## Impact

- **LightRAG fork** (carried patch): `lightrag/api/routers/document_routes.py`, `lightrag/api/routers/query_routes.py`, `lightrag/api/lightrag_server.py` (`get_workspace_from_request` already exists at `lightrag_server.py:1395`) — wire per-request workspace into doc/query handlers; re-apply after upstream merges.
- **New service**: Telegram gateway (new codebase/process) with its own datastore (`teams`, `memberships`, `invites`, `sessions`, plus media/temp handling).
- **External dependencies**: Telegram Bot API, an STT provider (voice), a vision/OCR provider (images), an LLM for summarization (can reuse LightRAG's configured LLM binding).
- **Storage backends**: shared LightRAG DB backends already namespace by workspace — no schema change there.
