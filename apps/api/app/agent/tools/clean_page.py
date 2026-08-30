"""clean_page tool: fetch the url server-side and strip boilerplate.

Never raises. Includes the SSRF guard (fail-closed).
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import trafilatura

from app.config import get_settings


@dataclass
class CleanPageResult:
    ok: bool
    clean_text: str = ""
    title: str = ""
    word_count: int = 0     # words after cleaning, before capping
    truncated: bool = False
    error: str = ""         # human-readable, safe to surface in the side panel


def ssrf_guard(url: str) -> str:
    """Return an error message, empty if the address is safe to fetch. Fail-closed."""
    try:
        parsed = urlparse(str(url))
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return "Not a valid web address."
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return "This address cannot be quizzed."
        return ""
    except Exception:  # noqa: BLE001 — resolution failed, fail closed
        return "Could not verify this address."


def clean_page(url: str) -> CleanPageResult:
    """Fetch a page and return clean, capped article text. Never raises."""
    max_words = get_settings().max_words
    try:
        blocked = ssrf_guard(url)
        if blocked:
            return CleanPageResult(ok=False, error=blocked)

        html = trafilatura.fetch_url(url)
        if not html:
            return CleanPageResult(
                ok=False, error="Could not fetch the page (offline, blocked, or requires login)."
            )

        text = (
            trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
        )
        meta = trafilatura.extract_metadata(html)
        title = (meta.title if meta and meta.title else "").strip()

        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return CleanPageResult(
                ok=False, title=title, error="Fetched the page but found no readable article text."
            )

        words = text.split(" ")
        return CleanPageResult(
            ok=True,
            clean_text=" ".join(words[:max_words]),
            title=title,
            word_count=len(words),
            truncated=len(words) > max_words,
        )
    except Exception as e:  # noqa: BLE001 — resilience boundary
        return CleanPageResult(ok=False, error=f"Unexpected extraction failure: {e}")
