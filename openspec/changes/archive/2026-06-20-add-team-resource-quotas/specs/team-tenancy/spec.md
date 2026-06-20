## ADDED Requirements

### Requirement: Gateway surfaces quota errors to users

The gateway SHALL relay a clear message to the Telegram user when a LightRAG request on behalf
of a team is rejected for exceeding a resource quota, rather than a generic failure.

#### Scenario: Storage quota reached during ingest

- **WHEN** a member's document ingest is rejected with 413 (storage cap)
- **THEN** the gateway tells the user the team's storage is full and the upload was not stored

#### Scenario: Monthly enquiry quota reached during query

- **WHEN** a member's query is rejected with 429 (monthly enquiry cap)
- **THEN** the gateway tells the user the team's monthly query limit is reached
- **AND** includes when the limit resets
