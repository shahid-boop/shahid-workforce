"""Tests for the allowlisted agent tools."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine

from tools import (
    BaseTool,
    ToolError,
    ToolNotFoundError,
    create_tool,
    tool_names,
    tool_specs,
)
from tools.browser import BrowserTool, html_to_text
from tools.database import DatabaseTool, validate_read_only
from tools.filesystem import FileSystemTool
from tools.github import GitHubTool
from tools.terminal import TerminalTool
from tools.testing import TestingTool, parse_summary

# --- registry ---------------------------------------------------------------


def test_all_six_tools_registered() -> None:
    assert tool_names() == (
        "browser",
        "database",
        "filesystem",
        "github",
        "terminal",
        "testing",
    )


def test_tool_specs_describe_every_tool() -> None:
    specs = tool_specs()
    assert len(specs) == 6
    for spec in specs:
        assert spec["name"]
        assert len(spec["description"]) > 20


def test_create_tool_unknown_name_raises() -> None:
    with pytest.raises(ToolNotFoundError, match="unknown tool"):
        create_tool("teleport")


def test_every_tool_is_a_basetool() -> None:
    config = {"database": {"database_url": "sqlite:///:memory:"}}
    for name in tool_names():
        assert isinstance(create_tool(name, **config.get(name, {})), BaseTool)


# --- filesystem -------------------------------------------------------------


def test_filesystem_write_read_roundtrip(tmp_path: Path) -> None:
    tool = FileSystemTool(root=tmp_path)
    written = tool.run(action="write", path="a/b.txt", content="hello")
    assert written.ok

    read = tool.run(action="read", path="a/b.txt")
    assert read.output == "hello"
    assert read.data["bytes"] == 5


def test_filesystem_list(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "two.txt").write_text("2", encoding="utf-8")
    result = FileSystemTool(root=tmp_path).run(action="list", path=".")
    assert result.output == "one.txt\ntwo.txt"
    assert result.data["count"] == 2


def test_filesystem_rejects_traversal(tmp_path: Path) -> None:
    tool = FileSystemTool(root=tmp_path / "jail")
    (tmp_path / "jail").mkdir()
    with pytest.raises(ToolError, match="escapes the workspace root"):
        tool.run(action="read", path="../secret.txt")


def test_filesystem_rejects_absolute_paths(tmp_path: Path) -> None:
    tool = FileSystemTool(root=tmp_path)
    with pytest.raises(ToolError, match="absolute paths"):
        tool.run(action="read", path="C:\\Windows\\win.ini" if _is_windows() else "/etc/passwd")


def test_filesystem_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="file not found"):
        FileSystemTool(root=tmp_path).run(action="read", path="nope.txt")


def test_filesystem_unknown_action_raises(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="unknown action"):
        FileSystemTool(root=tmp_path).run(action="delete", path="x")


def _is_windows() -> bool:
    return Path("/").anchor == "\\"


# --- terminal ---------------------------------------------------------------


def test_terminal_runs_allowlisted_command() -> None:
    result = TerminalTool().run(command='python -c "print(1234)"')
    assert result.ok
    assert "1234" in result.output
    assert result.data["exit_code"] == 0


def test_terminal_rejects_non_allowlisted_command() -> None:
    with pytest.raises(ToolError, match="not allowlisted"):
        TerminalTool().run(command="curl https://example.com")


def test_terminal_blocked_command_even_if_allowlisted() -> None:
    tool = TerminalTool(allowed={"rm", "python"})
    with pytest.raises(ToolError, match="blocked by policy"):
        tool.run(command="rm -rf /")


def test_terminal_nonzero_exit_is_not_ok() -> None:
    result = TerminalTool().run(command='python -c "raise SystemExit(3)"')
    assert result.ok is False
    assert result.data["exit_code"] == 3


def test_terminal_timeout_raises() -> None:
    tool = TerminalTool(timeout=0.2)
    with pytest.raises(ToolError, match="timed out"):
        tool.run(command='python -c "import time; time.sleep(5)"')


def test_terminal_empty_command_raises() -> None:
    with pytest.raises(ToolError, match="command is required"):
        TerminalTool().run(command="   ")


def test_terminal_rejects_unparseable_command() -> None:
    with pytest.raises(ToolError, match="could not parse"):
        TerminalTool().run(command='python -c "unterminated')


def test_terminal_rejects_non_positive_timeout() -> None:
    with pytest.raises(ToolError, match="positive"):
        TerminalTool(timeout=0)


# --- database ---------------------------------------------------------------


def _seed_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tool.db'}", future=True)
    from sqlalchemy import text as sql

    with engine.begin() as conn:
        conn.execute(sql("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(sql("INSERT INTO t (name) VALUES ('alpha')"))
        conn.execute(sql("INSERT INTO t (name) VALUES ('beta')"))
        conn.execute(sql("INSERT INTO t (name) VALUES ('gamma')"))
    return engine


def test_database_select_returns_rows(tmp_path: Path) -> None:
    tool = DatabaseTool(engine=_seed_engine(tmp_path))
    result = tool.run(query="SELECT id, name FROM t ORDER BY id")
    assert result.ok
    assert result.data["columns"] == ["id", "name"]
    assert [row["name"] for row in result.data["rows"]] == ["alpha", "beta", "gamma"]
    assert "alpha" in result.output


def test_database_limit_clamps_rows(tmp_path: Path) -> None:
    tool = DatabaseTool(engine=_seed_engine(tmp_path))
    result = tool.run(query="SELECT name FROM t", limit=2)
    assert result.data["count"] == 2


def test_database_rejects_writes(tmp_path: Path) -> None:
    tool = DatabaseTool(engine=_seed_engine(tmp_path))
    with pytest.raises(ToolError, match="read-only"):
        tool.run(query="DELETE FROM t")
    with pytest.raises(ToolError, match="read-only"):
        tool.run(query="DROP TABLE t")


def test_database_rejects_multiple_statements(tmp_path: Path) -> None:
    tool = DatabaseTool(engine=_seed_engine(tmp_path))
    with pytest.raises(ToolError, match="single statement"):
        tool.run(query="SELECT 1; DROP TABLE t")


def test_database_invalid_sql_becomes_tool_error(tmp_path: Path) -> None:
    tool = DatabaseTool(engine=_seed_engine(tmp_path))
    with pytest.raises(ToolError, match="query failed"):
        tool.run(query="SELECT * FROM missing_table")


def test_validate_read_only_accepts_with() -> None:
    assert validate_read_only("  WITH x AS (SELECT 1) SELECT * FROM x; ") == (
        "WITH x AS (SELECT 1) SELECT * FROM x"
    )


def test_database_requires_engine_or_url() -> None:
    with pytest.raises(ToolError, match="engine or a database_url"):
        DatabaseTool()


# --- testing ----------------------------------------------------------------


def test_parse_summary_counts() -> None:
    counts = parse_summary(".....F\n3 passed, 1 failed, 2 skipped in 0.5s")
    assert counts == {"passed": 3, "failed": 1, "errors": 0, "skipped": 2}


def test_parse_summary_counts_errors_word() -> None:
    counts = parse_summary("2 errors, 1 passed in 0.1s")
    assert counts["errors"] == 2
    assert counts["passed"] == 1


def test_testing_tool_runs_real_pytest(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n"
        "def test_bad():\n    assert 1 + 1 == 3\n",
        encoding="utf-8",
    )
    tool = TestingTool(cwd=tmp_path, timeout=60)
    result = tool.run(path="test_sample.py")

    assert result.ok is False
    assert result.data["exit_code"] == 1
    assert result.data["counts"]["passed"] == 1
    assert result.data["counts"]["failed"] == 1
    assert result.data["failed"] == 1


def test_testing_tool_all_green_is_ok(tmp_path: Path) -> None:
    (tmp_path / "test_green.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    result = TestingTool(cwd=tmp_path, timeout=60).run(path="test_green.py")
    assert result.ok is True
    assert result.data["counts"]["passed"] == 1
    assert result.data["failed"] == 0


def test_testing_tool_rejects_bad_timeout(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="positive"):
        TestingTool(timeout=0)


# --- github -----------------------------------------------------------------


def make_github(handler, token: str = "ghs_secret_token") -> GitHubTool:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GitHubTool(token=token, client=client, api_base="https://api.github.test")


def test_github_read_file_decodes_base64() -> None:
    import base64

    content = base64.b64encode(b"# hello from repo").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer ghs_secret_token"
        return httpx.Response(
            200,
            json={"content": content, "encoding": "base64", "size": 17},
        )

    tool = make_github(handler)
    result = tool.run(action="read_file", repo="acme/widgets", path="README.md")
    assert result.ok
    assert result.output == "# hello from repo"
    assert result.data["type"] == "file"


def test_github_read_file_list_directory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"name": "a.py"}, {"name": "b.py"}],
        )

    tool = make_github(handler)
    result = tool.run(action="read_file", repo="acme/widgets", path="src")
    assert result.data["type"] == "directory"
    assert result.data["entries"] == ["a.py", "b.py"]


def test_github_rejects_bad_repo_shape() -> None:
    tool = make_github(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ToolError, match="owner/name"):
        tool.run(action="repo_info", repo="not-a-repo")


def test_github_error_message_scrubs_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials ghs_secret_token"})

    tool = make_github(handler)
    with pytest.raises(ToolError) as exc:
        tool.run(action="repo_info", repo="acme/widgets")
    assert "ghs_secret_token" not in str(exc.value)
    assert "401" in str(exc.value)


def test_github_list_issues_skips_pull_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"number": 1, "title": "Bug", "state": "open", "html_url": "u1"},
                {
                    "number": 2,
                    "title": "A PR",
                    "state": "open",
                    "pull_request": {},
                },
            ],
        )

    tool = make_github(handler)
    result = tool.run(action="list_issues", repo="acme/widgets")
    assert result.data["count"] == 1
    assert "#1 [open] Bug" in result.output


def test_github_unknown_action_raises() -> None:
    tool = make_github(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ToolError, match="unknown action"):
        tool.run(action="delete_everything", repo="acme/widgets")


def test_github_path_traversal_rejected() -> None:
    tool = make_github(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ToolError, match="may not contain"):
        tool.run(action="read_file", repo="acme/widgets", path="a/../../b")


# --- browser ----------------------------------------------------------------


def test_browser_fetches_title_and_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Example &amp; Co</title>"
                "<script>evil()</script></head>"
                "<body><h1>Headline</h1><p>Some   text.</p></body></html>"
            ),
        )

    tool = BrowserTool(client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = tool.run(url="https://example.com/page")
    assert result.ok
    assert result.data["title"] == "Example & Co"
    assert "Headline" in result.output
    assert "Some text." in result.output
    assert "evil" not in result.output


def test_browser_rejects_non_http_schemes() -> None:
    tool = BrowserTool(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    for bad in ("ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", "not a url"):
        with pytest.raises(ToolError, match="http"):
            tool.run(url=bad)


def test_browser_http_error_status_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    tool = BrowserTool(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ToolError, match="404"):
        tool.run(url="https://example.com/missing")


def test_browser_unsupported_content_type_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    tool = BrowserTool(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ToolError, match="content-type"):
        tool.run(url="https://example.com/file.pdf")


def test_html_to_text_strips_styles_and_unescapes() -> None:
    html = "<style>.x{}</style><p>Bread &amp; butter</p>"
    assert html_to_text(html) == "Bread & butter"
