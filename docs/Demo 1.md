# Demo 1 — Claims API CPU and memory saturation

Reactive incident. Dynatrace opens a ServiceNow P2, the incident agents investigate it, and a certified runbook restarts the service and adds one node. Nothing in this demo calls a live ServiceNow tenant or restarts a real process.

Saving a ServiceNow or Dynatrace connection does not turn this walkthrough into that tenant. Demo load still reads this fixture catalog. Your tenant's incidents can appear on the same board. Investigating one of those incidents calls the saved connection. It does not replay INC0012345.

## What you are looking at

| Item | Value |
| --- | --- |
| ServiceNow incident | INC0012345 |
| Title | Claims API CPU and memory saturation |
| Priority | P2 |
| Configuration item | claims-app-01 (`ci-claims-app-01`) |
| Dynatrace entity | HOST-CLAIMS-APP-01 |
| Business service | Claims, tier-1 |
| Recent change | CHG00991, deploy claims-api 2.4.1 |
| Certified runbook | Restart Claims API and add one node |
| Autonomy on this process | L3. The on-call SRE must approve. |

CPU climbs 40 → 92. Memory climbs 55 → 91. The log says RSS grew from 1.2 GiB to 3.8 GiB after build 2.4.1. Trace `tr-claims-241` is a slow `GET /claims/adjudicate`. Synthetic checks are failing and the error rate is 0.04 before the restart.

The ranker, not an LLM, produces the causes. The scores come from measured slopes. They are not calibrated probabilities.

1. Memory utilization is rising and a deployment falls inside the six-hour window. Score 0.8.
2. CPU utilization is rising across the window. Score 0.65.
3. Application error rate is elevated. Score 0.39.

A work note on the incident says to ignore previous instructions and run a shell command. That note is stored as untrusted text. It does not create a tool and it does not change the plan.

## What the agents do

These are real agent classes. The operations engine runs them and stores each one. In this mode they do not call a model, and a model is never allowed to authorize an infrastructure action.

1. **Incident Goal Agent** records the child agents. It does not restart anything.
2. **Triage** reads the ServiceNow incident, the CMDB CI, the Claims service, change CHG00991, priority, work notes, and up to three similar incidents: INC0009911, INC0008801, and INC0007740.
3. **RCA** reads Dynatrace CPU, memory, the log line, and trace `tr-claims-241`, then ranks the three causes above.
4. **Remediation** selects the certified runbook. Parameters are fixed by the runbook: service `claims-api`, one added node. It does not execute the runbook.
5. **Governance** explains the policy decision. At L3 the policy engine holds the action for an on-call SRE. L4 would run this same certified runbook without the card, and only when `AUTONOMY_L4_ENABLED` is true. That flag is false on this process. A high-risk action stays on an approval card at every level.
6. After approval, the restricted runner performs the sandbox pre-check, writes the restart marker, and records one added node. The Ansible CLI is not invoked.
7. **Validation** checks CPU and memory recovery, error rate, synthetic success, post-action samples, and a stabilizing CPU sample. On success it resolves the ServiceNow incident, attaches the validation evidence, and records a notification to the on-call SRE on the operator console.

Targets for a fresh run: triage under 5 minutes, and L3 resolution under 20 minutes. The clock is the workflow start and finish time, not a scripted number.

## Open the console

The product UI is [http://127.0.0.1:5173](http://127.0.0.1:5173). [http://127.0.0.1:8000](http://127.0.0.1:8000) is the API and has no home page.

Sign in with:

- Tenant: `default`
- Email: `sre@example.com`
- Password: `correct-horse-battery`

The signed-in user is an administrator, so the SRE approval can be recorded from this account.

## Load the demo

1. Open **Settings**.
2. Turn **Demo load** on. The knob sits inside the violet pill when it is on.
3. The board then includes 52 fleet incidents (INC10001–INC10052) plus INC0012345, and the disk-capacity workflow from Demo 2.

Turning the switch off hides the fleet. It does not delete the rows. Turning it on again does not re-run a workflow that already exists.

## Walk the incident

1. Open **Incidents**. The queue stays on the screen. Search, priority, and state filters sit above the list. The list itself scrolls.
2. The header counts active incidents, P1, P2, and agent workflows.
3. Find **INC0012345**, or filter **P2** and open **Claims API CPU and memory saturation**.
4. The ServiceNow record shows priority, CI, business service, opened time, work notes, and attached evidence. **Back** returns to the queue.
5. Open **the agent workflow**. The page title is **Claims incident**. Autonomy is L3.
6. Read, in order:
   - **Triage** — CI, Claims service, CHG00991, similar incidents, and the untrusted work notes.
   - **RCA evidence** — CPU and memory series, the RSS log line, trace `tr-claims-241`, and the three ranked causes.
   - **Certified runbook** — Restart Claims API and add one node, medium risk, rollback defined, service `claims-api`, one node.
   - **On-call SRE approval** — only while the workflow is `AWAITING_APPROVAL`. Enter a reason and choose **Approve** or **Reject**. The same card is on **Approvals**, labeled On-call SRE.
   - **Execution** — phase, status, and the restricted-runner log.
   - **Validation and notification** — recovery checks and the on-call SRE notice.
   - **Agents** — each agent name, status, summary, and latency.

**Back** from the workflow returns to the incident record. **Back** from the record returns to the queue.

## What this console already shows

INC0012345 was investigated before the catalog gained the third similar incident and the trace. On this database the workflow is **RESOLVED**, triage completed in 0 ms, and resolution took 34 seconds. That stored triage lists two similar incidents and does not list the trace. The ServiceNow record can still say **open** because closure was added after that run. Loading the scenario again returns the same workflow and does not re-investigate it.

A new database runs the current catalog: three similar incidents, trace `tr-claims-241`, a resolved ServiceNow state, the restart marker, and the one-node marker. Tests cover that path. This console will not show those newer details on INC0012345 unless the local database is replaced.

## What this demo does not do

- It does not update a production ServiceNow instance.
- It does not restart a real claims-api process. The runner writes markers inside a local sandbox.
- It does not turn on L4. There is no Run at L4 button.
- It does not let the model, or the injected work note, choose or authorize the runbook.
- It does not become a live investigation because a connection was saved. The catalog load stays on fixtures.
