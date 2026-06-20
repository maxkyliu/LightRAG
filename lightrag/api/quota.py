"""Per-team resource quotas for header-based multi-tenancy.

Each team is bound 1:1 to a LightRAG workspace. A team is assigned one of three
**tiers** — ``normal`` / ``advance`` / ``unlimited`` — each defining a storage
cap and a monthly enquiry (query) cap (limits come from server config).

Two resources are metered per workspace:

- **Storage** — the live sum of ``DocProcessingStatus.content_length`` (extracted
  source-text length) across the workspace's documents, computed on demand from
  the doc-status store. Nothing is stored; there is no drift and no backfill.
- **Enquiries** — successful query / streaming-query / Ollama chat+generate calls,
  counted per calendar month (UTC) in a small SQLite table. Increments are atomic
  UPSERTs so counts stay correct across multiple gunicorn workers.

The store holds only durable state that cannot be derived live:

    workspace_tier(workspace TEXT PRIMARY KEY, tier TEXT NOT NULL)
    workspace_usage(workspace TEXT, period TEXT, query_count INT,
                    PRIMARY KEY (workspace, period))

See ``openspec/specs/team-resource-quotas`` for the behavioral contract.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional

from lightrag.base import DocStatus
from lightrag.utils import logger

DEFAULT_TIER = "normal"
_MB = 1024 * 1024


def current_period(now: Optional[datetime.datetime] = None) -> str:
    """The monthly bucket key, ``YYYY-MM`` in UTC."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m")


@dataclass(frozen=True)
class TierLimits:
    """Resolved caps for a tier. A value of 0 means "no cap" for that field."""

    storage_bytes: int
    queries: int
    max_docs: int
    max_upload_bytes: int

    @property
    def storage_capped(self) -> bool:
        return self.storage_bytes > 0

    @property
    def queries_capped(self) -> bool:
        return self.queries > 0

    @property
    def docs_capped(self) -> bool:
        return self.max_docs > 0

    @property
    def upload_capped(self) -> bool:
        return self.max_upload_bytes > 0


@dataclass(frozen=True)
class StorageUsage:
    used_bytes: int
    doc_count: int


class QuotaStore:
    """SQLite-backed tier assignments + monthly query counters.

    Storage is *not* stored here — call :meth:`compute_storage` to read it live
    from a workspace's doc-status store.
    """

    def __init__(self, db_path: str, tier_config: dict[str, dict[str, int]]) -> None:
        self._db_path = db_path
        self._tier_config = tier_config
        # SQLite connections are not safe to share across threads; guard with a
        # lock and a single connection (the request path only does tiny writes).
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        logger.info(f"Quota store ready at '{db_path}'")

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_tier (
                    workspace TEXT PRIMARY KEY,
                    tier      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_usage (
                    workspace   TEXT NOT NULL,
                    period      TEXT NOT NULL,
                    query_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (workspace, period)
                );
                """
            )
            self._conn.commit()

    # ----------------------------- tiers --------------------------------- #
    def get_tier(self, workspace: str) -> str:
        """Return the assigned tier, defaulting to ``normal`` when unassigned."""
        with self._lock:
            row = self._conn.execute(
                "SELECT tier FROM workspace_tier WHERE workspace = ?", (workspace,)
            ).fetchone()
        tier = row[0] if row else DEFAULT_TIER
        return tier if tier in self._tier_config else DEFAULT_TIER

    def all_tiers(self) -> dict[str, str]:
        """All explicit workspace→tier assignments."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT workspace, tier FROM workspace_tier"
            ).fetchall()
        return {ws: tier for ws, tier in rows}

    def set_tier(self, workspace: str, tier: str) -> None:
        if tier not in self._tier_config:
            raise ValueError(f"Unknown tier '{tier}'")
        with self._lock:
            self._conn.execute(
                "INSERT INTO workspace_tier (workspace, tier) VALUES (?, ?) "
                "ON CONFLICT(workspace) DO UPDATE SET tier = excluded.tier",
                (workspace, tier),
            )
            self._conn.commit()

    def limits_for(self, workspace: str) -> TierLimits:
        cfg = self._tier_config[self.get_tier(workspace)]
        return TierLimits(
            storage_bytes=int(cfg.get("storage_mb", 0)) * _MB,
            queries=int(cfg.get("queries", 0)),
            max_docs=int(cfg.get("max_docs", 0)),
            max_upload_bytes=int(cfg.get("max_upload_mb", 0)) * _MB,
        )

    # --------------------------- enquiries ------------------------------- #
    def get_query_count(self, workspace: str, period: Optional[str] = None) -> int:
        period = period or current_period()
        with self._lock:
            row = self._conn.execute(
                "SELECT query_count FROM workspace_usage "
                "WHERE workspace = ? AND period = ?",
                (workspace, period),
            ).fetchone()
        return int(row[0]) if row else 0

    def increment_query(self, workspace: str, period: Optional[str] = None) -> int:
        """Atomically add one to this month's count; returns the new value."""
        period = period or current_period()
        with self._lock:
            self._conn.execute(
                "INSERT INTO workspace_usage (workspace, period, query_count) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(workspace, period) "
                "DO UPDATE SET query_count = query_count + 1",
                (workspace, period),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT query_count FROM workspace_usage "
                "WHERE workspace = ? AND period = ?",
                (workspace, period),
            ).fetchone()
        return int(row[0]) if row else 1

    # ---------------------------- storage -------------------------------- #
    @staticmethod
    async def compute_storage(rag) -> StorageUsage:
        """Live source-content size + document count for a workspace's ``rag``.

        Sums ``content_length`` across all documents in every status. Used both
        for enforcement and for the usage endpoint, so pre-existing workspaces
        are metered correctly without any backfill.
        """
        doc_status = getattr(rag, "doc_status", None)
        if doc_status is None:
            return StorageUsage(used_bytes=0, doc_count=0)
        docs = await doc_status.get_docs_by_statuses(list(DocStatus))
        used = sum(int(getattr(d, "content_length", 0) or 0) for d in docs.values())
        return StorageUsage(used_bytes=used, doc_count=len(docs))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
