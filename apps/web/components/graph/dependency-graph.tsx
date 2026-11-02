"use client";

import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { TraceData } from "@/lib/types";
import { useEvidence } from "@/components/providers";

export default function DependencyGraph({ data, onSelect }: { data: TraceData; onSelect?: (id: string) => void }) {
  const { open } = useEvidence();

  const { nodes, edges } = useMemo(() => {
    const byDepth: Record<number, typeof data.nodes> = {};
    for (const n of data.nodes) {
      const d = n.depth ?? 0;
      (byDepth[d] ??= []).push(n);
    }
    const nodes: Node[] = data.nodes.map((n) => {
      const d = n.depth ?? 0;
      const col = byDepth[d];
      const i = col.findIndex((x) => x.id === n.id);
      return {
        id: n.id,
        position: { x: d * 220, y: i * 92 },
        data: { label: `${n.tag}\n${n.type}` },
        style: {
          background: "#2e3035",
          color: "#f0f2f5",
          border: "1px solid #2d2f33",
          borderRadius: 16,
          fontWeight: 600,
          fontSize: 13,
          padding: 12,
          whiteSpace: "pre-line",
          width: 180,
        },
      };
    });
    const edges: Edge[] = data.edges.map((e) => ({
      id: e.id,
      source: e.source_id,
      target: e.target_id,
      label: e.type,
      style: { stroke: e.status === "candidate" ? "#0075ff" : "#00b24b" },
      labelStyle: { fill: "#9aa1b1", fontWeight: 600, fontSize: 11 },
    }));
    return { nodes, edges };
  }, [data]);

  return (
    <div className="h-[560px] overflow-hidden rounded-card border border-hairline bg-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onSelect?.(node.id)}
        onEdgeClick={(_, edge) => {
          const rel = data.edges.find((e) => e.id === edge.id);
          if (rel?.evidence_ids.length) open(rel.evidence_ids);
        }}
      >
        <Background color="#2d2f33" gap={20} />
        <MiniMap
          pannable
          style={{ background: "#2e3035" }}
          maskColor="rgba(20,20,21,0.7)"
          nodeColor="#00b24b"
        />
        <Controls />
      </ReactFlow>
    </div>
  );
}
