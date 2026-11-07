# Threat model

This is the model for the foundation that exists now, plus the controls those later phases must keep. It is not a claim that every threat is already closed.

## Assets

- Tenant operational data: incidents, topology, telemetry, evidence.
- Approval decisions and the plan hash they bind.
- Integration credentials.
- Runbook contents and checksums.
- The audit log.

## Actors

- Authenticated operators (admin, sre, approver, dba, operator, observer, auditor).
- External webhook senders.
- A worker process.
- Later: an LLM reading untrusted tickets, logs, and notes.

## Threats and current treatment

| Threat | Treatment in this phase |
| --- | --- |
| Credential leakage | Secrets stay in the environment. Database rows store a `secret_ref`. Startup logs show the database target with the password hidden. Log lines and audit payloads redact token-shaped fields. |
| Cross-tenant access | Session carries `tenant_id`. Repositories require it. A test reads another tenant's incident id and gets 404. |
| Approval spoofing | Decisions require an authenticated principal. Cookie mutations require a CSRF token that matches the hashed value stored at login. Bearer tokens are not cookies, so they skip CSRF and still require a server-side session hash. |
| Stale approvals | Expired pending requests are marked `expired` and rejected. A second decision on a closed request conflicts. |
| Unauthorized remediation | The policy engine gates execution. L4 cannot be selected unless `AUTONOMY_L4_ENABLED=true`, and high-risk or non-rollback actions stay approval-gated. |
| Replay of webhooks | Unconfigured or mismatched webhook tokens are rejected with 401. A valid token stores the event once. |
| Duplicate webhook events | The `events` table has a unique `(tenant_id, source, idempotency_key)`. A replay returns the original row. |
| Prompt injection | Ticket notes are stored as untrusted text. The ranker does not read them as signals. The fixture injection line does not create a shell tool. |
| Worker crash | Leases expire. `retry_decision` returns `reconcile` when an external execution id exists, and `blocked` when a run is in progress without one. |
| Conflicting remediations | Workflow updates use a version column. A mismatched `expected_version` is a 409. |
| Malicious runbook modification | The runner rejects shell, command, raw, and script modules, refuses unsubstituted variables, and keeps paths inside the sandbox. The playbook checksum is compared before execution. |
| Audit tampering | ORM events reject update and delete. SQLite triggers abort SQL updates and deletes. PostgreSQL migrations install the equivalent trigger. |
| Session theft | The database stores a SHA-256 of the session token. Logout sets `revoked_at`. |
| Rate abuse | Each API process keeps an in-memory window. It is not shared across processes. |

## Residual risk

Webhook replay protection is authentication only until Phase 2 stores nonces. The rate limit resets on process restart and is not global. Prompt-injection tests belong with the first model call. Runbook integrity verification belongs with certification.
