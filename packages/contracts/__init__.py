"""Typed contracts shared by the API, agents, and connectors.

These models describe data. They do not call external systems.
"""

from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.contracts.approval import ApprovalDecisionRecord, ApprovalRequestRecord
from aegisops.contracts.capacity import CapacityAssessment, ForecastPoint
from aegisops.contracts.evidence import EvidenceArtifactRecord, MetricPoint, MetricSeries
from aegisops.contracts.incident import ConfigurationItem, HistoricalIncident, IncidentRecord
from aegisops.contracts.remediation import ExecutionResult, PrecheckResult, RemediationPlanRecord
from aegisops.contracts.workflow import WorkflowRecord, WorkflowState

__all__ = [
    "AgentContext",
    "AgentResult",
    "ApprovalDecisionRecord",
    "ApprovalRequestRecord",
    "CapacityAssessment",
    "ConfigurationItem",
    "EvidenceArtifactRecord",
    "ExecutionResult",
    "ForecastPoint",
    "HistoricalIncident",
    "IncidentRecord",
    "MetricPoint",
    "MetricSeries",
    "PrecheckResult",
    "RemediationPlanRecord",
    "WorkflowRecord",
    "WorkflowState",
]
