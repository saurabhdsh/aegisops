# Architecture

AegisOps is a modular monolith. One API process and one worker process share a database. There is no container runtime, no Redis, and no external job broker.

```text
React experience (Phase 7–8)
        |
   REST + SSE
        |
   FastAPI  apps/api
        |
   Workflow orchestrator
        |
   Policy enforcement point     Governance Agent (explains, does not authorize)
        |
   Tool layer (Phase 2–5)
   ServiceNow | Dynatrace | Ansible | OpenAI
        |
   SQLite in development, PostgreSQL in production
        |
   Audit, evidence, outbox
```

## Execution modes

| Mode | Meaning |
| --- | --- |
| LIVE | Configured enterprise systems. Missing credentials fail startup. A failed call stays an error. The local runbook runner is refused. |
| SANDBOX | Saved connection settings. A production configuration item is refused for the local runner. A failed call stays an error. |
| SIMULATOR | Fixture catalogs, until a ServiceNow or Dynatrace connection is saved. A complete saved connection is used for that system. Demo 1 and Demo 2 stay on fixtures. A failed live call stays an error. |

The API reports `execution_mode` on `/health`. The UI, when it exists, must show simulator mode.

## Domain

Tenants own users, roles, incidents, configuration items, business services, workflows, evidence, approvals, runbooks, and audit events. A user belongs to one tenant. Every operational query filters on `tenant_id` from the authenticated session, not from the request body.

Identifiers are prefixed (`inc_`, `wf_`, `aud_`) and contain a UUID4.

Timestamps are timezone-aware UTC. Naive datetimes are rejected by the column type.

Workflow states:

`RECEIVED`, `NORMALIZING`, `ENRICHING`, `INVESTIGATING`, `ANALYZING`, `PLANNING`, `POLICY_CHECK`, `AWAITING_APPROVAL`, `PRECHECKING`, `EXECUTING`, `VALIDATING`, `RESOLVED`, `PREVENTED`, `ESCALATED`, `FAILED`, `CANCELLED`.

Transitions are an explicit map in `aegisops.runtime.state_machine`. Terminal states have no outbound edge. Each accepted transition increments `version`, writes a step, and appends an outbox event in the same transaction.

Cancellation of a workflow that is `EXECUTING` or that already has an external execution id sets `cancel_requested` and leaves the state unchanged. The API does not report the external action as stopped.

An automation row with `external_execution_id` is classified `reconcile`. A recovered worker must not launch it again.

## Control plane

The Governance Agent will explain policy. `aegisops.policy.engine` makes the authorization decision. An approval is valid only when all of these hold:

- The request is pending and unexpired.
- The actor's role matches the required role (`dba` is not satisfied by a generic approver).
- Admins may decide.
- Emergency stop is off.

Changing autonomy to L4 requires `AUTONOMY_L4_ENABLED=true` and the admin role. The default is L3.

Emergency stop is a tenant row. Engaging it blocks new approvals. It does not claim that an already started external action has stopped.

## Integrations

The normalized contracts live in `packages/contracts`. ServiceNow, Dynatrace, and OpenAI have HTTP clients. The simulator adapters are used only when that system has no saved connection and the mode is `SIMULATOR`.

Connector secrets are encrypted in `connector_settings`. API responses and audit payloads return the URL, the auth mode, and whether a secret is stored. They do not return the secret. A blank secret on update keeps the stored value. Logs pass through a redaction filter.

## API and worker

The API process serves HTTP and SSE. SSE reads `outbox_events` and supports `Last-Event-ID` as the last sequence number. Events are not generated for display.

The worker is a native Python process. It confirms the schema exists, takes a lease on its own worker id, refreshes that lease, and releases it on SIGINT or SIGTERM. SQLite runs in WAL mode with foreign keys enabled. One worker is the development assumption. Production locking is the same lease table on PostgreSQL.

## Local deployment

Development uses a virtualenv, `uvicorn`, and `python -m workers.main`. Production uses the operating system service manager and a PostgreSQL `DATABASE_URL`. `APP_ENV=production` rejects SQLite.

## Experience direction

The later UI keeps SEAL's craft: Inter, hairline separators, a quiet sidebar, a command palette, tabular numbers, and reduced-motion support. The palette is the AegisOps mission-control palette (obsidian, graphite, electric violet, amber, cyan, coral, mint, titanium), because operational color has to carry state. SEAL's light blue product theme is not the AegisOps theme.

## Acceptance for this phase

- `alembic upgrade head` creates the schema.
- `pytest tests/` passes.
- `/health` and `/ready` respond.
- Unauthenticated operational routes return 401.
- A tenant cannot read another tenant's incident.
- Audit rows cannot be updated or deleted.
- Investigate, agent execution, and integration tests return `not_implemented` or are absent, and they do not fabricate an outcome.
