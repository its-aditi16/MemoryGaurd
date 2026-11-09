import { AnimatePresence, motion } from "framer-motion";
import { ShieldCheck, ShieldOff, X } from "lucide-react";
import type { CompareResult } from "../api";
import { ActionCard } from "./ActionCard";

/** "Without vs With" split screen: same memory, same question, two agents. */
export function CompareModal({ result, onClose }: { result: CompareResult | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {result && (
        <motion.div className="fixed inset-0 z-40 flex items-start justify-center bg-black/70 px-6 pt-16 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 8, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-5xl rounded-2xl border border-line bg-card shadow-2xl shadow-black/50">
            <div className="flex items-center justify-between border-b border-line px-6 py-4">
              <div>
                <div className="text-[11px] font-semibold tracking-[0.12em] text-gray-400 uppercase">Same memory · same question · two agents</div>
                <div className="text-[15px] font-semibold text-white">“{result.question}”</div>
              </div>
              <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-white/5 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-0 divide-x divide-line">
              <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}
                className="space-y-3 p-6">
                <div className="flex items-center gap-2 text-red-300">
                  <ShieldOff className="h-5 w-5" />
                  <span className="text-lg font-semibold">Without MemoryGuard</span>
                </div>
                <p className="rounded-xl border border-line bg-page px-3 py-2.5 text-[13px] leading-relaxed text-gray-200">
                  {result.without.answer}
                </p>
                <ActionCard payment={result.without.payment} email={result.without.email} action={result.without.action} gate={null} unprotected />
                {!result.without.payment && !result.without.email && !result.without.action && (
                  <p className="text-xs text-gray-500">No action drafted.</p>
                )}
                <p className="text-xs text-gray-500">The model trusted the poisoned memory. Nothing stopped it.</p>
              </motion.div>
              <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 }}
                className="space-y-3 p-6">
                <div className="flex items-center gap-2 text-emerald-300">
                  <ShieldCheck className="h-5 w-5" />
                  <span className="text-lg font-semibold">With MemoryGuard</span>
                </div>
                <p className="rounded-xl border border-line bg-page px-3 py-2.5 text-[13px] leading-relaxed text-gray-200">
                  {result.with.answer}
                </p>
                <ActionCard payment={result.with.payment} email={result.with.email} action={result.with.action} gate={result.with.gate}
                  status={result.with.action_status} actionId={result.with.action_id} />
                <p className="text-xs text-gray-500">Checked against the system of record. The poisoned memory is flagged and its blast radius traced.</p>
              </motion.div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
