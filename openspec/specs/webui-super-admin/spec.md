# webui-super-admin Specification

## Purpose
TBD - created by archiving change add-webui-team-owner-login. Update Purpose after archive.
## Requirements
### Requirement: Super admin has cross-workspace full access

A super admin (an `AUTH_ACCOUNTS` password login) SHALL be able to read and write any
workspace, including ingest, delete, and clear operations.

#### Scenario: Admin targets a team workspace

- **WHEN** an admin selects a team's workspace and ingests or deletes a document
- **THEN** the operation is applied to that team's workspace
- **AND** is not blocked by the read-only restriction that applies to owners

#### Scenario: Password logins are admins

- **WHEN** a user logs in via `AUTH_ACCOUNTS` credentials
- **THEN** the issued session has the `admin` role with unrestricted workspace selection

### Requirement: WebUI workspace switcher for admins

The WebUI SHALL provide admins a control to select which workspace to act on, and SHALL send the
chosen workspace as `LIGHTRAG-WORKSPACE` on subsequent requests.

#### Scenario: Switching workspace

- **WHEN** an admin selects a different workspace in the switcher
- **THEN** subsequent reads and writes target the selected workspace

#### Scenario: Switcher hidden for non-admins

- **WHEN** an owner (viewer) session loads the WebUI
- **THEN** the workspace switcher is not available and the session stays on its locked workspace

### Requirement: Admin mutations are audited

The system SHALL record an audit entry for every admin write/destructive operation.

#### Scenario: Audited ingest/delete/clear

- **WHEN** an admin performs ingest, delete, or clear on a workspace
- **THEN** an audit entry is recorded with the actor, action, target workspace, affected
  doc ids (where applicable), and timestamp

### Requirement: Super admin assigns team tiers

A super admin SHALL be able to view every workspace with its current tier and live usage
(storage used/limit and monthly enquiries used/limit), and to assign a workspace one of the
three tiers. Tier assignment SHALL be audited like other admin mutations.

#### Scenario: Admin lists workspaces with usage

- **WHEN** an admin opens the tier-management view
- **THEN** each workspace is shown with its tier, storage used/limit, and monthly enquiries
  used/limit

#### Scenario: Admin changes a workspace's tier

- **WHEN** an admin assigns `team_acme` the `advance` tier
- **THEN** subsequent enforcement for `team_acme` uses the `advance` limits
- **AND** an audit entry records the actor, target workspace, new tier, and timestamp

#### Scenario: Tier management hidden for non-admins

- **WHEN** a viewer (team owner) session loads the WebUI
- **THEN** the tier-management view is not available

