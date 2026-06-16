"""
SQLite datastore for the Telegram gateway.

Owns gateway-local state only (identity, sessions, talk-event bookkeeping).
Knowledge-base data lives in LightRAG, not here.

Tables:
- ``teams``        — one row per team (tenant); bound 1:1 to a LightRAG workspace
- ``memberships``  — telegram account -> team + role (DM-only: one team per user)
- ``invites``      — reusable join codes (optional expiry); rotate to revoke
- ``sessions``     — per-member DM session buffer + lifecycle flags
- ``talk_events``  — doc ids of ingested conversation summaries (for /forget)

Methods are synchronous; SQLite calls are fast at this scale. Async callers
should wrap calls in ``asyncio.to_thread`` to avoid blocking the event loop.
A single connection (``check_same_thread=False``) is guarded by a lock so it is
safe to use from worker threads.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

OWNER = "owner"
MEMBER = "member"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Membership:
    tg_user_id: int
    team_id: str
    role: str


@dataclass
class Team:
    team_id: str
    name: str
    owner_tg_id: int


@dataclass
class Invite:
    code: str
    team_id: str
    expires_at: Optional[str]


@dataclass
class Session:
    tg_user_id: int
    team_id: str
    turns: list[dict[str, Any]]
    token_estimate: int
    last_activity: str
    private: bool
    ingest_armed: bool


@dataclass
class TalkEvent:
    id: int
    tg_user_id: int
    team_id: str
    doc_id: str
    created_at: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    owner_tg_id  INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    tg_user_id   INTEGER PRIMARY KEY,
    team_id      TEXT NOT NULL,
    role         TEXT NOT NULL,
    joined_at    TEXT NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE TABLE IF NOT EXISTS invites (
    code         TEXT PRIMARY KEY,
    team_id      TEXT NOT NULL,
    expires_at   TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    tg_user_id     INTEGER PRIMARY KEY,
    team_id        TEXT NOT NULL,
    turns_json     TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    last_activity  TEXT NOT NULL,
    private        INTEGER NOT NULL DEFAULT 0,
    ingest_armed   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS talk_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id   INTEGER NOT NULL,
    team_id      TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invites_team ON invites(team_id);
CREATE INDEX IF NOT EXISTS idx_talk_events_user ON talk_events(tg_user_id, id);
"""


class Datastore:
    def __init__(self, path: str = "telegram_gateway.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ----------------------------- teams ----------------------------------- #

    def create_team(self, team_id: str, name: str, owner_tg_id: int) -> Team:
        with self._lock:
            self._conn.execute(
                "INSERT INTO teams (team_id, name, owner_tg_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (team_id, name, owner_tg_id, _now()),
            )
            self._conn.commit()
        return Team(team_id=team_id, name=name, owner_tg_id=owner_tg_id)

    def get_team(self, team_id: str) -> Optional[Team]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM teams WHERE team_id = ?", (team_id,)
            ).fetchone()
        return Team(row["team_id"], row["name"], row["owner_tg_id"]) if row else None

    def delete_team(self, team_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memberships WHERE team_id = ?", (team_id,))
            self._conn.execute("DELETE FROM invites WHERE team_id = ?", (team_id,))
            self._conn.execute("DELETE FROM teams WHERE team_id = ?", (team_id,))
            self._conn.commit()

    # -------------------------- memberships -------------------------------- #

    def get_membership(self, tg_user_id: int) -> Optional[Membership]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memberships WHERE tg_user_id = ?", (tg_user_id,)
            ).fetchone()
        return (
            Membership(row["tg_user_id"], row["team_id"], row["role"]) if row else None
        )

    def add_membership(self, tg_user_id: int, team_id: str, role: str) -> Membership:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memberships "
                "(tg_user_id, team_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (tg_user_id, team_id, role, _now()),
            )
            self._conn.commit()
        return Membership(tg_user_id, team_id, role)

    def remove_membership(self, tg_user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM memberships WHERE tg_user_id = ?", (tg_user_id,)
            )
            self._conn.commit()

    def list_team_members(self, team_id: str) -> list[Membership]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memberships WHERE team_id = ?", (team_id,)
            ).fetchall()
        return [Membership(r["tg_user_id"], r["team_id"], r["role"]) for r in rows]

    # ----------------------------- invites --------------------------------- #

    def create_invite(
        self, code: str, team_id: str, expires_at: Optional[str] = None
    ) -> Invite:
        with self._lock:
            self._conn.execute(
                "INSERT INTO invites (code, team_id, expires_at, created_at) "
                "VALUES (?, ?, ?, ?)",
                (code, team_id, expires_at, _now()),
            )
            self._conn.commit()
        return Invite(code, team_id, expires_at)

    def get_invite(self, code: str) -> Optional[Invite]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM invites WHERE code = ?", (code,)
            ).fetchone()
        return Invite(row["code"], row["team_id"], row["expires_at"]) if row else None

    def delete_invites_for_team(self, team_id: str) -> None:
        """Used to revoke-by-rotation: drop all existing codes for the team."""
        with self._lock:
            self._conn.execute("DELETE FROM invites WHERE team_id = ?", (team_id,))
            self._conn.commit()

    # ---------------------------- sessions --------------------------------- #

    def get_session(self, tg_user_id: int) -> Optional[Session]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE tg_user_id = ?", (tg_user_id,)
            ).fetchone()
        if not row:
            return None
        return Session(
            tg_user_id=row["tg_user_id"],
            team_id=row["team_id"],
            turns=json.loads(row["turns_json"]),
            token_estimate=row["token_estimate"],
            last_activity=row["last_activity"],
            private=bool(row["private"]),
            ingest_armed=bool(row["ingest_armed"]),
        )

    def save_session(self, session: Session) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions "
                "(tg_user_id, team_id, turns_json, token_estimate, last_activity, "
                " private, ingest_armed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session.tg_user_id,
                    session.team_id,
                    json.dumps(session.turns),
                    session.token_estimate,
                    session.last_activity,
                    int(session.private),
                    int(session.ingest_armed),
                ),
            )
            self._conn.commit()

    def delete_session(self, tg_user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE tg_user_id = ?", (tg_user_id,)
            )
            self._conn.commit()

    def sessions_idle_since(self, cutoff_iso: str) -> list[Session]:
        """Return sessions whose last_activity is at or before ``cutoff_iso``."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE last_activity <= ?", (cutoff_iso,)
            ).fetchall()
        return [
            Session(
                tg_user_id=r["tg_user_id"],
                team_id=r["team_id"],
                turns=json.loads(r["turns_json"]),
                token_estimate=r["token_estimate"],
                last_activity=r["last_activity"],
                private=bool(r["private"]),
                ingest_armed=bool(r["ingest_armed"]),
            )
            for r in rows
        ]

    # --------------------------- talk events ------------------------------- #

    def record_talk_event(self, tg_user_id: int, team_id: str, doc_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO talk_events (tg_user_id, team_id, doc_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (tg_user_id, team_id, doc_id, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def latest_talk_event(self, tg_user_id: int) -> Optional[TalkEvent]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM talk_events WHERE tg_user_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (tg_user_id,),
            ).fetchone()
        if not row:
            return None
        return TalkEvent(
            row["id"],
            row["tg_user_id"],
            row["team_id"],
            row["doc_id"],
            row["created_at"],
        )

    def delete_talk_event(self, event_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM talk_events WHERE id = ?", (event_id,))
            self._conn.commit()
