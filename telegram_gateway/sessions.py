"""
Per-member DM session buffering and lifecycle (task 6.1).

A session accumulates conversation turns until it ends via: 30-minute idle
timeout, an explicit ``/end``, or exceeding a token cap. On end the buffer is
handed to talk-event processing (unless the session is marked ``/private``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import GatewayConfig
from .db import Datastore, Session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Good enough for a cap heuristic."""
    return max(1, len(text) // 4)


class SessionService:
    def __init__(self, db: Datastore, config: GatewayConfig):
        self._db = db
        self._config = config

    def get(self, tg_user_id: int) -> Optional[Session]:
        return self._db.get_session(tg_user_id)

    def _get_or_create(self, tg_user_id: int, team_id: str) -> Session:
        session = self._db.get_session(tg_user_id)
        if session is None or session.team_id != team_id:
            session = Session(
                tg_user_id=tg_user_id,
                team_id=team_id,
                turns=[],
                token_estimate=0,
                last_activity=_now_iso(),
                private=False,
                ingest_armed=False,
            )
        return session

    def append_turn(
        self, tg_user_id: int, team_id: str, role: str, text: str
    ) -> tuple[Session, bool]:
        """Append a turn. Returns (session, token_cap_exceeded)."""
        session = self._get_or_create(tg_user_id, team_id)
        session.turns.append({"role": role, "text": text})
        session.token_estimate += estimate_tokens(text)
        session.last_activity = _now_iso()
        self._db.save_session(session)
        exceeded = session.token_estimate >= self._config.session_token_cap
        return session, exceeded

    def set_private(self, tg_user_id: int, team_id: str) -> None:
        session = self._get_or_create(tg_user_id, team_id)
        session.private = True
        session.last_activity = _now_iso()
        self._db.save_session(session)

    def arm_ingest(self, tg_user_id: int, team_id: str) -> None:
        session = self._get_or_create(tg_user_id, team_id)
        session.ingest_armed = True
        session.last_activity = _now_iso()
        self._db.save_session(session)

    def consume_ingest_arm(self, tg_user_id: int) -> bool:
        """Return True if ingest was armed for the next message, and disarm it."""
        session = self._db.get_session(tg_user_id)
        if not session or not session.ingest_armed:
            return False
        session.ingest_armed = False
        self._db.save_session(session)
        return True

    def end(self, tg_user_id: int) -> Optional[Session]:
        """Remove and return the session (its buffer is the talk-event input)."""
        session = self._db.get_session(tg_user_id)
        if session is not None:
            self._db.delete_session(tg_user_id)
        return session

    def idle_sessions(self) -> list[Session]:
        """Sessions whose last activity is older than the idle timeout."""
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.session_idle_timeout_seconds
        )
        return self._db.sessions_idle_since(cutoff.isoformat())
