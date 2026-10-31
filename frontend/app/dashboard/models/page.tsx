"use client";

import { useState } from "react";

import { PageHeader, PreviewNote } from "@/components/dashboard/PageHeader";
import { MODELS, type ModelEntry } from "@/lib/dashboard-data";

/**
 * The model registry: pick the architecture a workspace routes to, and set the
 * routing rules around it. UI only — nothing here calls the backend.
 */

const STATUS_COPY: Record<ModelEntry["status"], { label: string; dot: string }> = {
  available: { label: "Available", dot: "dot-ok" },
  tunnel: { label: "Self-hosted", dot: "dot-ok" },
  unconfigured: { label: "Needs a key", dot: "dot-wait" },
};

const price = (value: number) => (value === 0 ? "free" : `$${value.toFixed(3)}`);

export default function ModelsPage() {
  const [selected, setSelected] = useState(MODELS[0].id);
  const [fallback, setFallback] = useState(MODELS[1].id);
  const [maxConcurrency, setMaxConcurrency] = useState("6");
  const [timeout, setTimeoutValue] = useState("60");

  return (
    <div className="mx-auto max-w-6xl px-6 py-7">
      <PageHeader
        title="Models"
        lede="The architecture this workspace routes to, and the rules the compiler applies when it dispatches."
      />
      <PreviewNote>
        Interface only — selections are local state. Routing is still read from{" "}
        <code className="font-mono text-white/60">workflows/*.json</code> and{" "}
        <code className="font-mono text-white/60">config.py</code> on the backend.
      </PreviewNote>

      <fieldset>
        <legend className="pb-3 font-head text-[13px] font-semibold text-white">
          Primary model
        </legend>
        <div className="grid gap-3 pb-8 md:grid-cols-2">
          {MODELS.map((model) => {
            const on = selected === model.id;
            const status = STATUS_COPY[model.status];
            return (
              <label
                key={model.id}
                className={`void-card void-card-hover flex cursor-pointer gap-3.5 rounded-2xl p-4 ${
                  on ? "border-stream/40 shadow-[0_0_30px_-12px_hsl(var(--stream)/0.5)]" : ""
                }`}
              >
                <input
                  type="radio"
                  name="primary-model"
                  value={model.id}
                  checked={on}
                  onChange={() => setSelected(model.id)}
                  className="sr-only"
                />
                <span
                  aria-hidden
                  className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border transition-colors ${
                    on ? "border-stream" : "border-white/25"
                  }`}
                >
                  {on && <span className="h-2 w-2 rounded-full bg-stream" />}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-head text-[14px] font-semibold text-white">
                      {model.name}
                    </span>
                    <span className="flex items-center gap-1.5 font-sans text-[11px] text-white/45">
                      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
                      {status.label}
                    </span>
                  </span>
                  <span className="mt-1 block font-sans text-[11.5px] leading-relaxed text-white/45">
                    {model.note}
                  </span>
                  <span className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-sans text-[11px] text-white/40">
                    <span>{model.vendor}</span>
                    <span>{model.params} params</span>
                    <span>{model.context} context</span>
                    <span className="tabular">
                      in {price(model.inputPrice)} / out {price(model.outputPrice)} per 1M
                    </span>
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="void-card rounded-2xl p-5">
        <h2 className="font-head text-[14px] font-semibold text-white">Routing rules</h2>
        <p className="mt-1 font-sans text-[12px] text-white/45">
          Applied by the scheduler at dispatch. Fusion only ever merges nodes that already share a
          model, so a fallback never changes what can be fused.
        </p>

        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">
              Fallback model
            </span>
            <select
              value={fallback}
              onChange={(event) => setFallback(event.target.value)}
              className="void-input h-9 w-full rounded-xl px-3 font-sans text-[13px] text-white focus:outline-none"
            >
              {MODELS.filter((model) => model.id !== selected).map((model) => (
                <option key={model.id} value={model.id} className="bg-[#0a0a0a]">
                  {model.name}
                </option>
              ))}
            </select>
            <span className="mt-1.5 block font-sans text-[11px] text-white/40">
              Used when the primary is unreachable.
            </span>
          </label>

          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">
              Max concurrent tasks
            </span>
            <input
              value={maxConcurrency}
              onChange={(event) => setMaxConcurrency(event.target.value)}
              inputMode="numeric"
              className="void-input h-9 w-full rounded-xl px-3 font-sans text-[13px] text-white focus:outline-none"
            />
            <span className="mt-1.5 block font-sans text-[11px] text-white/40">
              The ready-node scheduler&apos;s dispatch ceiling.
            </span>
          </label>

          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">
              Request timeout (seconds)
            </span>
            <input
              value={timeout}
              onChange={(event) => setTimeoutValue(event.target.value)}
              inputMode="numeric"
              className="void-input h-9 w-full rounded-xl px-3 font-sans text-[13px] text-white focus:outline-none"
            />
            <span className="mt-1.5 block font-sans text-[11px] text-white/40">
              A node that overruns fails rather than stalling the graph.
            </span>
          </label>
        </div>
      </div>
    </div>
  );
}
