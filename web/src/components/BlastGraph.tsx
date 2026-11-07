import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";
import type { GNode, Graph } from "../api";
import { Card, Empty, SectionLabel } from "./ui";

const COLORS: Record<string, string> = {
  clean: "#10B981", live: "#10B981", drafted: "#10B981",
  flagged: "#F59E0B", held: "#F59E0B",
  tainted: "#EF4444", blocked: "#EF4444",
  quarantined: "#64748B", superseded: "#64748B",
};
const RED = new Set(["tainted", "blocked"]);
const SHAPES = { source: "diamond", memory: "ellipse", answer: "round-rectangle", action: "hexagon" } as const;
const SIZE = { source: 20, memory: 18, answer: 24, action: 26 } as const;
const STEP_MS = 150;

function nodeLabel(n: GNode): string {
  if (n.type === "source") return n.label.length > 16 ? n.label.slice(0, 15) + "…" : n.label;
  return n.id;
}

/** Nodes worth drawing: everything an answer touched, plus anything not from the seed. */
function visibleSubgraph(g: Graph, showAll: boolean) {
  if (showAll) return g;
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const keep = new Set<string>();
  for (const n of g.nodes) {
    if (n.type === "answer" || n.type === "action" || n.data.seed === false) keep.add(n.id);
  }
  for (const e of g.edges) if (e.kind === "used_in" && keep.has(e.dst)) keep.add(e.src);
  for (const e of g.edges) if (e.kind === "wrote" && keep.has(e.dst) && byId.get(e.src)?.type === "source") keep.add(e.src);
  return {
    nodes: g.nodes.filter((n) => keep.has(n.id)),
    edges: g.edges.filter((e) => keep.has(e.src) && keep.has(e.dst)),
  };
}

/** Left-to-right layout by longest-path rank: source → memory → answer → action/derived memory → … */
function positions(g: Graph): Record<string, { x: number; y: number }> {
  const rank: Record<string, number> = Object.fromEntries(g.nodes.map((n) => [n.id, 0]));
  for (let i = 0; i < g.nodes.length; i++) {
    let changed = false;
    for (const e of g.edges) {
      if (rank[e.dst] < rank[e.src] + 1) { rank[e.dst] = rank[e.src] + 1; changed = true; }
    }
    if (!changed) break;
  }
  const cols: Record<number, string[]> = {};
  for (const n of g.nodes) (cols[rank[n.id]] ??= []).push(n.id);
  const pos: Record<string, { x: number; y: number }> = {};
  for (const [r, ids] of Object.entries(cols)) {
    ids.forEach((id, i) => { pos[id] = { x: Number(r) * 118, y: (i - (ids.length - 1) / 2) * 36 }; });
  }
  return pos;
}

