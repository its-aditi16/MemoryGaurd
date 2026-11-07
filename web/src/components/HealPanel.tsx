import { Check, HeartPulse, ShieldX, Undo2, X } from "lucide-react";
import type { HealPlan, Metrics, Replay } from "../api";
import { Button, Card, Empty, SectionLabel, StatusBadge } from "./ui";

interface Props {
  plan: HealPlan | null;
  replays: Replay[];
  metrics: Metrics | null;
  busy: string | null;
  onHeal: () => void;
  onApprove: () => void;
  onUndo: () => void;
  onSelect: (id: string) => void;
}

export function HealPanel({ plan, replays, metrics, busy, onHeal, onApprove, onUndo, onSelect }: Props) {
  const toQuarantine = plan?.memories.filter((m) => m.status !== "quarantined") ?? [];
  const canHeal = !!plan?.active && (toQuarantine.length > 0 || (plan?.answers.length ?? 0) > 0);
  const pending = metrics?.vault_pending ?? 0;
  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel
        right={
          <div className="flex gap-2">
            <Button onClick={onHeal} loading={busy === "heal"} disabled={!canHeal} variant="primary"
              icon={<HeartPulse className="h-3.5 w-3.5" />}>Heal</Button>
            <Button onClick={onApprove} loading={busy === "approve"} disabled={pending === 0} variant="danger"
              icon={<ShieldX className="h-3.5 w-3.5" />}
              title="Permanently delete quarantined high-impact memories (human approval)">Approve deletion</Button>
            <Button onClick={onUndo} loading={busy === "undo"} disabled={pending === 0}
              icon={<Undo2 className="h-3.5 w-3.5" />}>Undo</Button>
          </div>
        }
      >
        Heal &amp; replay
      </SectionLabel>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,2fr)_minmax(0,5fr)] gap-5 px-5 pb-4">
        <div className="scroll-thin min-h-0 overflow-y-auto">
          <div className="mb-2 text-xs text-gray-500">
            {canHeal
              ? `Will quarantine ${toQuarantine.length} memor${toQuarantine.length === 1 ? "y" : "ies"} and replay ${plan?.answers.length} answer${plan?.answers.length === 1 ? "" : "s"}`
              : plan?.memories.length ? "Blast radius contained" : "No incident. Inject an attack, then ask about the vendor."}
          </div>
          <div className="space-y-1.5">
            {plan?.memories.map((m) => (
              <button key={m.id} type="button" onClick={() => onSelect(m.id)}
                className="flex w-full items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-left hover:border-gray-700">
                <span className="tnum text-xs font-medium text-white">{m.id}</span>
                <span className="text-[11px] text-gray-500">{m.source_class.replace("_", " ")} · trust {m.trust}</span>
                {m.high_impact && <span className="text-[10px] text-amber-300/80">high-impact</span>}
                <span className="ml-auto"><StatusBadge status={m.status} /></span>
              </button>
            ))}
          </div>
        </div>
        <div className="scroll-thin min-h-0 overflow-y-auto">
          {replays.length === 0 ? (
            <Empty>After healing, every affected question is replayed against the clean memory. Before → after shows here.</Empty>
          ) : (
            <table className="w-full table-fixed text-left text-xs">
              <thead className="text-[11px] tracking-wide text-gray-500 uppercase">
                <tr>
                  <th className="w-[22%] pb-2 font-medium">Question</th>
                  <th className="w-[35%] pb-2 font-medium">Before (poisoned)</th>
                  <th className="w-[35%] pb-2 font-medium">After (healed)</th>
                  <th className="w-[8%] pb-2 text-right font-medium">Fixed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/70 align-top">
                {replays.map((r) => (
                  <tr key={r.new_answer_id}>
                    <td className="py-2 pr-3 text-gray-200">{r.question}</td>
                    <td className="py-2 pr-3 leading-relaxed text-red-200/80">{r.old_answer}</td>
                    <td className="py-2 pr-3 leading-relaxed text-emerald-200/90">{r.new_answer}</td>
                    <td className="py-2 text-right">
                      {r.fixed ? (
                        <span className="inline-flex items-center gap-1 text-clean"><Check className="h-3.5 w-3.5" />Yes</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-bad"><X className="h-3.5 w-3.5" />No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </Card>
  );
}
