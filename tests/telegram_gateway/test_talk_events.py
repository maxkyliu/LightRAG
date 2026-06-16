"""Talk-event end-to-end tests with fakes (tasks 6.4-6.6, 7.1, 7.2)."""

from telegram_gateway.config import GatewayConfig
from telegram_gateway.db import Datastore, Session
from telegram_gateway.talk_events import TalkEventService


class FakeClient:
    """Records ingest/delete calls; resolves a deterministic doc id."""

    def __init__(self):
        self.inserted: list[tuple[str, str, str]] = []  # (workspace, text, file_source)
        self.deleted: list[tuple[str, list[str]]] = []

    async def insert_text(self, workspace, text, file_source):
        self.inserted.append((workspace, text, file_source))
        return "track-1"

    async def resolve_doc_ids(self, workspace, track_id):
        return ["doc-xyz"]

    async def delete_documents(self, workspace, doc_ids, delete_file=True):
        self.deleted.append((workspace, doc_ids))
        return {"status": "ok"}


class FakeSummarizer:
    def __init__(self, result):
        self._result = result

    @property
    def configured(self):
        return True

    async def summarize(self, turns):
        return self._result


def _make(summary):
    db = Datastore(":memory:")
    config = GatewayConfig(workspace_prefix="team_")
    client = FakeClient()
    svc = TalkEventService(db, client, FakeSummarizer(summary), config)
    return db, client, svc


def _session(turns=None, private=False, team_id="acme"):
    return Session(
        tg_user_id=1,
        team_id=team_id,
        turns=turns if turns is not None else [{"role": "user", "text": "hi"}],
        token_estimate=10,
        last_activity="now",
        private=private,
        ingest_armed=False,
    )


async def test_process_ingests_scrubbed_summary_and_records_doc():
    db, client, svc = _make("Refund policy is 30 days. Reach jane@example.com.")
    doc_id = await svc.process_ended_session(_session())
    assert doc_id == "doc-xyz"

    # Ingested into the team workspace, scrubbed, with the talk-events file_path.
    workspace, text, file_source = client.inserted[0]
    assert workspace == "team_acme"
    assert "jane@example.com" not in text  # redacted
    assert file_source.startswith("talk-events/1/")

    # Recorded for /forget.
    assert db.latest_talk_event(1).doc_id == "doc-xyz"


async def test_private_session_is_skipped():
    _db, client, svc = _make("something")
    assert await svc.process_ended_session(_session(private=True)) is None
    assert client.inserted == []


async def test_empty_session_is_skipped():
    _db, client, svc = _make("something")
    assert await svc.process_ended_session(_session(turns=[])) is None
    assert client.inserted == []


async def test_no_knowledge_summary_is_skipped():
    _db, client, svc = _make(None)  # summarizer judged NO_KNOWLEDGE
    assert await svc.process_ended_session(_session()) is None
    assert client.inserted == []


async def test_forget_deletes_latest_event():
    db, client, svc = _make("Durable fact about onboarding.")
    await svc.process_ended_session(_session())
    event = svc.latest_event(1)
    assert event is not None

    await svc.delete_event(event)
    assert client.deleted == [("team_acme", ["doc-xyz"])]
    assert db.latest_talk_event(1) is None
