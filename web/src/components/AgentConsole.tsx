import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Ban, Bot, CheckCircle2, CornerDownLeft, Loader2, PauseCircle, Repeat, TriangleAlert } from "lucide-react";
import type { Answer } from "../api";
import { Card, Empty, SectionLabel, trustTone } from "./ui";

const SUGGESTIONS = [
  "Where do we pay Acme Supplies?",
  "Pay Acme's invoice",
  "Pay the Bharat Logistics invoice",
  "When is the next Acme invoice due?",
];

interface Props {
  answers: Answer[];
  pending: string | null;
  onAsk: (q: string) => void;
  onSelect: (id: string) => void;
  selected: string | null;
}

function PaymentCard({ a }: { a: Answer }) {
  if (!a.payment) return null;
  const payees = a.payment.recipients.map((r) => `${r.name} · ${r.account}`);
  const blocked = a.gate?.decision === "block" || a.action_status === "blocked";
  const held = a.gate?.decision === "hold";
  const unprotected = !a.gate;
  const tone = blocked
    ? "border-bad/40 bg-bad/10"
    : held || unprotected ? "border-flag/40 bg-flag/10" : "border-clean/30 bg-clean/5";
  const title = blocked ? "Action blocked" : held ? "Held for verification"
    : unprotected ? "Payment drafted (unprotected)" : "Payment drafted · awaiting your review";
  const Icon = blocked ? Ban : held ? PauseCircle : unprotected ? TriangleAlert : CheckCircle2;
  const iconTone = blocked ? "text-bad" : held || unprotected ? "text-flag" : "text-clean";
  return (
    <div className={`mt-2 rounded-xl border px-3 py-2.5 ${tone}`}>
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-white">
        <Icon className={`h-4 w-4 ${iconTone}`} />
        {title}
        {a.action_id && <span className="ml-auto text-[11px] font-normal text-gray-400">{a.action_id}</span>}
      </div>
      <div className="tnum mt-1 text-xs text-gray-300">
        {a.payment.invoice} · INR {Number(a.payment.amount_inr ?? 0).toLocaleString("en-IN")}
      </div>
      {payees.map((p) => (
        <div key={p} className="tnum text-xs text-gray-400">→ {p}</div>
      ))}
      {a.gate?.reasons?.[0] && <div className="mt-1.5 text-xs leading-relaxed text-gray-300">{a.gate.reasons[0]}</div>}
    </div>
  );
}

export function AgentConsole({ answers, pending, onAsk, onSelect, selected }: Props) {
  const [text, setText] = useState("");
  const list = useRef<HTMLDivElement>(null);
  // Scroll only the message list (scrollIntoView would also scroll the page and hide the top bar).
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [answers.length, pending]);

  const submit = (q: string) => {
    if (!q.trim() || pending) return;
    onAsk(q.trim());
    setText("");
  };

  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel right={<span className="text-[11px] text-gray-500">Vendor-payments assistant</span>}>
        Agent console
      </SectionLabel>
      <div ref={list} className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-5">
        {answers.length === 0 && !pending && <Empty>Ask the payments assistant something, or pick a suggestion below.</Empty>}
        {answers.map((a) => (
          <motion.div key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent/90 px-3 py-2 text-[13px] text-white">
                {a.question}
              </div>
            </div>
            <div
              onClick={() => onSelect(a.id)}
              className={`cursor-pointer rounded-2xl rounded-bl-md border px-3 py-2.5 transition-colors ${
                selected === a.id ? "border-accent/60 bg-white/3" : "border-line hover:border-gray-700"
              }`}
            >
              <div className="mb-1 flex items-center gap-1.5 text-[11px] text-gray-500">
                <Bot className="h-3 w-3" /> {a.id}
                {a.replay_of && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 px-1.5 text-accent">
                    <Repeat className="h-2.5 w-2.5" /> replay of {a.replay_of}
                  </span>
                )}
                {a.engine === "fallback" && <span className="text-gray-600">· template</span>}
              </div>
              <p className="text-[13px] leading-relaxed text-gray-200">{a.answer}</p>
              <PaymentCard a={a} />
              <div className="mt-2 flex flex-wrap gap-1">
                {a.memories.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    title={`${m.source_class} · trust ${m.trust} · ${m.status}\n${m.preview}`}
                    onClick={(e) => { e.stopPropagation(); onSelect(m.id); }}
                    className={`tnum rounded-md border px-1.5 py-0.5 text-[10.5px] ${trustTone(m.trust)} ${
                      m.status === "quarantined" ? "line-through opacity-50" : ""
                    } ${m.status === "flagged" ? "ring-1 ring-bad/60" : ""}`}
                  >
                    {m.id} · {m.source_class.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
          </motion.div>
        ))}
        {pending && (
          <div className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent/60 px-3 py-2 text-[13px] text-white">{pending}</div>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Recalling memories and drafting an answer…
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-line px-5 pt-3 pb-4">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" disabled={!!pending} onClick={() => submit(s)}
              className="rounded-full border border-line px-2.5 py-1 text-[11.5px] text-gray-300 hover:border-accent/50 hover:text-white disabled:opacity-40">
              {s}
            </button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="flex items-center gap-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask the assistant… e.g. Pay Acme's invoice"
            className="h-9 flex-1 rounded-lg border border-line bg-page px-3 text-[13px] text-white placeholder:text-gray-600 focus:border-accent/60 focus:outline-none"
          />
          <button type="submit" disabled={!!pending || !text.trim()}
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-white disabled:opacity-40">
            <CornerDownLeft className="h-4 w-4" />
          </button>
        </form>
      </div>
    </Card>
  );
}
