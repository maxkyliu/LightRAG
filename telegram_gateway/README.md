# SmartRAG Telegram Gateway

A standalone service that puts a multi-tenant Telegram front-end ("SmartRAG") on
a (patched) LightRAG server. Teams share a knowledge base; members onboard over
chat, ask questions, ingest files/URLs/voice/images, and conversations are
distilled back into the KB.

This is the implementation of the `add-telegram-gateway` OpenSpec change. It
depends on the **per-request workspace routing** patch in this fork
(`docs/MultiTenancyWorkspaceRouting.md`).

## Architecture

```
Telegram DMs ──▶ gateway (this package) ──▶ LightRAG HTTP API
                    │  identity / sessions      (LIGHTRAG-WORKSPACE: team_<id>)
                    │  media (STT / vision)
                    └─ sqlite (teams, members, invites, sessions, talk_events)
```

- **Team = workspace.** Each gateway team maps to LightRAG workspace
  `team_<team_id>` via the `LIGHTRAG-WORKSPACE` header (set `GATEWAY_WORKSPACE_PREFIX`).
- **DM-only.** Members talk to the bot 1:1; teams are joined via invite codes.
- **Roles.** `owner` (manage/rotate invites, delete team) and `member`
  (ingest + query).

## Commands

| Command | Who | Effect |
| --- | --- | --- |
| `/createteam <name>` | anyone | create a team, become owner, get an invite code |
| `/join <code>` | anyone | join a team as member |
| `/invite` | owner | rotate the invite code (revokes old ones) |
| `/whoami` | member | show team, role, workspace |
| `/leave` | member/owner | leave (owner leaving deletes the team) |
| `/ingest …` | member | add content (text, file, image, voice, public URL) |
| `/end` | member | end session → summarize to the team KB |
| `/private` | member | don't save this session |
| `/forget` | member | delete your most recent saved summary (with confirmation) |

Any message without `/ingest` is treated as a **query**.

## Running

```bash
python -m venv .venv-gateway && . .venv-gateway/bin/activate
pip install -r telegram_gateway/requirements.txt
cp telegram_gateway/.env.example .env   # fill in TELEGRAM_BOT_TOKEN, LIGHTRAG_BASE_URL
set -a; . ./.env; set +a
python -m telegram_gateway
```

The STT, vision, and summarizer providers are optional. Without a summarizer,
conversation talk-events are skipped (default-deny). Without STT/vision, voice
and image inputs report the capability as unavailable instead of failing.

### Local Whisper Turbo STT

To transcribe voice notes in-process with a local GPU (no remote API), set
`STT_PROVIDER=local` and install the extra deps:

```bash
pip install -r telegram_gateway/requirements-local-stt.txt   # torch + transformers
# ffmpeg must also be installed (decodes Telegram OGG/Opus voice notes)
```

```bash
STT_PROVIDER=local
STT_MODEL=turbo        # openai/whisper-large-v3-turbo (size alias or full HF repo id)
STT_LANGUAGE=          # empty = auto-detect; or en / zh / yue / …
STT_DEVICE=            # empty = auto (cuda if available, else cpu)
```

The model is loaded lazily on the first voice message and cached for the process
lifetime. This mirrors the Whisper engine used by the voicebox project.

## Security notes

- The gateway is the trust boundary. Do not expose the LightRAG port publicly;
  the gateway injects the workspace header on the server's behalf.
- URL ingest is restricted to public http(s) hosts; private/loopback/link-local
  addresses are refused (SSRF guard), with size/time/redirect caps.
- Talk-events are summarized **default-deny** (sensitive content excluded by
  construction) and then regex-scrubbed before ingest — best-effort, not a
  guarantee. Members can use `/private` and `/forget`.
