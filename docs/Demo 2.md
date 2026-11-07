# Demo 2 — Predict and prevent disk capacity failure

The Claims database volume is at 80% and rising. No incident has been opened. Dynatrace emits a forecast, event management collapses the related alerts, and a certified runbook purges old logs and records a volume extension before the disk fills.

This run stays on the fixture catalog. It does not change a production volume or open a change on a live ServiceNow tenant.

Saving a Dynatrace connection does not rebuild this card from that tenant. The forecast, the 50 alerts, and CHG0044101 come from this catalog. Live disk forecasts, when a connection is saved, are separate and need at least two points from Dynatrace.

## What you are looking at

| Item | Value |
| --- | --- |
| Host | claims-db-01 (`ci-claims-db-01`) |
| Dynatrace entity | HOST-CLAIMS-DB-01 |
| Business service | Claims, tier-1 |
| Disk series | 64 → 68 → 72 → 76 → 80 |
| Growth | 4 points per hour |
| Time to 100% | 5 hours, inside the six-hour window |
| Forecast event | `forecast-claims-db-01` |
| Related alerts | 50, same host and same disk symptom |
| Grouped result | 1 actionable event |
| Recent change | CHG009880, Claims database backup window extended |
| Certified runbook | Purge logs older than seven days and extend the volume |
| Standard change | CHG0044101 |
| Autonomy on this process | L3. The DBA must approve. |

Logs are 30% of the disk. The cleanup may delete only `.log` files older than seven days, and only inside the sandbox. Fresh logs and files in nested directories stay. After the measured deletion, utilization is **60.8%** and the projected exhaustion moves past six hours (about 9.8 hours at the same 4-point slope). 60.8% is the result of that measurement, not a rounded target.

The service stays healthy for the whole window. The workflow does not create a ServiceNow incident.

## What the agents do

1. **Incident Goal Agent** records the capacity child agents. It does not delete files.
2. **Event correlation** takes the Dynatrace forecast plus the 50 disk alerts and emits one group, because they share the host, the symptom, and a 30-minute window.
3. **Capacity and Risk** reads the Dynatrace disk series and the ServiceNow CI. It attaches:
   - claims-db-01, class `cmdb_ci_linux_server`, production
   - Claims, tier-1
   - change CHG009880
   - the 4-point-per-hour trend and the 5-hour exhaustion
   - three closed fixes: CHG009102, CHG008774, and CHG008221
4. **Remediation** selects the certified runbook. The only parameter is `min_age_days` 7. It does not execute the playbook.
5. **Governance** explains the policy decision. At L3 the policy engine holds the action for a DBA. L4 runs this same medium-risk certified runbook without the card when `AUTONOMY_L4_ENABLED` is true. That flag is false here. A high-risk action remains approval-gated at L4 as well. The governance agent does not authorize the change.
6. After approval, the restricted runner, not the Ansible CLI, runs:
   - pre-check of the seven-day floor and the log directory
   - deletion of aged `.log` files
   - a sandbox marker that one volume was extended
   - a post-check that the extension marker exists
7. **Validation** checks that utilization fell by more than one point, exhaustion is beyond six hours, the service is healthy, and no incident was opened for this CI.
8. On success the engine opens ServiceNow standard change **CHG0044101**, writes the validation note onto it, closes it, stores the evidence, and records a notification to the on-call DBA. The workflow state is **PREVENTED**.

Prediction-to-remediation time is the workflow start time through the validation finish time. It is measured, not filled in. On this console the DBA card was approved while it was open, and the recorded time is **48 seconds**.

## Open the console

Use [http://127.0.0.1:5173](http://127.0.0.1:5173). The API at [http://127.0.0.1:8000](http://127.0.0.1:8000) has no home page.

Sign in with tenant `default`, email `sre@example.com`, and password `correct-horse-battery`. This administrator account can record the DBA decision.

## Load the demo

1. Open **Settings**.
2. Turn **Demo load** on.
3. In simulator mode that switch loads the 52-incident fleet, Demo 1 (INC0012345), and this capacity workflow.

If a capacity workflow for claims-db-01 already exists, turning the switch on again does not start a second one.

## Walk the forecast

1. Open **Capacity**. The Claims database card is at the top and stays on screen. Other host forecasts scroll underneath.
2. Read the card before any approval:
   - claims-db-01, Claims, tier-1
   - 80% and rising 4 points per hour, exhaustion in 5 hours
   - 1 forecast and 50 alerts grouped into 1 event
   - state **AWAITING APPROVAL**, with the line that the DBA card is waiting
3. Choose **Open the capacity workflow**. **Back** on that page returns here.
4. Read, in order:
   - **Forecast event** — the grouped event, HOST-CLAIMS-DB-01, 80%, 4 points per hour, 5 hours.
   - **Capacity and risk** — CI, Claims tier-1, CHG009880, and the three similar fixes.
   - **Certified runbook** — Purge logs older than seven days and extend the volume, medium risk, rollback defined, logs older than 7 days.
   - **DBA approval** — enter a reason, then **Approve** or **Reject**. **Approvals** shows the same pending card labeled DBA.
5. After approval the workflow leaves the card and shows:
   - **Before and after** — 80% → 60.8%, hours remaining, “No incident raised.”
   - **Execution** — the restricted-runner log for the pre-check, delete, extension, and post-check.
   - **Validation and notification** — utilization decreased, exhaustion beyond six hours, service healthy, no incident opened, plus the on-call DBA notice.
   - Standard change CHG0044101, state **closed**.
   - **Agents**, including validation: “Corrected before an incident or service impact. Utilization 80% to 60.8%. No incident was opened.”
6. Return to **Capacity**. The card badge is **PREVENTED**, with the same before-and-after line, the avoided-incident line, the measured time, and CHG0044101.

INC0012345 is a different host and a different workflow. This scenario does not add a row to the incident queue.

## What this console already shows

The DBA card for this database has already been approved. **Capacity** opens on the prevented result: 80% → 60.8%, no incident, prediction to remediation 48 seconds, change CHG0044101 closed. Open the workflow from that card to read the agent trail. There is no pending DBA card left on this run.

A new database stops at **AWAITING APPROVAL** until someone approves. With L4 enabled and the tenant set to L4, the same certified runbook finishes as **PREVENTED** without the card. This process does not have L4 enabled.

## What this demo does not do

- It does not raise a production incident. The prevented state is the result.
- It does not delete logs or extend a volume on a real host. Both steps are sandbox markers.
- It does not open CHG0044101 on a live ServiceNow instance. The simulator records that standard change, then closes it after validation.
- It does not let the capacity agent execute the runbook. Policy does that, and at L3 only after the DBA decision.
- It does not become a live capacity run because a connection was saved. The catalog load stays on fixtures.
