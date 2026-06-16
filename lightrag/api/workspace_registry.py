"""
Per-workspace LightRAG instance registry for header-based multi-tenancy.

A single LightRAG server process pins one ``workspace`` per ``LightRAG``
instance (storages are bound to the workspace at construction time). To let one
process serve many workspaces selected per-request via the ``LIGHTRAG-WORKSPACE``
header, this registry lazily builds and caches one ``LightRAG`` instance per
workspace, all sharing the same backend configuration.

See ``docs/MultiTenancyWorkspaceRouting.md`` for the rationale and the
fork re-apply procedure.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict

from lightrag import LightRAG
from lightrag.utils import logger


class WorkspaceRAGRegistry:
    """Lazily builds and caches one ``LightRAG`` per workspace.

    The default workspace's instance is supplied pre-built (it is initialized by
    the server lifespan). Additional workspaces are constructed and initialized
    on first use and then cached for the lifetime of the process.
    """

    def __init__(
        self,
        default_workspace: str,
        default_rag: LightRAG,
        builder: Callable[[str], LightRAG],
        initializer: Callable[[LightRAG], Awaitable[None]],
    ) -> None:
        self._default_workspace = default_workspace or ""
        self._builder = builder
        self._initializer = initializer
        self._instances: Dict[str, LightRAG] = {self._default_workspace: default_rag}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    def _normalize(self, workspace: str | None) -> str:
        """Empty/None resolves to the server's default workspace."""
        return workspace if workspace else self._default_workspace

    async def get(self, workspace: str | None) -> LightRAG:
        """Return the ``LightRAG`` for ``workspace``, building it on first use.

        Building is guarded by a per-workspace lock so concurrent first-requests
        for the same workspace create exactly one instance.
        """
        ws = self._normalize(workspace)

        instance = self._instances.get(ws)
        if instance is not None:
            return instance

        # Acquire (or create) the per-workspace build lock under the registry lock.
        async with self._registry_lock:
            lock = self._locks.get(ws)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[ws] = lock

        async with lock:
            # Re-check: another coroutine may have built it while we waited.
            instance = self._instances.get(ws)
            if instance is not None:
                return instance

            logger.info(f"Creating LightRAG instance for workspace '{ws}'")
            instance = self._builder(ws)
            await self._initializer(instance)
            self._instances[ws] = instance
            return instance

    def instances(self) -> Dict[str, LightRAG]:
        return dict(self._instances)

    async def finalize_dynamic(self) -> None:
        """Finalize every workspace instance except the default.

        The default instance is finalized by the server lifespan; this cleans up
        the lazily-created ones.
        """
        for ws, instance in list(self._instances.items()):
            if ws == self._default_workspace:
                continue
            try:
                await instance.finalize_storages()
            except Exception as e:  # pragma: no cover - best-effort cleanup
                logger.warning(f"Error finalizing workspace '{ws}': {e}")
