"""Tests for the sandbox execution policy and runner.

Docker itself is not required: command construction, source validation and
the local-mode opt-in are all tested without launching a container.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from sandbox.policy import DEFAULT_POLICY, ExecutionPolicy, PolicyError, validate_source
from sandbox.runner import (
    ExecutionResult,
    SandboxUnavailableError,
    build_command,
    docker_available,
    run_source,
)

# --------------------------------------------------------------------- policy


def test_default_policy_is_restricted() -> None:
    args = DEFAULT_POLICY.to_docker_args()
    joined = " ".join(args)
    assert "--network none" in joined
    assert "--read-only" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "--rm" in args
    assert "--user" in args
    assert "65534:65534" in args
    assert "--pids-limit" in args
    assert "--memory" in args


def test_policy_rejects_oversized_memory() -> None:
    with pytest.raises(PolicyError, match="memory_mb"):
        ExecutionPolicy(memory_mb=999_999)


def test_policy_rejects_negative_timeout() -> None:
    with pytest.raises(PolicyError, match="timeout_seconds"):
        ExecutionPolicy(timeout_seconds=0)


def test_policy_rejects_excessive_pids() -> None:
    with pytest.raises(PolicyError, match="max_pids"):
        ExecutionPolicy(max_pids=100_000)


def test_policy_allows_network_only_when_asked() -> None:
    open_net = ExecutionPolicy(network=True)
    assert "--network bridge" in " ".join(open_net.to_docker_args())


# -------------------------------------------------------------- source filter


def test_validate_source_accepts_benign_code() -> None:
    source = "import json\nprint(json.dumps({'ok': True}))\n"
    assert validate_source(source) == source


def test_validate_source_rejects_subprocess() -> None:
    with pytest.raises(PolicyError, match="system call"):
        validate_source("import subprocess; subprocess.run(['id'])")


def test_validate_source_rejects_network_modules() -> None:
    with pytest.raises(PolicyError, match="network call"):
        validate_source("import urllib.request\nurllib.request.urlopen('http://x')")


def test_validate_source_rejects_dynamic_import() -> None:
    with pytest.raises(PolicyError, match="dynamic import"):
        validate_source("__import__('os').system('id')")


def test_validate_source_rejects_private_keys() -> None:
    with pytest.raises(PolicyError, match="private key material"):
        validate_source("-----BEGIN PRIVATE KEY-----\nsecret\n")


def test_validate_source_rejects_empty_and_oversized() -> None:
    with pytest.raises(PolicyError, match="empty"):
        validate_source("   \n  ")
    with pytest.raises(PolicyError, match="100000"):
        validate_source("x" * 200_000)


# ------------------------------------------------------------------- commands


def test_build_command_docker_includes_policy_flags() -> None:
    """build_command refuses without docker unless we monkeypatch availability."""
    if not docker_available():
        pytest.skip("docker CLI not installed on this machine")

    argv = build_command("print(1)")
    assert argv[0] == "docker"
    assert argv[1] == "run"
    assert "--network" in argv
    assert argv[-3:-1] == ["-c"] or "python" in argv


def test_build_command_requires_docker_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    with pytest.raises(SandboxUnavailableError, match="docker CLI not found"):
        build_command("print(1)")


def test_build_command_local_mode_uses_sys_executable() -> None:
    argv = build_command("print(1)", mode="local")
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-c", "print(1)"]


def test_build_command_rejects_unknown_mode() -> None:
    with pytest.raises(PolicyError, match="unknown execution mode"):
        build_command("print(1)", mode="telepathy")


def test_build_command_rejects_bad_source_before_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: True)
    with pytest.raises(PolicyError, match="system call"):
        build_command("import subprocess")


# --------------------------------------------------------------- local runner


def test_run_source_refuses_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    with pytest.raises(SandboxUnavailableError, match="docker is required"):
        run_source("print(1)")


def test_run_source_local_optin_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    result = run_source("print('hello-sandbox')", allow_local=True)
    assert isinstance(result, ExecutionResult)
    assert result.mode == "local"
    assert result.exit_code == 0
    assert "hello-sandbox" in result.stdout
    assert result.ok


def test_run_source_local_captures_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    result = run_source("raise SystemExit(3)", allow_local=True)
    assert result.exit_code == 3
    assert not result.ok


def test_run_source_local_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    policy = ExecutionPolicy(timeout_seconds=1)
    result = run_source("import time; time.sleep(30)", policy, allow_local=True)
    assert result.timed_out
    assert result.exit_code == 124
    assert not result.ok


def test_local_mode_never_spawns_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """The argv is fixed - even source containing shell metacharacters is safe."""
    monkeypatch.setattr("sandbox.runner.docker_available", lambda: False)
    seen: list[list[str]] = []
    real_run = subprocess.run

    def spy(argv, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr("sandbox.runner.subprocess.run", spy)
    run_source("print('a | b & c')", allow_local=True)
    assert len(seen) == 1
    assert kwargs_shell_free(seen[0])


def kwargs_shell_free(argv: list[str]) -> bool:
    return argv[0] == sys.executable and argv[1] == "-c"
