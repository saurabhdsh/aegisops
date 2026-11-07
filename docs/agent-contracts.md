# Agent contracts

Agents share `AgentContext` and `AgentResult` from `aegisops.contracts.agent`. Each concrete agent validates a narrower input model and then raises `not_implemented`. None of them returns a hardcoded investigation.

| Agent | Input model | Mutation | Phase |
| --- | --- | --- | --- |
| Incident Goal | `incident_id` | No | 4 |
| Triage | `incident_id`, optional CI | No | 4 |
| RCA | `workflow_id`, `evidence_ids` | No | 4 |
| Remediation | `workflow_id`, `evidence_ids` | No. Planning does not execute a runbook. | 4 |
| Validation | `workflow_id`, optional `execution_id` | No | 4 |
| Capacity and Risk | `asset_id`, `metric_key` | No | 6 |
| Event Correlation | `event_ids` | No | 6 |
| Governance | `workflow_id`, optional `plan_hash` | No. Cannot authorize. | 5 |

`AgentResult.status` is `completed`, `failed`, `waiting_approval`, or `insufficient_evidence`. Confidence is optional and is not a calibrated probability unless a later phase documents a calibration method.

The goal agent must not gain a mutating tool. Triage and RCA must not receive mutating tools. That split is a registry rule for Phase 3, not a prompt instruction.

Tool calls, when they exist, will pass schema validation, an allowlist, tenant and target checks, the policy engine, execution, result validation, and evidence recording. Model output will not authorize an action.
