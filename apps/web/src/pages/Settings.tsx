import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button, ErrorNote, Field, inputClass } from "../components/ui";

type ConnectionView = {
  execution_mode: string;
  servicenow: {
    instance_url: string;
    auth_mode: string;
    client_id: string;
    username: string;
    table_incident: string;
    table_ci: string;
    table_change: string;
    has_client_secret: boolean;
    has_access_token: boolean;
    has_password: boolean;
    has_webhook_secret: boolean;
    last_health_status: string;
    last_error: string;
  };
  dynatrace: {
    environment_url: string;
    has_api_token: boolean;
    has_webhook_secret: boolean;
    last_health_status: string;
    last_error: string;
  };
  openai: {
    provider: string;
    base_url: string;
    model: string;
    api_version: string;
    has_api_key: boolean;
    last_health_status: string;
    last_error: string;
  };
};

type OpenAiForm = {
  provider: string;
  base_url: string;
  model: string;
  api_version: string;
  api_key: string;
};

const emptyModel: OpenAiForm = {
  provider: "openai",
  base_url: "",
  model: "",
  api_version: "2024-10-21",
  api_key: "",
};

type SnowForm = {
  instance_url: string;
  auth_mode: string;
  client_id: string;
  client_secret: string;
  access_token: string;
  username: string;
  password: string;
  webhook_secret: string;
  table_incident: string;
  table_ci: string;
  table_change: string;
};

const emptySnow: SnowForm = {
  instance_url: "",
  auth_mode: "oauth",
  client_id: "",
  client_secret: "",
  access_token: "",
  username: "",
  password: "",
  webhook_secret: "",
  table_incident: "incident",
  table_ci: "cmdb_ci",
  table_change: "change_request",
};

