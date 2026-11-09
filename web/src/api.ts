// Single API client for the MemoryGuard FastAPI backend (proxied at /api by Vite).
const BASE = "/api";

export type NodeType = "source" | "memory" | "answer" | "action";
export type Status =
  | "clean" | "live" | "tainted" | "flagged" | "blocked" | "drafted" | "held" | "quarantined" | "superseded";

export interface Metrics {
  live: number;
  flagged: number;
  quarantined: number;
  vault_pending: number;
  flagged_ids: string[];
  time_to_detect: number | null;
  time_to_heal: number | null;
  incident_active: boolean;
  guard_enabled: boolean;
  backend: string;
  llm: string;
  attacks: Record<string, string>;
  enforcement: "monitor" | "enforce";
  would_block: number;
  audit: { ok: boolean; entries: number; broken_at: number | null };
  customer: string;
  agent: AgentId;
  agent_name: string;
}

export type AgentId = "payments" | "helpdesk";
export interface AgentAction { kind: "draft_payment" | "draft_email" | "grant_access" | "reset_password"; data: Record<string, string> }

export interface Email { to: string; subject: string; body: string }
export interface DryRun {
  question: string; answer: string; payment: Payment | null; email: Email | null; action: AgentAction | null; engine: string;
}
export interface CompareResult { question: string; without: DryRun; with: Answer }
export interface BenchRow {
  id: string; label: "attack" | "benign"; category: string; source_class: string; text: string;
  score: number; detected: boolean; correct: boolean; latency_ms: number; why: string;
}
export interface BenchSummary {
  samples: number; attacks: number; benign: number; true_positives: number; false_negatives: number;
  false_positives: number; true_negatives: number; detection_rate: number; false_positive_rate: number;
  precision: number; accuracy: number; latency_ms_median: number; latency_ms_p95: number;
  threshold: number; llm: string; ran_at: string; note: string;
}
export interface Benchmark { summary: BenchSummary | null; rows: BenchRow[] }

export interface GNode {
  id: string;
  type: NodeType;
  label: string;
  status: Status;
  created_at: string;
  data: Record<string, any>;
}
export interface GEdge { src: string; dst: string; kind: string }
export interface Graph { nodes: GNode[]; edges: GEdge[] }

export interface UsedMemory { id: string; source_class: string; trust: number; status: string; preview: string }
export interface Recipient { name: string; account: string; amount_inr?: number }
export interface Payment { vendor: string; invoice: string; amount_inr: number; recipients: Recipient[] }
export interface GateDecision { decision: "allow" | "hold" | "block"; reasons: string[]; monitor?: boolean }
export interface Answer {
  id: string;
  redacted: string[];
  action: AgentAction | null;
  question: string;
  answer: string;
  memories: UsedMemory[];
  payment: Payment | null;
  email: Email | null;
  gate: GateDecision | null;
  action_id: string | null;
  action_status: Status | null;
  replay_of: string | null;
  engine: string;
  created_at: string;
}

export interface Signal {
  key: string; label: string; value: number; weight: number; contribution: number; share: number; detail: string;
}
export interface ScoreResult {
  memory_id: string;
  score: number;
  suggested_status: string;
  thresholds: { flag: number; quarantine: number };
  signals: Signal[];
}
export interface MemoryDetail {
  id: string;
  content: string;
  source_class: string;
  source_id: string;
  trust: number;
  status: string;
  event_time: string;
  accepted_time: string;
  sha256: string;
  vault_state: string | null;
  graph_status: string | null;
}
export interface ScoreResponse { memory: MemoryDetail; score: ScoreResult }
export interface NodeDetail extends GNode { answer?: Answer }

export interface EventItem { ts: string; kind: string; message: string; data: Record<string, any> }
export interface Replay {
  question: string; old_answer: string; new_answer: string; fixed: boolean; old_answer_id: string; new_answer_id: string;
}
export interface HealPlan {
  active: boolean;
  memories: { id: string; status: string; source_class: string; trust: number; preview: string; high_impact: boolean }[];
  answers: { id: string; question: string }[];
  actions: { id: string; label: string; status: string }[];
  sources: { id: string; label: string; status: string }[];
}

export interface IngestedMemory {
  id: string; preview: string; hidden: boolean; score: number; suggested_status: string; status: string; why: string;
}
export interface IngestResult {
  source_id: string; title: string; url: string | null; hidden_snippets: number; max_score: number; scanned: boolean;
  memories: IngestedMemory[];
}
export interface IngestIn { url?: string; text?: string; source_class: string; scan: boolean; title?: string }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text.slice(0, 200);
    try { detail = JSON.parse(text).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  metrics: () => request<Metrics>("GET", "/metrics"),
  graph: () => request<Graph>("GET", "/graph"),
  answers: () => request<Answer[]>("GET", "/answers"),
  events: () => request<EventItem[]>("GET", "/events"),
  replays: () => request<Replay[]>("GET", "/replays"),
  healPlan: () => request<HealPlan>("GET", "/heal/plan"),
  score: (id: string) => request<ScoreResponse>("GET", `/score/${encodeURIComponent(id)}`),
  node: (id: string) => request<NodeDetail>("GET", `/node/${encodeURIComponent(id)}`),
  chat: (question: string) => request<Answer>("POST", "/chat", { question }),
  ingest: (body: IngestIn) => request<IngestResult>("POST", "/ingest", body),
  setAgent: (agent: AgentId) => request<{ agent: AgentId; memories: number }>("POST", "/agent", { agent }),
  compare: (question: string) => request<CompareResult>("POST", "/compare", { question }),
  benchmark: () => request<Benchmark>("GET", "/benchmark"),
  runBenchmark: () => request<Benchmark>("POST", "/benchmark/run"),
  setEnforcement: (mode: "monitor" | "enforce") => request<{ enforcement: string }>("POST", "/enforcement", { mode }),
  inject: (attack: string) => request<{ memory_id: string; name: string }>("POST", `/inject/${attack}`),
  heal: () => request<{ quarantined: string[]; replays: unknown[]; time_to_heal: number | null }>("POST", "/heal"),
  approve: () => request<{ purged: string[] }>("POST", "/approve"),
  undo: () => request<{ restored: string[] }>("POST", "/undo"),
  reset: () => request<{ memories: number }>("POST", "/reset"),
  setGuard: (enabled: boolean) => request<{ guard_enabled: boolean }>("POST", "/guard", { enabled }),
};
