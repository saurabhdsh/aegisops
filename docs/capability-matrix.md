# Integration capability matrix

No live tenant has been called. HTTP clients are covered with a mock transport. Simulator mode reads `fixtures/`. "Required" means the product needs it. "Optional" means a missing API is reported rather than invented.

| Capability | System | Required | Status |
| --- | --- | --- | --- |
| Get incident by number or sys_id | ServiceNow | Required | HTTP client and simulator. The incident board lists up to 50 incidents when a connection is saved. Not live-validated. |
| Query incidents by CI and time | ServiceNow | Required | HTTP client query. Not live-validated. |
| Priority, state, work notes | ServiceNow | Required | Normalized by the HTTP client. Simulator read-after-write is tested through the scenario. |
| CI and business-service relationships | ServiceNow | Required | Simulator fixture and HTTP normalizer. Not live-validated. |
| Recent changes | ServiceNow | Required | HTTP client and simulator. Not live-validated. |
| Similar historical incidents | ServiceNow | Required | Returns the fixture list, at most the requested limit. Not padded. |
| Work notes, state update, attachments | ServiceNow | Required | Work notes and state update exist. Attachments are not implemented. Closure stays off unless `INCIDENT_AUTO_RESOLVE=true`. |
| Change request create and update | ServiceNow | Required | Capacity execution writes a local change row in `implement`. It does not call ServiceNow to create a change. |
| Change authorization check | ServiceNow | Required | Not implemented against ServiceNow. Local policy requires the `dba` role. |
| OAuth, bearer token, or basic auth | ServiceNow | Required, selectable | Implemented. Not live-validated. |
| Problems and events | Dynatrace | Required | Simulator problems plus webhook ingestion. HTTP client exists. Not live-validated. |
| Host CPU, memory, disk | Dynatrace | Required | HTTP query and simulator series. Not live-validated. |
| Service health, logs | Dynatrace | Required | Simulator fixture. HTTP logs treat 404 as unavailable. |
| Traces | Dynatrace | Optional | Reported unavailable by the simulator health check. |
| Entity relationships | Dynatrace | Required | Not queried from Dynatrace. Topology is the local service and CI rows. |
| Deployment markers | Dynatrace | Optional | The fixture change timestamp is used. No live deployment API. |
| Synthetic monitors | Dynatrace | Optional | The fixture supplies `synthetic_ok`. No live synthetic API. |
| Metric forecast inputs | Dynatrace | Optional | Disk slope uses stored observations until a connection is saved, then live disk points for non-demo entities. |
| Webhook authentication | Dynatrace, ServiceNow | Required | Shared secret plus idempotent insert. A secret saved on the connection is used before the environment secret. |
| Runbook precheck, execute, verify, rollback | Ansible | Required | Restricted local runner. The Ansible CLI is not invoked. |
| Structured model output | OpenAI | Required for reasoning | Adapter rejects causes outside the ranker list. A saved key and model are called in every mode, including `SIMULATOR`. The ranker still decides the causes. |

Table and field names will be configurable. A missing optional Dynatrace API is a capability gap, not a silent substitute.
