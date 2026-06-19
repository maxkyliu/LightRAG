# smartrag-branding Specification

## Purpose
TBD - created by archiving change rebrand-to-smartrag. Update Purpose after archive.
## Requirements
### Requirement: WebUI presents the SmartRAG name

The WebUI SHALL display the product name "SmartRAG" in its user-visible chrome (application
name, browser tab title, and header), and SHALL NOT display "LightRAG" in those surfaces.

#### Scenario: App name in the UI

- **WHEN** a user loads the WebUI
- **THEN** the visible application name is "SmartRAG"
- **AND** the browser tab title is "SmartRAG" (or the configured `WEBUI_TITLE`)

#### Scenario: Title configurable without rebuild

- **WHEN** `WEBUI_TITLE` / `WEBUI_DESCRIPTION` are set in the environment
- **THEN** the WebUI tab/header reflect those values at runtime without a source rebuild

### Requirement: No upstream GitHub link in the WebUI

The WebUI SHALL NOT render a link to the upstream HKUDS/LightRAG GitHub repository.

#### Scenario: GitHub link absent

- **WHEN** a user views the WebUI (header / about / settings)
- **THEN** no link to `github.com/HKUDS/LightRAG` is present

### Requirement: Telegram interface presents the SmartRAG name

The Telegram bot's user-facing copy SHALL refer to "SmartRAG", not "LightRAG".

#### Scenario: Help text branding

- **WHEN** a user sends `/start` or `/help`
- **THEN** the reply refers to "SmartRAG" and does not say "LightRAG"

