"""
Tests for per-team resource quotas (storage + monthly enquiries).

Covers the durable query-counter store, the live storage computation, and the
two FastAPI enforcement dependencies (storage → 413, enquiries → 429), including
default-workspace exemption and admin bypass.

The real ``LightRAG`` is replaced with a lightweight fake exposing a ``doc_status``
with ``get_docs_by_statuses`` so storage can be summed without any backend.
"""

import asyncio
import datetime
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# Import under a clean argv (config initializes at import time; see the sibling
# test_workspace_routing.py for the rationale).
_saved_argv = sys.argv
sys.argv = ["lightrag-server"]
try:
    from lightrag.api.quota import QuotaStore, current_period
    from lightrag.api.utils_api import (
        resolve_effective_workspace,
        require_query_quota,
        require_storage_quota,
    )
finally:
    sys.argv = _saved_argv

from fastapi import HTTPException

TIERS = {
    "normal": {"storage_mb": 1, "queries": 2, "max_docs": 3, "max_upload_mb": 1},
    "advance": {"storage_mb": 2048, "queries": 20000, "max_docs": 10000, "max_upload_mb": 200},
    "unlimited": {"storage_mb": 0, "queries": 0, "max_docs": 0, "max_upload_mb": 0},
}


def _store() -> QuotaStore:
    d = tempfile.mkdtemp()
    return QuotaStore(os.path.join(d, "quota.db"), TIERS)


# --------------------------------------------------------------------------- #
# Store: tiers + monthly counters
# --------------------------------------------------------------------------- #


def test_unknown_workspace_defaults_to_normal():
    q = _store()
    assert q.get_tier("never_seen") == "normal"
    assert q.limits_for("never_seen").queries == 2


def test_set_and_get_tier():
    q = _store()
    q.set_tier("team_a", "advance")
    assert q.get_tier("team_a") == "advance"


def test_unlimited_tier_has_no_caps():
    q = _store()
    q.set_tier("team_u", "unlimited")
    limits = q.limits_for("team_u")
    assert not limits.queries_capped
    assert not limits.storage_capped
    assert not limits.docs_capped


def test_unknown_tier_rejected():
    q = _store()
    with pytest.raises(ValueError):
        q.set_tier("team_a", "platinum")


def test_query_counter_increments_and_isolates_by_period():
    q = _store()
    for _ in range(5):
        q.increment_query("team_b")
    assert q.get_query_count("team_b") == 5
    past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc).strftime("%Y-%m")
    assert q.get_query_count("team_b", past) == 0  # prior month untouched


def test_concurrent_increments_not_lost():
    q = _store()

    async def run():
        await asyncio.gather(*(asyncio.to_thread(q.increment_query, "team_c") for _ in range(50)))

    asyncio.run(run())
    assert q.get_query_count("team_c") == 50


def test_current_period_format():
    p = current_period()
    assert len(p) == 7 and p[4] == "-"


# --------------------------------------------------------------------------- #
# Live storage computation
# --------------------------------------------------------------------------- #


class FakeDocStatus:
    def __init__(self, content_lengths):
        self._docs = {
            f"doc-{i}": SimpleNamespace(content_length=n)
            for i, n in enumerate(content_lengths)
        }

    async def get_docs_by_statuses(self, statuses):
        return self._docs


class FakeRAG:
    def __init__(self, content_lengths):
        self.doc_status = FakeDocStatus(content_lengths)


def test_compute_storage_sums_content_length():
    usage = asyncio.run(QuotaStore.compute_storage(FakeRAG([10, 20, 30])))
    assert usage.used_bytes == 60
    assert usage.doc_count == 3


# --------------------------------------------------------------------------- #
# Enforcement dependencies
# --------------------------------------------------------------------------- #


class FakeRegistry:
    def __init__(self, rag):
        self._rag = rag

    async def get(self, workspace):
        return self._rag


def _fake_request(quota, rag, *, headers=None, token_info=None):
    app = SimpleNamespace(
        state=SimpleNamespace(quota=quota, workspace_registry=FakeRegistry(rag), rag=rag)
    )
    return SimpleNamespace(
        app=app,
        state=SimpleNamespace(token_info=token_info),
        headers=headers or {},
    )


