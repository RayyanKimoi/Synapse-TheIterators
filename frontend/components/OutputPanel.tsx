"use client";

import { Braces } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { PipelineType } from "@/lib/types";
import { useTelemetryStore, type RunState } from "@/store/useTelemetryStore";

const LANES: { pipeline: PipelineType; label: string }[] = [
  { pipeline: "baseline", label: "Unoptimized Baseline" },
  { pipeline: "compiled", label: "SYNAPSE Compiled" },
];

export function OutputPanel() {
  const runs = useTelemetryStore((state) => state.runs);

  return (
    <section className="void-card rounded-2xl p-4">
      <div className="flex items-center gap-2.5 pb-3">
        <Braces className="h-3.5 w-3.5 text-stream" />
        <h2 className="font-head text-[12px] font-semibold uppercase tracking-[0.18em] text-white/70">
          Run output
        </h2>
        <span className="h-px flex-1 void-rule" />
      </div>

      <Tabs defaultValue="compiled">
        <TabsList className="bg-white/[0.04]">
          {LANES.map(({ pipeline, label }) => (
            <TabsTrigger key={pipeline} value={pipeline} className="text-xs">
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        {LANES.map(({ pipeline }) => (
          <TabsContent key={pipeline} value={pipeline}>
            <Output run={runs[pipeline]} />
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}

function Output({ run }: { run: RunState }) {
  const summary = run.summary;

  if (!summary) {
    return (
      <p className="rounded-xl border border-white/[0.08] bg-background/40 px-4 py-6 text-center text-xs text-white/40">
        {run.status === "streaming" ? "Running…" : "Run the workflow to see its output."}
      </p>
    );
  }

  const keys = Object.keys(summary.final_output);
  const calls = Object.entries(summary.llm_calls);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-white/45">
        <span>{summary.run_id}</span>
        <span>· {summary.total_elapsed_ms} ms</span>
        <span>· {summary.cache_hits} cache hits</span>
        {calls.map(([source, count]) => (
          <span key={source}>
            · {count} {source}
          </span>
        ))}
      </div>

      {keys.length === 0 ? (
        <p className="rounded-xl border border-state-failed/30 bg-state-failed/5 px-4 py-6 text-center text-xs text-white/50">
          No output produced — the run halted before a terminal node emitted JSON.
        </p>
      ) : (
        <pre className="max-h-[320px] overflow-auto rounded-xl border border-white/[0.08] bg-background/60 p-4 font-mono text-[11px] leading-relaxed text-white/80">
          {JSON.stringify(summary.final_output, null, 2)}
        </pre>
      )}
    </div>
  );
}
