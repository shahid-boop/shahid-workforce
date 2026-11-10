"""Tests for the infrastructure definitions.

These validate the *shape* of the deployment files without needing Docker:
compose services, required environment plumbing, Dockerfile hygiene and the
monitoring configs must parse and follow the security rules of the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA = REPO_ROOT / "infrastructure"


@pytest.fixture(scope="module")
def compose() -> dict:
    with (INFRA / "docker-compose.yml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


# ------------------------------------------------------------------- compose


def test_compose_has_all_services(compose: dict) -> None:
    services = compose["services"]
    assert set(services) == {"api", "worker", "redis", "dashboard"}


def test_api_key_is_required_not_defaulted(compose: dict) -> None:
    """No service may run with a baked-in API key."""
    for name, service in compose["services"].items():
        env = service.get("environment", {})
        if "WORKFORCE_API_KEY" in env:
            value = str(env["WORKFORCE_API_KEY"])
            assert "change-me" not in value
            assert "${WORKFORCE_API_KEY" in value, name
            assert ":?" in value, f"{name} must fail closed without a key"


def test_services_declare_healthchecks_or_dependencies(compose: dict) -> None:
    services = compose["services"]
    assert "healthcheck" in services["api"]
    assert "healthcheck" in services["redis"]
    assert services["worker"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert services["dashboard"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_redis_is_not_exposed_to_the_host(compose: dict) -> None:
    redis = compose["services"]["redis"]
    assert "ports" not in redis, "redis must stay on the internal network only"


def test_api_port_not_published(compose: dict) -> None:
    """Only the dashboard reaches the host; the API stays internal."""
    assert "ports" not in compose["services"]["api"]
    assert "ports" not in compose["services"]["worker"]


def test_worker_runs_the_worker_module(compose: dict) -> None:
    command = compose["services"]["worker"]["command"]
    assert "services.workers.task_worker" in " ".join(command)


# --------------------------------------------------------------- Dockerfiles


def test_api_dockerfile_runs_as_non_root() -> None:
    text = (INFRA / "api.Dockerfile").read_text(encoding="utf-8")
    assert "USER appuser" in text
    assert "USER root" not in text.split("USER appuser")[-1]


def test_api_dockerfile_uses_module_uvicorn() -> None:
    """The .exe console wrapper pattern must not be used in containers either."""
    text = (INFRA / "api.Dockerfile").read_text(encoding="utf-8")
    assert "python\", \"-m\", \"uvicorn" in text


def test_dashboard_dockerfile_does_not_bake_in_api_key() -> None:
    text = (INFRA / "dashboard.Dockerfile").read_text(encoding="utf-8")
    assert "WORKFORCE_API_KEY=" not in text


# ------------------------------------------------------- env + monitoring


def test_env_example_lists_required_variables() -> None:
    text = (INFRA / ".env.example").read_text(encoding="utf-8")
    for key in (
        "WORKFORCE_ENV",
        "WORKFORCE_API_KEY",
        "WORKFORCE_DATABASE_URL",
        "WORKFORCE_CORS_ORIGINS",
    ):
        assert key in text


def test_prometheus_config_parses() -> None:
    with (INFRA / "monitoring" / "prometheus.yml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    jobs = {job["job_name"] for job in data["scrape_configs"]}
    assert jobs == {"workforce-api", "redis"}
    assert data["global"]["scrape_interval"] == "15s"


def test_alerts_cover_api_and_redis() -> None:
    with (INFRA / "monitoring" / "alerts.yml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    names = {rule["alert"] for group in data["groups"] for rule in group["rules"]}
    assert {"ApiDown", "RedisDown", "HighErrorRate"} <= names
    for group in data["groups"]:
        for rule in group["rules"]:
            assert "severity" in rule["labels"]
            assert rule["annotations"]["summary"]


def test_logging_config_is_valid_json() -> None:
    data = json.loads((INFRA / "logging.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["root"]["level"] == "INFO"
