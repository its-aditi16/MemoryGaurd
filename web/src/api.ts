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
}

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
export interface GateDecision { decision: "allow" | "hold" | "block"; reasons: string[] }
export interface Answer {
  id: string;
  question: string;
  answer: string;
  memories: UsedMemory[];
  payment: Payment | null;
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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text.slice(0, 160)}`);
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
  inject: (attack: string) => request<{ memory_id: string; name: string }>("POST", `/inject/${attack}`),
  heal: () => request<{ quarantined: string[]; replays: unknown[]; time_to_heal: number | null }>("POST", "/heal"),
  approve: () => request<{ purged: string[] }>("POST", "/approve"),
  undo: () => request<{ restored: string[] }>("POST", "/undo"),
  reset: () => request<{ memories: number }>("POST", "/reset"),
  setGuard: (enabled: boolean) => request<{ guard_enabled: boolean }>("POST", "/guard", { enabled }),
};
