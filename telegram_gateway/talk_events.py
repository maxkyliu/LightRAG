"""
Talk-event processing (tasks 6.4–6.6).

When a session ends, distill it into team knowledge and ingest it:

    session buffer
        -> summarize (default-deny)        [summarizer.py]
        -> regex/NER post-scrub             [redaction.py]
        -> ingest into team workspace        [lightrag_client]
           tagged via a ``talk-events/...`` file_path convention (design D8)
        -> record the doc id                  [db.talk_events]

Empty/trivial sessions and ``/private`` sessions produce no talk-event.
``/forget`` deletes the most recent talk-event by its recorded doc id (D9).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import redaction
from .config import GatewayConfig
from .db import Datastore, Session, TalkEvent
from .lightrag_client import LightRAGClient
from .summarizer import Summarizer


def _talk_event_file_path(tg_user_id: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"talk-events/{tg_user_id}/{stamp}.md"


class TalkEventService:
    def __init__(
        self,
        db: Datastore,
        client: LightRAGClient,
        summarizer: Summarizer,
        config: GatewayConfig,
    ):
        self._db = db
        self._client = client
        self._summarizer = summarizer
        self._config = config

    async def process_ended_session(self, session: Session) -> Optional[str]:
        """Summarize + scrub + ingest a finished session.

        Returns the ingested doc id, or ``None`` when nothing was captured
        (private session, empty buffer, summarizer not configured, or the model
        judged there was no durable knowledge).
        """
        if session.private or not session.turns:
            return None

        summary = await self._summarizer.summarize(session.turns)
        if not summary:
            return None

        scrubbed = redaction.scrub(summary).text
        workspace = self._config.workspace_for_team(session.team_id)
        file_source = _talk_event_file_path(session.tg_user_id)

        track_id = await self._client.insert_text(workspace, scrubbed, file_source)
        doc_ids = await self._client.resolve_doc_ids(workspace, track_id)
        # Fall back to the track_id if the doc id can't be resolved in time; the
        # record still lets /forget target this ingestion.
        doc_id = doc_ids[0] if doc_ids else track_id

        self._db.record_talk_event(session.tg_user_id, session.team_id, doc_id)
        return doc_id

    def latest_event(self, tg_user_id: int) -> Optional[TalkEvent]:
        return self._db.latest_talk_event(tg_user_id)

    async def delete_event(self, event: TalkEvent) -> None:
        workspace = self._config.workspace_for_team(event.team_id)
        await self._client.delete_documents(workspace, [event.doc_id])
        self._db.delete_talk_event(event.id)