def test_resolve_effective_workspace_default_is_exempt():
    # No header, no token → the default workspace, which is exempt (None).
    req = _fake_request(_store(), FakeRAG([]), headers={})
    assert resolve_effective_workspace(req) is None


def test_resolve_effective_workspace_named():
    req = _fake_request(_store(), FakeRAG([]), headers={"LIGHTRAG-WORKSPACE": "team_x"})
    assert resolve_effective_workspace(req) == "team_x"


def test_storage_quota_blocks_over_cap():
    q = _store()  # normal: 1 MB cap
    rag = FakeRAG([2 * 1024 * 1024])  # 2 MB used
    req = _fake_request(q, rag, headers={"LIGHTRAG-WORKSPACE": "team_full"})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(require_storage_quota(req))
    assert ei.value.status_code == 413


def test_storage_quota_allows_under_cap():
    q = _store()
    rag = FakeRAG([1024])  # 1 KB used, well under 1 MB
    req = _fake_request(q, rag, headers={"LIGHTRAG-WORKSPACE": "team_ok"})
    asyncio.run(require_storage_quota(req))  # no raise


def test_storage_quota_blocks_over_doc_count():
    q = _store()  # normal: max_docs 3
    rag = FakeRAG([1, 1, 1, 1])  # 4 docs
    req = _fake_request(q, rag, headers={"LIGHTRAG-WORKSPACE": "team_docs"})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(require_storage_quota(req))
    assert ei.value.status_code == 413


def test_storage_quota_default_workspace_exempt():
    q = _store()
    rag = FakeRAG([999 * 1024 * 1024])  # way over, but default ws is exempt
    req = _fake_request(q, rag, headers={})
    asyncio.run(require_storage_quota(req))  # no raise


def test_query_quota_blocks_at_cap_and_counts():
    q = _store()  # normal: 2 queries/mo
    req = _fake_request(q, FakeRAG([]), headers={"LIGHTRAG-WORKSPACE": "team_q"})
    asyncio.run(require_query_quota(req))  # 1
    asyncio.run(require_query_quota(req))  # 2
    assert q.get_query_count("team_q") == 2
    with pytest.raises(HTTPException) as ei:
        asyncio.run(require_query_quota(req))  # over
    assert ei.value.status_code == 429
    # The rejected request is not charged.
    assert q.get_query_count("team_q") == 2


def test_query_quota_admin_bypasses_and_is_not_charged():
    q = _store()
    req = _fake_request(
        q,
        FakeRAG([]),
        headers={"LIGHTRAG-WORKSPACE": "team_admin"},
        token_info={"role": "admin", "metadata": {}},
    )
    # Push well past the cap; admin is never blocked.
    for _ in range(5):
        asyncio.run(require_query_quota(req))
    assert q.get_query_count("team_admin") == 0  # not charged to the team


def test_query_quota_unlimited_tier_not_counted():
    q = _store()
    q.set_tier("team_unl", "unlimited")
    req = _fake_request(q, FakeRAG([]), headers={"LIGHTRAG-WORKSPACE": "team_unl"})
    for _ in range(10):
        asyncio.run(require_query_quota(req))
    assert q.get_query_count("team_unl") == 0


# --------------------------------------------------------------------------- #
# End-to-end through FastAPI dependencies (mirrors router usage)
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_client():
    q = _store()
    q.set_tier("team_e2e", "normal")
    rag = FakeRAG([])

    app = FastAPI()
    app.state.quota = q
    app.state.workspace_registry = FakeRegistry(rag)
    app.state.rag = rag

    @app.post("/q", dependencies=[Depends(require_query_quota)])
    async def do_query():
        return {"ok": True}

    return TestClient(app), q


def test_e2e_query_429_after_cap(app_client):
    client, q = app_client
    h = {"LIGHTRAG-WORKSPACE": "team_e2e"}
    assert client.post("/q", headers=h).status_code == 200
    assert client.post("/q", headers=h).status_code == 200
    assert client.post("/q", headers=h).status_code == 429
    # Default workspace (no header) stays exempt.
    assert client.post("/q").status_code == 200
