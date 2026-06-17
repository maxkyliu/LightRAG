"""
Public-URL fetcher with SSRF guards (task 5.4).

v1 supports *public* URLs only (no authenticated cloud storage). To avoid
server-side request forgery, the fetcher:

- accepts only ``http``/``https`` schemes,
- resolves the host and rejects private / loopback / link-local / reserved /
  multicast IPs (re-validated on every redirect hop),
- follows a bounded number of redirects manually,
- caps total bytes and wall-clock time.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class FetchError(RuntimeError):
    """Raised when a URL cannot be safely fetched."""


@dataclass
class FetchedResource:
    url: str
    filename: str
    content: bytes
    content_type: str


def _is_blocked_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_url_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")
    host = parsed.hostname
    if not host:
        raise FetchError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchError(f"Cannot resolve host '{host}': {e}") from e
    for info in infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            raise FetchError(
                f"Refusing to fetch '{host}': resolves to non-public address {ip_str}"
            )


def _filename_from(url: str, content_type: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    if name:
        return name
    # Fall back to a generic name with a best-effort extension.
    ext = ""
    if "pdf" in content_type:
        ext = ".pdf"
    elif "html" in content_type:
        ext = ".html"
    elif "text" in content_type:
        ext = ".txt"
    return f"download{ext or '.bin'}"


async def fetch_public_url(
    url: str,
    *,
    max_bytes: int = 50 * 1024 * 1024,
    timeout_seconds: int = 60,
    max_redirects: int = 3,
) -> FetchedResource:
    """Fetch ``url`` safely and return its bytes.

    Raises :class:`FetchError` for unsupported schemes, non-public hosts,
    oversized bodies, redirect loops, or transport errors.
    """
    current = url
    async with httpx.AsyncClient(
        timeout=timeout_seconds, follow_redirects=False
    ) as client:
        for _ in range(max_redirects + 1):
            _validate_url_host(current)
            try:
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError("Redirect without Location header")
                        current = str(httpx.URL(current).join(location))
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(
                            f"Fetch failed: {resp.status_code} for {current}"
                        )
                    chunks = bytearray()
                    async for chunk in resp.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            raise FetchError(
                                f"Resource exceeds max size of {max_bytes} bytes"
                            )
                    content_type = resp.headers.get("content-type", "").split(";")[0]
                    return FetchedResource(
                        url=current,
                        filename=_filename_from(current, content_type),
                        content=bytes(chunks),
                        content_type=content_type,
                    )
            except httpx.HTTPError as e:
                raise FetchError(f"Transport error fetching '{current}': {e}") from e
    raise FetchError(f"Too many redirects (>{max_redirects})")
