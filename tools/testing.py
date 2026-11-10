"""Run the test suite and summarise results for an agent.

Shells out to ``python -m pytest`` (allowlisted by the terminal tool's
policy anyway) with a hard timeout and returns pass/fail counts plus a
trimmed failure summary, so a QA agent can act on real results.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

from tools.base import BaseTool, ToolError, ToolResult, register, truncate

DEFAULT_TIMEOUT_SECONDS = 300.0
SUMMARY_PATTERN = re.compile(
    r"=+ (?P<summary>.+?) =+\s*$", re.MULTILINE | re.DOTALL
)
COUNT_PATTERN = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")


def parse_summary(output: str) -> dict[str, int]:
    """Extract pass/fail/error/skip counts from pytest output."""
    counts: dict[str, int] = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    matches = COUNT_PATTERN.findall(output)
    for value, label in matches:
        key = "errors" if label in ("error", "errors") else label
        counts[key] += int(value)
    return counts


def _tail(output: str, lines: int = 30) -> str:
    """Last ``lines`` non-empty lines - typically failures and summary."""
    kept = [line for line in output.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


@register
class TestingTool(BaseTool):
    """Run pytest on a path and return counts plus a failure summary."""

    name: ClassVar[str] = "testing"
    description: ClassVar[str] = (
        "Run the pytest suite (optionally on a specific path) and get pass/"
        "fail counts with a failure summary"
    )
    __test__ = False  # not a pytest test class despite the name

    def __init__(
        self,
        *,
        cwd: str | Path | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        python: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ToolError("timeout must be positive")
        self.cwd = Path(cwd) if cwd is not None else None
        self.timeout = timeout
        self.python = python or sys.executable

    def run(self, path: str = "", extra_args: tuple[str, ...] = (), **_: Any) -> ToolResult:
        """Run ``pytest`` and summarise the outcome."""
        if self.cwd is not None and not self.cwd.is_dir():
            raise ToolError(f"working directory does not exist: {self.cwd}")

        argv = [self.python, "-m", "pytest", "-q", "--no-header"]
        if path:
            argv.append(path)
        argv.extend(extra_args)

        try:
            completed = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.cwd) if self.cwd else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"pytest timed out after {self.timeout:g}s") from exc
        except OSError as exc:
            raise ToolError(f"could not run pytest: {exc}") from exc

        combined = f"{completed.stdout}\n{completed.stderr}".strip()
        counts = parse_summary(combined)
        passed = counts["passed"]
        failed = counts["failed"] + counts["errors"]
        ok = completed.returncode == 0 and failed == 0

        summary_match = SUMMARY_PATTERN.search(combined)
        summary = summary_match.group("summary").strip() if summary_match else ""

        return ToolResult(
            tool=self.name,
            ok=ok,
            output=truncate(
                f"{summary or 'no summary'}\n\n{_tail(combined)}".strip()
            ),
            data={
                "exit_code": completed.returncode,
                "counts": counts,
                "passed": passed,
                "failed": failed,
            },
        )
