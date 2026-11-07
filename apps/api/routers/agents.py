from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aegisops.core.exceptions import NotFoundError
from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import Principal, get_session, require
from apps.api.schemas.common import AgentCatalogItem, AgentExecutionResponse, ToolCallResponse

router = APIRouter(tags=["agents"])

# Catalog of responsibilities. Each agent runs inside the workflow engine.
AGENT_CATALOG: tuple[AgentCatalogItem, ...] = (
    AgentCatalogItem(
        id="incident_goal",
        name="Incident Goal Agent",
        responsibility="Coordinate reactive incident resolution. Does not execute infrastructure actions.",
        executable=True,
    ),
    AgentCatalogItem(
        id="triage",
        name="Triage Agent",
        responsibility="Identify the impacted CI, service, priority, related changes, and similar incidents.",
        executable=True,
    ),
    AgentCatalogItem(
        id="rca",
        name="RCA Agent",
        responsibility="Rank hypotheses from telemetry and change evidence.",
        executable=True,
    ),
    AgentCatalogItem(
        id="remediation",
        name="Remediation Agent",
        responsibility="Select a certified runbook and produce an execution plan.",
        executable=True,
    ),
    AgentCatalogItem(
        id="validation",
        name="Validation Agent",
        responsibility="Compare post-action evidence with resolution criteria.",
        executable=True,
    ),
    AgentCatalogItem(
        id="capacity_risk",
        name="Capacity and Risk Agent",
        responsibility="Enrich a capacity forecast with the CI, service, recent changes, growth trend, and similar fixes.",
        executable=True,
    ),
    AgentCatalogItem(
        id="event_correlation",
        name="Event Correlation Agent",
        responsibility="Deduplicate and group related operational events.",
        executable=True,
    ),
    AgentCatalogItem(
        id="governance",
        name="Governance Agent",
        responsibility="Explain policy. Does not authorize infrastructure actions.",
        executable=True,
    ),
)


@router.get("/api/v1/agents", response_model=list[AgentCatalogItem])
def list_agents(principal: Principal = Depends(require("agent:read"))) -> list[AgentCatalogItem]:
    del principal
    return list(AGENT_CATALOG)


@router.get("/api/v1/agents/{agent_id}", response_model=AgentCatalogItem)
def get_agent(agent_id: str, principal: Principal = Depends(require("agent:read"))) -> AgentCatalogItem:
    del principal
    for agent in AGENT_CATALOG:
        if agent.id == agent_id:
            return agent
    raise NotFoundError("Agent not found")


@router.get("/api/v1/agent-executions/{execution_id}", response_model=AgentExecutionResponse)
def get_execution(
    execution_id: str,
    principal: Principal = Depends(require("agent:read")),
    session: Session = Depends(get_session),
) -> AgentExecutionResponse:
    row = OperationsRepository(session).get_agent_execution(principal.tenant_id, execution_id)
    return AgentExecutionResponse.model_validate(row)


@router.get("/api/v1/agent-executions/{execution_id}/tool-calls", response_model=list[ToolCallResponse])
def tool_calls(
    execution_id: str,
    principal: Principal = Depends(require("agent:read")),
    session: Session = Depends(get_session),
) -> list[ToolCallResponse]:
    rows = OperationsRepository(session).tool_calls_for(principal.tenant_id, execution_id)
    return [ToolCallResponse.model_validate(row) for row in rows]
