import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bot, CornerDownLeft, EyeOff, Loader2, Repeat } from "lucide-react";
import type { AgentId, Answer } from "../api";
import { ActionCard } from "./ActionCard";
import { Card, Empty, SectionLabel, trustTone } from "./ui";

const SUGGESTIONS = [
  "Where do we pay Acme Supplies?",
  "Pay Acme's invoice",
  "Pay the Bharat Logistics invoice",
  "Send the vendor payment summary to the audit team",
];

interface Props {
  answers: Answer[];
  pending: string | null;
  onAsk: (q: string) => void;
  onSelect: (id: string) => void;
  selected: string | null;
  agent: AgentId;
  agentName: string;
}

function PaymentCard({ a }: { a: Answer }) {
  return <ActionCard payment={a.payment} email={a.email} action={a.action} gate={a.gate} status={a.action_status}
    actionId={a.action_id} />;
}

const SUGGESTIONS_BY_AGENT: Record<AgentId, string[]> = {
  payments: SUGGESTIONS,
  helpdesk: [
    "What laptop does John Mathew have?",
    "Give Meera Iyer read access to the Finance shared drive",
    "Grant John Mathew admin access to the finance server",
    "John Mathew asked for a password reset on Meera Iyer's account - send the link where he asked",
  ],
};

export function AgentConsole({ answers, pending, onAsk, onSelect, selected, agent, agentName }: Props) {
  const suggestions = SUGGESTIONS_BY_AGENT[agent] ?? SUGGESTIONS;
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
      <SectionLabel right={<span className="text-[11px] text-gray-500">{agentName}</span>}>
        Agent console
      </SectionLabel>
      <div ref={list} className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-5">
        {answers.length === 0 && !pending && <Empty>Ask the {agentName.toLowerCase()} something, or pick a suggestion below.</Empty>}
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
              {a.redacted?.length > 0 && (
                <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-bad/40 bg-bad/10 px-2.5 py-1.5 text-xs text-red-200">
                  <EyeOff className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  Disclosure blocked: bank details of {a.redacted.join(", ")} redacted. Untrusted memory shaped this answer.
                </div>
              )}
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
          {suggestions.map((s) => (
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
            placeholder={`Ask the assistant… e.g. ${suggestions[1]}`}
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
