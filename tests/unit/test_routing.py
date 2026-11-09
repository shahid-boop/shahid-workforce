"""Tests for keyword routing and plan construction (no langgraph needed)."""

from __future__ import annotations

from services.orchestrator.routing import build_plan, select_specialists
from services.orchestrator.state import initial_state

GATES = ["code_reviewer", "qa_engineer"]


def test_plan_always_ends_with_both_gates() -> None:
    goals = [
        "Build a React frontend page",
        "Design the database schema",
        "secure the deployment pipeline",
        "nothing relevant at all",
    ]
    for goal in goals:
        plan = build_plan(goal)
        assert plan[-2:] == GATES, goal


def test_plan_has_no_duplicates() -> None:
    plan = build_plan("review the test coverage and qa report")
    assert len(plan) == len(set(plan))


def test_gate_matched_earlier_is_moved_to_the_end() -> None:
    plan = build_plan("add a code review checklist and tests")
    assert plan[-2:] == GATES
    assert plan.count("code_reviewer") == 1
    assert plan.count("qa_engineer") == 1


def test_frontend_goal_selects_frontend_and_design() -> None:
    selected = select_specialists("Build the React login page UI")
    assert "frontend_engineer" in selected
    assert "ui_ux_designer" in selected


def test_build_does_not_false_positive_ui_inside_build() -> None:
    selected = select_specialists("please build the thing")
    assert "ui_ux_designer" not in selected


def test_database_goal_selects_database_engineer() -> None:
    assert "database_engineer" in select_specialists("write the SQL migration")


def test_unknown_goal_defaults_to_system_architect() -> None:
    plan = build_plan("qqzzxxyy")
    assert plan[0] == "system_architect"
    assert plan[-2:] == GATES


def test_project_manager_selected_for_planning_goal() -> None:
    assert "project_manager" in select_specialists("create a roadmap plan")


def test_initial_state_defaults() -> None:
    state = initial_state("t-1", "goal")
    assert state["task_id"] == "t-1"
    assert state["goal"] == "goal"
    assert state["plan"] == []
    assert state["step_index"] == 0
    assert state["outputs"] == []
    assert state["status"] == "pending"
    assert state["error"] is None
