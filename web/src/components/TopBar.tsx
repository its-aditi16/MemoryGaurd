import { Bug, Globe, HeartPulse, RotateCcw, ShieldCheck, ShieldOff } from "lucide-react";
import type { Metrics } from "../api";
import { Button } from "./ui";

interface Props {
  metrics: Metrics | null;
  busy: string | null;
  canHeal: boolean;
  onInject: (attack: string) => void;
  onHeal: () => void;
  onReset: () => void;
  onToggleGuard: () => void;
}

export function TopBar({ metrics, busy, canHeal, onInject, onHeal, onReset, onToggleGuard }: Props) {
  const incident = metrics?.incident_active;
  const guardOn = metrics?.guard_enabled ?? true;
  return (
    <header className="flex h-14 items-center justify-between border-b border-line px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15">
            <ShieldCheck className="h-4 w-4 text-accent" />
          </div>
          <span className="text-[15px] font-semibold tracking-tight text-white">MemoryGuard</span>
        </div>

        <span
          className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${
            incident ? "border-bad/40 bg-bad/10 text-red-300" : "border-clean/30 bg-clean/10 text-emerald-300"
          }`}
        >
          <span className="relative flex h-2 w-2">
            {incident && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-bad opacity-75" />}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${incident ? "bg-bad" : "bg-clean"}`} />
          </span>
          {incident ? "Incident active" : "All clear"}
        </span>

        <span className="rounded-md border border-line px-2 py-0.5 text-[11px] font-medium text-gray-400">
          Memory: <span className="text-gray-200 capitalize">{metrics?.backend ?? "…"}</span>
        </span>
        <span className="rounded-md border border-line px-2 py-0.5 text-[11px] font-medium text-gray-400">
          LLM: <span className="text-gray-200">{metrics?.llm ?? "…"}</span>
        </span>
        <button
          type="button"
          onClick={onToggleGuard}
          title="Toggle MemoryGuard protection (turn off to prove the threat)"
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors ${
            guardOn ? "border-line text-gray-300 hover:bg-white/5" : "border-flag/50 bg-flag/10 text-amber-300"
          }`}
        >
          {guardOn ? <ShieldCheck className="h-3 w-3" /> : <ShieldOff className="h-3 w-3" />}
          {guardOn ? "Protection on" : "Protection off"}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <Button onClick={() => onInject("a1")} loading={busy === "a1"} icon={<Bug className="h-3.5 w-3.5" />}
          title={metrics?.attacks?.a1}>
          Inject A1
        </Button>
        <Button onClick={() => onInject("a2")} loading={busy === "a2"} icon={<Globe className="h-3.5 w-3.5" />}
          title={metrics?.attacks?.a2}>
          Inject A2
        </Button>
        <Button onClick={onHeal} loading={busy === "heal"} disabled={!canHeal} variant="primary"
          icon={<HeartPulse className="h-3.5 w-3.5" />}>
          Heal
        </Button>
        <Button onClick={onReset} loading={busy === "reset"} icon={<RotateCcw className="h-3.5 w-3.5" />}>
          Reset
        </Button>
      </div>
    </header>
  );
}
