"""Execution policy for agent-generated code.

The policy is the single source of truth for how untrusted code runs:
container flags, resource limits and the wall-clock timeout. It renders to
``docker run`` arguments (:func:`to_docker_args`) so the runner and the
tests share exactly one definition of "restricted".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Numeric ceilings - a policy may never exceed these, whatever the caller asks.
MAX_MEMORY_MB = 4096
MAX_TIMEOUT_SECONDS = 600.0
MAX_CPU = 8.0
MAX_PIDS = 512


class PolicyError(RuntimeError):
    """The requested execution violates the sandbox policy."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Hardened settings applied to every sandbox run."""

    memory_mb: int = 256
    cpu_seconds: float = 1.0
    timeout_seconds: float = 30.0
    max_pids: int = 64
    network: bool = False  # no network by default
    read_only_root: bool = True
    user: str = "65534:65534"  # nobody:nogroup
    workdir: str = "/work"
    allowed_imports: tuple[str, ...] = (
        "json",
        "re",
        "math",
        "itertools",
        "collections",
        "functools",
        "statistics",
        "textwrap",
        "string",
        "datetime",
        "typing",
        "dataclasses",
    )

    def __post_init__(self) -> None:
        if self.memory_mb <= 0 or self.memory_mb > MAX_MEMORY_MB:
            raise PolicyError(f"memory_mb must be in 1..{MAX_MEMORY_MB}")
        if self.timeout_seconds <= 0 or self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise PolicyError(f"timeout_seconds must be in 1..{MAX_TIMEOUT_SECONDS}")
        if self.cpu_seconds <= 0 or self.cpu_seconds > MAX_CPU:
            raise PolicyError(f"cpu_seconds must be in 0..{MAX_CPU}")
        if self.max_pids <= 0 or self.max_pids > MAX_PIDS:
            raise PolicyError(f"max_pids must be in 1..{MAX_PIDS}")

    def to_docker_args(self) -> list[str]:
        """Render the restriction flags for ``docker run``."""
        args = [
            "--rm",
            "--network", "none" if not self.network else "bridge",
            "--read-only" if self.read_only_root else "--read-write",
            "--tmpfs", "/tmp:noexec,nosuid,size=64m",
            "--user", self.user,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(self.max_pids),
            "--memory", f"{self.memory_mb}m",
            "--memory-swap", f"{self.memory_mb}m",
            "--cpus", str(self.cpu_seconds),
            "--workdir", self.workdir,
        ]
        return args


DEFAULT_POLICY = ExecutionPolicy()


# Obvious exfiltration / privilege probes in submitted *source*. This is a
# cheap pre-filter - the container isolation is the real boundary.
_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("subprocess/os system call", re.compile(r"\b(os\.system|subprocess|popen)\b")),
    ("file system escape", re.compile(r"\b(shutil\.rmtree|/etc/passwd|~\/)\b")),
    ("network call", re.compile(r"\b(requests\.|urllib\.|socket\.|http\.client)\b")),
    ("dynamic import", re.compile(r"\b__import__\s*\(|importlib\b")),
    ("private key material", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


def validate_source(source: str) -> str:
    """Reject source that obviously tries to escape the sandbox.

    Returns the normalised source; raises :class:`PolicyError` with the
    matched category (never echoing the offending snippet back).
    """
    if not source or not source.strip():
        raise PolicyError("empty source")
    if len(source) > 100_000:
        raise PolicyError("source exceeds 100000 characters")

    for label, pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(source):
            raise PolicyError(f"source rejected: {label} is not allowed")
    return source
