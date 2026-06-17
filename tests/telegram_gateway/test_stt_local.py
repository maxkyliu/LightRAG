"""Local Whisper STT: model resolution + MediaService provider dispatch."""

import pytest

from telegram_gateway.config import GatewayConfig
from telegram_gateway.media import MediaError, MediaService
from telegram_gateway.stt_local import resolve_model_repo


def test_resolve_turbo_alias():
    assert resolve_model_repo("turbo") == "openai/whisper-large-v3-turbo"


def test_resolve_default_is_turbo():
    assert resolve_model_repo("") == "openai/whisper-large-v3-turbo"


def test_resolve_size_alias():
    assert resolve_model_repo("small") == "openai/whisper-small"
    assert resolve_model_repo("large") == "openai/whisper-large-v3"


def test_resolve_full_repo_passthrough():
    assert resolve_model_repo("my-org/whisper-ft") == "my-org/whisper-ft"


def test_resolve_unknown_size_falls_back():
    assert resolve_model_repo("tinyx") == "openai/whisper-tinyx"


def test_local_provider_reports_configured():
    config = GatewayConfig(stt_provider="local", stt_model="turbo")
    svc = MediaService(config)
    assert svc.stt_configured is True
    # The engine targets Whisper Turbo by default.
    assert svc._local_stt.model_repo == "openai/whisper-large-v3-turbo"


def test_openai_provider_requires_endpoint():
    assert MediaService(GatewayConfig(stt_provider="openai")).stt_configured is False
    assert (
        MediaService(
            GatewayConfig(stt_provider="openai", stt_endpoint="http://x/v1")
        ).stt_configured
        is True
    )


async def test_transcribe_dispatches_to_local_engine():
    svc = MediaService(GatewayConfig(stt_provider="local"))

    class FakeEngine:
        async def transcribe(self, audio):
            assert audio == b"OGGdata"
            return "  hello world  "

    svc._local_stt = FakeEngine()
    assert await svc.transcribe(b"OGGdata") == "  hello world  "


async def test_missing_torch_maps_to_media_error():
    svc = MediaService(GatewayConfig(stt_provider="local"))

    class BrokenEngine:
        async def transcribe(self, audio):
            raise ModuleNotFoundError("No module named 'torch'", name="torch")

    svc._local_stt = BrokenEngine()
    with pytest.raises(MediaError) as exc:
        await svc.transcribe(b"x")
    assert "torch" in str(exc.value)
