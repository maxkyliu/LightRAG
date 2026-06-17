"""
Default-deny conversation summarizer (task 6.2).

On session end, an LLM is asked to *construct* a team-relevant summary that omits
anything personal or sensitive — rather than redacting a transcript. This is the
default-deny posture (design D4): when in doubt, leave it out.

Uses an OpenAI-compatible chat-completions endpoint. When no summarizer endpoint
is configured, ``summarize`` returns ``None`` and the caller skips the
talk-event (we never ingest an un-vetted raw transcript).
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

SYSTEM_PROMPT = (
    "You distill a support/enquiry conversation into durable TEAM KNOWLEDGE for a "
    "shared knowledge base that all teammates can later search.\n\n"
    "Rules:\n"
    "1. Include ONLY information that is useful to the team as reusable knowledge: "
    "facts, decisions, answers, procedures, and resolved questions.\n"
    "2. DEFAULT-DENY on anything personal or sensitive. Exclude (do not rephrase, "
    "do not hint at): personal identifiers, contact details, credentials, secrets, "
    "API keys, passwords, financial/account numbers, health details, and any "
    "private intentions or off-topic chatter.\n"
    "3. If the conversation contains no durable team knowledge, reply with exactly: "
    "NO_KNOWLEDGE\n"
    "4. Write the summary as concise declarative notes (not a chat transcript), in "
    "third person, without quoting the participants verbatim."
)

NO_KNOWLEDGE = "NO_KNOWLEDGE"


def _render_conversation(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        role = turn.get("role", "user")
        text = (turn.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


class Summarizer:
    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        timeout_seconds: int = 60,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self._endpoint and self._model)

    async def summarize(self, turns: list[dict[str, Any]]) -> Optional[str]:
        """Return a redacted team-knowledge summary, or ``None`` to skip.

        ``None`` is returned when the summarizer is not configured or the model
        judges there is no durable knowledge (``NO_KNOWLEDGE``).
        """
        if not self.configured:
            return None
        conversation = _render_conversation(turns)
        if not conversation.strip():
            return None

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": conversation},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._endpoint}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        ).strip()
        if not content or content.upper().startswith(NO_KNOWLEDGE):
            return None
        return content
