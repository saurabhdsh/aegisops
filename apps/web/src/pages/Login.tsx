import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, ErrorNote, Field, inputClass } from "../components/ui";
import { api, saveSession, token } from "../lib/api";

export function Login() {
  const navigate = useNavigate();
  const [tenant, setTenant] = useState("default");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (token()) return <Navigate to="/incidents" replace />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = await api<{ access_token: string; user: object }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ tenant_slug: tenant, email, password }),
      });
      saveSession(body.access_token, body.user);
      navigate("/incidents");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen sm:grid-cols-[38%_62%]">
      <section className="flex flex-col justify-end bg-[#090a0c] px-8 py-10 sm:px-12 sm:pb-12">
        <div>
          <div className="text-[15px] font-semibold uppercase tracking-[0.24em] text-white/40">AegisOps</div>
          <h1 className="mt-2 text-5xl font-semibold leading-tight text-white" style={{ letterSpacing: "-0.025em" }}>
            Agentic
            <br />
            operations
          </h1>
          <p className="mt-4 max-w-xs text-[15px] text-white/50">Evidence first. Policy decides. Execution stays inside the sandbox.</p>
        </div>
      </section>
      <section className="flex items-center justify-center bg-[var(--bg)] p-8">
        <form className="w-full max-w-[340px] space-y-5" onSubmit={submit}>
          <div className="mb-8">
            <h2 className="text-[28px] font-semibold text-[var(--ink)]" style={{ letterSpacing: "-0.022em" }}>
              Sign in
            </h2>
            <p className="mt-1 text-[14px] text-[var(--ink-muted)]">Use your tenant, email, and password.</p>
          </div>
          <Field label="Tenant">
            <input className={inputClass} value={tenant} onChange={(event) => setTenant(event.target.value)} autoComplete="organization" />
          </Field>
          <Field label="Email">
            <input className={inputClass} value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
          </Field>
          <Field label="Password">
            <input className={inputClass} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </Field>
          {error ? <ErrorNote message={error} /> : null}
          <Button disabled={busy} className="w-full" type="submit">
            {busy ? "Signing in" : "Continue"}
          </Button>
        </form>
      </section>
    </div>
  );
}
