## 1. WebUI chrome

- [x] 1.1 `lightrag_webui/src/lib/constants.ts`: set app `name` to `SmartRAG`
- [x] 1.2 `constants.ts`: remove the `github` entry and the component/markup that renders the GitHub link (also dropped the now-unused `GithubIcon` import in `SiteHeader.tsx`)
- [x] 1.3 `lightrag_webui/index.html`: set `<title>` to `SmartRAG`
- [x] 1.4 `bun run build` in `lightrag_webui/`; rebuilt assets emitted to `lightrag/api/webui` (served at `/webui`). Note: that output dir is gitignored (`.gitignore:76`) — it's a deploy artifact, so the commit carries source only; deploy = rebuild.
- [x] 1.5 Set `WEBUI_TITLE=SmartRAG` and `WEBUI_DESCRIPTION=…` in `.env` (runtime only, gitignored)

## 2. Telegram interface

- [x] 2.1 `telegram_gateway/bot.py`: `HELP_TEXT` "LightRAG team assistant" → "SmartRAG team assistant"
- [x] 2.2 `telegram_gateway/README.md`: rebranded the product framing (kept technical LightRAG-engine references)

## 3. Verify

- [x] 3.1 Built output verified: `index.html` `<title>SmartRAG</title>`, `SmartRAG` present in assets, no `HKUDS/LightRAG` URL in assets (live browser load pending deploy)
- [x] 3.2 `HELP_TEXT` shows SmartRAG; 46 gateway tests pass, ruff clean (live `/help` pending bot redeploy)
- [x] 3.3 WebUI rebrand is a carried fork patch (source edits only; built assets are gitignored/rebuilt on deploy) — re-apply after upstream merges
