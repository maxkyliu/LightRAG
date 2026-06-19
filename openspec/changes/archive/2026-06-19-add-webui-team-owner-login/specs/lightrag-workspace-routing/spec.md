## MODIFIED Requirements

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
