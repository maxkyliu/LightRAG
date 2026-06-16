"""Session lifecycle tests (task 6.1)."""

import pytest

from telegram_gateway.config import GatewayConfig
from telegram_gateway.db import Datastore
from telegram_gateway.sessions import SessionService


@pytest.fixture
def svc():
    db = Datastore(":memory:")
    config = GatewayConfig(session_token_cap=50, session_idle_timeout_seconds=1800)
    return SessionService(db, config)


def test_append_accumulates_and_flags_token_cap(svc):
    _session, exceeded = svc.append_turn(1, "t1", "user", "short")
    assert exceeded is False
    # Push well past the 50-token cap (~4 chars/token).
    _session, exceeded = svc.append_turn(1, "t1", "assistant", "x" * 400)
    assert exceeded is True


def test_arm_and_consume_ingest(svc):
    svc.append_turn(1, "t1", "user", "hi")
    svc.arm_ingest(1, "t1")
    assert svc.consume_ingest_arm(1) is True
    # Second consume returns False (disarmed).
    assert svc.consume_ingest_arm(1) is False


def test_private_flag_persists(svc):
    svc.set_private(1, "t1")
    session = svc.get(1)
    assert session is not None and session.private is True


def test_end_returns_and_clears(svc):
    svc.append_turn(1, "t1", "user", "hello")
    ended = svc.end(1)
    assert ended is not None and len(ended.turns) == 1
    assert svc.get(1) is None


def test_idle_sessions_detected_with_zero_timeout():
    db = Datastore(":memory:")
    config = GatewayConfig(session_idle_timeout_seconds=0)
    svc = SessionService(db, config)
    svc.append_turn(1, "t1", "user", "hi")
    idle = svc.idle_sessions()
    assert any(s.tg_user_id == 1 for s in idle)
