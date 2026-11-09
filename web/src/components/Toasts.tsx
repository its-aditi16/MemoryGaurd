import { AnimatePresence, motion } from "framer-motion";
import { Ban, CheckCircle2, Flag, Info, ScanSearch, TriangleAlert } from "lucide-react";

export interface Toast { id: number; kind: string; message: string }

const ICONS: Record<string, React.ReactNode> = {
  blocked: <Ban className="h-4 w-4 text-bad" />,
  injected: <TriangleAlert className="h-4 w-4 text-bad" />,
  ingested: <ScanSearch className="h-4 w-4 text-accent" />,
  flagged: <Flag className="h-4 w-4 text-flag" />,
  healed: <CheckCircle2 className="h-4 w-4 text-clean" />,
  error: <TriangleAlert className="h-4 w-4 text-bad" />,
};

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="pointer-events-none fixed right-6 bottom-6 z-50 flex w-[380px] flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6 }}
            className="pointer-events-auto flex items-start gap-2.5 rounded-xl border border-line bg-[#0F1522] px-3.5 py-3 shadow-xl shadow-black/40"
          >
            <span className="mt-0.5">{ICONS[t.kind] ?? <Info className="h-4 w-4 text-accent" />}</span>
            <p className="text-[13px] leading-snug text-gray-200">{t.message}</p>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