export function Settings() {
  const [view, setView] = useState<ConnectionView | null>(null);
  const [snow, setSnow] = useState<SnowForm>(emptySnow);
  const [dynaUrl, setDynaUrl] = useState("");
  const [dynaToken, setDynaToken] = useState("");
  const [dynaWebhook, setDynaWebhook] = useState("");
  const [model, setModel] = useState<OpenAiForm>(emptyModel);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [demo, setDemo] = useState(false);
  const [demoCount, setDemoCount] = useState(0);

  function apply(body: ConnectionView) {
    setView(body);
    setSnow((current) => ({
      ...current,
      instance_url: body.servicenow.instance_url,
      auth_mode: body.servicenow.auth_mode || "oauth",
      client_id: body.servicenow.client_id,
      username: body.servicenow.username,
      table_incident: body.servicenow.table_incident,
      table_ci: body.servicenow.table_ci,
      table_change: body.servicenow.table_change,
      client_secret: "",
      access_token: "",
      password: "",
      webhook_secret: "",
    }));
    setDynaUrl(body.dynatrace.environment_url);
    setDynaToken("");
    setDynaWebhook("");
    setModel({
      provider: body.openai.provider || "openai",
      base_url: body.openai.base_url,
      model: body.openai.model,
      api_version: body.openai.api_version || "2024-10-21",
      api_key: "",
    });
  }

  useEffect(() => {
    api<ConnectionView>("/api/v1/settings/connections")
      .then(apply)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
    api<{ enabled: boolean; incident_count: number }>("/api/v1/settings/connections/demo")
      .then((body) => {
        setDemo(body.enabled);
        setDemoCount(body.incident_count);
      })
      .catch(() => undefined);
  }, []);

  async function toggleDemo() {
    setBusy("demo");
    setError("");
    setNotice("");
    try {
      const body = await api<{ enabled: boolean; incident_count: number }>("/api/v1/settings/connections/demo", {
        method: "PUT",
        body: JSON.stringify({ enabled: !demo }),
      });
      setDemo(body.enabled);
      setDemoCount(body.incident_count);
      setNotice(body.enabled ? `${body.incident_count} ServiceNow incidents and their Dynatrace samples are loaded.` : "Demo records are hidden.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Demo switch failed");
    } finally {
      setBusy("");
    }
  }

  async function saveSnow() {
    setBusy("snow-save");
    setError("");
    setNotice("");
    try {
      apply(await api<ConnectionView>("/api/v1/settings/connections/servicenow", { method: "PUT", body: JSON.stringify(snow) }));
      setNotice("ServiceNow settings saved. Secrets stay on the server.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function testSnow() {
    setBusy("snow-test");
    setError("");
    setNotice("");
    try {
      const report = await api<{ status: string; capabilities?: Record<string, boolean> }>("/api/v1/settings/connections/servicenow/test", { method: "POST" });
      setNotice(`ServiceNow responded ${report.status}. Table API ${report.capabilities?.table_api ? "available" : "not confirmed"}.`);
      apply(await api<ConnectionView>("/api/v1/settings/connections"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ServiceNow test failed");
      api<ConnectionView>("/api/v1/settings/connections").then(apply).catch(() => undefined);
    } finally {
      setBusy("");
    }
  }

  async function saveDyna() {
    setBusy("dyna-save");
    setError("");
    setNotice("");
    try {
      apply(
        await api<ConnectionView>("/api/v1/settings/connections/dynatrace", {
          method: "PUT",
          body: JSON.stringify({ environment_url: dynaUrl, api_token: dynaToken, webhook_secret: dynaWebhook }),
        }),
      );
      setNotice("Dynatrace settings saved. The API token is not shown again.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function testDyna() {
    setBusy("dyna-test");
    setError("");
    setNotice("");
    try {
      const report = await api<{ status: string; capabilities?: Record<string, string> }>("/api/v1/settings/connections/dynatrace/test", { method: "POST" });
      setNotice(`Dynatrace responded ${report.status}. Traces ${report.capabilities?.traces || "unknown"}.`);
      apply(await api<ConnectionView>("/api/v1/settings/connections"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Dynatrace test failed");
      api<ConnectionView>("/api/v1/settings/connections").then(apply).catch(() => undefined);
    } finally {
      setBusy("");
    }
  }

  async function saveModel() {
    setBusy("model-save");
    setError("");
    setNotice("");
    try {
      apply(await api<ConnectionView>("/api/v1/settings/connections/openai", { method: "PUT", body: JSON.stringify(model) }));
      setNotice("Model settings saved. The API key is not shown again.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function testModel() {
    setBusy("model-test");
    setError("");
    setNotice("");
    try {
      const report = await api<{ status: string; provider?: string; model?: string }>("/api/v1/settings/connections/openai/test", { method: "POST" });
      setNotice(`${report.provider === "azure" ? "Azure OpenAI" : "OpenAI"} responded ${report.status}${report.model ? ` · ${report.model}` : ""}.`);
      apply(await api<ConnectionView>("/api/v1/settings/connections"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Model test failed");
      api<ConnectionView>("/api/v1/settings/connections").then(apply).catch(() => undefined);
    } finally {
      setBusy("");
    }
  }

  const secretHint = "Leave blank to keep the saved value.";
  const azure = model.provider === "azure";

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl">Settings</h1>
      <p className="mt-1 text-sm text-[var(--ink-muted)]">
        Connect ServiceNow, Dynatrace, and OpenAI or Azure OpenAI, or load the prepared operations fleet.
      </p>
      <section className="card mt-6 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[17px] font-semibold">Demo load</h2>
          <button
            type="button"
            role="switch"
            aria-checked={demo}
            aria-label="Demo load"
            disabled={busy !== ""}
            onClick={toggleDemo}
            className={`box-border flex h-8 w-14 shrink-0 items-center overflow-hidden rounded-full p-1 transition-colors ${demo ? "justify-end bg-[var(--violet)]" : "justify-start bg-[var(--line)]"}`}
          >
            <span className="block h-6 w-6 shrink-0 rounded-full bg-white" />
          </button>
        </div>
        <p className="mt-2 text-[13px] text-[var(--ink-muted)]">
          {demo ? `${demoCount} ServiceNow incidents with Dynatrace problems and host metrics are on the board.` : "Off. The board shows only records from the connected systems."}
        </p>
      </section>
      {notice ? <p className="mt-4 text-sm text-[var(--cyan)]">{notice}</p> : null}
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}

      <section className="card mt-8 p-5">
        <h2 className="text-[17px] font-semibold">ServiceNow</h2>
        <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
          Last check: {view?.servicenow.last_health_status || "unknown"}
          {view?.servicenow.last_error ? ` · ${view.servicenow.last_error}` : ""}
        </p>
        <div className="mt-4 space-y-4">
          <Field label="Instance URL">
            <input className={inputClass} placeholder="https://example.service-now.com" value={snow.instance_url} onChange={(event) => setSnow({ ...snow, instance_url: event.target.value })} />
          </Field>
          <Field label="Authentication">
            <select className={inputClass} value={snow.auth_mode} onChange={(event) => setSnow({ ...snow, auth_mode: event.target.value })}>
              <option value="oauth">OAuth client credentials</option>
              <option value="token">Bearer token</option>
              <option value="basic">Username and password</option>
            </select>
          </Field>
          {snow.auth_mode === "oauth" ? (
            <>
              <Field label="Client ID">
                <input className={inputClass} value={snow.client_id} onChange={(event) => setSnow({ ...snow, client_id: event.target.value })} />
              </Field>
              <Field label={`Client secret${view?.servicenow.has_client_secret ? " · saved" : ""}`}>
                <input className={inputClass} type="password" placeholder={secretHint} value={snow.client_secret} onChange={(event) => setSnow({ ...snow, client_secret: event.target.value })} />
              </Field>
            </>
          ) : null}
          {snow.auth_mode === "token" || snow.auth_mode === "oauth" ? (
            <Field label={`Access token${view?.servicenow.has_access_token ? " · saved" : ""}`}>
              <input className={inputClass} type="password" placeholder={snow.auth_mode === "oauth" ? "Optional when client credentials are set" : secretHint} value={snow.access_token} onChange={(event) => setSnow({ ...snow, access_token: event.target.value })} />
            </Field>
          ) : null}
          {snow.auth_mode === "basic" ? (
            <>
              <Field label="Username">
                <input className={inputClass} value={snow.username} onChange={(event) => setSnow({ ...snow, username: event.target.value })} />
              </Field>
              <Field label={`Password${view?.servicenow.has_password ? " · saved" : ""}`}>
                <input className={inputClass} type="password" placeholder={secretHint} value={snow.password} onChange={(event) => setSnow({ ...snow, password: event.target.value })} />
              </Field>
            </>
          ) : null}
          <Field label={`Webhook secret${view?.servicenow.has_webhook_secret ? " · saved" : ""}`}>
            <input className={inputClass} type="password" placeholder={secretHint} value={snow.webhook_secret} onChange={(event) => setSnow({ ...snow, webhook_secret: event.target.value })} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Incident table">
              <input className={inputClass} value={snow.table_incident} onChange={(event) => setSnow({ ...snow, table_incident: event.target.value })} />
            </Field>
            <Field label="CI table">
              <input className={inputClass} value={snow.table_ci} onChange={(event) => setSnow({ ...snow, table_ci: event.target.value })} />
            </Field>
            <Field label="Change table">
              <input className={inputClass} value={snow.table_change} onChange={(event) => setSnow({ ...snow, table_change: event.target.value })} />
            </Field>
          </div>
        </div>
        <div className="mt-5 flex gap-2">
          <Button disabled={busy !== ""} onClick={saveSnow}>{busy === "snow-save" ? "Saving" : "Save ServiceNow"}</Button>
          <Button tone="quiet" disabled={busy !== ""} onClick={testSnow}>{busy === "snow-test" ? "Testing" : "Test ServiceNow"}</Button>
        </div>
      </section>

      <section className="card mt-6 p-5">
        <h2 className="text-[17px] font-semibold">Dynatrace</h2>
        <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
          Last check: {view?.dynatrace.last_health_status || "unknown"}
          {view?.dynatrace.last_error ? ` · ${view.dynatrace.last_error}` : ""}
        </p>
        <div className="mt-4 space-y-4">
          <Field label="Environment URL">
            <input className={inputClass} placeholder="https://abc12345.live.dynatrace.com" value={dynaUrl} onChange={(event) => setDynaUrl(event.target.value)} />
          </Field>
          <Field label={`API token${view?.dynatrace.has_api_token ? " · saved" : ""}`}>
            <input className={inputClass} type="password" placeholder={secretHint} value={dynaToken} onChange={(event) => setDynaToken(event.target.value)} />
          </Field>
          <Field label={`Webhook secret${view?.dynatrace.has_webhook_secret ? " · saved" : ""}`}>
            <input className={inputClass} type="password" placeholder={secretHint} value={dynaWebhook} onChange={(event) => setDynaWebhook(event.target.value)} />
          </Field>
        </div>
        <div className="mt-5 flex gap-2">
          <Button disabled={busy !== ""} onClick={saveDyna}>{busy === "dyna-save" ? "Saving" : "Save Dynatrace"}</Button>
          <Button tone="quiet" disabled={busy !== ""} onClick={testDyna}>{busy === "dyna-test" ? "Testing" : "Test Dynatrace"}</Button>
        </div>
      </section>

      <section className="card mt-6 p-5">
        <h2 className="text-[17px] font-semibold">OpenAI</h2>
        <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
          The model only restates causes the ranker already produced. It cannot approve an action.
          Last check: {view?.openai.last_health_status || "unknown"}
          {view?.openai.last_error ? ` · ${view.openai.last_error}` : ""}
        </p>
        <div className="mt-4 space-y-4">
          <Field label="Provider">
            <select
              className={inputClass}
              value={model.provider}
              onChange={(event) => {
                const provider = event.target.value;
                setModel({
                  ...model,
                  provider,
                  base_url: provider === "azure" && model.base_url === "https://api.openai.com/v1" ? "" : model.base_url,
                });
              }}
            >
              <option value="openai">OpenAI</option>
              <option value="azure">Azure OpenAI</option>
            </select>
          </Field>
          <Field label={azure ? "Azure endpoint" : "API base URL"}>
            <input
              className={inputClass}
              placeholder={azure ? "https://YOUR_RESOURCE.openai.azure.com" : "https://api.openai.com/v1"}
              value={model.base_url}
              onChange={(event) => setModel({ ...model, base_url: event.target.value })}
            />
          </Field>
          <Field label={azure ? "Deployment name" : "Model"}>
            <input
              className={inputClass}
              placeholder={azure ? "claims-narrator" : "gpt-4o-mini"}
              value={model.model}
              onChange={(event) => setModel({ ...model, model: event.target.value })}
            />
          </Field>
          {azure ? (
            <Field label="API version">
              <input className={inputClass} value={model.api_version} onChange={(event) => setModel({ ...model, api_version: event.target.value })} />
            </Field>
          ) : null}
          <Field label={`API key${view?.openai.has_api_key ? " · saved" : ""}`}>
            <input className={inputClass} type="password" placeholder={secretHint} value={model.api_key} onChange={(event) => setModel({ ...model, api_key: event.target.value })} />
          </Field>
        </div>
        <div className="mt-5 flex gap-2">
          <Button disabled={busy !== ""} onClick={saveModel}>{busy === "model-save" ? "Saving" : "Save OpenAI"}</Button>
          <Button tone="quiet" disabled={busy !== ""} onClick={testModel}>{busy === "model-test" ? "Testing" : "Test OpenAI"}</Button>
        </div>
      </section>
    </div>
  );
}
