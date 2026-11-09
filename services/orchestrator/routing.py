"""Keyword and goal based routing that selects the specialist sequence.

Every plan ends with the two independent gates - code review and QA - in that
order. Specialists matched earlier are moved to the end if they collide with
the gates, so the gates always run last and see everyone else's output.
"""

from __future__ import annotations

import re

# Ordered rules: first match wins per agent; order defines plan order.
_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("architecture", "system design", "microservice", "diagram"),
        "system_architect",
    ),
    (("ui", "ux", "layout", "figma", "design system"), "ui_ux_designer"),
    (("frontend", "react", "next.js", "component", "css"), "frontend_engineer"),
    (("backend", "fastapi", "server", "endpoint", "service"), "backend_engineer"),
    (("database", "sql", "schema", "migration", "index"), "database_engineer"),
    (
        ("webhook", "oauth", "third-party", "rest api", "integrate"),
        "api_integrator",
    ),
    (("security", "auth", "secret", "vulnerab", "permission"), "security_engineer"),
    (("test", "qa", "regression", "coverage"), "qa_engineer"),
    (("review", "code review", "diff"), "code_reviewer"),
    (("docker", "deploy", "ci/cd", "pipeline", "kubernetes"), "devops_engineer"),
    (("queue", "scheduler", "background", "retry", "automation"), "automation_engineer"),
    (("research", "compare", "evaluate", "benchmark"), "research_agent"),
    (("plan", "milestone", "roadmap", "priorit"), "project_manager"),
    (("docs", "readme", "runbook", "documentation"), "documentation_engineer"),
    (("ai", "model", "llm", "agent"), "chief_ai_officer"),
)

DEFAULT_PLAN_HEAD = ("system_architect",)
GATE_AGENTS = ("code_reviewer", "qa_engineer")


def _matches(text: str, keyword: str) -> bool:
    """Whole-word match so 'ui' does not fire inside 'build'."""
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def select_specialists(goal: str) -> list[str]:
    """Return unique specialists matched by the goal's keywords, in plan order."""
    text = goal.lower()
    selected: list[str] = []
    for keywords, agent_id in _RULES:
        if agent_id in selected:
            continue
        if any(_matches(text, keyword) for keyword in keywords):
            selected.append(agent_id)
    return selected


def build_plan(goal: str) -> list[str]:
    """Turn a goal into an ordered agent plan ending with review and QA gates."""
    specialists = select_specialists(goal)
    if not specialists:
        specialists = list(DEFAULT_PLAN_HEAD)

    plan = list(specialists)
    for gate in GATE_AGENTS:
        while gate in plan:
            plan.remove(gate)
        plan.append(gate)
    return plan
