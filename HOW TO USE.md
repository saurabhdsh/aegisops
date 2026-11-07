# How to use AegisOps

AegisOps is the operator console for incident response and capacity prevention. ServiceNow holds the records. Dynatrace holds the telemetry. Agents investigate and recommend one certified runbook. The policy engine decides whether a person must approve. A restricted runner carries out the approved steps in a local sandbox. A model never authorizes an infrastructure action.

The console is [http://127.0.0.1:5173](http://127.0.0.1:5173). The API is [http://127.0.0.1:8000](http://127.0.0.1:8000). Opening the API root returns `Not Found`. Health is [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health). OpenAPI is [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Start the local console

Python 3.12 and Node are required. Nothing in this project starts a container.

```bash
./scripts/bootstrap.sh
```

That creates `.venv`, installs the package, copies `.env.example` to `.env` when needed, sets `APP_SECRET` when it is shorter than 32 characters, and migrates the database. It does not print the secret.

Put a bootstrap admin in `.env` before the first start if the user table is empty:

```bash
BOOTSTRAP_TENANT_SLUG=default
BOOTSTRAP_ADMIN_EMAIL=sre@example.com
BOOTSTRAP_ADMIN_PASSWORD=correct-horse-battery
EXECUTION_MODE=SIMULATOR
DATABASE_URL=sqlite:///./aegisops-ui.db
AUTONOMY_L4_ENABLED=false
```

The password above is the local demo account. Do not reuse it anywhere else.

Start the API and the worker:

```bash
./dev.sh
```

Start the console in another terminal:

```bash
./scripts/dev-web.sh
```

`./dev.sh` prints the API address and starts `workers.main`, which resumes workflows that are not waiting for approval and are not already finished. Ctrl-C stops the API and the worker together.

## Sign in

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

| Field | Local demo |
| --- | --- |
| Tenant | `default` |
| Email | `sre@example.com` |
| Password | `correct-horse-battery` |

The sidebar stays visible. Your name and role are at the bottom. The arrow next to the name signs you out.

Press Cmd-K (Ctrl-K on other keyboards) to jump to a page. Escape closes the palette.

**Back** appears on an incident record and on a workflow. It returns to the previous page. If you opened that URL directly, it returns to the incident queue.

## Incidents

This is the home page. The queue fills the screen. Search, priority chips (All, P1–P4), and state chips stay at the top. The list scrolls inside the page.

Each row shows the number, priority, state, title, service, host, and opened time. A violet workflow state means an agent workflow exists for that incident. Select the number or the title to open the ServiceNow record: description, CI, business service, work notes, and attached evidence. From there, open the agent workflow.

The fleet incidents INC10001–INC10052 are demo records. They appear only while **Demo load** is on. INC0012345 is the Claims investigation in [Demo 1](docs/Demo%201.md).

When a ServiceNow connection is saved, opening this page also reads up to 50 incidents from that instance and stores them beside the local rows. Demo rows stay while Demo load is on. A failed read is an error on the page. The board does not fill the gap with fixture incidents.

## RCA

**RCA** in the sidebar lists every incident on the board. INC0012345 is the investigated Claims workflow, with the change, log, recovery samples, and validation checks. Each other incident uses the Dynatrace samples already stored for its host, unless a Dynatrace connection is saved and the host is not a demo entity (`DEMO-`). In that case the page reads CPU and memory from Dynatrace and labels the source. The same ranker scores the points it received. An incident with no cause across the thresholds shows the chart and an empty cause list. The chart does not insert points between samples. A failed Dynatrace read stays an error and is not replaced with the demo chart. A model restates causes only after an investigation runs with a saved model.

## Approvals

A workflow creates a card only when policy requires a person.

- An incident runbook asks for the **on-call SRE**.
- The disk-capacity runbook asks for the **DBA**.

Type a reason, then **Approve** or **Reject**. The same card is also on the workflow page while the state is `AWAITING_APPROVAL`. Approving continues the sandbox pre-check, the action, and validation. Rejecting stops that path. An administrator can record either decision.

## Capacity

The Claims database card is the Demo 2 fixture. It shows that disk forecast, the grouped forecast and alerts, and a link to the capacity workflow. After the runbook finishes, the card shows the before-and-after utilization, whether an incident was avoided, the measured prediction-to-remediation time, and the standard change. Other host forecasts and configuration items scroll below the card.

When a Dynatrace connection is saved, this page reads live disk series for configuration items that are not demo hosts. A host needs at least two points. Demo disk rows stay available from the stored samples only while no Dynatrace connection is saved. A failed live read is an error. It is not replaced with the Claims fixture.

The full walkthrough is [Demo 2](docs/Demo%202.md).

## Topology

Services and configuration items for the tenant, drawn as a graph. With Demo load on, this includes the fleet plus the Claims application host and the Claims database host.

## Runbooks

Certified runbooks the remediation agent is allowed to select. Each row shows the name, version, whether rollback is defined, the checksum, who certified it, and which configuration items are in scope.

**Probe connectors** asks ServiceNow and Dynatrace for a health check. A saved connection is used. With none saved, `SIMULATOR` answers from fixtures. A failed live check stays an error.

The two certified runbooks used by the demos are:

- Restart Claims API and add one node
- Purge logs older than seven days and extend the volume

## Audit and controls

The control card shows the autonomy level and the emergency stop. Engage or clear it with a reason.

Emergency stop blocks new approvals and new executions. It does not claim that an action already sent to an external system has stopped.

The list under the card is the audit trail: sign-in, approvals, and control changes. Those rows cannot be edited or deleted.

## Settings

**Demo load** is the switch at the top. On, the board includes the prepared ServiceNow incidents and Dynatrace samples, and in simulator mode it also loads Demo 1 and Demo 2 if those workflows are not already stored. Off, the board hides demo rows. The stored rows remain. Turning the switch on again does not re-run a workflow that already exists.

Below the switch are the ServiceNow, Dynatrace, and model connection forms. The model form is **OpenAI** or **Azure OpenAI**. OpenAI takes an API key, a model, and an optional API base URL. Azure OpenAI takes the resource endpoint (`https://YOUR_RESOURCE.openai.azure.com`), the API key, the deployment name, and the API version. **Test** calls that provider's chat API. A failed call stays an error and is recorded as the last health check. Saving a blank secret keeps the secret already stored. Secret values are not shown again after you save them. Testing a connection does not change `EXECUTION_MODE`.

When a key and a model or deployment are saved, the RCA agent asks that model to restate the causes the ranker already produced. This happens in every execution mode, including `SIMULATOR`. A saved ServiceNow or Dynatrace connection is used as well. The two demo catalogs stay on fixtures. The model cannot add a cause or approve an action. If the call fails, the ranked causes stay and the error is stored on the RCA row.

## How a workflow moves

1. A Dynatrace problem or forecast is grouped and enriched from ServiceNow and Dynatrace.
2. The remediation agent selects one certified runbook. It does not execute it.
3. The policy engine decides. L3 holds the action for the required role. L4 can run a certified medium-risk runbook that has a rollback, and only when `AUTONOMY_L4_ENABLED` is true. This process leaves that flag false. High-risk actions stay on an approval card at every level.
4. After the gate, the restricted runner performs the pre-check and the action inside a sandbox. It is not the Ansible CLI. `LIVE` refuses this local runner.
5. Validation compares the measured result with the checks for that scenario, writes evidence, and notifies the operator console.

## Agents

Eight agents are written and executed by the workflow engine. Each one is a `BaseAgent` class under `packages/agents/`. None of them is allowed to mutate infrastructure. The engine stores every run as an agent row with a status, a summary, the tool calls, and the latency. The ranker decides the causes. A saved OpenAI or Azure OpenAI key is used only to restate those causes. It cannot add a cause or approve an action.

| Agent | Class | What it does | Used by |
| --- | --- | --- | --- |
| Incident Goal Agent | `IncidentGoalAgent` | Opens the workflow and records the child agents. It does not execute a runbook. | Demo 1 and Demo 2 |
| Triage Agent | `TriageAgent` | Reads the ServiceNow incident, configuration item, business service, priority, recent changes, similar incidents, and work notes. Work notes stay untrusted and are not signals. | Demo 1 |
| RCA Agent | `RCAAgent` | Reads Dynatrace CPU, memory, logs, and traces, then ranks causes from the measured slopes. The scores are not calibrated probabilities. | Demo 1 |
| Event Correlation Agent | `EventCorrelationAgent` | Groups events that share an entity, a symptom, and a 30-minute window. It does not invent extra alerts. | Demo 2 |
| Capacity and Risk Agent | `CapacityRiskAgent` | Reads the Dynatrace disk series and attaches the CI, tier, recent changes, growth trend, hours to exhaustion, and similar fixes. | Demo 2 |
| Remediation Agent | `RemediationAgent` | Selects one certified runbook and its allowlisted parameters. It stops there. It does not run the playbook. | Demo 1 and Demo 2 |
| Governance Agent | `GovernanceAgent` | Explains the policy-engine decision, including why a human is required. It does not authorize the action. | Demo 1 and Demo 2 |
| Validation Agent | `ValidationAgent` | Compares the measured result with the checks for that workflow, then records evidence and the operator notification. | Demo 1 and Demo 2 |

On a Claims incident the goal agent names triage, RCA, remediation, validation, and governance. On the disk forecast it names event correlation, capacity and risk, remediation, validation, and governance. The **Agents** section at the bottom of a workflow page is the record of the run you are looking at.

## Execution mode

`EXECUTION_MODE` in `.env` is `SIMULATOR`, `SANDBOX`, or `LIVE`.

| Mode | What it uses |
| --- | --- |
| `SIMULATOR` | Fixtures, until a ServiceNow or Dynatrace connection is saved. A saved connection is used for that system. The two demo catalogs stay on fixtures. A saved OpenAI or Azure OpenAI key restates RCA causes. A failed live call stays an error. |
| `SANDBOX` | The saved connection settings. It refuses a production configuration item. |
| `LIVE` | The saved ServiceNow, Dynatrace, and OpenAI settings. A failed call stays an error. The process does not fall back to fixtures. The local runbook runner is not used. |

Changing the mode means restarting the API. The Settings test button does not switch the mode.

## A saved connection is not the demo

The screens stay the same. The records come from the system you saved.

With no ServiceNow or Dynatrace connection, the console reads the local samples. **Demo load**, in `SIMULATOR`, fills those samples from the two fixture catalogs. Saving a connection does not replay INC0012345 or the disk forecast inside your tenant.

After a connection is complete, that system is called even while the process is still `SIMULATOR`:

- The incident board adds up to 50 ServiceNow incidents and keeps the demo rows while Demo load is on.
- An investigation, an approval continuation, and the worker use the saved clients. Loading Demo 1 or Demo 2 does not.
- RCA for a finished workflow shows that stored investigation. RCA for another host reads Dynatrace when the entity is not a `DEMO-` host.
- Capacity reads live disk series for configuration items that are not demo hosts.
- Runbook **Probe connectors** and the Settings **Test** buttons call the saved connection.
- Webhooks accept the secret saved on the connection when one is stored. Otherwise they use the secret in the environment.

These parts stay as they are in the demo:

- INC0012345, INC10001–INC10052, and the Claims disk card are fixture stories. They are not created in your tenant by saving a URL.
- The certified incident runbook is still **Restart Claims API and add one node**. A CPU or memory cause can select it. The local runner writes sandbox markers. It does not restart a process on the host. `LIVE` refuses that runner. `SANDBOX` refuses a production configuration item.
- A failed ServiceNow or Dynatrace call stays an error. The page does not substitute fixture numbers.
- A saved model only restates causes the ranker already scored. It does not choose the runbook.

## The two demos

- [Demo 1](docs/Demo%201.md) — Claims API CPU and memory saturation, incident INC0012345, on-call SRE approval.
- [Demo 2](docs/Demo%202.md) — Claims database disk forecast, DBA approval, no incident opened.
- [Using the UI only](docs/Using%20the%20UI%20only.md) — keep this console and serve it from your own agents and API.

## Checks

```bash
pytest tests/ -v
```

Run that from the repository root with `.venv` active.

## What this console does not do

- It does not change a production ServiceNow instance or a production host.
- It does not enable L4 by itself.
- It does not treat a work note, a forecast, or a model sentence as permission to act.
- It does not claim an emergency stop has halted an action that already left this process.
