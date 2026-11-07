# Runbook certification

Execution is not available in this phase. The data model and the rules below are what Phase 5 must enforce. An LLM must never submit a shell command.

## Definition

A runbook row is a versioned file under `runbooks/`, addressed by `slug` and `version`, with:

- a parameter schema
- a SHA-256 checksum of the file bytes
- `rollback_defined`
- a target class

The unique key is `(tenant_id, slug, version)`. A new file is a new version. Approvals bind `runbook_version` and `plan_hash`. Changing either invalidates the approval because the hash no longer matches.

## Certification states

`pending`, `certified`, `revoked`, `expired`.

A runbook may execute only when a certification row is `certified`, the checksum still matches the file, `expires_at` is in the future, and the target CI is inside the certification scope. High-risk actions stay approval-gated at L4.

## Rollback

Rollback is offered only when `rollback_defined` is true and the procedure has been exercised in certification evidence. Absence of a rollback is a reason to require a human decision, not a reason to invent one.

## Parameters

Parameter values are validated against the schema before any process starts. Names that look like shell metacharacters are data, not syntax. The runner receives structured arguments, not a concatenated command string.

## This repository

`runbooks/compute`, `runbooks/capacity`, and `runbooks/manifests` are reserved. No playbook here is certified, and the worker does not invoke Ansible.
