"""Fetch a web page and return readable text (no JS execution).

This is a plain HTTP client - it does not run JavaScript or drive a real
browser. It exists so research agents can read documentation pages and
API responses; size and time are capped to keep the tool bounded.
"""

from __future__ import annotations

import os
import re
from html import unescape
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from tools.base import BaseTool, ToolError, ToolResult, register, truncate

MAX_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 15.0
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ANY_TAG_PATTERN = re.compile(r"<[^>]+>")
_BLOCK_SEP_PATTERN = re.compile(r"</(p|div|li|h[1-6]|tr|br)\s*>", re.IGNORECASE)
_WS_PATTERN = re.compile(r"[ \t]+")
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def html_to_text(html: str) -> str:
    """Strip scripts/styles/tags, keeping readable block structure."""
    text = _BLOCK_SEP_PATTERN.sub("\n", html)
    text = _TAG_PATTERN.sub(" ", text)
    text = _ANY_TAG_PATTERN.sub(" ", text)
    text = unescape(text)
    lines = [_WS_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


@register
class BrowserTool(BaseTool):
    """GET an http(s) page and return its title plus readable text."""

    name: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "Fetch an http(s) web page and get its title and readable text "
        "(static HTML only, no JavaScript)"
    )

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ToolError("timeout must be positive")
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self._user_agent = user_agent or os.environ.get(
            "WORKFORCE_USER_AGENT", "shahid-workforce/0.1"
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def run(self, url: str = "", **_: Any) -> ToolResult:
        """GET ``url`` and return title + text (bounded size)."""
        parsed = urlparse(url.strip())
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
            raise ToolError("url must be http(s) with a host, e.g. https://example.com")

        try:
            with self._client.stream(
                "GET",
                url,
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            ) as response:
                if response.status_code >= 400:
                    raise ToolError(
                        f"fetch failed: HTTP {response.status_code} for {url}"
                    )
                content_type = response.headers.get("content-type", "")
                if content_type and "html" not in content_type and "text" not in content_type:
                    raise ToolError(
                        f"unsupported content-type: {content_type} "
                        "(only HTML/text is readable)"
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ToolError(f"page exceeds {MAX_BYTES} bytes")
                    chunks.append(chunk)
                raw = b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise ToolError(f"fetch timed out for {url}") from exc
        except httpx.HTTPError as exc:
            raise ToolError(f"fetch failed for {url}: {exc}") from exc

        html = raw.decode(response.encoding or "utf-8", errors="replace")
        title_match = _TITLE_PATTERN.search(html)
        title = unescape(title_match.group(1)).strip() if title_match else ""
        body = html_to_text(html)
        excerpt = "\n".join(body.splitlines()[:200])

        return ToolResult(
            tool=self.name,
            ok=True,
            output=truncate(f"# {title}\n\n{excerpt}" if title else excerpt),
            data={
                "url": url,
                "title": title,
                "status_code": response.status_code,
                "bytes": len(raw),
            },
        )
