import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-card shadow-[0_1px_2px_rgba(0,0,0,0.4)] ${className}`}>
      {children}
    </section>
  );
}

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 pt-4 pb-3">
      <h2 className="text-[11px] font-semibold tracking-[0.12em] text-gray-400 uppercase">{children}</h2>
      {right}
    </div>
  );
}

// Status colours carry meaning only: clean / flagged / tainted+blocked / quarantined.
export const STATUS_STYLE: Record<string, { label: string; dot: string; text: string; ring: string }> = {
  clean: { label: "Clean", dot: "bg-clean", text: "text-clean", ring: "border-clean/40" },
  live: { label: "Live", dot: "bg-clean", text: "text-clean", ring: "border-clean/40" },
  drafted: { label: "Drafted", dot: "bg-clean", text: "text-clean", ring: "border-clean/40" },
  flagged: { label: "Flagged", dot: "bg-flag", text: "text-flag", ring: "border-flag/40" },
  held: { label: "Held", dot: "bg-flag", text: "text-flag", ring: "border-flag/40" },
  tainted: { label: "Tainted", dot: "bg-bad", text: "text-bad", ring: "border-bad/40" },
  blocked: { label: "Blocked", dot: "bg-bad", text: "text-bad", ring: "border-bad/40" },
  quarantined: { label: "Quarantined", dot: "bg-quar", text: "text-quar", ring: "border-quar/40" },
  superseded: { label: "Superseded", dot: "bg-quar", text: "text-quar", ring: "border-quar/40" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.clean;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border ${s.ring} px-2 py-0.5 text-[11px] font-medium ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

type Variant = "primary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-indigo-500 border-transparent",
  ghost: "bg-transparent text-gray-200 hover:bg-white/5 border-line",
  danger: "bg-transparent text-red-300 hover:bg-bad/10 border-bad/40",
};

export function Button({
  children, onClick, loading, disabled, variant = "ghost", icon, title,
}: {
  children: ReactNode;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: Variant;
  icon?: ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || loading}
      className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]}`}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function trustTone(trust: number): string {
  if (trust >= 0.8) return "border-clean/40 text-emerald-300";
  if (trust >= 0.5) return "border-line text-gray-300";
  return "border-flag/50 text-amber-300";
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center px-6 text-center text-sm text-gray-500">{children}</div>;
}
