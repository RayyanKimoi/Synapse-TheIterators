"use client";

import { useState } from "react";

import { PageHeader, PreviewNote } from "@/components/dashboard/PageHeader";

/**
 * Workspace settings. UI only — nothing is persisted.
 *
 * The toggles below name real backend behaviour (offline mode, the breaker,
 * tracing) so the panel reads honestly, but changing them here does not reach
 * `config.py`; that is still environment-driven.
 */

type ToggleProps = {
  id: string;
  label: string;
  hint: string;
  defaultOn?: boolean;
};

function Toggle({ id, label, hint, defaultOn = false }: ToggleProps) {
  const [on, setOn] = useState(defaultOn);
  return (
    <div className="flex items-start justify-between gap-5 py-4">
      <div className="min-w-0">
        <label htmlFor={id} className="font-sans text-[13px] text-white">
          {label}
        </label>
        <p className="mt-1 font-sans text-[11.5px] leading-relaxed text-white/45">{hint}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        onClick={() => setOn((value) => !value)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-colors ${
          on ? "border-stream/50 bg-stream/30" : "border-white/15 bg-white/[0.06]"
        }`}
      >
        <span
          aria-hidden
          className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full transition-all ${
            on ? "left-[24px] bg-stream" : "left-[3px] bg-white/50"
          }`}
        />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const [name, setName] = useState("The Iterators");
  const [slug, setSlug] = useState("the-iterators");

  return (
    <div className="mx-auto max-w-3xl px-6 py-7">
      <PageHeader
        title="Settings"
        lede="Workspace identity and the runtime defaults new workflows inherit."
      />
      <PreviewNote>
        Interface only. Runtime behaviour is still read from{" "}
        <code className="font-mono text-white/60">backend/.env</code> and{" "}
        <code className="font-mono text-white/60">config.py</code>; these controls do not write to
        either.
      </PreviewNote>

      <section className="void-card rounded-2xl p-5">
        <h2 className="font-head text-[14px] font-semibold text-white">Workspace</h2>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">Display name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="void-input h-9 w-full rounded-xl px-3 font-sans text-[13px] text-white focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">Slug</span>
            <input
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              className="void-input h-9 w-full rounded-xl px-3 font-mono text-[12.5px] text-white focus:outline-none"
            />
            <span className="mt-1.5 block font-sans text-[11px] text-white/40">
              Used in run URLs and trace names.
            </span>
          </label>
        </div>
      </section>

      <section className="void-card mt-4 rounded-2xl px-5 py-1">
        <h2 className="pb-1 pt-4 font-head text-[14px] font-semibold text-white">
          Execution defaults
        </h2>
        <div className="divide-y divide-white/[0.07]">
          <Toggle
            id="set-offline"
            label="Offline mode"
            hint="Simulate the model and the tool clients deterministically and touch no network. What the test suite pins."
          />
          <Toggle
            id="set-breaker"
            label="Budget circuit breaker"
            hint="Reserve each call's worst case before it is sent, and sever a branch rather than overspend."
            defaultOn
          />
          <Toggle
            id="set-cache"
            label="Context-aware semantic cache"
            hint="Admit a hit only when the query and its upstream context both clear the threshold."
            defaultOn
          />
          <Toggle
            id="set-tracing"
            label="Export traces to Langfuse"
            hint="One span per request, node, completion, cache probe and tool call, over OTLP."
            defaultOn
          />
        </div>
        <div className="h-3" />
      </section>

      <section className="void-card mt-4 rounded-2xl border-red-500/20 p-5">
        <h2 className="font-head text-[14px] font-semibold text-white">Danger zone</h2>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="font-sans text-[13px] text-white">Reset the PASTE transition matrix</p>
            <p className="mt-1 font-sans text-[11.5px] leading-relaxed text-white/45">
              Returns speculative pre-fetching to cold. Equivalent to{" "}
              <code className="font-mono text-white/60">python clean_db.py</code>.
            </p>
          </div>
          <button
            type="button"
            className="h-9 shrink-0 rounded-xl border border-red-500/30 px-4 font-head text-[13px] font-medium text-red-300 transition-colors hover:border-red-500/55 hover:bg-red-500/10"
          >
            Reset matrix
          </button>
        </div>
      </section>
    </div>
  );
}
