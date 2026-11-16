"""Safely find a public PyPI package's issue tracker for --explain (#400)."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from . import origin
from .check import Row
from .sources import Source


_ISSUE_KEYS = ("issues", "bug tracker", "tracker")
_FALLBACK_KEYS = ("source", "homepage")


def _safe_https(value: object) -> str | None:
    """Reject credentials, whitespace, control characters and non-HTTPS URLs."""
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None:
            return None
    except ValueError:
        return None
    return value


def project_issues_url(info: object) -> str | None:
    """Prefer an explicit tracker, else derive GitHub's /issues from a repository home."""
    if not isinstance(info, dict) or not isinstance(info.get("project_urls"), dict):
        return None
    urls = {str(key).strip().lower(): value for key, value in info["project_urls"].items()}
    for key in _ISSUE_KEYS:
        if url := _safe_https(urls.get(key)):
            return url
    for key in _FALLBACK_KEYS:
        if (url := _safe_https(urls.get(key))) is None:
            continue
        parsed = urlsplit(url)
        if parsed.hostname != "github.com" or parsed.port not in (None, 443):
            continue
        path = parsed.path.strip("/").removesuffix(".git")
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
            return f"https://github.com/{path}/issues"
    return None


def markdown_link(url: str) -> str:
    """Encode Markdown punctuation before placing an untrusted project URL in a link."""
    return quote(url, safe="/:@?&=#%+-._~")


def populate_issues_urls(
    rows: list[Row], sources: list[Source], *, simple_index: str | None = None
) -> None:
    """Use metadata from existing PyPI lookups; do not change --explain's network behaviour.

    A lockfile's stored wheels already explain the gaps without contacting PyPI, so only
    records whose index metadata was fetched during the normal check can provide a URL.
    """
    source_of = {id(p): s for s in sources for source in s.packages for p in source.variants}
    private = origin.private_names(sources, simple_index=simple_index)
    for row in rows:
        package = row.package
        source = source_of.get(id(package))
        if source is None or not origin.known_pypi(package, source, simple_index=simple_index, private=private):
            package.issues_url = None
