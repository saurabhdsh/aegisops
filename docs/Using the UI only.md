# Using the UI only

Use this when the AegisOps screens are the part you want, and the agents, the policy engine, and the API are yours.

The console is not a component kit. `apps/web` is a set of pages. Each page asks `/api/v1/...` for records and draws the JSON it gets back. Your agents never run inside the browser. They write the records. Your API returns them in the shapes below.

You do not need the Python packages, the worker, the fixture catalogs, or the local runbook runner for this path.

## What you keep

Keep `apps/web`. It is a Vite React app. In development it listens on [http://127.0.0.1:5173](http://127.0.0.1:5173) and proxies `/api`, `/health`, and `/ready` to `http://127.0.0.1:8000`. Point that proxy at your API, or serve the built files behind a host that forwards `/api` the same way.

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Sign-in stores `access_token` and `user` in `sessionStorage`. Later calls send `Authorization: Bearer`. A `401` clears that session and returns the person to `/login`. Cookie auth is not required for these pages.

Errors the pages can show use this body. The message is what the person reads. Any other failure becomes `Request failed` plus the status code.

```json
{
  "error": {
    "code": "not_found",
    "message": "Incident not found"
  }
}
```

Empty lists are empty arrays. A missing list should be `[]` or `{ "items": [] }`, matching the route below. `null` where the page expects an array leaves the screen blank or failed.

## What you have to build

Your API owns the data. The pages only need the routes for the screens you leave in the sidebar. A route you delete from `apps/web/src/App.tsx` and from the sidebar in `apps/web/src/components/Shell.tsx` does not need an implementation.

### Sign-in

`POST /api/v1/auth/login` with `{ "tenant_slug", "email", "password" }`.

Return `access_token` and `user`. The sidebar reads `user.display_name`, `user.email`, and `user.roles[0]`.

### Incidents

`GET /api/v1/incidents?limit=100` returns `{ "items": [...] }`.

Each item needs `id`, `number`, `title`, `state`, `priority`, `service_name`, `ci_name`, `opened_at`. The queue matches a workflow when `workflow.incident_id` equals `incident.id`.

`GET /api/v1/incidents/{id}` adds `description`, `source_state`, `resolved_at`, and `work_notes` (an array of strings).

`GET /api/v1/incidents/{id}/evidence` returns an array of `{ id, kind, summary, source, content_hash }`.

### Root cause

`GET /api/v1/workflows?limit=100` returns `{ "items": [...] }` with `id`, `kind`, `state`, `incident_id`.

When an incident has a workflow of kind `incident`, the RCA page loads that workflow. Otherwise it calls `GET /api/v1/incidents/{id}/analysis`.

The analysis body needs `number`, `title`, `state`, `priority`, `ci_name`, `service_name`, `entity_id`, `source`, `hypotheses`, `series.cpu`, `series.memory`, and `confidence_note`. Each sample is `{ "timestamp", "value" }`. The chart plots those points. It does not invent samples between them.

A hypothesis is `{ rank, cause, confidence, limitations, requires_human_review }`.

### Workflow

`GET /api/v1/workflows/{id}` needs `id`, `kind`, `state`, `execution_mode`, `autonomy_level`, `summary`, `incident_id`, `started_at`, `finished_at`.

Also:

| Call | Body the page reads |
| --- | --- |
| `GET /api/v1/workflows/{id}/hypotheses` | `{ "items": [{ rank, cause, confidence, limitations, requires_human_review }] }` |
| `GET /api/v1/workflows/{id}/plan` | `{ "plan": { summary, parameters, risk_level, rollback_available, plan_hash } }` or `{ "plan": null }` |
| `GET /api/v1/workflows/{id}/agents` | `{ "items", "tools", "validation", "notifications", "change" }` |
| `GET /api/v1/workflows/{id}/executions` | `{ "items": [{ status, phase, external_execution_id, result }] }` |

Agent rows use these `agent_name` values when you want the existing sections to fill in: `triage`, `rca`, `event_correlation`, `capacity_risk`, `validation`. Any other name still appears in the agent list. The named sections stay empty until a row uses that name.

`validation` is `{ status, summary, checks: [{ name, passed }] }` or null. `change` is `{ number, state, summary }` or null. `tools` is `{ tool_name, status }[]`. `notifications` is `{ channel, recipient, subject, body, status }[]`.

`output` on an agent row is free JSON. The incident RCA section looks for `series`, `logs`, `traces`, `narrative`, and `llm_error`. The capacity section looks for `configuration_item.name`, `business_service`, `current_utilization`, `growth_per_hour`, `hours_to_exhaustion`, `related_changes`, `similar_fixes`, `forecast_count`, and `alert_count`.

### Approvals

`GET /api/v1/approvals` returns `{ "items": [{ id, workflow_id, required_role, status, runbook_version, plan_hash }] }`.

`POST /api/v1/approvals/{id}/approve` and `POST /api/v1/approvals/{id}/reject` take `{ "reason" }`. The page reloads the list after a `2xx`. Your policy decides whether that call is allowed. The screen does not.

### Capacity

`GET /api/v1/capacity/assets` returns an array of `{ id, name, external_id, environment, criticality }`. The page uses the length.

`GET /api/v1/capacity/forecasts` and `GET /api/v1/capacity/risks` return `{ "items": [...] }`.

Each forecast needs `entity_id`, `current_utilization`, `growth_per_hour`, `hours_to_exhaustion`, `sample_count`, `method`, `source`, and `points`. A point is `{ "timestamp", "value" }`. Two or more points draw the curve. The dashed line continues `growth_per_hour` from the last point. It is not another sample. `hours_to_exhaustion: null` means the page shows the series as steady.

A forecast is the Claims card only when `entity_id` is `HOST-CLAIMS-DB-01` and a workflow with `kind: "capacity"` exists. For your own hosts, the chart and the host strip are enough. Leave the Claims workflow out and that story stays off the page.

### Topology

`GET /api/v1/topology/services` returns `{ "items": [{ id, name, criticality }] }`.

`GET /api/v1/topology/configuration-items` returns `{ "items": [{ id, name, business_service_id, environment }] }`. A configuration item is drawn under the service whose `id` equals `business_service_id`.

### Runbooks

`GET /api/v1/runbooks` returns an array of `{ id, slug, version, name, checksum, rollback_defined }`.

`GET /api/v1/runbooks/{id}/certification` returns an array of `{ status, certified_by, expires_at, scope }`. `scope.external_ids` is the list of configuration items in scope.

**Probe connectors** calls `POST /api/v1/integrations/servicenow/test` and `POST /api/v1/integrations/dynatrace/test`. Each returns `{ "status" }`. ServiceNow may include `mode`. Dynatrace may include `capabilities.traces`. If you do not have those systems, remove the button or return a clear error message.

### Audit

`GET /api/v1/audit` returns `{ "items": [{ id, action, resource_type, resource_id, created_at }] }`.

`GET /api/v1/operations/controls` returns `{ emergency_stop, autonomy_level, freeze_reason }`.

`POST /api/v1/operations/emergency-stop` and `POST /api/v1/operations/emergency-stop/clear` take `{ "reason" }`.

### Settings

Leave this page in only if your API implements it. The screen loads `GET /api/v1/settings/connections` and `GET /api/v1/settings/connections/demo`.

The connection view is `execution_mode` plus `servicenow`, `dynatrace`, and `openai` objects. Secrets are booleans (`has_api_token`, `has_api_key`, and the ServiceNow `has_*` fields), never the secret values. Save is `PUT` on `/servicenow`, `/dynatrace`, and `/openai`. Test is `POST` on those same paths plus `/test`. Demo load is `PUT /api/v1/settings/connections/demo` with `{ "enabled" }` and returns `{ enabled, incident_count }`.

If your product has no ServiceNow, Dynatrace, or model settings, take Settings out of the sidebar instead of inventing those forms.

## How your agents fit

Your agent process is out of band. A person opens an incident, your agents investigate, and your API then has a workflow, agent rows, hypotheses, and a plan. The workflow page renders that stored result. It does not import your agent framework.

The same split applies to capacity. Your forecaster writes `points` and the slope. The chart draws them.

An approval button does not run your agent. It calls the approve or reject route. Your backend continues the work after that call.

## A small slice

You do not have to implement every page. A console that is only the queue, the incident record, and the workflow needs:

1. Login.
2. Incident list and incident record, including evidence.
3. Workflow list and the workflow routes in the table above.
4. Approvals, if the workflow can be waiting on a person.

Capacity, RCA's sample view, topology, runbooks, audit, and settings are separate. Add a page only when its routes exist.

## What this does not do

- The pages do not discover your routes. The paths above are fixed unless you change the React files.
- The charts do not accept an image or a pre-drawn series. They need timestamped numbers.
- The workflow sections for triage, RCA, and capacity stay empty until `agent_name` matches the names above.
- Replacing this API does not keep the Claims demo, the disk demo, or the local sandbox runner. Those belong to the Python app.
