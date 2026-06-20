# team-resource-quotas Specification

## Purpose

Each team is bound 1:1 to a LightRAG workspace, but a workspace can ingest and query without
bound, letting one tenant fill the knowledge base or run unlimited LLM queries and starve others.
This capability defines per-team resource limits across three tiers (`normal`, `advance`,
`unlimited`), metering storage as live source-content size and enquiries per calendar month, with
durable worker-safe counters, a usage endpoint, and non-destructive enforcement at the request
chokepoint.

## Requirements

### Requirement: Three resource tiers with configurable limits

The system SHALL support three team tiers — `normal`, `advance`, and `unlimited` — where each
tier defines a maximum **storage** (accumulated source bytes) and a maximum **monthly enquiry**
(query) count. Tier limit values SHALL be read from server configuration. The `unlimited` tier
(and any limit left unset) SHALL impose no enforcement.

#### Scenario: Default tier limits applied from config

- **WHEN** the server starts with no tier overrides
- **THEN** `normal` allows 100 MB storage and 1,000 monthly enquiries
- **AND** `advance` allows 2 GB storage and 20,000 monthly enquiries
- **AND** `unlimited` enforces neither

#### Scenario: Unassigned workspace defaults to normal

- **WHEN** a workspace has no tier assigned
- **THEN** the system treats it as `normal`

### Requirement: Storage metered as live source-content size

The system SHALL meter a workspace's storage as the live sum of its documents' source-content
length (the extracted-text `content_length`), computed from the doc-status store at check time,
not the backend disk or database footprint. An ingest into a workspace already at/over its
tier's storage cap or document-count cap, or a single upload exceeding the per-tier upload cap,
SHALL be rejected with HTTP 413 before processing, and no content SHALL be stored.

#### Scenario: Ingest within the cap is accepted

- **WHEN** a `normal` workspace below its storage and document caps ingests a document
- **THEN** the document is accepted

#### Scenario: Ingest into an over-cap workspace is rejected

- **WHEN** a `normal` workspace whose live source-content size is at/over its cap uploads a file
- **THEN** the server responds 413 and stores nothing

#### Scenario: Usage reflects deletions immediately

- **WHEN** documents are deleted or the workspace is cleared
- **THEN** the reported storage usage drops accordingly on the next check, with no stored counter
  to reconcile

### Requirement: Enquiries metered per calendar month

The system SHALL count enquiries (successful query, streaming-query, and Ollama chat/generate
calls) per workspace within a calendar month (UTC), resetting the count at the start of each
month. A request that fails before serving SHALL NOT be counted.

#### Scenario: Enquiry over the monthly cap is rejected

- **WHEN** a `normal` workspace has already served 1,000 enquiries this month and issues another
- **THEN** the server responds 429 and does not serve the query

#### Scenario: Counter resets on a new month

- **WHEN** a new UTC calendar month begins
- **THEN** the workspace's monthly enquiry count starts again at zero
- **AND** prior months' totals are retained

#### Scenario: Failed query is not counted

- **WHEN** a query request errors before a result is produced
- **THEN** the monthly enquiry count is unchanged

### Requirement: Durable, worker-safe query counters

The system SHALL persist tier assignments and monthly query counters in an API-side SQLite store
with two tables (`workspace_tier`, `workspace_usage`). Counter updates SHALL be atomic so that
counts remain correct when the API runs under multiple worker processes. (Storage usage is
live-computed and not stored.)

#### Scenario: Concurrent increments are not lost

- **WHEN** two worker processes each serve an enquiry for the same workspace at the same time
- **THEN** the recorded monthly count increases by exactly two

### Requirement: Workspace usage endpoint

The system SHALL expose `GET /usage` returning, for the requesting workspace, the tier, used and
limit storage, and used and limit monthly enquiries.

#### Scenario: Owner reads usage

- **WHEN** a viewer (team owner) session calls `GET /usage`
- **THEN** the response reports its tier, storage used/limit, and monthly enquiries used/limit
  for its locked workspace

### Requirement: Enforcement is non-destructive

Reaching a cap SHALL only block the new action; it SHALL NOT delete existing data, and a
workspace at its storage cap SHALL still be able to query (subject to its enquiry cap).

#### Scenario: Storage-full workspace can still query

- **WHEN** a workspace has reached its storage cap
- **THEN** ingest is rejected with 413
- **AND** queries are still served while monthly enquiries remain

#### Scenario: Tier downgrade keeps data

- **WHEN** a workspace over the `normal` storage cap is assigned the `normal` tier
- **THEN** its existing data remains readable and queryable
- **AND** further ingest is rejected until it is below the cap
