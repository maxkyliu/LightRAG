"""
Tests for header-based multi-tenancy (per-request workspace routing).

These cover the routing mechanism that the document and query routers rely on:
- ``extract_workspace_from_request`` header parsing + sanitization
- ``WorkspaceRAGRegistry`` lazy-build, caching, and per-workspace isolation
- ``get_rag_for_request`` end-to-end through a FastAPI dependency, proving a
  request's ``LIGHTRAG-WORKSPACE`` header selects the right instance and the
  no-header path falls back to the default instance unchanged.

The real ``LightRAG`` is replaced with a lightweight fake so the tests need no
storage backends; the routing logic under test is storage-agnostic.
"""

import sys
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# Importing lightrag.api.utils_api triggers config initialization at import time
# (auth.py builds an AuthHandler that reads global_args, which calls parse_args).
# Under pytest, sys.argv holds pytest's arguments, which argparse rejects. Import
# under a clean argv (as the other API tests do) so config initializes cleanly.
_saved_argv = sys.argv
sys.argv = ["lightrag-server"]
try:
    from lightrag.api.utils_api import (
        extract_workspace_from_request,
        get_rag_for_request,
        require_write_access,
    )
    from lightrag.api.workspace_registry import WorkspaceRAGRegistry
finally:
    sys.argv = _saved_argv


