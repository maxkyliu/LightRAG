"""SSRF-guard tests for the public-URL fetcher (task 7.3)."""

import socket

import pytest

from telegram_gateway import fetcher
from telegram_gateway.fetcher import FetchError, _is_blocked_ip, _validate_url_host


def _fake_getaddrinfo(ip: str):
    def _inner(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _inner


def test_is_blocked_ip():
    assert _is_blocked_ip("127.0.0.1") is True
    assert _is_blocked_ip("10.0.0.5") is True
    assert _is_blocked_ip("192.168.1.1") is True
    assert _is_blocked_ip("169.254.1.1") is True  # link-local
    assert _is_blocked_ip("0.0.0.0") is True
    assert _is_blocked_ip("1.1.1.1") is False  # public


def test_rejects_non_http_scheme():
    with pytest.raises(FetchError):
        _validate_url_host("ftp://example.com/file")


def test_rejects_url_without_host():
    with pytest.raises(FetchError):
        _validate_url_host("http://")


def test_rejects_private_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(FetchError):
        _validate_url_host("http://evil.internal/secret")


def test_allows_public_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("1.1.1.1"))
    # Should not raise.
    _validate_url_host("https://example.com/report.pdf")


async def test_fetch_public_url_refuses_private(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(FetchError):
        # Cloud metadata endpoint must be refused before any network call.
        await fetcher.fetch_public_url("http://169.254.169.254/latest/meta-data/")
