## Context

Two disjoint identity worlds exist today: the Telegram gateway keys everything off
`tg_user_id` with no passwords (`teams.owner_tg_id`), while the LightRAG WebUI authenticates
via static `AUTH_ACCOUNTS` (`user:pass` in `.env`) → JWT and only ever talks to the default
workspace (it never sends `LIGHTRAG-WORKSPACE`). The multi-tenant routing patch
(`lightrag-workspace-routing`) routes data by header but **trusts the header blindly** — its
optional identity→workspace binding was deferred. This change is what makes header routing safe
for human logins.

## Goals / Non-Goals

**Goals:**
- A team owner reaches a read-only, workspace-locked WebUI session from Telegram with one tap.
- A super admin can ingest/delete/clear on any team's workspace via the WebUI.
- Server-side enforcement so a token can only act within its allowed scope (no header spoofing).

**Non-Goals:**
- Non-owner members getting WebUI logins (future).
- Owners getting write access in the WebUI (writes stay on Telegram; destructive ops are admin-only).
- A full RBAC matrix beyond `admin` / `viewer`.
- OIDC/SSO providers.

## Decisions

### D1 — Magic link, not credentials
Owners have no password, so the gateway hands out a short-lived signed token via a `/webui`
command rather than minting username/passwords. One-tap, nothing to store on the user side.

### D2 — LightRAG mints the token (secret stays in one place)
Rather than the gateway signing JWTs with a copied secret, the gateway calls an **authenticated
admin endpoint on LightRAG** ("mint scoped token for workspace W, role=viewer, short TTL"). The
JWT signing secret never leaves LightRAG; the gateway authenticates to that endpoint with an
admin credential/API key. Alternative (gateway signs with a shared `TOKEN_SECRET`) was rejected
to avoid duplicating the secret across services.

### D3 — Role × workspace enforcement (the security crux)
The JWT carries `role` (`admin` | `viewer`) and, for viewers, `workspace`. Enforcement:

```
   endpoint class     admin            viewer
   GET / /query       any workspace    forced to token.workspace
   ingest / upload    any workspace    403
   delete / clear     any workspace    403
```

- Viewer: the server **ignores** any client `LIGHTRAG-WORKSPACE` and uses `token.workspace`;
  mutating endpoints return 403 via a write-guard dependency.
- Admin: may set `LIGHTRAG-WORKSPACE` freely (workspace switcher) with full rights.
- `AUTH_ACCOUNTS` logins are minted as `role=admin` (v1: all password users are admins).

### D4 — WebUI changes
- Send `LIGHTRAG-WORKSPACE` from the session (viewer: token workspace; admin: switcher value).
- Hide/disable write controls for viewers (defense-in-depth; the server is authoritative).
- Add an admin-only workspace switcher (Option 1). Requires a `bun run build`.

### D5 — Audit log
Every admin mutation (ingest/delete/clear) logs `{actor, action, workspace, doc_ids?, ts}` to a
durable audit sink (append-only log/table) — because a human is now reaching into tenants' data.

## Risks / Trade-offs

- [Header spoofing] → server binds workspace to the token for viewers; never trusts the header
  for them. Admins are trusted by design.
- [Token leak] → short TTL on magic-link tokens; scope limited to one workspace + read-only.
- [Secret duplication] → avoided by D2 (LightRAG mints).
- [Fork-maintenance] → WebUI changes (header, switcher, read-only) are a carried patch needing
  rebuild after upstream merges.
- [Admin over-reach] → mitigated by the audit log, not prevented (admins are trusted).

## Migration Plan

1. Ship server-side enforcement first (backward-compatible: no token role/workspace ⇒ existing
   default behavior). 
2. Add the mint-scoped-token endpoint + `/webui` gateway command.
3. Ship the WebUI changes (header + read-only + switcher) behind a rebuild.
4. Rollback: disable the `/webui` command and the mint endpoint; the WebUI falls back to the
   default-workspace admin view.

## Open Questions

- Magic-link token TTL (e.g. 15 min to obtain the session, then a normal session token)?
- Audit sink: a Postgres table vs an append-only file — reuse an existing store?
- Should an admin's workspace switcher list teams by friendly name (needs a gateway lookup) or
  by raw workspace id?
