# webui-team-owner-login Specification

## Purpose
TBD - created by archiving change add-webui-team-owner-login. Update Purpose after archive.
## Requirements
### Requirement: Owner obtains a WebUI session via Telegram magic link

A team owner SHALL be able to request a WebUI login from Telegram and receive a one-tap link
that authenticates them into a session scoped to their team's workspace.

#### Scenario: Owner requests a WebUI link

- **WHEN** a team owner sends `/webui` to the bot
- **THEN** the gateway obtains a short-lived, workspace-scoped token for that owner's workspace
- **AND** replies with a WebUI URL that establishes the session in one tap

#### Scenario: Non-owner is declined

- **WHEN** a user who is not a team owner sends `/webui`
- **THEN** the gateway declines (owners only in v1) and does not issue a link

#### Scenario: Link is short-lived

- **WHEN** the magic-link token has expired
- **THEN** following the link does not establish a session and the user must request a new one

### Requirement: Owner WebUI session is read-only and workspace-locked

An owner's WebUI session SHALL be confined to their own workspace and SHALL NOT permit
mutating operations.

#### Scenario: Owner sees only their workspace

- **WHEN** an owner browses documents, the graph, or runs a query in the WebUI
- **THEN** only their team's workspace data is shown
- **AND** supplying a different `LIGHTRAG-WORKSPACE` value does not expose another team's data

#### Scenario: Owner cannot mutate

- **WHEN** an owner session attempts ingest, upload, delete, or clear
- **THEN** the server rejects it with 403
- **AND** the WebUI hides/disables those controls for the owner

