# Per-Request Workspace Routing (Header-Based Multi-Tenancy)

This is a **fork patch**: a feature carried on the `maxkyliu/LightRAG` fork that
must be re-applied by hand after merging upstream `HKUDS/LightRAG` changes (the
same maintenance model as the llama-swap binding patch). This document explains
what the patch does, why it is shaped the way it is, the exact touch points, and
how to re-apply it.

## Why

Stock LightRAG is effectively single-tenant per server process: the
`rag = LightRAG(...)` instance is constructed once with a fixed `workspace`
(from `WORKSPACE` / `--workspace`), and its storages are bound to that workspace
at construction time. The `LIGHTRAG-WORKSPACE` header existed but was honored
**only** by the `/health` status endpoint — document and query routes always
used the boot-time workspace.

This patch lets a **single** server process serve **many** workspaces, selected
per request via the `LIGHTRAG-WORKSPACE` header, with full data isolation. The
Telegram gateway (`add-telegram-gateway`) maps each team to a workspace and sends
`LIGHTRAG-WORKSPACE: <team_id>` on every call.

## Design

A `LightRAG` instance is bound to one workspace, so per-request routing requires
**one instance per workspace**, built lazily and cached:

```
request ── LIGHTRAG-WORKSPACE: team_a ──▶ get_rag_for_request (FastAPI dep)
                                              │
                                              ▼
                                   WorkspaceRAGRegistry.get("team_a")
                                              │  (cached? return it)
                                              │  (else build + initialize_storages, then cache)
                                              ▼
                                   LightRAG(workspace="team_a")  ── shared DB backends
```

- **No header / empty header → default workspace** (the boot-time instance),
  so existing single-workspace deployments are byte-for-byte unchanged.
- Header values are sanitized to `[a-zA-Z0-9_]` (matching `--workspace`
  sanitization) to prevent injection into backend identifiers.
- All workspace instances share the same backend configuration (Postgres,
  Neo4j, etc.); those backends already namespace data by workspace, so isolation
  is enforced at the storage layer.

The routers consume this through a single FastAPI dependency parameter
(`rag=Depends(get_rag_for_request)`) added to each handler. Because it is a
**parameter**, it shadows the factory's closure `rag` with the per-request
instance — no handler body changes are required.

## Touch points

| File | Change |
| --- | --- |
| `lightrag/api/workspace_registry.py` | **New.** `WorkspaceRAGRegistry`: lazy build, per-workspace lock, cache, `finalize_dynamic()`. |
| `lightrag/api/utils_api.py` | **New** `extract_workspace_from_request()` and the `get_rag_for_request()` FastAPI dependency. (`import re` added.) |
| `lightrag/api/lightrag_server.py` | Refactor `rag = LightRAG(...)` into a `_build_rag(workspace)` builder; build the default instance from it; create `WorkspaceRAGRegistry`; set `app.state.rag` and `app.state.workspace_registry`; finalize dynamic instances in the lifespan `finally`. |
| `lightrag/api/routers/query_routes.py` | Add `rag=Depends(get_rag_for_request)` to `query_text`, `query_text_stream`, `query_data`. |
| `lightrag/api/routers/document_routes.py` | Add `rag=Depends(get_rag_for_request)` to all 14 route handlers (scan, upload, insert_text/texts, clear_documents, pipeline_status, documents, delete_document, clear_cache, track_status, paginated, status_counts, reprocess, cancel). |
| `tests/api/test_workspace_routing.py` | **New.** Isolation + routing tests (no DB required). |

## Usage

```bash
# Server: start once with a default workspace (or none).
lightrag-server --workspace base

# Clients select a workspace per request:
curl -H "LIGHTRAG-WORKSPACE: team_acme"  ... /documents/upload   # ingest into team_acme
curl -H "LIGHTRAG-WORKSPACE: team_acme"  ... /query              # query team_acme only
curl                                     ... /query              # query the default workspace
```

## Re-applying after an upstream merge

1. Re-add `workspace_registry.py` and the two `utils_api.py` helpers if a merge
   dropped them (they are additive — unlikely to conflict).
2. In `lightrag_server.py`, ruff reformatting upstream may move the
   `rag = LightRAG(...)` block. Re-wrap it in `_build_rag(workspace_value)`
   (set `workspace=workspace_value`), move the post-construction
   `_log_role_provider_options` / `register_role_llm_builder` inside the builder,
   then rebuild the default via `rag = _build_rag(args.workspace)` and recreate
   the registry + `app.state` assignments.
3. Re-add the `rag=Depends(get_rag_for_request)` parameter to any new or
   reformatted route handlers in `document_routes.py` / `query_routes.py`.
4. Run `uv run pytest tests/api/test_workspace_routing.py` to confirm routing,
   and `uv run ruff check lightrag/api` for formatting.

## Limitations / notes

- **Optional API-key → workspace binding** (defense-in-depth) is not implemented
  (`tasks 1.4`, deferred). The gateway is the trust boundary; do not expose the
  LightRAG port publicly without it.
- Under Gunicorn multi-worker mode each worker maintains its own per-workspace
  instance cache. This is correct for shared DB backends (Postgres/Neo4j);
  file-based storages (json/nano) retain the same multi-worker caveats they
  already have for the single-workspace case.
