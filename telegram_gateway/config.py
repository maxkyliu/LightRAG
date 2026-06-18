"""Gateway configuration, loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class GatewayConfig:
    """All runtime configuration for the Telegram gateway.

    Values come from environment variables so the service can be configured
    without code changes (12-factor style). ``from_env`` is the entry point.
    """

    # --- Telegram ---
    telegram_bot_token: str = ""

    # --- LightRAG backend ---
    lightrag_base_url: str = "http://localhost:9621"
    lightrag_api_key: str = ""
    workspace_prefix: str = "team_"
    request_timeout_seconds: int = 120
    # Public base URL of the WebUI for the /webui magic link (defaults to the
    # LightRAG base URL). Short-lived viewer-token TTL in minutes.
    webui_url: str = ""
    webui_token_ttl_minutes: int = 15

    # --- Gateway datastore ---
    db_path: str = "telegram_gateway.db"

    # --- Session / talk-events ---
    session_idle_timeout_seconds: int = 1800  # 30 minutes
    session_token_cap: int = 6000

    # --- Public URL fetch (SSRF-guarded) ---
    fetch_max_bytes: int = 50 * 1024 * 1024  # 50 MB
    fetch_timeout_seconds: int = 60
    fetch_max_redirects: int = 3

    # --- Speech-to-text (optional) ---
    # Provider: "openai" (remote /audio/transcriptions) or "local" (in-process
    # Whisper via transformers, e.g. Whisper Turbo on a local GPU).
    stt_provider: str = "openai"
    stt_endpoint: str = ""
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    # Local-engine knobs (used when stt_provider == "local").
    stt_language: str = ""  # e.g. "en", "zh", "yue"; empty = auto-detect
    stt_device: str = ""  # e.g. "cuda:0" / "cpu"; empty = auto

    # --- Vision provider (OpenAI-compatible HTTP endpoint; optional) ---
    vision_endpoint: str = ""
    vision_api_key: str = ""
    vision_model: str = ""

    # --- Summarizer LLM (OpenAI-compatible chat endpoint; optional) ---
    summarizer_endpoint: str = ""
    summarizer_api_key: str = ""
    summarizer_model: str = ""

    # Extra HTTP headers to forward to LightRAG (besides the workspace header).
    extra_headers: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls(
            telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
            lightrag_base_url=_get("LIGHTRAG_BASE_URL", "http://localhost:9621").rstrip(
                "/"
            ),
            lightrag_api_key=_get("LIGHTRAG_API_KEY"),
            workspace_prefix=_get("GATEWAY_WORKSPACE_PREFIX", "team_"),
            request_timeout_seconds=_get_int("LIGHTRAG_REQUEST_TIMEOUT", 120),
            webui_url=_get(
                "GATEWAY_WEBUI_URL",
                _get("LIGHTRAG_BASE_URL", "http://localhost:9621"),
            ).rstrip("/"),
            webui_token_ttl_minutes=_get_int("GATEWAY_WEBUI_TOKEN_TTL_MINUTES", 15),
            db_path=_get("GATEWAY_DB_PATH", "telegram_gateway.db"),
            session_idle_timeout_seconds=_get_int("SESSION_IDLE_TIMEOUT_SECONDS", 1800),
            session_token_cap=_get_int("SESSION_TOKEN_CAP", 6000),
            fetch_max_bytes=_get_int("FETCH_MAX_BYTES", 50 * 1024 * 1024),
            fetch_timeout_seconds=_get_int("FETCH_TIMEOUT_SECONDS", 60),
            fetch_max_redirects=_get_int("FETCH_MAX_REDIRECTS", 3),
            stt_provider=_get("STT_PROVIDER", "openai").lower(),
            stt_endpoint=_get("STT_ENDPOINT"),
            stt_api_key=_get("STT_API_KEY"),
            stt_model=_get("STT_MODEL", "whisper-1"),
            stt_language=_get("STT_LANGUAGE"),
            stt_device=_get("STT_DEVICE"),
            vision_endpoint=_get("VISION_ENDPOINT"),
            vision_api_key=_get("VISION_API_KEY"),
            vision_model=_get("VISION_MODEL"),
            summarizer_endpoint=_get("SUMMARIZER_ENDPOINT"),
            summarizer_api_key=_get("SUMMARIZER_API_KEY"),
            summarizer_model=_get("SUMMARIZER_MODEL"),
        )

    def validate(self) -> list[str]:
        """Return a list of fatal configuration problems (empty == OK)."""
        problems: list[str] = []
        if not self.telegram_bot_token:
            problems.append("TELEGRAM_BOT_TOKEN is required")
        if not self.lightrag_base_url:
            problems.append("LIGHTRAG_BASE_URL is required")
        return problems

    def workspace_for_team(self, team_id: str) -> str:
        """Map a gateway team id to its LightRAG workspace name."""
        return f"{self.workspace_prefix}{team_id}"
