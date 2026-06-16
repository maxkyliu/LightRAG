"""
Telegram gateway for LightRAG — a multi-tenant chat front-end.

A standalone service (separate process) that maps Telegram accounts to teams,
each team to a LightRAG workspace, and brokers query/ingest/conversation-memory
over the LightRAG HTTP API using the ``LIGHTRAG-WORKSPACE`` header.

See ``openspec/changes/add-telegram-gateway/`` for the design of record.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
