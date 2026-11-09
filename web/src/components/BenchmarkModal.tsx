import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FlaskConical, Loader2, X } from "lucide-react";
import { api } from "../api";
import type { Benchmark } from "../api";

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border border-line px-4 py-3">
      <div className="text-[11px] font-semibold tracking-[0.12em] text-gray-400 uppercase">{label}</div>
      <div className="tnum mt-1 text-2xl font-semibold text-white">{value}</div>
      <div className="text-[11px] text-gray-500">{hint}</div>
    </div>
  );
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

export function BenchmarkModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [data, setData] = useState<Benchmark | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) api.benchmark().then(setData).catch(() => setData(null));
  }, [open]);

  const run = async () => {
    setRunning(true); setError(null);
    try { setData(await api.runBenchmark()); } catch (e) { setError((e as Error).message); } finally { setRunning(false); }
  };
  const s = data?.summary;

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-40 flex items-start justify-center bg-black/70 px-6 pt-12 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 8, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[85vh] w-full max-w-5xl flex-col rounded-2xl border border-line bg-card shadow-2xl shadow-black/50">
            <div className="flex items-center justify-between border-b border-line px-6 py-4">
              <div>
                <h2 className="text-[15px] font-semibold text-white">Detection benchmark</h2>
                <p className="text-xs text-gray-500">{s?.note ?? "32 labelled samples scored by the real engine."}</p>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={run} disabled={running}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[13px] font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
                  {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
                  {running ? "Running benchmark…" : s ? "Run again" : "Run benchmark"}
                </button>
                <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-white/5 hover:text-white">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            {error && <p className="mx-6 mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-red-200">{error}</p>}
            {!s ? (
              <div className="px-6 py-16 text-center text-sm text-gray-500">No results yet. Click “Run benchmark” (about 10–20 seconds).</div>
            ) : (
              <>
                <div className="grid grid-cols-5 gap-3 px-6 pt-4">
                  <Tile label="Detection rate" value={pct(s.detection_rate)} hint={`${s.true_positives}/${s.attacks} attacks caught`} />
                  <Tile label="False positives" value={pct(s.false_positive_rate)} hint={`${s.false_positives}/${s.benign} benign flagged`} />
                  <Tile label="Precision" value={pct(s.precision)} hint="flags that were real attacks" />
                  <Tile label="Median latency" value={`${Math.round(s.latency_ms_median)} ms`} hint={`p95 ${Math.round(s.latency_ms_p95)} ms per memory`} />
                  <Tile label="Accuracy" value={pct(s.accuracy)} hint={`threshold ${s.threshold} · LLM ${s.llm}`} />
                </div>
                <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-4 pb-5">
                  <table className="w-full table-fixed text-left text-xs">
                    <thead className="text-[11px] tracking-wide text-gray-500 uppercase">
                      <tr>
                        <th className="w-[9%] pb-2 font-medium">Truth</th>
                        <th className="w-[15%] pb-2 font-medium">Category</th>
                        <th className="w-[44%] pb-2 font-medium">Sample</th>
                        <th className="w-[8%] pb-2 text-right font-medium">Score</th>
                        <th className="w-[12%] pb-2 text-right font-medium">Verdict</th>
                        <th className="w-[12%] pb-2 text-right font-medium">Latency</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/70">
                      {data!.rows.map((r) => (
                        <tr key={r.id} title={r.why}>
                          <td className={`py-1.5 font-medium ${r.label === "attack" ? "text-red-300" : "text-gray-300"}`}>{r.label}</td>
                          <td className="py-1.5 text-gray-400">{r.category}</td>
                          <td className="truncate py-1.5 pr-3 text-gray-300">{r.text}</td>
                          <td className="tnum py-1.5 text-right text-white">{r.score.toFixed(2)}</td>
                          <td className="py-1.5 text-right">
                            <span className={`inline-flex items-center gap-1 ${r.correct ? "text-clean" : "text-bad"}`}>
                              {r.correct ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                              {r.detected ? "flagged" : "clean"}
                            </span>
                          </td>
                          <td className="tnum py-1.5 text-right text-gray-400">{Math.round(r.latency_ms)} ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
