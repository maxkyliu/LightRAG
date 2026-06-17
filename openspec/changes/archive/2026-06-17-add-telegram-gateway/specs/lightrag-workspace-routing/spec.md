## ADDED Requirements

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

The system SHALL ensure that document ingestion, deletion, query, graph access, and document-status operations all respect the per-request workspace, with no cross-workspace leakage.

#### Scenario: Cross-tenant read isolation

- **WHEN** team A ingests a document and team B issues a query under its own workspace
- **THEN** team B's results never include team A's content

#### Scenario: Deletion scoped to workspace

- **WHEN** a delete-document or clear-documents request is made under workspace `team_acme`
- **THEN** only `team_acme` data is affected and other workspaces are untouched
