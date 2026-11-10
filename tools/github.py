"""GitHub operations through the GitHub REST API with a token from env.

The token is read from ``GITHUB_TOKEN`` at construction time and is never
included in outputs or error messages (see :func:`tools.base.scrub`).
Network access happens through an injectable ``httpx`` client so tests run
against a mock transport.
"""

from __future__ import annotations

import base64
import os
from typing import Any, ClassVar

import httpx

from tools.base import BaseTool, ToolError, ToolResult, register, scrub, truncate

API_BASE = "https://api.github.com"
USER_AGENT = "shahid-workforce/0.1"
MAX_FILE_BYTES = 500_000


@register
class GitHubTool(BaseTool):
    """Read repository files and metadata via the GitHub REST API."""

    name: ClassVar[str] = "github"
    description: ClassVar[str] = (
        "Read files and repository metadata from GitHub (contents, repo info, "
        "open issues) using the configured token"
    )

    def __init__(
        self,
        token: str | None = None,
        *,
        client: httpx.Client | None = None,
        api_base: str = API_BASE,
    ) -> None:
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self._api_base = api_base.rstrip("/")
        self._client = client or httpx.Client(timeout=15.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, path: str) -> Any:
        url = f"{self._api_base}{path}"
        try:
            response = self._client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ToolError(scrub(f"github request failed: {exc}", self._token)) from exc
        if response.status_code >= 400:
            detail = _error_detail(response)
            raise ToolError(
                scrub(
                    f"github returned {response.status_code} for {path}: {detail}",
                    self._token,
                )
            )
        return response.json()

    def run(
        self,
        action: str = "read_file",
        *,
        repo: str = "",
        path: str = "",
        ref: str | None = None,
        state: str = "open",
        **_: Any,
    ) -> ToolResult:
        """Dispatch: ``read_file``, ``repo_info`` or ``list_issues``."""
        if action == "read_file":
            return self._read_file(repo, path, ref)
        if action == "repo_info":
            return self._repo_info(repo)
        if action == "list_issues":
            return self._list_issues(repo, state)
        raise ToolError(
            f"unknown action: {action!r} (use read_file, repo_info or list_issues)"
        )

    def _require_repo(self, repo: str) -> str:
        parts = repo.split("/")
        if len(parts) != 2 or not all(parts):
            raise ToolError("repo must look like 'owner/name'")
        return repo

    def _read_file(self, repo: str, path: str, ref: str | None) -> ToolResult:
        repo = self._require_repo(repo)
        if not path:
            raise ToolError("path is required for read_file")
        quoted_path = "/".join(part for part in path.split("/") if part not in ("", ".", ".."))
        if ".." in path.split("/"):
            raise ToolError("path segments may not contain '..'")
        query = f"?ref={ref}" if ref else ""
        payload = self._get(f"/repos/{repo}/contents/{quoted_path}{query}")

        if isinstance(payload, list):
            names = [entry["name"] for entry in payload if isinstance(entry, dict)]
            return ToolResult(
                tool=self.name,
                ok=True,
                output="\n".join(names),
                data={"type": "directory", "entries": names, "path": path},
            )
        if not isinstance(payload, dict) or "content" not in payload:
            raise ToolError(f"unexpected github response for {path}")
        size = int(payload.get("size", 0))
        if size > MAX_FILE_BYTES:
            raise ToolError(f"file too large to read ({size} bytes)")
        encoding = str(payload.get("encoding", ""))
        if encoding != "base64":
            raise ToolError(f"unsupported content encoding: {encoding}")
        raw = base64.b64decode(payload.get("content", "")).decode(
            "utf-8", errors="replace"
        )
        return ToolResult(
            tool=self.name,
            ok=True,
            output=truncate(raw),
            data={"type": "file", "path": path, "bytes": size},
        )

    def _repo_info(self, repo: str) -> ToolResult:
        repo = self._require_repo(repo)
        payload = self._get(f"/repos/{repo}")
        info = {
            key: payload.get(key)
            for key in (
                "full_name",
                "description",
                "default_branch",
                "stargazers_count",
                "open_issues_count",
                "html_url",
            )
        }
        lines = [f"{key}: {value}" for key, value in info.items()]
        return ToolResult(
            tool=self.name, ok=True, output="\n".join(lines), data=info
        )

    def _list_issues(self, repo: str, state: str) -> ToolResult:
        repo = self._require_repo(repo)
        if state not in ("open", "closed", "all"):
            raise ToolError("state must be open, closed or all")
        payload = self._get(f"/repos/{repo}/issues?state={state}&per_page=30")
        if not isinstance(payload, list):
            raise ToolError("unexpected github issues response")
        issues = [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
            }
            for item in payload
            if isinstance(item, dict) and "pull_request" not in item
        ]
        lines = [f"#{i['number']} [{i['state']}] {i['title']}" for i in issues]
        return ToolResult(
            tool=self.name,
            ok=True,
            output="\n".join(lines) or "(no issues)",
            data={"count": len(issues), "issues": issues},
        )


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("message"):
            return str(body["message"])
    except ValueError:
        pass
    return response.reason_phrase or "error"
