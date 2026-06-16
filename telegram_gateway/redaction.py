"""
Deterministic sensitive-data scrub (task 6.3).

This is the *second* line of defense for talk-events: the summarizer is
instructed to omit sensitive content by construction (default-deny, see
``summarizer.py``); this module then pattern-scrubs any residual identifiers
from the summary before it is ingested into the shared team KB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED = "[REDACTED]"

# Each pattern is (label, compiled regex). Order matters: scrub high-entropy
# secrets before generic number runs so they aren't partially masked.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{10,}\b", re.IGNORECASE)),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?\d{1,3}[ .\-]?)?(?:\(?\d{3}\)?[ .\-]?)\d{3}[ .\-]?\d{4}(?!\d)"
        ),
    ),
]


@dataclass
class ScrubResult:
    text: str
    found: list[str]  # labels of pattern types that matched


def scrub(text: str) -> ScrubResult:
    """Replace recognized sensitive tokens with ``[REDACTED]``.

    Returns the scrubbed text and the list of pattern labels that fired.
    """
    found: list[str] = []
    out = text
    for label, pattern in _PATTERNS:
        if pattern.search(out):
            found.append(label)
            out = pattern.sub(REDACTED, out)
    return ScrubResult(text=out, found=found)
