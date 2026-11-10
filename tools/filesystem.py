"""Sandboxed file operations confined to a configured root directory.

Every path is resolved and checked against the root: absolute paths and
``..`` traversal outside the root are rejected before any I/O happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from tools.base import BaseTool, ToolError, ToolResult, register, truncate

MAX_READ_CHARS = 200_000


@register
class FileSystemTool(BaseTool):
    """Read, write and list files inside a jail rooted at one directory."""

    name: ClassVar[str] = "filesystem"
    description: ClassVar[str] = (
        "Read, write or list files inside the workspace (paths are confined "
        "to a single root directory)"
    )

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        """Resolve ``path`` under the root, rejecting any escape."""
        if not path or not str(path).strip():
            raise ToolError("path is required")
        candidate = Path(path)
        if candidate.is_absolute():
            raise ToolError("absolute paths are not allowed")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ToolError(f"path escapes the workspace root: {path}")
        return resolved

    def run(
        self,
        action: str = "read",
        path: str = "",
        content: str | None = None,
        **_: Any,
    ) -> ToolResult:
        """Dispatch to ``read``, ``write`` or ``list``."""
        target = self._resolve(path)

        if action == "read":
            if not target.is_file():
                raise ToolError(f"file not found: {path}")
            text = target.read_text(encoding="utf-8", errors="replace")
            return ToolResult(
                tool=self.name,
                ok=True,
                output=truncate(text),
                data={"path": path, "bytes": target.stat().st_size},
            )

        if action == "write":
            if content is None:
                raise ToolError("content is required for write")
            if len(content) > MAX_READ_CHARS:
                raise ToolError(
                    f"content exceeds {MAX_READ_CHARS} characters"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(
                tool=self.name,
                ok=True,
                output=f"wrote {len(content)} chars to {path}",
                data={"path": path, "chars": len(content)},
            )

        if action == "list":
            if not target.is_dir():
                raise ToolError(f"directory not found: {path}")
            entries = sorted(child.name for child in target.iterdir())
            listing = "\n".join(entries)
            return ToolResult(
                tool=self.name,
                ok=True,
                output=truncate(listing),
                data={"path": path, "count": len(entries)},
            )

        raise ToolError(f"unknown action: {action!r} (use read, write or list)")
