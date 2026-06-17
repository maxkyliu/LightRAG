"""Redaction tests (task 7.2)."""

from telegram_gateway.redaction import REDACTED, scrub


def test_scrubs_email():
    result = scrub("contact me at jane.doe@example.com please")
    assert "jane.doe@example.com" not in result.text
    assert REDACTED in result.text
    assert "email" in result.found


def test_scrubs_openai_key():
    result = scrub("key is sk-abcdEFGH1234567890abcdEFGH")
    assert "sk-abcd" not in result.text
    assert "openai_key" in result.found


def test_scrubs_ssn_and_phone():
    result = scrub("SSN 123-45-6789 call +1 (415) 555-1234")
    assert "123-45-6789" not in result.text
    assert "ssn" in result.found
    assert "phone" in result.found


def test_scrubs_credit_card():
    result = scrub("card 4111 1111 1111 1111 expiry soon")
    assert "4111 1111 1111 1111" not in result.text
    assert "credit_card" in result.found


def test_clean_text_unchanged():
    text = "Our refund window is 30 days from purchase."
    result = scrub(text)
    assert result.text == text
    assert result.found == []
