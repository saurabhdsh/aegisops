# Implementation progress

## Phase 0 — Architecture

Done. See `docs/architecture.md`, `docs/threat-model.md`, `docs/api-contracts.md`, `docs/agent-contracts.md`, `docs/runbook-certification.md`, `docs/operational-readiness.md`, and `docs/adr/`.

## Phase 1 — Backend foundation

Done. Auth, schema, leases, transitions, SSE replay, and audit immutability are covered by tests.

## Phases 2–9

| Phase | State |
| --- | --- |
| 2 ServiceNow and Dynatrace | HTTP clients and simulator adapters. A saved connection is used in every mode. Demo catalogs stay on fixtures. A failed call stays an error. No live tenant was called from this workspace. |
| 3 Agent runtime and LLM | Agents run inside the engine. A saved OpenAI or Azure OpenAI model restates RCA causes in every mode, including `SIMULATOR`. A response that adds a cause is rejected. |
| 4 Incident agents | The compute fixture stops at approval, then resolves after approval. Prompt text does not become a tool. |
| 5 Approval and runbooks | Approval continues the workflow. The local runner allowlists modules and sandboxes paths. `ansible-playbook` is not invoked. |
| 6 Capacity | Fifty fixture alerts become one group. Cleanup deletes the aged log only. Utilization after cleanup is derived (60.8 from the fixture sizes). The change stays in `implement`. |
| 7–8 UI | React console on port 5173, bound to the API. Empty lists stay empty. |
| 9 Hardening | `pytest tests/` covers the connection routing. `scripts/backup-sqlite.sh` copies a SQLite file. No load test and no PostgreSQL execution of the audit trigger. |

## Unresolved

- Live ServiceNow, Dynatrace, OpenAI, and Ansible credentials are absent, so those paths are unvalidated.
- The in-memory rate limit is per process.
- PostgreSQL trigger SQL is in the migration and has not been executed against a PostgreSQL server here.
- L4 stays disabled unless `AUTONOMY_L4_ENABLED=true`.
