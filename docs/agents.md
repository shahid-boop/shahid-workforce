# Agents

> Skeleton document — expand as the registry is implemented.

## Specialists (15)

| ID | Name | Department |
|---|---|---|
| chief_ai_officer | Chief AI Officer | Leadership |
| system_architect | System Architect | Development |
| ui_ux_designer | UI/UX Designer | Development |
| frontend_engineer | Frontend Engineer | Development |
| backend_engineer | Backend Engineer | Development |
| database_engineer | Database Engineer | Development |
| api_integrator | API Integration Engineer | Development |
| security_engineer | Security Engineer | Quality & Security |
| qa_engineer | QA Engineer | Quality & Security |
| code_reviewer | Code Review Engineer | Quality & Security |
| devops_engineer | DevOps Engineer | Infrastructure |
| automation_engineer | Automation Engineer | Infrastructure |
| research_agent | Research Agent | Intelligence |
| project_manager | Project Manager | Intelligence |
| documentation_engineer | Documentation Engineer | Intelligence |

## Files

- Prompts: `agents/prompts/*.md`
- Configuration: `agents/configs/agents.yaml`
- Loading: `agents/registry.py`
- Shared interface: `agents/base_agent.py`

## Rules

- Agent IDs are stable; the orchestrator references agents by ID.
- Every plan ends with independent code-review and QA gates.
- Prompts must not contain secrets or credentials.
