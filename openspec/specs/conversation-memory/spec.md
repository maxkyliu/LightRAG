# conversation-memory Specification

## Purpose
TBD - created by archiving change add-telegram-gateway. Update Purpose after archive.
## Requirements
### Requirement: DM session lifecycle

The gateway SHALL track a per-member DM session and SHALL end it on any of: 30 minutes of inactivity, an explicit `/end` command, or exceeding a configured token cap.

#### Scenario: Idle timeout ends session

- **WHEN** a member sends no message for 30 minutes
- **THEN** the gateway closes the session and triggers talk-event processing

#### Scenario: Explicit end

- **WHEN** a member sends `/end`
- **THEN** the gateway closes the session immediately and triggers talk-event processing

#### Scenario: Token cap forces a flush

- **WHEN** an ongoing session's buffered content exceeds the configured token cap
- **THEN** the gateway flushes the current session into a talk-event and starts a new session

### Requirement: Talk-event summarization with default-deny redaction

On session end the gateway SHALL produce an LLM summary that includes only team-relevant knowledge and **omits sensitive/personal information by construction** (default-deny), then SHALL apply a deterministic regex/NER post-scrub to the summary before ingest.

#### Scenario: Summary ingested into team KB

- **WHEN** a non-private session ends with substantive content
- **THEN** the gateway generates a redacted summary and ingests it into the team workspace as a talk-event document
- **AND** the document is tagged as a talk-event via a `talk-events/...` `file_path` convention
- **AND** the gateway records the resulting doc id against the member for later recall/forget

#### Scenario: Sensitive content excluded

- **WHEN** the conversation contains personal/sensitive details (e.g. credentials, personal identifiers, private intentions)
- **THEN** the generated summary excludes them
- **AND** any residual pattern-matched sensitive tokens are scrubbed before ingest

#### Scenario: Empty or trivial session is skipped

- **WHEN** a session ends with no substantive knowledge to capture
- **THEN** no talk-event is ingested

### Requirement: Privacy controls

The gateway SHALL provide `/private` to exclude the current session from talk-event capture, and `/forget` to remove recently captured conversation memory.

#### Scenario: Private session not captured

- **WHEN** a member sends `/private` during a session
- **THEN** that session produces no talk-event regardless of how it ends

#### Scenario: Forget most recent memory with confirmation

- **WHEN** a member sends `/forget`
- **THEN** the gateway identifies the member's most recent talk-event and asks for confirmation
- **AND** on confirmation deletes that talk-event from the team workspace by its recorded doc id

#### Scenario: Nothing to forget

- **WHEN** a member sends `/forget` but has no recorded talk-events
- **THEN** the gateway reports there is nothing to forget and deletes nothing

