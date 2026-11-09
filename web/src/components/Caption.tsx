import { AnimatePresence, motion } from "framer-motion";
import { Clapperboard } from "lucide-react";

/** Autopilot caption banner: big, readable on a projector or in a recording. */
export function Caption({ text, step, total }: { text: string | null; step: number; total: number }) {
  return (
    <AnimatePresence>
      {text && (
        <motion.div key="caption" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
          className="pointer-events-none fixed bottom-6 left-1/2 z-50 w-[min(900px,90vw)] -translate-x-1/2">
          <motion.div key={text} initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-3 rounded-2xl border border-accent/40 bg-[#10142A]/95 px-5 py-3.5 shadow-2xl shadow-black/60">
            <Clapperboard className="h-5 w-5 shrink-0 text-accent" />
            <p className="flex-1 text-[17px] leading-snug font-medium text-white">{text}</p>
            <span className="tnum shrink-0 text-xs text-gray-400">{step}/{total}</span>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
