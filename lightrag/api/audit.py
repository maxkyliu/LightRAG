"""
Audit logging for mutating operations.

Records who performed (or attempted) a write/destructive operation, on which
workspace. Used to keep a trail once a super admin can reach into any tenant's
data (see the webui-super-admin capability). Always emits to the logger; also
appends a JSON line to ``AUDIT_LOG_PATH`` when that env var is set.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("lightrag")

# Mutating document endpoints, matched by path suffix (robust to api prefixes).
_POST_MUTATIONS = (
    "/documents/scan",
    "/documents/upload",
    "/documents/text",
    "/documents/texts",
    "/documents/clear_cache",
    "/documents/reprocess_failed",
    "/documents/cancel_pipeline",
)
_DELETE_MUTATIONS = (
    "/documents",  # clear all
    "/documents/delete_document",
)


def is_mutation(method: str, path: str) -> bool:
    """True for write/destructive document endpoints (not reads or /query)."""
    method = method.upper()
    if method == "POST":
        # "/documents/text" must not match "/documents/texts" — endswith handles
        # this since the strings differ.
        return any(path.endswith(s) for s in _POST_MUTATIONS)
    if method == "DELETE":
        return any(path.endswith(s) for s in _DELETE_MUTATIONS)
    return False


def audit_log(**fields) -> None:
    """Append an audit entry (timestamped) to the logger and optional file sink."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **fields}
    line = json.dumps(entry, ensure_ascii=False)
    path = os.getenv("AUDIT_LOG_PATH")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as e:  # pragma: no cover - best-effort sink
            logger.warning("audit file write failed: %s", e)
    logger.info("AUDIT %s", line)
