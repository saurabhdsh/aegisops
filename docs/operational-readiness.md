# Operational readiness

This checklist is the bar for a later production deployment. Items marked done are true of the current tree. The rest are open.

| Item | State |
| --- | --- |
| Native processes only, no container manifests | Done |
| Configuration fails closed in LIVE mode and in production-on-SQLite | Done |
| Secrets out of source, logs, and database columns | Done for the current code |
| Authentication, RBAC, tenant isolation, CSRF | Done |
| Migrations and append-only audit | Done |
| Worker lease and external-action reconcile rule | Done as a rule; no runner yet |
| Emergency stop | Done as a gate on new approvals |
| ServiceNow and Dynatrace read paths | Open |
| Agent execution with evidence | Open |
| Certified Ansible execution on a non-production target | Open |
| Backup and restore drill | Open |
| Load measurement for 20 interactive users | Open. No number is claimed. |
| OS service unit | Open |
| Frontend bound to these APIs | Open |

Do not enable `AUTONOMY_L4_ENABLED` until the certification and pre-check gates exist. Do not point `DATABASE_URL` at a production database from a workstation.
