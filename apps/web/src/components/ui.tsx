import type { ButtonHTMLAttributes, ReactNode } from "react";

const BADGE: Record<string, string> = {
  RESOLVED: "bg-[rgba(125,206,160,0.14)] text-[var(--mint)] border border-[rgba(125,206,160,0.35)]",
  resolved: "bg-[rgba(125,206,160,0.14)] text-[var(--mint)] border border-[rgba(125,206,160,0.35)]",
  open: "bg-[rgba(226,163,58,0.14)] text-[var(--amber)] border border-[rgba(226,163,58,0.35)]",
  in_progress: "bg-[rgba(111,191,201,0.14)] text-[var(--cyan)] border border-[rgba(111,191,201,0.35)]",
  on_hold: "bg-[rgba(232,234,237,0.08)] text-[var(--titanium)] border border-[var(--line)]",
  passed: "bg-[rgba(125,206,160,0.14)] text-[var(--mint)] border border-[rgba(125,206,160,0.35)]",
  approved: "bg-[rgba(125,206,160,0.14)] text-[var(--mint)] border border-[rgba(125,206,160,0.35)]",
  PREVENTED: "bg-[rgba(111,191,201,0.14)] text-[var(--cyan)] border border-[rgba(111,191,201,0.35)]",
  AWAITING_APPROVAL: "bg-[rgba(226,163,58,0.14)] text-[var(--amber)] border border-[rgba(226,163,58,0.35)]",
  pending: "bg-[rgba(226,163,58,0.14)] text-[var(--amber)] border border-[rgba(226,163,58,0.35)]",
  FAILED: "bg-[rgba(224,122,106,0.14)] text-[var(--coral)] border border-[rgba(224,122,106,0.35)]",
  ESCALATED: "bg-[rgba(224,122,106,0.14)] text-[var(--coral)] border border-[rgba(224,122,106,0.35)]",
  rejected: "bg-[rgba(224,122,106,0.14)] text-[var(--coral)] border border-[rgba(224,122,106,0.35)]",
};

export function Badge({ value }: { value: string }) {
  const tone = BADGE[value] ?? "border border-[var(--line)] bg-[var(--violet-soft)] text-[var(--violet)]";
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${tone}`}>{value.replaceAll("_", " ")}</span>;
}

export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--line)] p-14 text-center">
      <div className="text-xl font-semibold text-[var(--ink)]">{title}</div>
      <p className="mx-auto mt-2 max-w-md text-[13px] text-[var(--ink-muted)]">{detail}</p>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <div className="rounded-xl border border-[rgba(224,122,106,0.4)] bg-[rgba(224,122,106,0.1)] p-4 text-[13px] text-[var(--coral)]">{message}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium text-[var(--ink-muted)]">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-[14px] text-[var(--ink)] outline-none transition focus:border-[var(--violet)] focus:ring-2 focus:ring-[var(--violet-soft)]";

export function Button({
  children,
  tone = "violet",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "violet" | "quiet" }) {
  const color =
    tone === "violet"
      ? "bg-[var(--violet)] text-white hover:brightness-110"
      : "border border-[var(--line)] bg-transparent text-[var(--ink)] hover:bg-[var(--bg-muted)]";
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-[13px] font-medium transition-all disabled:opacity-40 ${color} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
