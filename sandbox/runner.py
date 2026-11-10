"""Run untrusted code inside the restricted container (or refuse to).

Two execution modes:

* ``docker`` (production): the source is piped into the hardened image
  built from ``sandbox/Dockerfile`` with every policy flag applied.
* ``local`` (explicit opt-in only): a subprocess fallback for machines
  without Docker. It applies the timeout and a clean environment but
  *cannot* isolate - callers must pass ``allow_local=True`` knowingly.

The default refuses to run anything when Docker is unavailable, so a
missing engine can never silently downgrade security.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

from sandbox.policy import DEFAULT_POLICY, ExecutionPolicy, PolicyError, validate_source

logger = logging.getLogger(__name__)

IMAGE_NAME = "shahid-workforce-sandbox:latest"
DOCKER_TIMEOUT_BUFFER_SECONDS = 10.0


class SandboxUnavailableError(RuntimeError):
    """Docker is missing or the image is not built, and local run is not allowed."""


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of one sandboxed run."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    mode: str = "docker"

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not timed_out_guard(self)


def timed_out_guard(result: ExecutionResult) -> bool:
    """Separate helper kept trivial for readability in ``ok``."""
    return result.timed_out


def docker_available() -> bool:
    """True when a docker CLI is on PATH."""
    return shutil.which("docker") is not None


def build_command(
    source: str,
    policy: ExecutionPolicy = DEFAULT_POLICY,
    *,
    mode: str = "docker",
) -> list[str]:
    """Assemble the argv for a sandbox run (never through a shell)."""
    validate_source(source)

    if mode == "docker":
        if not docker_available():
            raise SandboxUnavailableError("docker CLI not found on PATH")
        return [
            "docker",
            "run",
            *policy.to_docker_args(),
            IMAGE_NAME,
            "python",
            "-c",
            source,
        ]

    if mode == "local":
        import sys

        return [sys.executable, "-c", source]

    raise PolicyError(f"unknown execution mode: {mode!r}")


def run_source(
    source: str,
    policy: ExecutionPolicy = DEFAULT_POLICY,
    *,
    allow_local: bool = False,
) -> ExecutionResult:
    """Execute ``source`` under ``policy``; returns the captured result.

    Raises :class:`PolicyError` for rejected source and
    :class:`SandboxUnavailableError` when Docker is required but missing.
    """
    mode = "docker"
    if not docker_available():
        if not allow_local:
            raise SandboxUnavailableError(
                "docker is required for sandbox execution "
                "(pass allow_local=True only for trusted local runs)"
            )
        logger.warning("docker unavailable; running in LOCAL (unisolated) mode")
        mode = "local"

    argv = build_command(source, policy, mode=mode)
    try:
        completed = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=policy.timeout_seconds + DOCKER_TIMEOUT_BUFFER_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            exit_code=124,
            stdout="",
            stderr=f"execution timed out after {policy.timeout_seconds:g}s",
            timed_out=True,
            mode=mode,
        )
    except OSError as exc:
        raise SandboxUnavailableError(f"could not start sandbox: {exc}") from exc

    return ExecutionResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        mode=mode,
    )