class FakeRAG:
    """Stand-in for a LightRAG instance, identified by its workspace."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.initialized = False
        self.finalized = False

    async def finalize_storages(self):
        self.finalized = True


def _make_registry(default_workspace: str = ""):
    build_log: list[str] = []

    def builder(ws: str) -> FakeRAG:
        build_log.append(ws)
        return FakeRAG(ws)

    async def initializer(rag: FakeRAG) -> None:
        rag.initialized = True

    default_rag = FakeRAG(default_workspace)
    registry = WorkspaceRAGRegistry(
        default_workspace=default_workspace,
        default_rag=default_rag,
        builder=builder,
        initializer=initializer,
    )
    return registry, default_rag, build_log


def _request_with_header(value):
    headers = {} if value is None else {"LIGHTRAG-WORKSPACE": value}
    return SimpleNamespace(headers=headers)


# --------------------------------------------------------------------------- #
# Header extraction + sanitization
# --------------------------------------------------------------------------- #


def test_extract_workspace_absent_returns_none():
    assert extract_workspace_from_request(_request_with_header(None)) is None


def test_extract_workspace_empty_returns_none():
    assert extract_workspace_from_request(_request_with_header("   ")) is None


def test_extract_workspace_valid_passthrough():
    assert (
        extract_workspace_from_request(_request_with_header("team_acme")) == "team_acme"
    )


def test_extract_workspace_sanitizes_invalid_chars():
    # Spaces, punctuation, and path traversal characters collapse to underscores.
    assert (
        extract_workspace_from_request(_request_with_header("team acme!/../x"))
        == "team_acme_____x"
    )


# --------------------------------------------------------------------------- #
# Registry: lazy build, caching, isolation
# --------------------------------------------------------------------------- #


async def test_registry_returns_default_for_empty():
    registry, default_rag, build_log = _make_registry(default_workspace="")
    assert await registry.get(None) is default_rag
    assert await registry.get("") is default_rag
    # Default instance is pre-built; builder never invoked for it.
    assert build_log == []


async def test_registry_lazily_builds_and_initializes():
    registry, _default, build_log = _make_registry()
    rag_a = await registry.get("team_a")
    assert rag_a.workspace == "team_a"
    assert rag_a.initialized is True
    assert build_log == ["team_a"]


async def test_registry_caches_per_workspace():
    registry, _default, build_log = _make_registry()
    first = await registry.get("team_a")
    second = await registry.get("team_a")
    assert first is second
    assert build_log == ["team_a"]  # built exactly once


async def test_registry_isolates_distinct_workspaces():
    registry, _default, _log = _make_registry()
    rag_a = await registry.get("team_a")
    rag_b = await registry.get("team_b")
    assert rag_a is not rag_b
    assert rag_a.workspace == "team_a"
    assert rag_b.workspace == "team_b"


async def test_registry_concurrent_first_use_builds_once():
    import asyncio

    registry, _default, build_log = _make_registry()
    results = await asyncio.gather(*(registry.get("team_a") for _ in range(10)))
    # All callers get the same instance; the builder ran exactly once.
    assert all(r is results[0] for r in results)
    assert build_log == ["team_a"]


async def test_finalize_dynamic_skips_default():
    registry, default_rag, _log = _make_registry(default_workspace="base")
    rag_a = await registry.get("team_a")
    await registry.finalize_dynamic()
    assert rag_a.finalized is True
    assert default_rag.finalized is False  # default is finalized by the lifespan


# --------------------------------------------------------------------------- #
# End-to-end through a FastAPI dependency (mirrors how routers consume it)
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_client():
    registry, default_rag, _log = _make_registry(default_workspace="base")
    app = FastAPI()
    app.state.rag = default_rag
    app.state.workspace_registry = registry

    @app.get("/whoami")
    async def whoami(rag=Depends(get_rag_for_request)):
        return {"workspace": rag.workspace}

    return TestClient(app)


def test_request_without_header_uses_default(app_client):
    resp = app_client.get("/whoami")
    assert resp.status_code == 200
    assert resp.json() == {"workspace": "base"}


def test_request_with_header_routes_to_workspace(app_client):
    resp = app_client.get("/whoami", headers={"LIGHTRAG-WORKSPACE": "team_acme"})
    assert resp.status_code == 200
    assert resp.json() == {"workspace": "team_acme"}


def test_request_header_is_sanitized(app_client):
    resp = app_client.get("/whoami", headers={"LIGHTRAG-WORKSPACE": "team acme!"})
    assert resp.status_code == 200
    assert resp.json() == {"workspace": "team_acme_"}


def test_two_tenants_do_not_cross_over(app_client):
    a = app_client.get("/whoami", headers={"LIGHTRAG-WORKSPACE": "tenant_a"}).json()
    b = app_client.get("/whoami", headers={"LIGHTRAG-WORKSPACE": "tenant_b"}).json()
    assert a == {"workspace": "tenant_a"}
    assert b == {"workspace": "tenant_b"}


def test_no_registry_falls_back_to_default_rag():
    app = FastAPI()
    app.state.rag = FakeRAG("only")

    @app.get("/whoami")
    async def whoami(rag=Depends(get_rag_for_request)):
        return {"workspace": rag.workspace}

    client = TestClient(app)
    # No header and no registry → the single default instance, unchanged behavior.
    assert client.get("/whoami").json() == {"workspace": "only"}
    # Header present but no registry → still the default instance.
    assert client.get("/whoami", headers={"LIGHTRAG-WORKSPACE": "ignored"}).json() == {
        "workspace": "only"
    }


# --------------------------------------------------------------------------- #
# Role × workspace enforcement (add-webui-team-owner-login)
# --------------------------------------------------------------------------- #


def _fake_request(registry, *, headers=None, token_info=None):
    """Build a minimal object exposing the attrs get_rag_for_request reads."""
    state = SimpleNamespace()
    if token_info is not None:
        state.token_info = token_info
    app = SimpleNamespace(state=SimpleNamespace(workspace_registry=registry, rag=None))
    return SimpleNamespace(app=app, state=state, headers=headers or {})


async def test_viewer_token_locked_to_its_workspace():
    registry, _default, _log = _make_registry(default_workspace="base")
    req = _fake_request(
        registry,
        headers={"LIGHTRAG-WORKSPACE": "team_other"},  # spoof attempt
        token_info={"role": "viewer", "metadata": {"workspace": "team_owner"}},
    )
    rag = await get_rag_for_request(req)
    # Header is ignored; the viewer is forced to the token's workspace.
    assert rag.workspace == "team_owner"


async def test_admin_token_may_target_header_workspace():
    registry, _default, _log = _make_registry(default_workspace="base")
    req = _fake_request(
        registry,
        headers={"LIGHTRAG-WORKSPACE": "team_globex"},
        token_info={"role": "admin", "metadata": {}},
    )
    rag = await get_rag_for_request(req)
    assert rag.workspace == "team_globex"


async def test_no_token_uses_header():
    registry, _default, _log = _make_registry(default_workspace="base")
    req = _fake_request(registry, headers={"LIGHTRAG-WORKSPACE": "team_x"})
    rag = await get_rag_for_request(req)
    assert rag.workspace == "team_x"


async def test_write_guard_blocks_viewer():
    from fastapi import HTTPException

    req = _fake_request(
        None, token_info={"role": "viewer", "metadata": {"workspace": "team_owner"}}
    )
    with pytest.raises(HTTPException) as exc:
        await require_write_access(req)
    assert exc.value.status_code == 403


async def test_write_guard_allows_admin_and_anonymous():
    # admin
    await require_write_access(
        _fake_request(None, token_info={"role": "admin", "metadata": {}})
    )
    # no token (api-key / default) — not a viewer, allowed
    await require_write_access(_fake_request(None))
