"use client";

import { useMemo, useState } from "react";

import { PageHeader, PreviewNote } from "@/components/dashboard/PageHeader";
import { IconSearch } from "@/components/dashboard/icons";
import { LEDGER, LEDGER_TAGS, type LedgerStatus } from "@/lib/dashboard-data";

/**
 * The work ledger: a time-ordered record of runs, searchable and filterable
 * by tag. Status is a dot plus a word — never colour alone.
 */

const DOT: Record<LedgerStatus, string> = {
  success: "dot-ok",
  waiting: "dot-wait",
  failed: "dot-fail",
};

const STATUS_LABEL: Record<LedgerStatus, string> = {
  success: "Succeeded",
  waiting: "Waiting",
  failed: "Halted",
};

const ms = (value: number) => (value ? `${value.toLocaleString("en-US")} ms` : "—");

export default function HistoryPage() {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<string[]>([]);

  const toggleTag = (tag: string) =>
    setActive((tags) => (tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag]));

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return LEDGER.filter((entry) => {
      const matchesQuery =
        !needle ||
        entry.title.toLowerCase().includes(needle) ||
        entry.id.toLowerCase().includes(needle) ||
        entry.tags.some((tag) => tag.includes(needle));
      // Every selected tag must be present, so filters narrow rather than widen.
      const matchesTags = active.every((tag) => entry.tags.includes(tag));
      return matchesQuery && matchesTags;
    });
  }, [query, active]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-7">
      <PageHeader
        title="Usage history"
        lede="Every execution this workspace has run, newest first — the pipeline it took, what it cost, and how it ended."
      />
      <PreviewNote>
        Sample ledger. There is no history endpoint yet, so these rows come from{" "}
        <code className="font-mono text-white/60">lib/dashboard-data.ts</code>; their latencies
        mirror the measured runs in the project log.
      </PreviewNote>

      <div className="flex flex-wrap items-center gap-3 pb-5">
        <div className="void-input flex h-9 min-w-0 flex-1 items-center gap-2.5 rounded-xl px-3 sm:max-w-xs">
          <IconSearch className="h-4 w-4 shrink-0 text-white/40" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            type="search"
            placeholder="Search runs…"
            aria-label="Search runs"
            className="min-w-0 flex-1 bg-transparent font-sans text-[13px] text-white placeholder:text-white/35 focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {LEDGER_TAGS.map((tag) => {
            const on = active.includes(tag);
            return (
              <button
                key={tag}
                type="button"
                onClick={() => toggleTag(tag)}
                aria-pressed={on}
                className={`rounded-lg border px-2.5 py-1 font-sans text-[11px] transition-colors ${
                  on
                    ? "border-stream/40 bg-stream/15 text-stream"
                    : "border-white/10 text-white/50 hover:border-white/25 hover:text-white"
                }`}
              >
                {tag}
              </button>
            );
          })}
          {active.length > 0 && (
            <button
              type="button"
              onClick={() => setActive([])}
              className="px-2 py-1 font-sans text-[11px] text-white/40 underline-offset-2 hover:text-white hover:underline"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="void-card overflow-hidden rounded-2xl">
        <div className="hidden grid-cols-[1fr_auto_auto_auto_auto] gap-4 border-b border-white/10 px-5 py-3 font-sans text-[10.5px] uppercase tracking-[0.14em] text-white/40 md:grid">
          <span>Run</span>
          <span className="text-right">Latency</span>
          <span className="text-right">Tokens</span>
          <span className="text-right">Cost</span>
          <span className="text-right">Status</span>
        </div>

        <ul>
          {rows.map((entry) => (
            <li
              key={entry.id}
              className="grid grid-cols-1 gap-2 border-b border-white/[0.07] px-5 py-3.5 transition-colors last:border-b-0 hover:bg-white/[0.03] md:grid-cols-[1fr_auto_auto_auto_auto] md:items-center md:gap-4"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${DOT[entry.status]}`} />
                <div className="min-w-0">
                  <p className="truncate font-sans text-[13px] text-white">{entry.title}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 font-sans text-[11px] text-white/40">
                    <span className="font-mono">{entry.id}</span>
                    <span aria-hidden>·</span>
                    <span className="capitalize">{entry.pipeline}</span>
                    <span aria-hidden>·</span>
                    <span>{entry.when}</span>
                  </p>
                </div>
              </div>
              <span className="tabular font-sans text-[12.5px] text-white/70 md:text-right">
                {ms(entry.latencyMs)}
              </span>
              <span className="tabular font-sans text-[12.5px] text-white/70 md:text-right">
                {entry.tokens ? entry.tokens.toLocaleString("en-US") : "—"}
              </span>
              <span className="tabular font-sans text-[12.5px] text-white/70 md:text-right">
                {entry.costUsd ? `$${entry.costUsd.toFixed(4)}` : "—"}
              </span>
              <span className="font-sans text-[12px] text-white/60 md:text-right">
                {STATUS_LABEL[entry.status]}
              </span>
            </li>
          ))}
        </ul>

        {rows.length === 0 && (
          <p className="px-5 py-10 text-center font-sans text-[13px] text-white/40">
            No runs match that search.
          </p>
        )}
      </div>
    </div>
  );
}
