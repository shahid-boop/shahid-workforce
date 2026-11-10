"""Tests for the documentation set.

Docs must exist, be non-trivial and the README must link to them - a broken
or deleted doc counts as a regression.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

EXPECTED_DOCS = (
    "architecture.md",
    "setup.md",
    "security.md",
    "deployment.md",
    "agents.md",
)


def test_all_expected_docs_exist_and_are_substantial() -> None:
    for name in EXPECTED_DOCS:
        path = DOCS / name
        assert path.exists(), f"missing doc: docs/{name}"
        text = path.read_text(encoding="utf-8")
        assert len(text) > 500, f"docs/{name} looks like a stub"
        assert text.startswith("# "), f"docs/{name} must start with a heading"
        # The old placeholder banner must not survive.
        assert "Skeleton document" not in text, name


def test_no_skeleton_banners_left_in_docs() -> None:
    for path in DOCS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "Skeleton document" not in text, path.name
        assert "TODO" not in text, f"{path.name} still contains TODO"


def test_readme_links_to_setup_and_docs() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/setup.md" in readme
    for name in EXPECTED_DOCS:
        # every doc should be referenced somewhere in the README or docs
        assert (DOCS / name).exists()


def test_security_doc_covers_api_key_and_sandbox() -> None:
    text = (DOCS / "security.md").read_text(encoding="utf-8")
    for topic in (
        "WORKFORCE_API_KEY",
        "fails closed",
        "--network none",
        "--cap-drop",
        "allow_local",
        "read-only",
    ):
        assert topic in text, f"security.md must mention {topic}"


def test_setup_doc_covers_api_and_dashboard() -> None:
    text = (DOCS / "setup.md").read_text(encoding="utf-8")
    for topic in (
        "uvicorn",
        "WORKFORCE_API_KEY",
        "npm",
        "alembic upgrade head",
        "pytest",
    ):
        assert topic in text, f"setup.md must mention {topic}"


def test_deployment_doc_covers_compose_and_monitoring() -> None:
    text = (DOCS / "deployment.md").read_text(encoding="utf-8")
    for topic in (
        "docker compose up",
        "WORKFORCE_API_KEY",
        "alembic downgrade",
        "alerts.yml",
        "/health",
    ):
        assert topic in text, f"deployment.md must mention {topic}"
