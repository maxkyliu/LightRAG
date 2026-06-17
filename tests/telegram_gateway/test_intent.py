"""Intent parsing tests (task 4.1)."""

from telegram_gateway.intent import extract_first_url, parse_command


def test_parse_known_command_with_args():
    cmd = parse_command("/createteam Acme Corp")
    assert cmd is not None
    assert cmd.name == "createteam"
    assert cmd.args == "Acme Corp"


def test_parse_command_strips_botname_suffix():
    cmd = parse_command("/join@MyBot ABC123")
    assert cmd is not None
    assert cmd.name == "join"
    assert cmd.args == "ABC123"


def test_unknown_command_returns_none():
    assert parse_command("/notacommand foo") is None


def test_plain_text_is_not_a_command():
    assert parse_command("what is our refund policy?") is None


def test_empty_and_none():
    assert parse_command("") is None
    assert parse_command(None) is None


def test_ingest_is_a_command():
    cmd = parse_command("/ingest https://example.com/a.pdf")
    assert cmd is not None and cmd.name == "ingest"
    assert cmd.args == "https://example.com/a.pdf"


def test_extract_first_url():
    assert extract_first_url("see https://a.com/x.pdf now") == "https://a.com/x.pdf"
    assert extract_first_url("no url here") is None
    assert extract_first_url(None) is None
