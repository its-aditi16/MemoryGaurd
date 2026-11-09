import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { AgentId, Answer, CompareResult, EventItem, Graph, HealPlan, Metrics, Replay } from "./api";
import { AgentConsole } from "./components/AgentConsole";
import { BenchmarkModal } from "./components/BenchmarkModal";
import { BlastGraph } from "./components/BlastGraph";
import { Caption } from "./components/Caption";
import { CompareModal } from "./components/CompareModal";
import { HealPanel } from "./components/HealPanel";
import { IngestDialog } from "./components/IngestDialog";
import { Inspector } from "./components/Inspector";
import type { Inspected } from "./components/Inspector";
import { KpiRow } from "./components/KpiRow";
import { Timeline } from "./components/Timeline";
import { Toasts } from "./components/Toasts";
import type { Toast } from "./components/Toasts";
import { TopBar } from "./components/TopBar";

const POLL_MS = 1000;
let autoStartDone = false;  // module-level so React StrictMode's double effects start autopilot once
const TOAST_KINDS = new Set(["injected", "ingested", "blocked", "would_block", "policy", "disclosure_blocked", "retention", "flagged", "held", "quarantined", "healed", "approved", "undone", "llm_error"]);

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
  const [ingestOpen, setIngestOpen] = useState(false);
  const [benchOpen, setBenchOpen] = useState(false);
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [autopilot, setAutopilot] = useState(false);
  const [caption, setCaption] = useState<{ text: string; step: number } | null>(null);
  const [autoTotal, setAutoTotal] = useState(0);
  const autoRef = useRef(false);

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
    setCompare(null);
    prevFlagged.current = 0;
    toast("reset", "Memory bank reset to the clean seed state");
  });

  const switchAgent = (a: AgentId) => run("agent", async () => {
    const r = await api.setAgent(a);
    setSelected(null); setCompare(null); prevFlagged.current = 0;
    toast("reset", `Switched to the ${a === "helpdesk" ? "IT helpdesk" : "vendor payments"} agent (${r.memories} memories). Same MemoryGuard engine.`);
  });

  const COMPARE_Q: Record<AgentId, string> = {
    payments: "Pay Acme's invoice",
    helpdesk: "Grant John Mathew admin access to the finance server",
  };
  const runCompare = (q = COMPARE_Q[metrics?.agent ?? "payments"]) => run("compare", async () => {
    setPending(q);
    try { setCompare(await api.compare(q)); } finally { setPending(null); }
  });

  // ---- Autopilot: the whole story, captioned, one click ----------------------
  const stopAutopilot = () => { autoRef.current = false; setAutopilot(false); setCaption(null); };
  const runAutopilot = async () => {
    if (autoRef.current) { stopAutopilot(); return; }
    autoRef.current = true;
    setAutopilot(true);
    const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
    const chat = async (q: string) => { setPending(q); try { await api.chat(q); } finally { setPending(null); } };
    const steps: [string, () => Promise<unknown>, number][] = [
      ["This payments agent remembers 21 trusted facts. Everything is clean.", async () => {
        await api.setAgent("payments"); setSelected(null); setCompare(null); prevFlagged.current = 0;
      }, 3500],
      ["An attacker's email plants a fake Acme Supplies bank account in the agent's memory.", () => api.inject("a1"), 4000],
      ["The agent answers a routine question and repeats the attacker's account. The poison spreads.",
        () => chat("Where do we pay Acme Supplies?"), 5000],
      ["Same memory, same request, two agents: without vs with MemoryGuard.",
        async () => { setPending("Pay Acme's invoice"); try { setCompare(await api.compare("Pay Acme's invoice")); } finally { setPending(null); } }, 9000],
      ["MemoryGuard blocked the payment and traced everything the fake email touched (red).",
        async () => setCompare(null), 6000],
      ["Why it was flagged: it contradicts the verified record, comes from a low-trust email and reads like a known scam.",
        async () => undefined, 6000],
      ["Heal: quarantine only the poisoned memories, then replay every affected answer as proof.", () => api.heal(), 7000],
      ["Not just money: a second email tries to make the agent leak every vendor's bank details.", () => api.inject("a3"), 4000],
      ["The agent drafts the email to the attacker's look-alike domain, and MemoryGuard blocks the data leak.",
        () => chat("Send the vendor payment summary to the audit team"), 7000],
      ["Heal again: the leak instruction is quarantined and the answer replayed safely.", () => api.heal(), 6000],
      ["Not just payments: same MemoryGuard engine, now protecting an IT helpdesk agent.", async () => {
        await api.setAgent("helpdesk"); setSelected(null); prevFlagged.current = 0;
      }, 4000],
      ["A fake 'IT service desk' email claims a Sales employee is now an admin, with an outside 'recovery' address.",
        () => api.inject("a4"), 4000],
      ["The agent tries to send a colleague's password-reset link to the attacker's address. Account takeover blocked, fake email quarantined.",
        () => chat("John Mathew asked for a password reset on Meera Iyer's account - send the link where he asked"), 8000],
      ["Asked to make John an admin: refused. The official admin list is the authority, not a fake email.",
        () => chat("Grant John Mathew admin access to the finance server"), 7000],
      ["Heal: every answer the fake email touched is replayed against the clean memory.",
        () => api.heal(), 6000],
      ["MemoryGuard: antivirus and undo for any AI agent's memory. Plug in its source of truth and its actions.",
        async () => undefined, 5000],
    ];
    setAutoTotal(steps.length);
    try {
      for (let i = 0; i < steps.length && autoRef.current; i++) {
        setCaption({ text: steps[i][0], step: i + 1 });
        await steps[i][1]();
        await refresh();
        await sleep(steps[i][2]);
      }
    } catch (err) {
      toast("error", `Autopilot stopped: ${(err as Error).message}`);
    } finally {
      stopAutopilot();
    }
  };

  // http://localhost:5173/?autopilot starts the captioned story on load (handy for recording).
  useEffect(() => {
    if (!autoStartDone && new URLSearchParams(window.location.search).has("autopilot")) {
      autoStartDone = true;
      window.setTimeout(runAutopilot, 1500);
    }
  });

  return (
    <div className="min-h-screen">
      <TopBar
        metrics={metrics}
        busy={busy}
        autopilot={autopilot}
        canHeal={!!plan?.active && ((plan.memories.some((m) => m.status !== "quarantined")) || plan.answers.length > 0)}
        onInject={(a) => run(a, () => api.inject(a))}
        onHeal={() => run("heal", api.heal)}
        onReset={reset}
        onToggleGuard={() => run("guard", () => api.setGuard(!(metrics?.guard_enabled ?? true)))}
        onToggleEnforcement={() => run("mode", () => api.setEnforcement(metrics?.enforcement === "monitor" ? "enforce" : "monitor"))}
        onIngest={() => setIngestOpen(true)}
        onCompare={() => runCompare()}
        onBenchmark={() => setBenchOpen(true)}
        onAutopilot={runAutopilot}
        onSwitchAgent={switchAgent}
      />
      <Caption text={caption?.text ?? null} step={caption?.step ?? 0} total={autoTotal} />
      <CompareModal result={compare} onClose={() => setCompare(null)} />
      <BenchmarkModal open={benchOpen} onClose={() => setBenchOpen(false)} />
      <IngestDialog
        open={ingestOpen}
        onClose={() => setIngestOpen(false)}
        onInspect={setSelected}
        onDone={(r) => {
          const worst = [...r.memories].sort((a, b) => b.score - a.score)[0];
          if (worst) setSelected(worst.id);  // show the most suspicious chunk in the Inspector
          refresh();
        }}
      />
      {offline && (
        <div className="border-b border-bad/30 bg-bad/10 px-6 py-2 text-xs text-red-200">
          Can't reach the MemoryGuard API on port 8000. Start it with <code className="text-white">npm run dev</code> from the project root.
        </div>
      )}
      <main className="mx-auto max-w-[1600px] space-y-4 p-5">
        <KpiRow metrics={metrics} />
        <div className="grid h-[580px] grid-cols-[minmax(0,3fr)_minmax(0,4fr)_minmax(0,3fr)] gap-4">
          <AgentConsole answers={answers} pending={pending} onAsk={ask} onSelect={setSelected} selected={selected}
            agent={metrics?.agent ?? "payments"} agentName={metrics?.agent_name ?? "Vendor payments assistant"} />
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
      <Toasts toasts={autopilot ? [] : toasts} />
    </div>
  );
}
