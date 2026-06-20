## ADDED Requirements

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
