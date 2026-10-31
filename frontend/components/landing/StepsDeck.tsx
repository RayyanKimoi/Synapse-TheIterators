import type { CSSProperties } from "react";

/**
 * The compiler's four passes, as a deck that converges on scroll: the cards
 * fly in from the edges and square up into one stack. CSS does the motion —
 * ScrollStage only flips `data-settled` on arrival.
 */

type Pass = {
  index: string;
  name: string;
  claim: string;
  detail: string;
  proof: string;
};

const PASSES: Pass[] = [
  {
    index: "01",
    name: "Ready-Node Scheduler",
    claim: "Dispatch the instant a dependency clears",
    detail:
      "An asyncio queue and a task group bounded by max_concurrent_tasks. Every node carries an in-degree countdown; a child that hits zero goes out immediately instead of waiting for its depth tier.",
    proof: "Dispatches 8 000 ms earlier than depth-tiering on an asymmetric DAG",
  },
  {
    index: "02",
    name: "Context-Aware Semantic Cache",
    claim: "Two vectors, or it is not a hit",
    detail:
      "The query and its upstream context are embedded separately and both must clear the threshold. Model, system prompt, tool, params and side-effect are hashed into the key, so similarity only ever decides whether the question matched.",
    proof: "0.98 on a paraphrase, 0.30 across topics, 1.00 exact",
  },
  {
    index: "03",
    name: "PASTE Speculative Prefetch",
    claim: "Fire the tool call during the decode",
    detail:
      "A SQLite transition matrix over observed runs. A target is speculated only above P > 0.75 with at least three observations, never for a side-effecting node and never in the baseline lane.",
    proof: "A search finished 1.6 ms before the scheduler asked for it",
  },
  {
    index: "04",
    name: "DSPy-Assisted Prompt Fusion",
    claim: "One call where the graph allows one call",
    detail:
      "Maximal chains of adjacent, private, read-only LLM nodes on the same model merge into a single signature with one output field each. Any member whose field comes back empty abandons the fusion for that run.",
    proof: "Two runs in three fuse; the third falls back and still returns content",
  },
];

export function StepsDeck() {
  return (
    // `clip` rather than `hidden`: it contains the cards' off-edge entry without
    // making this a scroll container, which would break the sticky panels.
    <div className="grid gap-4 overflow-x-clip md:grid-cols-2 xl:grid-cols-4">
      {PASSES.map((pass, index) => {
        const fromLeft = index % 2 === 0;
        return (
          <article
            key={pass.index}
            data-settle
            className="deck-card glass group relative overflow-hidden rounded-2xl border border-white/[0.07] p-5 transition-colors duration-300 hover:border-stream/30"
            style={
              {
                // Alternating entry from the left and right edges.
                "--deck-x": fromLeft ? "-14vw" : "14vw",
                "--deck-y": "26px",
                "--deck-r": fromLeft ? "-3.5deg" : "3.5deg",
                "--settle-at": `${index * 110}ms`,
              } as CSSProperties
            }
          >
            <span
              aria-hidden
              className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-stream/[0.07] blur-2xl transition-opacity duration-300 group-hover:bg-stream/[0.14]"
            />
            <div className="flex items-center gap-3 font-sans text-[10px] uppercase tracking-[0.22em] text-white/50">
              <span className="stream-text tabular">{pass.index}</span>
              <span className="hairline h-px flex-1" />
            </div>
            <h3 className="mt-4 font-display text-[19px] leading-tight tracking-tight text-white">
              {pass.name}
            </h3>
            <p className="mt-2 font-serif text-[16px] leading-snug text-white/70">{pass.claim}</p>
            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-white/55">{pass.detail}</p>
            <p className="stream-text mt-4 font-sans text-[10.5px] uppercase tracking-[0.14em]">
              {pass.proof}
            </p>
          </article>
        );
      })}
    </div>
  );
}
