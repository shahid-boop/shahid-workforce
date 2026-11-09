"""Load and expose the specialist agent registry.

Configuration lives in ``agents/configs/agents.yaml``; each agent points to a
prompt file in ``agents/prompts/``. Loading validates the configuration and
fails fast when a prompt file is missing or an id is duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "agents.yaml"

_REQUIRED_FIELDS = ("id", "name", "department", "prompt")


class AgentRegistryError(RuntimeError):
    """Raised when the agent configuration is missing or invalid."""


@dataclass(frozen=True)
class AgentDefinition:
    """One specialist role loaded from configuration."""

    id: str
    name: str
    department: str
    prompt_path: Path
    model: str | None = None

    @property
    def prompt(self) -> str:
        """Return the prompt text for this agent."""
        return self.prompt_path.read_text(encoding="utf-8").strip()


def _resolve_prompt_path(raw: str, config_path: Path) -> Path:
    """Prompt paths are repo-relative; also accept paths relative to config."""
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    for base in (REPO_ROOT, config_path.resolve().parent):
        resolved = base / candidate
        if resolved.exists():
            return resolved
    return REPO_ROOT / candidate


def load_agents(config_path: Path | None = None) -> list[AgentDefinition]:
    """Parse and validate the agent configuration."""
    config_path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not config_path.exists():
        raise AgentRegistryError(f"agent config not found: {config_path}")

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentRegistryError(f"invalid agent config: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("agents"), list):
        raise AgentRegistryError("agent config must contain an 'agents' list")

    definitions: list[AgentDefinition] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(data["agents"]):
        if not isinstance(entry, dict):
            raise AgentRegistryError(f"agent #{index} must be a mapping")
        missing = [field for field in _REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            raise AgentRegistryError(
                f"agent #{index} missing fields: {', '.join(missing)}"
            )
        agent_id = str(entry["id"])
        if agent_id in seen_ids:
            raise AgentRegistryError(f"duplicate agent id: {agent_id}")
        seen_ids.add(agent_id)

        prompt_path = _resolve_prompt_path(str(entry["prompt"]), config_path)
        if not prompt_path.exists():
            raise AgentRegistryError(
                f"prompt file for '{agent_id}' not found: {prompt_path}"
            )

        model = entry.get("model")
        definitions.append(
            AgentDefinition(
                id=agent_id,
                name=str(entry["name"]),
                department=str(entry["department"]),
                prompt_path=prompt_path,
                model=str(model) if model else None,
            )
        )

    if not definitions:
        raise AgentRegistryError("agent config contains no agents")
    return definitions


def get_agent(agent_id: str, config_path: Path | None = None) -> AgentDefinition:
    """Return one agent by id or raise ``AgentRegistryError``."""
    for definition in load_agents(config_path):
        if definition.id == agent_id:
            return definition
    raise AgentRegistryError(f"unknown agent id: {agent_id}")


def agent_ids(config_path: Path | None = None) -> tuple[str, ...]:
    """Return all configured agent ids in configuration order."""
    return tuple(definition.id for definition in load_agents(config_path))
