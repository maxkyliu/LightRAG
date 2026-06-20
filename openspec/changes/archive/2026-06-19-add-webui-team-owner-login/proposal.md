## Why

Telegram team owners need a richer **read** view of their team's knowledge base (browse the
graph, list documents, run queries) than the chat interface offers — but they have no WebUI
credentials, and the WebUI today only ever shows the *default* workspace. Separately, a
**super admin** must be able to perform the write/destructive operations (ingest, delete,
clear) on any team's behalf. This change bridges the Telegram identity into a workspace-scoped
WebUI session and adds the server-side enforcement that makes per-request workspace selection
actually safe (the previously-deferred identity→workspace binding).

## What Changes

- **Magic-link owner login**: an owner sends `/webui` in Telegram; the gateway obtains a
  short-lived, workspace-scoped token and replies with a one-tap WebUI link. The owner's
  session is **read-only** and **locked to their own workspace**.
- **Super-admin role**: existing `AUTH_ACCOUNTS` password logins become **admin** — full
  read/write across **any** workspace (ingest/delete/clear), selectable via a new **WebUI
  workspace switcher**.
- **Server-side role × workspace enforcement** (**BREAKING** for the trust model — closes a
  hole): the JWT carries `role` and, for owners, a locked `workspace`. The server forces a
  viewer's workspace to the token's value and rejects mutating endpoints for viewers; an admin
  may target any workspace with full rights. Header spoofing no longer grants cross-tenant
  access.
- **WebUI sends `LIGHTRAG-WORKSPACE`** derived from the session token (it sends none today).
- **Audit log** of admin mutations (who / what / which workspace).

## Capabilities

### New Capabilities
- `webui-team-owner-login`: Telegram → magic-link → read-only, workspace-locked WebUI session.
- `webui-super-admin`: admin role with cross-workspace full RW, a WebUI workspace switcher, and
  an audit trail of mutations.

### Modified Capabilities
- `lightrag-workspace-routing`: add **role × workspace enforcement** — the per-request
  workspace is bound to the authenticated principal (viewer locked + read-only; admin
  unrestricted), instead of being trusted blindly from the header.

## Impact

- **LightRAG**: `lightrag/api/auth.py` (token role/workspace metadata), `lightrag/api/utils_api.py`
  (enforce role × workspace in `get_rag_for_request` + a write-guard dependency),
  `lightrag/api/lightrag_server.py` (admin role on `AUTH_ACCOUNTS` login; a gateway-callable
  "mint scoped token" endpoint; audit logging).
- **Gateway**: `telegram_gateway/bot.py` (`/webui` command), a LightRAG client call to mint the
  scoped token, owner-only guard.
- **WebUI**: send `LIGHTRAG-WORKSPACE` from the token; read-only affordances for viewers; a
  workspace switcher for admins → requires a `bun run build` (carried fork patch).
- **Secrets**: gateway and LightRAG must share the JWT signing trust (gateway calls LightRAG to
  mint, so the secret stays in LightRAG).
- Depends on the existing per-request workspace routing (`lightrag-workspace-routing`).
