import { useEffect, useRef } from "react";
import { animate } from "framer-motion";
import { Archive, Database, Flag, Timer, TimerReset } from "lucide-react";
import type { ReactNode } from "react";
import type { Metrics } from "../api";
import { Card } from "./ui";

function AnimatedNumber({ value, decimals = 0 }: { value: number | null; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(0);
  useEffect(() => {
    if (value === null) { prev.current = 0; return; }
    if (!ref.current) return;
    const node = ref.current;
    const controls = animate(prev.current, value, {
      duration: 0.6,
      ease: "easeOut",
      onUpdate: (v) => { node.textContent = v.toFixed(decimals); },
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, decimals]);
  if (value === null) return <span className="text-gray-600">—</span>;
  return <span ref={ref}>{(0).toFixed(decimals)}</span>;
}

function Kpi({ label, icon, value, decimals, unit, hint }: {
  label: string; icon: ReactNode; value: number | null; decimals?: number; unit?: string; hint: string;
}) {
  return (
    <Card className="flex flex-col gap-2 px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-[0.12em] text-gray-400 uppercase">{label}</span>
        {icon}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="tnum text-3xl font-semibold tracking-tight text-white">
          <AnimatedNumber value={value} decimals={decimals} />
        </span>
        {unit && value !== null && <span className="text-sm text-gray-500">{unit}</span>}
      </div>
      <span className="text-xs text-gray-500">{hint}</span>
    </Card>
  );
}

export function KpiRow({ metrics }: { metrics: Metrics | null }) {
  const m = metrics;
  return (
    <div className="grid grid-cols-5 gap-4">
      <Kpi label="Live memories" value={m?.live ?? null} hint="Serving the agent"
        icon={<Database className="h-4 w-4 text-clean" />} />
      <Kpi label="Flagged" value={m?.flagged ?? null} hint="Suspicious, still live"
        icon={<Flag className={`h-4 w-4 ${m?.flagged ? "text-flag" : "text-gray-600"}`} />} />
      <Kpi label="Quarantined" value={m?.quarantined ?? null} hint="Moved to the vault"
        icon={<Archive className={`h-4 w-4 ${m?.quarantined ? "text-quar" : "text-gray-600"}`} />} />
      <Kpi label="Time to detect" value={m?.time_to_detect ?? null} decimals={1} unit="s"
        hint="Injection → harmful action blocked" icon={<Timer className="h-4 w-4 text-accent" />} />
      <Kpi label="Time to heal" value={m?.time_to_heal ?? null} decimals={1} unit="s"
        hint="Quarantine + replay" icon={<TimerReset className="h-4 w-4 text-accent" />} />
    </div>
  );
}
