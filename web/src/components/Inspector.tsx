import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import type { NodeDetail, ScoreResponse, ScoreResult } from "../api";
import { Card, Empty, SectionLabel, StatusBadge } from "./ui";

export type Inspected =
  | { kind: "memory"; data: ScoreResponse }
  | { kind: "node"; data: NodeDetail }
  | null;

function Gauge({ score }: { score: ScoreResult }) {
  const v = Math.max(0, Math.min(1, score.score));
  const { flag, quarantine } = score.thresholds;
  const color = v >= quarantine ? "#EF4444" : v >= flag ? "#F59E0B" : "#10B981";
  const verdict = v >= quarantine ? "Quarantine" : v >= flag ? "Flag" : "Clean";
  const r = 52, cx = 64, cy = 62;
  const pt = (t: number) => {
    const a = Math.PI * (1 - t);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  };
  const arc = (t: number) => {
    const [x, y] = pt(t);
    return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)}`;
  };
  const tick = (t: number) => {
    const [x1, y1] = pt(t);
    const a = Math.PI * (1 - t);
    return { x1, y1, x2: cx + (r - 9) * Math.cos(a), y2: cy - (r - 9) * Math.sin(a) };
  };
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 128 72" className="h-[72px] w-[128px]" role="img" aria-label={`Suspicion score ${v.toFixed(2)}`}>
        <path d={arc(1)} fill="none" stroke="#1F2937" strokeWidth="8" strokeLinecap="round" />
        <motion.path
          d={arc(Math.max(v, 0.001))} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6 }}
        />
        {[flag, quarantine].map((t) => {
          const k = tick(t);
          return <line key={t} {...k} stroke="#9CA3AF" strokeWidth="1.5" />;
        })}
        <text x={cx} y={cy - 6} textAnchor="middle" className="tnum" fill="#fff" fontSize="20" fontWeight="600">
          {v.toFixed(2)}
        </text>
      </svg>
      <div className="text-xs leading-5 text-gray-400">
        <div className="text-[13px] font-semibold text-white">Suspicion score</div>
        <div>Verdict: <span style={{ color }} className="font-medium">{verdict}</span></div>
        <div className="tnum">Flag ≥ {flag.toFixed(1)} · Quarantine ≥ {quarantine.toFixed(1)}</div>
      </div>
    </div>
  );
}

function Contributions({ score }: { score: ScoreResult }) {
  return (
    <div className="space-y-3">
      {score.signals.map((s) => (
        <div key={s.key} title={`signal ${s.value.toFixed(2)} × weight ${s.weight} = ${s.contribution.toFixed(3)}`}>
          <div className="flex items-baseline justify-between text-[13px]">
            <span className={s.share > 0 ? "text-gray-200" : "text-gray-500"}>{s.label}</span>
            <span className="tnum font-medium text-white">{(s.share * 100).toFixed(0)}%</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line">
            <motion.div
              className="h-full rounded-full bg-accent"
              initial={{ width: 0 }} animate={{ width: `${s.share * 100}%` }} transition={{ duration: 0.5 }}
            />
          </div>
          <div className="mt-1 truncate text-[11px] text-gray-500" title={s.detail}>{s.detail}</div>
        </div>
      ))}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-1 text-xs">
      <span className="text-gray-500">{k}</span>
      <span className="tnum truncate text-right text-gray-200">{v}</span>
    </div>
  );
}

const fmt = (iso?: string) => (iso ? new Date(iso).toLocaleString([], { hour12: false }) : "—");

function MemoryView({ data }: { data: ScoreResponse }) {
  const m = data.memory;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="tnum text-sm font-semibold text-white">{m.id}</span>
        <StatusBadge status={m.vault_state === "purged" ? "quarantined" : m.status} />
      </div>
      <p className="scroll-thin max-h-28 overflow-y-auto rounded-xl border border-line bg-page px-3 py-2 text-xs leading-relaxed text-gray-300">
        {m.content}
      </p>
      <div className="divide-y divide-line/60">
        <Row k="Source" v={<span className="capitalize">{m.source_class.replace("_", " ")}</span>} />
        <Row k="Source id" v={m.source_id} />
        <Row k="Trust (by source)" v={m.trust.toFixed(1)} />
        <Row k="Event time (claimed)" v={fmt(m.event_time)} />
        <Row k="Accepted time (stored)" v={fmt(m.accepted_time)} />
        <Row k="SHA-256" v={m.sha256?.slice(0, 16) + "…"} />
      </div>
      <Gauge score={data.score} />
      <div>
        <div className="mb-2 text-[11px] font-semibold tracking-[0.12em] text-gray-400 uppercase">Why it was scored</div>
        <Contributions score={data.score} />
      </div>
    </div>
  );
}

function NodeView({ data }: { data: NodeDetail }) {
  const a = data.answer;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-white">
          <span className="text-gray-500 capitalize">{data.type}</span> · {data.id}
        </span>
        <StatusBadge status={data.status} />
      </div>
      {a && (
        <>
          <Row k="Question" v={a.question} />
          <p className="rounded-xl border border-line bg-page px-3 py-2 text-xs leading-relaxed text-gray-300">{a.answer}</p>
          <div className="text-xs text-gray-500">Recalled {a.memories.length} memories:
            <span className="tnum text-gray-300"> {a.memories.map((m) => m.id).join(", ")}</span>
          </div>
        </>
      )}
      {data.type === "action" && data.data.payment && (
        <div className="space-y-1">
          <Row k="Vendor" v={data.data.payment.vendor} />
          <Row k="Invoice" v={data.data.payment.invoice} />
          {data.data.payment.recipients.map((r: { name: string; account: string }) => (
            <Row key={r.account} k={r.name} v={r.account} />
          ))}
          {data.data.gate?.reasons?.map((r: string) => (
            <p key={r} className="rounded-lg border border-bad/30 bg-bad/10 px-2.5 py-2 text-xs text-red-200">{r}</p>
          ))}
        </div>
      )}
      {data.type === "source" && (
        <div className="space-y-1">
          <Row k="Source class" v={data.data.source_class} />
          <Row k="Trust" v={data.data.trust} />
          <p className="text-xs text-gray-500">Everything downstream of this source is its blast radius.</p>
        </div>
      )}
    </div>
  );
}

export function Inspector({ item, loading }: { item: Inspected; loading: boolean }) {
  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel right={loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-500" /> : null}>
        Inspector
      </SectionLabel>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        {!item && <Empty>Click a node in the graph or a memory chip to inspect it.</Empty>}
        {item?.kind === "memory" && <MemoryView data={item.data} />}
        {item?.kind === "node" && <NodeView data={item.data} />}
      </div>
    </Card>
  );
}
