"use client";

import { useState } from "react";

import { PageHeader, PreviewNote } from "@/components/dashboard/PageHeader";
import { IconCopy, IconEye, IconEyeOff } from "@/components/dashboard/icons";

/**
 * API keys. Every field is masked by default and reveal is per-field and
 * explicit, so a shared screen never exposes a credential by accident.
 *
 * UI only: nothing here is persisted or sent anywhere. Real credentials live
 * in the backend's `.env` and are never served to the browser.
 */

type KeyFieldProps = {
  id: string;
  label: string;
  hint: string;
  placeholder: string;
  defaultValue?: string;
};

function KeyField({ id, label, hint, placeholder, defaultValue = "" }: KeyFieldProps) {
  const [value, setValue] = useState(defaultValue);
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked; the field is still selectable by hand */
    }
  };

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block font-sans text-[12px] text-white/70">
        {label}
      </label>
      <div className="void-input flex h-9 items-center gap-1 rounded-xl pl-3 pr-1">
        <input
          id={id}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          type={shown ? "text" : "password"}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent font-mono text-[12.5px] text-white placeholder:font-sans placeholder:text-white/30 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => setShown((v) => !v)}
          aria-label={shown ? `Hide ${label}` : `Reveal ${label}`}
          aria-pressed={shown}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-white/45 transition-colors hover:bg-white/10 hover:text-white"
        >
          {shown ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={copy}
          aria-label={`Copy ${label}`}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-white/45 transition-colors hover:bg-white/10 hover:text-white"
        >
          <IconCopy className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-1.5 font-sans text-[11px] leading-relaxed text-white/40">
        {copied ? <span className="text-stream">Copied to clipboard.</span> : hint}
      </p>
    </div>
  );
}

export default function KeysPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-7">
      <PageHeader
        title="API keys"
        lede="Credentials this workspace uses to reach models, tools and the evaluation judge."
      />
      <PreviewNote>
        Interface only — nothing typed here is saved or transmitted. The running backend reads its
        credentials from <code className="font-mono text-white/60">backend/.env</code>, which is
        never exposed to the browser.
      </PreviewNote>

      <section className="void-card rounded-2xl p-5">
        <h2 className="font-head text-[14px] font-semibold text-white">Platform keys</h2>
        <p className="mt-1 font-sans text-[12px] text-white/45">
          Issued by SYNAPSE. Used by the gateway and the tool clients.
        </p>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <KeyField
            id="key-platform"
            label="Platform key"
            placeholder="syn_live_••••••••••••••••"
            hint="Authenticates this workspace against the SYNAPSE gateway."
          />
          <KeyField
            id="key-tavily"
            label="Tavily (tool I/O)"
            placeholder="tvly-••••••••••••••••"
            hint="Search and crawl nodes. Configured and live on this deployment."
          />
        </div>
      </section>

      <section className="void-card mt-4 rounded-2xl p-5">
        <h2 className="font-head text-[14px] font-semibold text-white">Private BYOK keys</h2>
        <p className="mt-1 font-sans text-[12px] text-white/45">
          Bring your own provider credentials. Requests route directly; SYNAPSE never stores the
          completion body.
        </p>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <KeyField
            id="key-litellm"
            label="litellm proxy"
            placeholder="sk-••••••••••••••••"
            hint="The tunnel the self-hosted Qwen model sits behind."
          />
          <KeyField
            id="key-openai"
            label="OpenAI-compatible"
            placeholder="sk-••••••••••••••••"
            hint="Optional. Used only if a workflow declares an OpenAI model."
          />
        </div>
      </section>

      {/* The judge is the one credential that changes what the product can
          claim, so it gets its own panel rather than a row in a list. */}
      <section className="void-card void-card-hover mt-4 overflow-hidden rounded-2xl border-stream/25">
        <div className="flex items-start gap-4 border-b border-white/10 bg-stream/[0.05] p-5">
          <span
            aria-hidden
            className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-stream/30 bg-stream/10"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              className="h-[18px] w-[18px] text-stream"
            >
              <path d="M12 4v16M6 8l-3 6h6l-3-6ZM18 8l-3 6h6l-3-6Z" />
              <path d="M7 20h10" />
            </svg>
          </span>
          <div className="min-w-0">
            <h2 className="font-head text-[14px] font-semibold text-white">
              LLM-as-a-judge
              <span className="ml-2 rounded-md border border-stream/30 bg-stream/10 px-1.5 py-0.5 align-middle font-sans text-[10px] uppercase tracking-[0.1em] text-stream">
                Evaluation
              </span>
            </h2>
            <p className="mt-1.5 font-sans text-[12px] leading-relaxed text-white/55">
              An independent model compares the baseline and compiled outputs in both directions and
              calls them equivalent only when both agree. It judges the pipeline, so it is
              deliberately kept outside it — offline mode does not disable it, and with no key it
              reports itself unavailable rather than inventing a verdict.
            </p>
          </div>
        </div>

        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <KeyField
            id="key-gemini"
            label="Gemini API key"
            placeholder="AIza••••••••••••••••"
            hint="Not set on this deployment — the judge currently reports unavailable."
          />
          <label className="block">
            <span className="mb-1.5 block font-sans text-[12px] text-white/70">Judge model</span>
            <select
              defaultValue="gemini-3.5-flash"
              className="void-input h-9 w-full rounded-xl px-3 font-sans text-[13px] text-white focus:outline-none"
            >
              <option className="bg-[#0a0a0a]">gemini-3.5-flash</option>
              <option className="bg-[#0a0a0a]">gemini-3.5-pro</option>
            </select>
            <span className="mt-1.5 block font-sans text-[11px] text-white/40">
              Flash is the default: the comparison is short and runs twice per evaluation.
            </span>
          </label>
        </div>
      </section>
    </div>
  );
}
