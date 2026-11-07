import type { EventItem } from "../api";
import { Card, Empty, SectionLabel, fmtTime } from "./ui";

// Status colour only where the event carries that meaning.
const KIND_TONE: Record<string, string> = {
  injected: "bg-bad", blocked: "bg-bad", flagged: "bg-flag", held: "bg-flag", recalled: "bg-flag",
  quarantined: "bg-quar", approved: "bg-quar", healed: "bg-clean", drafted: "bg-clean", reset: "bg-accent",
  undone: "bg-accent", guard: "bg-accent", llm_error: "bg-flag",
};

export function Timeline({ events }: { events: EventItem[] }) {
  const items = [...events].reverse();
  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel>Event timeline</SectionLabel>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-4">
        {items.length === 0 && <Empty>No events yet.</Empty>}
        <ol className="relative space-y-2.5 border-l border-line pl-4">
          {items.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="relative">
              <span className={`absolute top-1.5 -left-[21px] h-2 w-2 rounded-full ring-4 ring-card ${KIND_TONE[e.kind] ?? "bg-gray-500"}`} />
              <div className="flex items-baseline gap-2">
                <span className="tnum text-[11px] text-gray-500">{fmtTime(e.ts)}</span>
                <span className="text-[11px] font-semibold tracking-wide text-gray-300 uppercase">{e.kind}</span>
              </div>
              <p className="text-xs leading-relaxed text-gray-400">{e.message}</p>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
