## Why

The product is being presented as **SmartRAG**, not LightRAG, and should not advertise the
upstream HKUDS GitHub repo to end users. This is a cosmetic rebrand of the **user-visible**
surfaces only — no behavior change.

## What Changes

- **WebUI visible chrome → SmartRAG**:
  - App name shown in the UI: `LightRAG` → `SmartRAG` (`lightrag_webui/src/lib/constants.ts`).
  - Browser tab / header title + description via the existing `WEBUI_TITLE` / `WEBUI_DESCRIPTION`
    env vars (no source change needed for these) and `index.html` `<title>`.
  - **Remove the upstream GitHub link** (`constants.ts` `github: …HKUDS/LightRAG`) and the UI
    element that renders it.
- **Telegram interface → SmartRAG**: the user-facing help text (`telegram_gateway/bot.py`
  `HELP_TEXT` "LightRAG team assistant") and README.
- **Out of scope**: deep in-app locale strings (the 11 `locales/*.json` files keep their
  internal "LightRAG" strings for now); internal code identifiers (`LightRAGClient`,
  `LightRAGError`, module names) are unchanged — they are not user-visible.

## Capabilities

### New Capabilities
- `smartrag-branding`: the user-visible product name is "SmartRAG" across the WebUI chrome and
  the Telegram interface, with no upstream GitHub link.

### Modified Capabilities
<!-- None — no existing branding spec. -->

## Impact

- `lightrag_webui/src/lib/constants.ts`, `lightrag_webui/index.html` — source edits → requires a
  `bun run build` and serving the rebuilt assets. Carried fork patch (re-apply after upstream
  merges).
- `telegram_gateway/bot.py` (`HELP_TEXT`), `telegram_gateway/README.md`.
- `.env` (gitignored): `WEBUI_TITLE=SmartRAG`, `WEBUI_DESCRIPTION=…` (runtime only, not committed).
- No API, data, or behavior changes.
