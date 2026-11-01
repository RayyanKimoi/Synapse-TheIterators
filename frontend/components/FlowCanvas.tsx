"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AgentNode, type AgentFlowNode } from "@/components/AgentNode";
import { CustomEdge, type SynapseEdge } from "@/components/CustomEdge";
import { sequentialLayout, tierLayout } from "@/lib/layout";
import type { WorkflowIR } from "@/lib/types";
import { nodeTelemetry, type RunState } from "@/store/useTelemetryStore";

const NODE_TYPES: NodeTypes = { agent: AgentNode };
const EDGE_TYPES: EdgeTypes = { synapse: CustomEdge };

type FlowCanvasProps = {
  workflow: WorkflowIR;
  run: RunState;
  variant: "baseline" | "compiled";
  /** Depth columns render as parallel rows; a bare sequence renders as one column. */
  tiers?: string[][];
  sequence?: string[];
};

export function FlowCanvas({ workflow, run, variant, tiers, sequence }: FlowCanvasProps) {
  const positions = useMemo(
    () =>
      tiers
        ? tierLayout(tiers)
        : sequentialLayout(sequence ?? workflow.nodes.map((n) => n.id)),
    [tiers, sequence, workflow.nodes],
  );

  const nodes = useMemo<AgentFlowNode[]>(
    () =>
      workflow.nodes.map((node) => ({
        id: node.id,
        type: "agent",
        position: positions[node.id] ?? { x: 0, y: 0 },
        data: {
          persona: node.persona,
          nodeType: node.type,
          telemetry: nodeTelemetry(run, node.id),
          variant,
        },
      })),
    [workflow.nodes, positions, run, variant],
  );

  // Edge state tracks the *source* node: a finished parent shows a committed
  // path, a generating parent flows, a cache hit bursts.
  const edges = useMemo<SynapseEdge[]>(
    () =>
      workflow.nodes.flatMap((node) =>
        node.dependencies.map((dependency) => ({
          id: `${dependency}->${node.id}`,
          source: dependency,
          target: node.id,
          type: "synapse" as const,
          data: { upstream: nodeTelemetry(run, dependency).status, variant },
        })),
      ),
    [workflow.nodes, run, variant],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.24 }}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      proOptions={{ hideAttribution: true }}
      className="bg-transparent"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={26}
        size={1}
        color={variant === "baseline" ? "hsl(0 0% 24%)" : "hsl(83 40% 26%)"}
      />
    </ReactFlow>
  );
}
