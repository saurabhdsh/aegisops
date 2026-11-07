import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearSession, currentUser } from "../lib/api";
import { CommandPalette } from "./CommandPalette";

const LINKS = [
  ["/incidents", "Incidents"],
  ["/rca", "RCA"],
  ["/approvals", "Approvals"],
  ["/capacity", "Capacity"],
  ["/topology", "Topology"],
  ["/runbooks", "Runbooks"],
  ["/audit", "Audit"],
  ["/settings", "Settings"],
] as const;

function parentPath(pathname: string): string | null {
  if (pathname.startsWith("/incidents/")) return "/incidents";
  if (pathname.startsWith("/workflows/")) return "/incidents";
  return null;
}

function BackButton() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const parent = parentPath(pathname);
  if (!parent) return null;
  const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
  return (
    <button
      type="button"
      onClick={() => {
        if (idx > 0) navigate(-1);
        else if (parent) navigate(parent);
      }}
      className="mb-4 inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--bg-elev)] px-2.5 py-1.5 text-[13px] font-medium text-[var(--ink)] hover:border-[var(--violet)]"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
      Back
    </button>
  );
}

function initials(name: string): string {
  const parts = name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export function Shell() {
  const navigate = useNavigate();
  const user = currentUser();
  const display = user?.display_name || user?.email || "";
  const handle = user?.email?.split("@")[0] || "";

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <CommandPalette />
      <div className="grid h-screen grid-cols-[220px_1fr] overflow-hidden">
        <aside className="sticky top-0 flex h-screen flex-col border-r border-[var(--line)] bg-[var(--bg-muted)]">
          <div className="shrink-0 px-6 py-6">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--ink-faint)]">Operations</div>
            <div className="mt-0.5 text-[17px] font-semibold text-[var(--ink)]" style={{ letterSpacing: "-0.022em" }}>
              AegisOps
            </div>
          </div>
          <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2">
            {LINKS.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? "bg-[var(--bg-elev)] text-[var(--ink)] shadow-[var(--shadow-sm)]"
                      : "text-[var(--ink-muted)] hover:bg-[var(--bg-elev)]/70 hover:text-[var(--ink)]"
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="shrink-0 border-t border-[var(--line)] px-4 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--violet)] text-[11px] font-semibold tracking-wide text-white">
                {initials(display || "A")}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold text-[var(--ink)]">{display}</div>
                <div className="truncate text-[11px] text-[var(--ink-muted)]">
                  {user?.roles?.[0] || "operator"} · @{handle}
                </div>
              </div>
              <button
                type="button"
                title="Sign out"
                className="shrink-0 rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-[var(--bg-elev)] hover:text-[var(--ink)]"
                onClick={() => {
                  clearSession();
                  navigate("/login");
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M9 6H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3" />
                  <path d="M14 16l4-4-4-4" />
                  <path d="M18 12H9" />
                </svg>
              </button>
            </div>
          </div>
        </aside>
        <div className="flex min-h-0 min-w-0 flex-col">
          <header className="glass flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-[var(--line)] px-6 py-3">
            <div className="whitespace-nowrap text-[13px] font-medium text-[var(--ink-muted)]">Enterprise agentic operations</div>
          </header>
          <main className="min-h-0 flex-1 overflow-auto px-6 py-5">
            <BackButton />
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
