import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

const DESTINATIONS = [
  { label: "Incidents", path: "/incidents" },
  { label: "Root cause analysis", path: "/rca" },
  { label: "Approvals", path: "/approvals" },
  { label: "Capacity", path: "/capacity" },
  { label: "Topology", path: "/topology" },
  { label: "Runbooks", path: "/runbooks" },
  { label: "Audit and controls", path: "/audit" },
  { label: "Settings", path: "/settings" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const matches = useMemo(
    () => DESTINATIONS.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase())),
    [query],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;
  const go = (path: string) => {
    setOpen(false);
    setQuery("");
    navigate(path);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-28" onClick={() => setOpen(false)}>
      <div className="w-full max-w-xl rounded-2xl border border-[var(--line)] bg-[var(--bg-elev)] p-3 shadow-[var(--shadow)]" onClick={(event) => event.stopPropagation()}>
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Go to a screen"
          className="w-full rounded-xl bg-[var(--bg-muted)] px-4 py-3 text-[14px] outline-none"
        />
        <div className="mt-3 space-y-1 text-[13px]">
          {matches.length === 0 ? (
            <p className="px-3 py-2 text-[var(--ink-muted)]">No matching screen.</p>
          ) : (
            matches.map((item) => (
              <button key={item.path} className="block w-full rounded-lg px-3 py-2 text-left hover:bg-[var(--bg-muted)]" onClick={() => go(item.path)}>
                {item.label}
              </button>
            ))
          )}
        </div>
        <div className="mono mt-2 px-3 pb-1 text-[10px] uppercase tracking-[0.16em] text-[var(--ink-muted)]">⌘K</div>
      </div>
    </div>
  );
}
