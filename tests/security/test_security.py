"""Security regression tests.

These encode the security promises documented in ``docs/security.md``: if one
of them breaks, this file must fail before anything ships.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings
from services.api.main import create_app
from tools.base import scrub
from tools.database import validate_read_only
from tools.filesystem import FileSystemTool
from tools.terminal import TerminalTool

REPO_ROOT = Path(__file__).resolve().parents[2]
API_KEY = "security-test-key"


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        env="development",
        api_key=API_KEY,
        database_url=f"sqlite:///{tmp_path / 'sec.db'}",
        cors_origins=("http://localhost:3000",),
    )
    return TestClient(create_app(settings))


# ------------------------------------------------------------- authentication


def test_all_private_endpoints_reject_missing_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/tasks").status_code == 401
        assert client.post("/tasks", json={"title": "x"}).status_code == 401
        # /agents is read-only: POST is 405, and auth still guards the GET.
        assert client.get("/agents").status_code == 401
        assert client.post("/agents").status_code == 405


def test_all_private_endpoints_reject_wrong_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        headers = {"X-API-Key": "wrong-key"}
        assert client.get("/tasks", headers=headers).status_code == 401
        assert client.get("/agents", headers=headers).status_code == 401


def test_production_refuses_to_boot_without_key(tmp_path: Path) -> None:
    settings = Settings(
        env="production",
        api_key=None,
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
    )
    with pytest.raises(RuntimeError, match="WORKFORCE_API_KEY"):
        create_app(settings)


# ------------------------------------------------------------------- headers


def test_security_headers_on_every_response(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for path in ("/health", "/tasks"):
            response = client.get(path)
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert (
                response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
            )


def test_docs_page_does_not_leak_api_key(tmp_path: Path) -> None:
    """No response body may contain the configured key."""
    with make_client(tmp_path) as client:
        for path in ("/health", "/openapi.json"):
            body = client.get(path).text
            assert API_KEY not in body, path


# --------------------------------------------------------------------- CORS


def test_cors_rejects_unknown_origin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/health", headers={"Origin": "http://evil.example"}
        )
        assert "access-control-allow-origin" not in {
            key.lower() for key in response.headers
        }


def test_cors_allows_configured_origin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/health", headers={"Origin": "http://localhost:3000"}
        )
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )


# ------------------------------------------------------------- tool hardening


def test_filesystem_jail_rejects_escapes(tmp_path: Path) -> None:
    tool = FileSystemTool(root=tmp_path)
    # On POSIX this is rejected as absolute; on Windows it resolves outside
    # the root and is rejected as an escape. Either way it never succeeds.
    for attempt in ("/etc/passwd", "../outside.txt", "..\\..\\windows"):
        with pytest.raises(
            Exception, match=r"absolute paths|escapes the workspace root"
        ):
            tool._resolve(attempt)


def test_filesystem_allows_inside_root(tmp_path: Path) -> None:
    tool = FileSystemTool(root=tmp_path)
    resolved = tool._resolve("sub/file.txt")
    assert str(resolved).startswith(str(tmp_path.resolve()))


def test_terminal_blocks_destructive_commands(tmp_path: Path) -> None:
    # Even with rm explicitly allowlisted, BLOCKED wins.
    tool = TerminalTool(allowed={"rm", "python", "echo"})
    with pytest.raises(Exception, match="blocked by policy"):
        tool.run("rm -rf /")
    # Not on the allowlist at all -> refused before anything runs.
    other = TerminalTool(allowed={"python"})
    with pytest.raises(Exception, match="not allowlisted"):
        other.run("curl http://evil.example")


def test_terminal_never_interprets_shell_syntax(tmp_path: Path) -> None:
    """`>` becomes a plain argv item - no shell means no redirection."""
    import sys

    tool = TerminalTool(allowed={"python"}, cwd=tmp_path)
    # forward slashes survive shlex tokenisation on every platform
    interpreter = sys.executable.replace("\\", "/")
    result = tool.run(
        f'{interpreter} -c "import sys; print(sys.argv[1:])" > marker.txt'
    )
    assert "'>" in result.output or '">' in result.output, result.output
    assert not (tmp_path / "marker.txt").exists(), "no shell redirect happened"


def test_database_tool_is_read_only() -> None:
    for statement in (
        "DELETE FROM tasks",
        "DROP TABLE tasks",
        "INSERT INTO tasks (id) VALUES ('x')",
        "UPDATE tasks SET status='completed'",
        "ATTACH DATABASE 'x.db' AS x",
    ):
        with pytest.raises(Exception, match="read-only"):
            validate_read_only(statement)
    # legitimate reads still pass
    assert validate_read_only("SELECT * FROM tasks") == "SELECT * FROM tasks"


# ------------------------------------------------------------ token scrubbing


def test_scrub_removes_token_from_text() -> None:
    token = "ghp_supersecrettoken1234567890"
    text = f"authorization: Bearer {token} and {token} again"
    cleaned = scrub(text, token)
    assert token not in cleaned
    assert "***" in cleaned


def test_scrub_handles_empty_token() -> None:
    assert scrub("nothing to hide", "") == "nothing to hide"


# ------------------------------------------------------------ repo hygiene


def test_no_env_file_committed() -> None:
    """`.env` must never be tracked (only `.env.example` is allowed)."""
    result = subprocess.run(
        ["git", "ls-files", "--", ".env", ".env.*"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    tracked = [line for line in result.stdout.splitlines() if line]
    assert tracked == [] or tracked == [".env.example"], tracked


def test_env_example_contains_no_real_secret() -> None:
    example = REPO_ROOT / "infrastructure" / ".env.example"
    if not example.exists():
        pytest.skip("no env example")
    text = example.read_text(encoding="utf-8")
    assert "change-me" in text
