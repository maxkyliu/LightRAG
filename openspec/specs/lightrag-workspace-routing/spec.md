# lightrag-workspace-routing Specification

## Purpose
TBD - created by archiving change add-telegram-gateway. Update Purpose after archive.
## Requirements
### Requirement: Per-request workspace selection via header on data routes

The LightRAG API SHALL select the storage workspace for document and query operations from the `LIGHTRAG-WORKSPACE` request header when present, falling back to the server's configured default workspace when the header is absent or empty.

#### Scenario: Query routed to header workspace

- **WHEN** a query request arrives with header `LIGHTRAG-WORKSPACE: team_acme`
- **THEN** retrieval reads from the `team_acme` workspace's storages
- **AND** results contain only data ingested under `team_acme`

#### Scenario: Ingest routed to header workspace

- **WHEN** a document insert/upload request arrives with header `LIGHTRAG-WORKSPACE: team_acme`
- **THEN** the document and its derived entities/relations/chunks are written to the `team_acme` workspace
- **AND** they are not visible to requests made under any other workspace

#### Scenario: Backward-compatible default

- **WHEN** a request arrives with no `LIGHTRAG-WORKSPACE` header (or an empty value)
- **THEN** the server uses its configured default workspace exactly as before this change

#### Scenario: Header value sanitized

- **WHEN** a request supplies a `LIGHTRAG-WORKSPACE` header containing characters outside `[a-zA-Z0-9_]`
- **THEN** the value is sanitized to that character set before use
- **AND** the sanitized workspace is used consistently for that request

### Requirement: Workspace isolation is enforced across all data operations

The system SHALL ensure that document ingestion, deletion, query, graph access, and
document-status operations all respect the per-request workspace, with no cross-workspace
leakage. When the request is made by an **authenticated principal**, the workspace and the
allowed operations SHALL be bound to that principal's role rather than trusted blindly from the
`LIGHTRAG-WORKSPACE` header:

- a **viewer** (e.g. a team owner) is forced to the workspace encoded in its token and may only
  perform read/query operations;
- an **admin** may select any workspace via the header and may perform all operations;
- requests with no role/workspace token retain the prior header/default behavior.

#### Scenario: Cross-tenant read isolation

- **WHEN** team A ingests a document and team B issues a query under its own workspace
- **THEN** team B's results never include team A's content

#### Scenario: Deletion scoped to workspace

- **WHEN** a delete-document or clear-documents request is made under workspace `team_acme`
- **THEN** only `team_acme` data is affected and other workspaces are untouched

#### Scenario: Viewer cannot escape its workspace via the header

- **WHEN** a viewer token scoped to `team_acme` sends a request with header
  `LIGHTRAG-WORKSPACE: team_globex`
- **THEN** the server serves `team_acme` (the token's workspace), not `team_globex`

#### Scenario: Viewer is denied mutations

- **WHEN** a viewer token is used on an ingest/upload/delete/clear endpoint
- **THEN** the server responds 403 and performs no write

#### Scenario: Admin may target any workspace with full rights

- **WHEN** an admin token sends a request with header `LIGHTRAG-WORKSPACE: team_globex`
- **THEN** the request is served against `team_globex` for both reads and writes

### Requirement: Quota enforcement at the per-request workspace chokepoint

The system SHALL enforce per-team resource quotas at the point where each request resolves to a
workspace, keyed on the **resolved** workspace (viewer → token workspace; otherwise the
`LIGHTRAG-WORKSPACE` header; else the server default). Metering and enforcement SHALL apply only
to named, non-default workspaces; the server's default workspace SHALL be exempt.

#### Scenario: Storage guard on ingest for a team workspace

- **WHEN** an ingest request resolves to a named workspace that is at its storage cap
- **THEN** the request is rejected with 413 and nothing is stored

#### Scenario: Enquiry guard on query for a team workspace

- **WHEN** a query request resolves to a named workspace that has reached its monthly enquiry cap
- **THEN** the request is rejected with 429 and is not served

#### Scenario: Default workspace is exempt

- **WHEN** a request resolves to the server's default workspace (no header / no viewer token)
- **THEN** no quota is enforced and the request proceeds as before

#### Scenario: Gateway-on-behalf-of-team traffic is metered

- **WHEN** an API-key caller sends a request with header `LIGHTRAG-WORKSPACE: team_acme`
- **THEN** the request is metered against `team_acme`'s quota

#### Scenario: Admin may exceed a team's block

- **WHEN** an admin acts on a team workspace that is at its cap
- **THEN** the operation is not blocked
- **AND** the team's recorded usage still reflects the operation

