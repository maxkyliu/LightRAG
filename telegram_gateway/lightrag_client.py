"""
Async HTTP client for the LightRAG API.

Every call injects the ``LIGHTRAG-WORKSPACE`` header so the (patched) LightRAG
server routes the request to the caller's team workspace. This is the only place
the gateway talks to LightRAG.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx


class LightRAGError(RuntimeError):
    """Raised when a LightRAG API call fails."""


class QuotaExceededError(LightRAGError):
    """Raised when a request is rejected for exceeding a team resource quota.

    Subclasses :class:`LightRAGError` so existing handlers still catch it, while
    carrying the server's human-readable detail for surfacing to the user.
    """

    def __init__(self, message: str, kind: str = "quota") -> None:
        super().__init__(message)
        self.user_message = message
        self.kind = kind  # "storage" (413) or "enquiry" (429)


class LightRAGClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_seconds: int = 120,
        extra_headers: Optional[dict] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._base_headers: dict[str, str] = dict(extra_headers or {})
        if api_key:
            self._base_headers["X-API-Key"] = api_key

    def _headers(self, workspace: str) -> dict[str, str]:
        headers = dict(self._base_headers)
        if workspace:
            headers["LIGHTRAG-WORKSPACE"] = workspace
        return headers

    async def _request(
        self, method: str, path: str, workspace: str, **kwargs: Any
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers = {**self._headers(workspace), **kwargs.pop("headers", {})}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as e:
            raise LightRAGError(f"LightRAG request failed: {e}") from e
        if resp.status_code in (413, 429):
            # Team resource quota exceeded — surface the server's friendly detail.
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            kind = "storage" if resp.status_code == 413 else "enquiry"
            raise QuotaExceededError(detail or "Team resource quota reached.", kind)
        if resp.status_code >= 400:
            raise LightRAGError(
                f"LightRAG {method} {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp

    # ------------------------------- query --------------------------------- #

    async def query(
        self, workspace: str, query: str, mode: str = "mix", **params: Any
    ) -> str:
        """Run a retrieval query against ``workspace`` and return the answer."""
        payload = {"query": query, "mode": mode, **params}
        resp = await self._request("POST", "/query", workspace, json=payload)
        data = resp.json()
        return data.get("response", "")

    # ------------------------------- auth ---------------------------------- #

    async def mint_viewer_token(self, workspace: str, ttl_minutes: int = 15) -> str:
        """Mint a short-lived, read-only WebUI token scoped to ``workspace``.

        Admin-authenticated (the client's X-API-Key); the auth endpoint is not
        workspace-scoped, so no LIGHTRAG-WORKSPACE header is sent.
        """
        payload = {"workspace": workspace, "ttl_minutes": ttl_minutes}
        resp = await self._request("POST", "/auth/mint-viewer-token", "", json=payload)
        return resp.json().get("access_token", "")

    # ------------------------------ ingest --------------------------------- #

    async def insert_text(self, workspace: str, text: str, file_source: str) -> str:
        """Insert raw text. Returns the track_id for status polling."""
        payload = {"text": text, "file_source": file_source}
        resp = await self._request("POST", "/documents/text", workspace, json=payload)
        return resp.json().get("track_id", "")

    async def upload_file(
        self, workspace: str, filename: str, content: bytes, content_type: str = ""
    ) -> str:
        """Upload a file for ingestion. Returns the track_id."""
        files = {
            "file": (filename, content, content_type or "application/octet-stream")
        }
        resp = await self._request("POST", "/documents/upload", workspace, files=files)
        return resp.json().get("track_id", "")

    # ------------------------------ delete --------------------------------- #

    async def delete_documents(
        self, workspace: str, doc_ids: list[str], delete_file: bool = True
    ) -> dict:
        payload = {"doc_ids": doc_ids, "delete_file": delete_file}
        resp = await self._request(
            "DELETE", "/documents/delete_document", workspace, json=payload
        )
        return resp.json()

    # ------------------------------ status --------------------------------- #

    async def track_status(self, workspace: str, track_id: str) -> dict:
        resp = await self._request(
            "GET", f"/documents/track_status/{track_id}", workspace
        )
        return resp.json()

    async def resolve_doc_ids(
        self,
        workspace: str,
        track_id: str,
        attempts: int = 10,
        delay_seconds: float = 1.0,
    ) -> list[str]:
        """Poll track_status until documents appear, returning their doc ids.

        Ingestion is asynchronous on the server; the documents for a track_id
        may not exist immediately after insert. Returns an empty list if none
        appear within the budget.
        """
        for _ in range(attempts):
            data = await self.track_status(workspace, track_id)
            docs = data.get("documents") or []
            ids = [d.get("id") for d in docs if d.get("id")]
            if ids:
                return ids
            await asyncio.sleep(delay_seconds)
        return []
