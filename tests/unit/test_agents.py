"""Tests for the agent registry and base agent behaviour."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agents.base_agent import AgentContext, TemplateAgent, make_agent
from agents.registry import (
    AgentRegistryError,
    agent_ids,
    get_agent,
    load_agents,
)

EXPECTED_IDS = (
    "chief_ai_officer",
    "system_architect",
    "ui_ux_designer",
    "frontend_engineer",
    "backend_engineer",
    "database_engineer",
    "api_integrator",
    "security_engineer",
    "qa_engineer",
    "code_reviewer",
    "devops_engineer",
    "automation_engineer",
    "research_agent",
    "project_manager",
    "documentation_engineer",
)


def test_load_agents_returns_all_fifteen() -> None:
    agents = load_agents()
    assert len(agents) == 15


def test_agent_ids_match_expected_order() -> None:
    assert agent_ids() == EXPECTED_IDS


def test_ids_are_unique() -> None:
    ids = agent_ids()
    assert len(set(ids)) == len(ids)


def test_every_prompt_file_exists_and_is_non_empty() -> None:
    for definition in load_agents():
        assert definition.prompt_path.exists(), definition.id
        assert definition.prompt.strip(), definition.id


def test_prompt_contains_role_metadata() -> None:
    chief = get_agent("chief_ai_officer")
    prompt = chief.prompt
    assert "# Chief AI Officer" in prompt
    assert "decompose goals" in prompt


def test_model_defaults_to_none() -> None:
    for definition in load_agents():
        assert definition.model is None


def test_departments_are_assigned() -> None:
    departments = {d.id: d.department for d in load_agents()}
    assert departments["chief_ai_officer"] == "Leadership"
    assert departments["security_engineer"] == "Quality & Security"
    assert departments["research_agent"] == "Intelligence"


def test_get_agent_unknown_id_raises() -> None:
    with pytest.raises(AgentRegistryError, match="unknown agent id"):
        get_agent("does_not_exist")


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(AgentRegistryError, match="config not found"):
        load_agents(tmp_path / "nope.yaml")


def test_config_without_agents_list_raises(tmp_path: Path) -> None:
    config = tmp_path / "agents.yaml"
    config.write_text("agents: not-a-list\n", encoding="utf-8")
    with pytest.raises(AgentRegistryError, match="'agents' list"):
        load_agents(config)


def test_duplicate_ids_raise(tmp_path: Path) -> None:
    config = tmp_path / "agents.yaml"
    prompt = tmp_path / "p.md"
    prompt.write_text("hi", encoding="utf-8")
    config.write_text(
        "agents:\n"
        "  - {id: a, name: A, department: D, prompt: p.md}\n"
        "  - {id: a, name: A2, department: D, prompt: p.md}\n",
        encoding="utf-8",
    )
    with pytest.raises(AgentRegistryError, match="duplicate agent id"):
        load_agents(config)


def test_missing_prompt_file_raises(tmp_path: Path) -> None:
    config = tmp_path / "agents.yaml"
    config.write_text(
        "agents:\n  - {id: a, name: A, department: D, prompt: missing.md}\n",
        encoding="utf-8",
    )
    with pytest.raises(AgentRegistryError, match="prompt file"):
        load_agents(config)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    config = tmp_path / "agents.yaml"
    config.write_text("agents:\n  - {id: a, name: A}\n", encoding="utf-8")
    with pytest.raises(AgentRegistryError, match="missing fields"):
        load_agents(config)


# --- base agent -------------------------------------------------------------


def test_build_messages_includes_system_prompt_and_task() -> None:
    agent = make_agent("backend_engineer")
    messages = agent.build_messages(
        AgentContext(task_id="t-1", input="Build the API")
    )
    assert messages[0]["role"] == "system"
    assert "Backend Engineer" in messages[0]["content"]
    assert "Task ID: t-1" in messages[1]["content"]
    assert "Build the API" in messages[1]["content"]


def test_build_messages_numbers_prior_outputs() -> None:
    agent = make_agent("code_reviewer")
    messages = agent.build_messages(
        AgentContext(
            task_id="t-2",
            input="Review",
            prior_outputs=("first result", "second result"),
        )
    )
    user = messages[1]["content"]
    assert "Previous specialist outputs:" in user
    assert "1. first result" in user
    assert "2. second result" in user


def test_template_agent_run_returns_assembled_prompt() -> None:
    agent = make_agent("qa_engineer")
    output = asyncio.run(
        agent.run(AgentContext(task_id="t-3", input="Run the test suite"))
    )
    assert "# QA Engineer" in output
    assert "Run the test suite" in output


def test_make_agent_unknown_id_raises() -> None:
    with pytest.raises(AgentRegistryError, match="unknown agent id"):
        make_agent("ghost")


def test_template_agent_is_constructible_from_definition() -> None:
    definition = get_agent("project_manager")
    agent = TemplateAgent(definition)
    assert agent.agent_id == "project_manager"
