"""
Media providers: speech-to-text and image understanding (tasks 5.2–5.3).

Both use OpenAI-compatible HTTP endpoints and are optional: when an endpoint is
not configured, the corresponding capability reports as unavailable and the bot
tells the user instead of failing silently.
"""

from __future__ import annotations

import base64

import httpx

from .config import GatewayConfig


class MediaError(RuntimeError):
    """Raised when a media provider call fails."""


class MediaService:
    def __init__(self, config: GatewayConfig):
        self._config = config
        self._local_stt = None
        if config.stt_provider == "local":
            # Lazy-import so torch/transformers are only required when enabled.
            from .stt_local import LocalWhisperEngine

            self._local_stt = LocalWhisperEngine(
                model=config.stt_model if config.stt_model != "whisper-1" else "turbo",
                device=config.stt_device,
                language=config.stt_language,
            )

    # -------------------------------- STT ---------------------------------- #

    @property
    def stt_configured(self) -> bool:
        if self._config.stt_provider == "local":
            return True
        return bool(self._config.stt_endpoint)

    async def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        """Transcribe voice audio to text (local Whisper or remote API)."""
        if not self.stt_configured:
            raise MediaError("Voice transcription is not configured on this gateway.")
        if self._local_stt is not None:
            try:
                return await self._local_stt.transcribe(audio)
            except ModuleNotFoundError as e:
                raise MediaError(
                    "Local STT requires torch + transformers (see "
                    "telegram_gateway/requirements-local-stt.txt). "
                    f"Missing: {e.name}"
                ) from e
            except Exception as e:  # decode/inference failure
                raise MediaError(f"Local transcription failed: {e}") from e
        url = f"{self._config.stt_endpoint.rstrip('/')}/audio/transcriptions"
        headers = {}
        if self._config.stt_api_key:
            headers["Authorization"] = f"Bearer {self._config.stt_api_key}"
        files = {"file": (filename, audio, "application/octet-stream")}
        data = {"model": self._config.stt_model}
        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout_seconds
            ) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
        except httpx.HTTPError as e:
            raise MediaError(f"STT endpoint unreachable: {e}") from e
        if resp.status_code >= 400:
            raise MediaError(f"STT failed: {resp.status_code} {resp.text[:200]}")
        return (resp.json().get("text") or "").strip()

    # ------------------------------- vision -------------------------------- #

    @property
    def vision_configured(self) -> bool:
        return bool(self._config.vision_endpoint and self._config.vision_model)

    async def describe_image(
        self,
        image: bytes,
        prompt: str = "Describe this image and transcribe any text in it.",
        mime: str = "image/jpeg",
    ) -> str:
        """Caption / OCR an image via an OpenAI-compatible vision chat endpoint."""
        if not self.vision_configured:
            raise MediaError("Image understanding is not configured on this gateway.")
        url = f"{self._config.vision_endpoint.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._config.vision_api_key:
            headers["Authorization"] = f"Bearer {self._config.vision_api_key}"
        b64 = base64.b64encode(image).decode("ascii")
        payload = {
            "model": self._config.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout_seconds
            ) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise MediaError(f"Vision endpoint unreachable: {e}") from e
        if resp.status_code >= 400:
            raise MediaError(f"Vision failed: {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        return (
            data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        ).strip()
