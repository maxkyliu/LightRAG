# telegram-gateway Specification

## Purpose
TBD - created by archiving change add-telegram-gateway. Update Purpose after archive.
## Requirements
### Requirement: Intent routing defaults to query, `/ingest` selects ingest

The gateway SHALL treat any inbound message as a **query** by default, and SHALL route the message into the **ingest** pipeline when it carries the `/ingest` command.

#### Scenario: Plain message is a query

- **WHEN** a member sends a message without `/ingest`
- **THEN** the gateway runs it as a retrieval query against the team workspace and replies with the answer

#### Scenario: `/ingest` with attachment in the same message

- **WHEN** a member sends `/ingest` with a file/image/url in the same message
- **THEN** the gateway ingests that content into the team workspace

#### Scenario: `/ingest` arms the next message

- **WHEN** a member sends `/ingest` with no payload
- **THEN** the gateway treats the member's next single message as ingest content
- **AND** reverts to query mode afterwards

### Requirement: Multimodal input handling

The gateway SHALL accept text, image, voice, and file-attachment inputs. Voice SHALL be transcribed to text; images SHALL be captioned/OCR'd; the chosen modality SHALL be processed according to the active intent (query vs ingest).

#### Scenario: Voice query

- **WHEN** a member sends a voice note without `/ingest`
- **THEN** the gateway transcribes it to text and runs it as a query

#### Scenario: Voice ingest

- **WHEN** a member sends `/ingest` then a voice note
- **THEN** the gateway transcribes it and ingests the transcript as a document

#### Scenario: Image query

- **WHEN** a member sends an image without `/ingest`
- **THEN** the gateway derives text (caption/OCR/vision) from the image and runs it as a query

#### Scenario: File ingest

- **WHEN** a member sends `/ingest` with a document attachment
- **THEN** the gateway uploads the file to LightRAG's ingest pipeline under the team workspace

### Requirement: Mass ingest by public URL (v1)

The gateway SHALL fetch content from a **public** URL provided after `/ingest` and push it to LightRAG for ingestion. Authenticated cloud storage (e.g. Google Drive OAuth) is out of scope for v1.

#### Scenario: Ingest a public URL

- **WHEN** a member sends `/ingest https://example.com/report.pdf`
- **THEN** the gateway downloads the resource and ingests it into the team workspace

#### Scenario: Unreachable or non-public URL

- **WHEN** the URL cannot be fetched without authentication or returns an error
- **THEN** the gateway reports the failure and ingests nothing

### Requirement: Query responses come from the team workspace

The gateway SHALL execute queries against the resolved team workspace and return LightRAG's answer to the requesting member.

#### Scenario: Answer scoped to team knowledge

- **WHEN** a member queries
- **THEN** the answer is derived only from the team's workspace data

