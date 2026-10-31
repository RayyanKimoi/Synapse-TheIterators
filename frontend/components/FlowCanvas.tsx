"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AgentNode, type AgentFlowNode } from "@/components/AgentNode";
import { sequentialLayout, tierLayout } from "@/lib/layout";
import { STATE_STYLE } from "@/lib/node-state";
import type { WorkflowIR } from "@/lib/types";
import { nodeTelemetry, type RunState } from "@/store/useTelemetryStore";

const NODE_TYPES: NodeTypes = { agent: AgentNode };

type FlowCanvasProps = {
  workflow: WorkflowIR;
  run: RunState;
  /** Tiers render as parallel rows; a bare sequence renders as one column. */
  tiers?: string[][];
  sequence?: string[];
};

export function FlowCanvas({ workflow, run, tiers, sequence }: FlowCanvasProps) {
  const positions = useMemo(
    () => (tiers ? tierLayout(tiers) : sequentialLayout(sequence ?? workflow.nodes.map((n) => n.id))),
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
        },
      })),
    [workflow.nodes, positions, run],
  );

  // Edge colour tracks the *source* node: a finished parent shows a solid
  // committed path, a generating parent shows flowing dashes.
  const edges = useMemo<Edge[]>(
    () =>
      workflow.nodes.flatMap((node) =>
        node.dependencies.map((dependency) => {
          const upstream = nodeTelemetry(run, dependency).status;
          return {
            id: `${dependency}->${node.id}`,
            source: dependency,
            target: node.id,
            animated: upstream === "RUNNING",
            style: {
              stroke: STATE_STYLE[upstream].edge,
              strokeWidth: upstream === "IDLE" ? 1.2 : 1.8,
            },
          };
        }),
      ),
    [workflow.nodes, run],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.22 }}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      proOptions={{ hideAttribution: false }}
      className="bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="hsl(240 4% 18%)" />
    </ReactFlow>
  );
}
