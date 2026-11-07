import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Answer, EventItem, Graph, HealPlan, Metrics, Replay } from "./api";
import { AgentConsole } from "./components/AgentConsole";
import { BlastGraph } from "./components/BlastGraph";
import { HealPanel } from "./components/HealPanel";
import { Inspector } from "./components/Inspector";
import type { Inspected } from "./components/Inspector";
import { KpiRow } from "./components/KpiRow";
import { Timeline } from "./components/Timeline";
import { Toasts } from "./components/Toasts";
import type { Toast } from "./components/Toasts";
import { TopBar } from "./components/TopBar";

const POLL_MS = 1500;
const TOAST_KINDS = new Set(["injected", "blocked", "flagged", "held", "quarantined", "healed", "approved", "undone", "llm_error"]);

export default function App() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [plan, setPlan] = useState<HealPlan | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [inspected, setInspected] = useState<Inspected>(null);
  const [inspecting, setInspecting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [offline, setOffline] = useState(false);

  const seenEvents = useRef<number | null>(null);
  const prevFlagged = useRef(0);
  const inFlight = useRef(false);
  const toastId = useRef(0);

  const toast = useCallback((kind: string, message: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t.slice(-3), { id, kind, message }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5500);
  }, []);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [m, g, a, e, r, p] = await Promise.all([
        api.metrics(), api.graph(), api.answers(), api.events(), api.replays(), api.healPlan(),
      ]);
      setMetrics(m); setGraph(g); setAnswers(a); setEvents(e); setReplays(r); setPlan(p);
      setOffline(false);

      if (seenEvents.current === null || e.length < seenEvents.current) seenEvents.current = e.length;
      e.slice(seenEvents.current).filter((x) => TOAST_KINDS.has(x.kind)).forEach((x) => toast(x.kind, x.message));
      seenEvents.current = e.length;

      if (m.flagged_ids.length > prevFlagged.current) setSelected(m.flagged_ids[0]);  // jump to the evidence
      prevFlagged.current = m.flagged_ids.length;
    } catch {
      setOffline(true);
    } finally {
      inFlight.current = false;
    }
  }, [toast]);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(t);
  }, [refresh]);

  // Inspector follows the selection and refreshes when graph statuses change.
  const statusSig = graph?.nodes.map((n) => n.status).join("") ?? "";
  useEffect(() => {
    if (!selected) { setInspected(null); return; }
    let cancelled = false;
    setInspecting(true);
    const load = selected.startsWith("mem-")
      ? api.score(selected).then((data) => ({ kind: "memory" as const, data }))
      : api.node(selected).then((data) => ({ kind: "node" as const, data }));
    load.then((it) => { if (!cancelled) setInspected(it); })
      .catch(() => { if (!cancelled) setInspected(null); })
      .finally(() => { if (!cancelled) setInspecting(false); });
    return () => { cancelled = true; };
  }, [selected, statusSig]);

  const run = useCallback(async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
    } catch (err) {
      toast("error", `Action failed: ${(err as Error).message}`);
    } finally {
      setBusy(null);
      await refresh();
    }
  }, [refresh, toast]);

  const ask = async (q: string) => {
    setPending(q);
    try {
      await api.chat(q);
    } catch (err) {
      toast("error", `Chat failed: ${(err as Error).message}`);
    } finally {
      setPending(null);
      await refresh();
    }
  };

  const reset = () => run("reset", async () => {
    await api.reset();
    setSelected(null);
    prevFlagged.current = 0;
    toast("reset", "Memory bank reset to the clean seed state");
  });

  return (
    <div className="min-h-screen">
      <TopBar
        metrics={metrics}
        busy={busy}
        canHeal={!!plan?.active && ((plan.memories.some((m) => m.status !== "quarantined")) || plan.answers.length > 0)}
        onInject={(a) => run(a, () => api.inject(a))}
        onHeal={() => run("heal", api.heal)}
        onReset={reset}
        onToggleGuard={() => run("guard", () => api.setGuard(!(metrics?.guard_enabled ?? true)))}
      />
      {offline && (
        <div className="border-b border-bad/30 bg-bad/10 px-6 py-2 text-xs text-red-200">
          Can't reach the MemoryGuard API on port 8000. Start it with <code className="text-white">npm run dev</code> from the project root.
        </div>
      )}
      <main className="mx-auto max-w-[1600px] space-y-4 p-5">
        <KpiRow metrics={metrics} />
        <div className="grid h-[580px] grid-cols-[minmax(0,3fr)_minmax(0,4fr)_minmax(0,3fr)] gap-4">
          <AgentConsole answers={answers} pending={pending} onAsk={ask} onSelect={setSelected} selected={selected} />
          <BlastGraph graph={graph} selected={selected} onSelect={setSelected} />
          <Inspector item={inspected} loading={inspecting} />
        </div>
        <div className="grid h-[300px] grid-cols-[minmax(0,7fr)_minmax(0,3fr)] gap-4">
          <HealPanel
            plan={plan} replays={replays} metrics={metrics} busy={busy} onSelect={setSelected}
            onHeal={() => run("heal", api.heal)}
            onApprove={() => run("approve", api.approve)}
            onUndo={() => run("undo", api.undo)}
          />
          <Timeline events={events} />
        </div>
      </main>
      <Toasts toasts={toasts} />
    </div>
  );
}
