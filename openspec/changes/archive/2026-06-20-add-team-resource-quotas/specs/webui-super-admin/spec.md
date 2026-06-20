## ADDED Requirements

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