export function BlastGraph({ graph, selected, onSelect }: {
  graph: Graph | null; selected: string | null; onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const shown = useRef<Record<string, string>>({});  // status each node is (or will be) displayed with
  const timers = useRef<number[]>([]);
  const layoutKey = useRef("");
  const [showAll, setShowAll] = useState(false);
  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  const sub = useMemo(() => (graph ? visibleSubgraph(graph, showAll) : null), [graph, showAll]);

  useEffect(() => {
    const cy = cytoscape({
      container: container.current,
      minZoom: 0.3,
      maxZoom: 2.2,
      wheelSensitivity: 0.3,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (el: cytoscape.NodeSingular) => COLORS[el.data("status")] ?? "#10B981",
            shape: (el: cytoscape.NodeSingular) => el.data("shape"),
            width: "data(size)", height: "data(size)",
            label: "data(label)", color: "#9CA3AF", "font-size": 10, "font-family": "Inter",
            "text-valign": "bottom", "text-margin-y": 4,
            "border-width": 2, "border-color": "#0B0F17",
            "transition-property": "background-color", "transition-duration": 250,
          } as any,
        },
        { selector: "node.sel", style: { "border-color": "#6366F1", "border-width": 3, color: "#E5E7EB" } },
        {
          selector: "edge",
          style: {
            width: 1.2, "line-color": "#374151", "target-arrow-color": "#374151",
            "target-arrow-shape": "triangle", "arrow-scale": 0.7, "curve-style": "bezier",
            "transition-property": "line-color, target-arrow-color, width", "transition-duration": 250,
          } as any,
        },
        { selector: "edge[?red]", style: { "line-color": "#EF4444", "target-arrow-color": "#EF4444", width: 2 } },
      ],
    });
    cy.on("tap", "node", (e) => onSelectRef.current(e.target.id()));
    cyRef.current = cy;
    // Cytoscape only measures its container at init; re-measure and re-fit whenever the card resizes.
    const ro = new ResizeObserver(() => { cy.resize(); cy.fit(undefined, 28); });
    if (container.current) ro.observe(container.current);
    const pendingTimers = timers.current;
    return () => { ro.disconnect(); pendingTimers.forEach(clearTimeout); cy.destroy(); };
  }, []);

  // Sync elements, then animate newly tainted nodes in BFS order (~150ms apart).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !sub) return;
    const ids = new Set(sub.nodes.map((n) => n.id));
    cy.nodes().forEach((n) => { if (!ids.has(n.id())) { n.remove(); delete shown.current[n.id()]; } });

    const queue: { id: string; status: string; seq: number }[] = [];
    for (const n of sub.nodes) {
      const prev = shown.current[n.id];
      const spreading = RED.has(n.status) && (prev === undefined || !RED.has(prev)) && n.data.taint_seq !== undefined;
      const display = spreading ? (prev ?? "clean") : n.status;
      const el = cy.getElementById(n.id);
      if (el.empty()) {
        cy.add({ group: "nodes", data: { id: n.id, label: nodeLabel(n), status: display, shape: SHAPES[n.type], size: SIZE[n.type] } });
      } else if (!spreading) {
        el.data("status", display);
      }
      if (spreading) queue.push({ id: n.id, status: n.status, seq: n.data.taint_seq });
      shown.current[n.id] = n.status;
    }
    const edgeIds = new Set(sub.edges.map((e) => `${e.src}->${e.dst}`));
    cy.edges().forEach((e) => { if (!edgeIds.has(e.id())) e.remove(); });
    for (const e of sub.edges) {
      if (cy.getElementById(`${e.src}->${e.dst}`).empty()) {
        cy.add({ group: "edges", data: { id: `${e.src}->${e.dst}`, source: e.src, target: e.dst } });
      }
    }
    const paintEdges = () => cy.edges().forEach((e) => {
      e.data("red", RED.has(e.source().data("status")) && RED.has(e.target().data("status")));
    });
    paintEdges();

    const key = [...ids].sort().join("|");
    if (key !== layoutKey.current) {
      layoutKey.current = key;
      const pos = positions(sub);
      cy.nodes().forEach((n) => { if (pos[n.id()]) n.position(pos[n.id()]); });
      cy.fit(undefined, 28);
    }

    queue.sort((a, b) => a.seq - b.seq).forEach((q, i) => {
      timers.current.push(window.setTimeout(() => {
        const el = cy.getElementById(q.id);
        if (el.empty()) return;
        const size = el.data("size");
        el.data("status", q.status);
        paintEdges();
        el.animate({ style: { width: size * 1.6, height: size * 1.6 } }, {
          duration: 140,
          complete: () => { el.animate({ style: { width: size, height: size } }, { duration: 180 }); },
        });
      }, i * STEP_MS));
    });
  }, [sub]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("sel");
    if (selected) cy.getElementById(selected).addClass("sel");
  }, [selected, sub]);

  const empty = !sub || sub.nodes.length === 0;
  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel
        right={
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-gray-400">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-indigo-500" />
            Show full memory bank
          </label>
        }
      >
        Blast radius
      </SectionLabel>
      <div className="relative min-h-0 flex-1">
        {/* Cytoscape rewrites its container's position style, so it gets its own full-size child. */}
        <div className="absolute inset-0">
          <div ref={container} className="h-full w-full" />
        </div>
        {empty && <div className="absolute inset-0"><Empty>Ask the agent a question to see memory lineage appear here.</Empty></div>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-5 py-2.5 text-[11px] text-gray-400">
        <span className="flex items-center gap-1.5"><Shape d="M5 0 L10 5 L5 10 L0 5 Z" /> Source</span>
        <span className="flex items-center gap-1.5"><Shape circle /> Memory</span>
        <span className="flex items-center gap-1.5"><Shape d="M1 2 H9 V8 H1 Z" /> Answer</span>
        <span className="flex items-center gap-1.5"><Shape d="M3 0 H7 L10 5 L7 10 H3 L0 5 Z" /> Action</span>
        <span className="ml-auto flex items-center gap-3">
          <Dot c="bg-clean" l="Clean" /> <Dot c="bg-flag" l="Flagged" /> <Dot c="bg-bad" l="Tainted / blocked" />
          <Dot c="bg-quar" l="Quarantined" />
        </span>
      </div>
    </Card>
  );
}

function Shape({ d, circle }: { d?: string; circle?: boolean }) {
  return (
    <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 fill-gray-400">
      {circle ? <circle cx="5" cy="5" r="5" /> : <path d={d} />}
    </svg>
  );
}

function Dot({ c, l }: { c: string; l: string }) {
  return <span className="flex items-center gap-1"><span className={`h-2 w-2 rounded-full ${c}`} />{l}</span>;
}
