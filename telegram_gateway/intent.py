"""
Intent parsing for inbound Telegram messages.

Rule (design D3): the default intent is *query*. An ``/ingest`` directive routes
the input into the ingest pipeline instead — applying to the payload in the same
message if present, otherwise arming the next single message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Commands the gateway understands (without the leading slash).
COMMANDS = {
    "start",
    "help",
    "createteam",
    "join",
    "invite",
    "leave",
    "whoami",
    "webui",
    "ingest",
    "end",
    "private",
    "forget",
}

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


@dataclass
class Command:
    name: str  # canonical command name without the slash
    args: str  # everything after the command token, stripped


def parse_command(text: Optional[str]) -> Optional[Command]:
    """Parse a leading ``/command`` (optionally ``/command@botname``).

    Returns ``None`` when the text is not a recognized command.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    head, _, rest = stripped.partition(" ")
    name = head[1:].split("@", 1)[0].lower()  # drop slash and @botname suffix
    if name not in COMMANDS:
        return None
    return Command(name=name, args=rest.strip())


def extract_first_url(text: Optional[str]) -> Optional[str]:
    """Return the first http(s) URL found in ``text``, if any."""
    if not text:
        return None
    match = _URL_RE.search(text)
    return match.group(0) if match else None
