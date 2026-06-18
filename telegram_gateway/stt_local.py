"""
In-process Whisper speech-to-text (local engine).

Mirrors the voicebox integration: transformers Whisper (default
``openai/whisper-large-v3-turbo`` — "Whisper Turbo") running on a local GPU/CPU,
rather than calling a remote transcription API.

Heavy dependencies (``torch``, ``transformers``) are imported lazily inside the
engine so the rest of the gateway runs without them when local STT is disabled.
Install them with ``telegram_gateway/requirements-local-stt.txt`` (and ensure
``ffmpeg`` is available for decoding Telegram's OGG/Opus voice notes).
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("telegram_gateway")

# Friendly size aliases -> HuggingFace repos (matches voicebox's mapping).
WHISPER_HF_REPOS = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large": "openai/whisper-large-v3",
    "turbo": "openai/whisper-large-v3-turbo",
}


def resolve_model_repo(model: str) -> str:
    """Map a size alias (e.g. ``turbo``) to its HF repo; pass through full ids."""
    if not model:
        return WHISPER_HF_REPOS["turbo"]
    if "/" in model:  # already a full HF repo id
        return model
    return WHISPER_HF_REPOS.get(model.lower(), f"openai/whisper-{model}")


class LocalWhisperEngine:
    """Lazily-loaded transformers ASR pipeline for local transcription."""

    def __init__(
        self,
        model: str = "turbo",
        device: str = "",
        language: str = "",
        chunk_length_s: int = 30,
    ):
        self._repo = resolve_model_repo(model)
        self._device = device
        self._language = language
        self._chunk_length_s = chunk_length_s
        self._pipe = None
        self._load_lock = asyncio.Lock()

    @property
    def model_repo(self) -> str:
        return self._repo

    def _build_pipeline(self):
        """Construct the ASR pipeline (runs in a worker thread)."""
        import torch
        from transformers import pipeline

        if self._device:
            device = self._device
        elif torch.cuda.is_available():
            device = "cuda:0"
        else:
            device = "cpu"
        dtype = torch.float16 if "cuda" in str(device) else torch.float32

        logger.info("Loading local Whisper '%s' on %s...", self._repo, device)
        pipe = pipeline(
            "automatic-speech-recognition",
            model=self._repo,
            dtype=dtype,  # transformers 5.x kwarg (replaces deprecated torch_dtype)
            device=device,
            chunk_length_s=self._chunk_length_s,  # long-form support via chunking
        )
        logger.info("Local Whisper '%s' loaded.", self._repo)
        return pipe

    async def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        async with self._load_lock:
            if self._pipe is None:
                self._pipe = await asyncio.to_thread(self._build_pipeline)

    async def transcribe(self, audio: bytes) -> str:
        """Transcribe raw audio bytes (any ffmpeg-decodable format) to text."""
        await self._ensure_loaded()

        generate_kwargs: dict = {"task": "transcribe"}
        if self._language:
            generate_kwargs["language"] = self._language

        def _run() -> str:
            # The pipeline ffmpeg-decodes raw bytes to 16 kHz mono internally.
            result = self._pipe(audio, generate_kwargs=generate_kwargs)
            return (result.get("text") or "").strip()

        return await asyncio.to_thread(_run)
