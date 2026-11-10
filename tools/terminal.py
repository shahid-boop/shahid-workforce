"""Allowlisted, shell-free command execution for agents.

Commands are tokenized with :func:`shlex.split` and executed with
``shell=False``: the agent text is never interpreted by a shell, so no
quoting tricks can reach it. Only programs on the allowlist may run, and
obviously destructive ones are refused even if someone allowlists them.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from tools.base import BaseTool, ToolError, ToolResult, register, truncate

DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_OUTPUT_CHARS = 20_000

DEFAULT_ALLOWED: frozenset[str] = frozenset(
    {
        "git",
        "python",
        "pip",
        "pytest",
        "ruff",
        "mypy",
        "node",
        "npm",
        "ls",
        "dir",
        "cat",
        "echo",
    }
)

# Never executable, regardless of allowlist contents.
BLOCKED: frozenset[str] = frozenset(
    {
        "rm",
        "rmdir",
        "del",
        "rd",
        "mkfs",
        "format",
        "shutdown",
        "reboot",
        "reg",
        "regedit",
        "powershell",
        "pwsh",
        "cmd",
        "bash",
        "sh",
        "sudo",
    }
)


@register
class TerminalTool(BaseTool):
    """Run one allowlisted command without a shell, with a timeout."""

    name: ClassVar[str] = "terminal"
    description: ClassVar[str] = (
        "Run an allowlisted command (git, python, pytest, ruff, ...) with no "
        "shell interpretation and a hard timeout"
    )

    def __init__(
        self,
        allowed: frozenset[str] | set[str] | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: str | Path | None = None,
    ) -> None:
        self.allowed = frozenset(allowed) if allowed is not None else DEFAULT_ALLOWED
        if timeout <= 0:
            raise ToolError("timeout must be positive")
        self.timeout = timeout
        self.cwd = Path(cwd) if cwd is not None else None

    def run(self, command: str = "", **_: Any) -> ToolResult:
        """Tokenize ``command`` and execute it (no shell, hard timeout)."""
        if not command.strip():
            raise ToolError("command is required")

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ToolError(f"could not parse command: {exc}") from exc
        if not argv:
            raise ToolError("command is required")

        program = Path(argv[0]).name.lower()
        for suffix in (".exe", ".bat", ".cmd"):
            if program.endswith(suffix):
                program = program[: -len(suffix)]

        if program in BLOCKED:
            raise ToolError(f"command is blocked by policy: {program}")
        if program not in self.allowed:
            raise ToolError(
                f"command not allowlisted: {program} "
                f"(allowed: {', '.join(sorted(self.allowed))})"
            )
        if self.cwd is not None and not self.cwd.is_dir():
            raise ToolError(f"working directory does not exist: {self.cwd}")

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
            raise ToolError(
                f"command timed out after {self.timeout:g}s: {program}"
            ) from exc
        except OSError as exc:
            raise ToolError(f"could not run {program}: {exc}") from exc

        output = completed.stdout
        if completed.stderr:
            output = f"{output}\n[stderr]\n{completed.stderr}".strip()

        return ToolResult(
            tool=self.name,
            ok=completed.returncode == 0,
            output=truncate(output),
            data={
                "exit_code": completed.returncode,
                "command": program,
                "timed_out": False,
            },
        )
