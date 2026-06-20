# team-tenancy Specification

## Purpose
TBD - created by archiving change add-telegram-gateway. Update Purpose after archive.
## Requirements
### Requirement: Team creation establishes a workspace and an owner

The gateway SHALL let a Telegram user create a team, assigning that user the **owner** role and binding the team 1:1 to a LightRAG workspace identifier.

#### Scenario: Create a new team

- **WHEN** a Telegram user sends `/createteam Acme`
- **THEN** the gateway creates a team with a unique `team_id`, sets the user as owner, and binds workspace `team_<team_id>`
- **AND** subsequent requests from that user resolve to that workspace

#### Scenario: Reject duplicate creation by an already-affiliated user

- **WHEN** a user who already belongs to a team sends `/createteam`
- **THEN** the gateway declines and explains they must leave their current team first

### Requirement: Members join a team via invite code

The gateway SHALL allow a Telegram user to join an existing team using an invite code, assigning them the **member** role. Invite codes SHALL be reusable and MAY carry an optional expiry.

#### Scenario: Join with a valid code

- **WHEN** a user sends `/join ACME-7F3K` with a valid, unexpired code
- **THEN** the gateway adds them to the team as a member
- **AND** their messages thereafter resolve to the team's workspace

#### Scenario: Reject an invalid or expired code

- **WHEN** a user sends `/join` with an unknown or expired code
- **THEN** the gateway rejects the request and does not change the user's membership

#### Scenario: Owner generates an invite code

- **WHEN** the team owner requests a new invite code
- **THEN** the gateway returns a reusable code bound to that team (with optional expiry)

### Requirement: Identity resolution maps Telegram account to workspace

For every inbound message the gateway SHALL resolve the Telegram account to its team and inject the team's workspace into the LightRAG request via the `LIGHTRAG-WORKSPACE` header.

#### Scenario: Affiliated user message is routed

- **WHEN** a message arrives from a Telegram account that belongs to `team_acme`
- **THEN** the gateway calls LightRAG with header `LIGHTRAG-WORKSPACE: team_acme`

#### Scenario: Unaffiliated user is prompted to onboard

- **WHEN** a message arrives from a Telegram account with no team
- **THEN** the gateway does not call LightRAG and instead prompts the user to `/createteam` or `/join`

### Requirement: Role-gated destructive operations

The system SHALL restrict team-destructive and membership-management actions to the **owner** role; **members** SHALL be able to ingest and query but not delete the knowledge base or manage the team.

#### Scenario: Member cannot clear the knowledge base

- **WHEN** a member attempts to clear/delete the team's documents
- **THEN** the gateway denies the action and reports insufficient privileges

#### Scenario: Owner manages membership

- **WHEN** the owner removes a member or rotates the invite code
- **THEN** the gateway applies the change and the affected member can no longer resolve to the workspace

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

