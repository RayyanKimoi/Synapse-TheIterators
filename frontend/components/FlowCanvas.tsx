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
import type { NodeStatus, WorkflowIR } from "@/lib/types";
import { nodeTelemetry, type RunState } from "@/store/useTelemetryStore";

// A node has been "reached" once execution has touched it or a predecessor
// finished, which is when the next card fades in.
const reached = (status: NodeStatus) =>
  status === "COMPLETED" || status === "CACHED" || status === "FAILED";

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

  // Progressive reveal: at rest only the entry node(s) show, and each following
  // card fades in once its predecessor has been reached. The baseline runs the
  // nodes in `sequence`, so there each node waits on the previous one; the
  // compiled lane waits on a node's real dependencies, so a whole tier appears
  // together. Keyed off telemetry, so resetting a run replays the cascade.
  const revealed = useMemo(() => {
    const status = (id: string) => nodeTelemetry(run, id).status;
    const result: Record<string, boolean> = {};
    if (sequence && !tiers) {
      sequence.forEach((id, index) => {
        result[id] =
          index === 0 ||
          status(id) !== "IDLE" ||
          reached(status(sequence[index - 1]));
      });
    } else {
      workflow.nodes.forEach((node) => {
        result[node.id] =
          node.dependencies.length === 0 ||
          status(node.id) !== "IDLE" ||
          node.dependencies.some((dependency) => reached(status(dependency)));
      });
    }
    // Any node the structure above did not cover stays visible by default.
    workflow.nodes.forEach((node) => {
      if (!(node.id in result)) result[node.id] = true;
    });
    return result;
  }, [workflow.nodes, sequence, tiers, run]);

  const nodes = useMemo<AgentFlowNode[]>(
    () =>
      workflow.nodes.map((node) => ({
        id: node.id,
        type: "agent",
        position: positions[node.id] ?? { x: 0, y: 0 },
        data: {
          persona: node.persona || node.id,
          nodeType: node.type,
          telemetry: nodeTelemetry(run, node.id),
          variant,
          revealed: revealed[node.id] ?? true,
        },
      })),
    [workflow.nodes, positions, run, variant, revealed],
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
          data: {
            upstream: nodeTelemetry(run, dependency).status,
            variant,
            // An edge shows only once both of its endpoints have faded in.
            revealed: (revealed[dependency] ?? true) && (revealed[node.id] ?? true),
          },
        })),
      ),
    [workflow.nodes, run, variant, revealed],
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
