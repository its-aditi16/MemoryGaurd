import { Banknote, Bug, Clapperboard, Columns2, Eye, FlaskConical, Globe, HeartPulse, Laptop, Lock, MailWarning,
  RotateCcw, ScanSearch, ShieldCheck, ShieldOff, TriangleAlert, UserCog } from "lucide-react";
import type { AgentId, Metrics } from "../api";
import { Button } from "./ui";

const ATTACK_BUTTONS: Record<string, { label: string; Icon: typeof Bug }> = {
  a1: { label: "A1 fake bank", Icon: Bug },
  a2: { label: "A2 hidden", Icon: Globe },
  a3: { label: "A3 data leak", Icon: MailWarning },
  a4: { label: "A4 fake admin", Icon: UserCog },
};

interface Props {
  metrics: Metrics | null;
  busy: string | null;
  canHeal: boolean;
  autopilot: boolean;
  onInject: (attack: string) => void;
  onHeal: () => void;
  onReset: () => void;
  onToggleGuard: () => void;
  onToggleEnforcement: () => void;
  onIngest: () => void;
  onCompare: () => void;
  onBenchmark: () => void;
  onAutopilot: () => void;
  onSwitchAgent: (agent: AgentId) => void;
}

export function TopBar(p: Props) {
  const m = p.metrics;
  const incident = m?.incident_active;
  const guardOn = m?.guard_enabled ?? true;
  const monitor = m?.enforcement === "monitor";
  const badge = "rounded-md border border-line px-2 py-0.5 text-[11px] font-medium text-gray-400";
  return (
    <header className="border-b border-line">
      <div className="flex h-13 items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15">
              <ShieldCheck className="h-4 w-4 text-accent" />
            </div>
            <span className="text-[15px] font-semibold tracking-tight text-white">MemoryGuard</span>
          </div>
          <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${
            incident ? "border-bad/40 bg-bad/10 text-red-300" : "border-clean/30 bg-clean/10 text-emerald-300"}`}>
            <span className="relative flex h-2 w-2">
              {incident && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-bad opacity-75" />}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${incident ? "bg-bad" : "bg-clean"}`} />
            </span>
            {incident ? "Incident active" : "All clear"}
          </span>
          <div className="inline-flex rounded-lg border border-line p-0.5 text-[12px]" title="Same MemoryGuard engine, different agent">
            {([["payments", "Payments agent", Banknote], ["helpdesk", "IT Helpdesk agent", Laptop]] as const).map(([id, label, Icon]) => (
              <button key={id} type="button" disabled={!!p.busy} onClick={() => m?.agent !== id && p.onSwitchAgent(id)}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-medium transition-colors ${
                  m?.agent === id ? "bg-accent text-white" : "text-gray-300 hover:text-white"}`}>
                <Icon className="h-3.5 w-3.5" /> {label}
              </button>
            ))}
          </div>
          <span className={badge}>Memory: <span className="text-gray-200 capitalize">{m?.backend ?? "…"}{m?.backend_where ? ` ${m.backend_where}` : ""}</span></span>
          <span className={badge}>LLM: <span className="text-gray-200">{m?.llm ?? "…"}</span></span>
          <button type="button" onClick={p.onToggleGuard} title="Turn protection off to prove the threat"
            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
              guardOn ? "border-line text-gray-300 hover:bg-white/5" : "border-flag/50 bg-flag/10 text-amber-300"}`}>
            {guardOn ? <ShieldCheck className="h-3 w-3" /> : <ShieldOff className="h-3 w-3" />}
            {guardOn ? "Protection on" : "Protection off"}
          </button>
          <button type="button" onClick={p.onToggleEnforcement}
            title="Monitor = shadow mode: log what would be blocked, block nothing (how companies roll out safely)"
            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
              monitor ? "border-flag/50 bg-flag/10 text-amber-300" : "border-line text-gray-300 hover:bg-white/5"}`}>
            {monitor ? <Eye className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
            {monitor ? `Monitor mode · ${m?.would_block ?? 0} would-block` : "Enforce mode"}
          </button>
          {m?.audit && (
            <span title="Tamper-evident audit log (SHA-256 hash chain)" className={`inline-flex items-center gap-1 ${badge} ${
              m.audit.ok ? "" : "border-bad/50 text-red-300"}`}>
              {m.audit.ok ? <Lock className="h-3 w-3 text-clean" /> : <TriangleAlert className="h-3 w-3" />}
              Audit {m.audit.ok ? "chain intact" : "TAMPERED"} · {m.audit.entries}
            </span>
          )}
        </div>
      </div>
      <div className="flex h-12 items-center justify-between border-t border-line/60 px-6">
        <div className="flex items-center gap-2">
          <span className="mr-1 text-[11px] font-semibold tracking-[0.12em] text-gray-500 uppercase">Demo</span>
          <Button onClick={p.onAutopilot} variant={p.autopilot ? "danger" : "primary"} icon={<Clapperboard className="h-3.5 w-3.5" />}>
            {p.autopilot ? "Stop autopilot" : "Autopilot"}
          </Button>
          <Button onClick={p.onCompare} loading={p.busy === "compare"} icon={<Columns2 className="h-3.5 w-3.5" />}
            title="Same attack, two agents: without vs with MemoryGuard">Without vs With</Button>
          <Button onClick={p.onBenchmark} icon={<FlaskConical className="h-3.5 w-3.5" />}>Benchmark</Button>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={p.onIngest} icon={<ScanSearch className="h-3.5 w-3.5" />}
            title="Fetch any web page or paste an email into the agent's memory">Ingest</Button>
          <span className="mx-1 h-5 w-px bg-line" />
          {Object.entries(m?.attacks ?? {}).sort().map(([id, name]) => {
            const { label, Icon } = ATTACK_BUTTONS[id] ?? { label: id.toUpperCase(), Icon: Bug };
            return (
              <Button key={id} onClick={() => p.onInject(id)} loading={p.busy === id} title={name}
                icon={<Icon className="h-3.5 w-3.5" />}>{label}</Button>
            );
          })}
          <span className="mx-1 h-5 w-px bg-line" />
          <Button onClick={p.onHeal} loading={p.busy === "heal"} disabled={!p.canHeal} variant="primary"
            icon={<HeartPulse className="h-3.5 w-3.5" />}>Heal</Button>
          <Button onClick={p.onReset} loading={p.busy === "reset"} icon={<RotateCcw className="h-3.5 w-3.5" />}>Reset</Button>
        </div>
      </div>
    </header>
  );
}
