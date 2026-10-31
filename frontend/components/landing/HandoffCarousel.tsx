"use client";

import { useMemo } from "react";

import { LiquidGlassCarousel } from "@/components/ui/liquid-glass-carousel";

/**
 * The workflow-handoff carousel.
 *
 * The carousel renders its panels as WebGL textures, so each card is drawn
 * here as an SVG and handed over as a data URI. That keeps the whole section
 * in-repo: no stock photography, no network fetch, and the copy stays
 * editable as text rather than baked into a binary. The carousel wraps itself
 * in a WebGL error boundary, so a machine without WebGL still gets a fallback.
 */

type Handoff = {
  step: string;
  title: string;
  from: string;
  to: string;
  body: string;
};

const HANDOFFS: Handoff[] = [
  {
    step: "01",
    title: "Parse",
    from: "Agent script",
    to: "Intermediate representation",
    body: "The imperative script becomes an IR and a directed acyclic graph. Cycles are rejected here, at compile time, not discovered mid-run.",
  },
  {
    step: "02",
    title: "Plan",
    from: "Graph",
    to: "Dependency tree",
    body: "Each node's in-degree is counted and the critical path is measured, so the scheduler knows what can move the moment a dependency clears.",
  },
  {
    step: "03",
    title: "Dispatch",
    from: "Scheduler",
    to: "Worker pool",
    body: "A ready-node queue bounded by an explicit concurrency ceiling. Depth tiers label the canvas; they never gate what runs.",
  },
  {
    step: "04",
    title: "Elide",
    from: "Probe",
    to: "Semantic cache",
    body: "Query and upstream context are embedded separately, and both must clear the threshold before an answer is reused.",
  },
  {
    step: "05",
    title: "Speculate",
    from: "Transition matrix",
    to: "Tool call",
    body: "A tool request fires before the model finishes decoding, so the round trip overlaps generation instead of following it.",
  },
  {
    step: "06",
    title: "Verify",
    from: "Merged payload",
    to: "Contract",
    body: "The sink's declared output keys are checked after the last node terminates. A run that drifts fails loudly rather than quietly.",
  },
];

const W = 900;
const H = 1200;

/** One card, drawn as an SVG string sized for the carousel's 3:4 panels. */
function cardSvg({ step, title, from, to, body }: Handoff): string {
  // Wrap by hand: SVG has no flow layout, and the panel width is fixed.
  const words = body.split(" ");
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    if ((line + " " + word).trim().length > 34) {
      lines.push(line.trim());
      line = word;
    } else {
      line = (line + " " + word).trim();
    }
  }
  if (line) lines.push(line);

  const copy = lines
    .map(
      (text, index) =>
        `<text x="72" y="${720 + index * 44}" font-family="Helvetica,Arial,sans-serif" font-size="30" fill="#ffffff" fill-opacity="0.58">${text}</text>`,
    )
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="#0c0f0a"/>
      <stop offset="55%" stop-color="#050505"/>
      <stop offset="100%" stop-color="#000000"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.1" r="0.8">
      <stop offset="0%" stop-color="#a3e635" stop-opacity="0.26"/>
      <stop offset="100%" stop-color="#a3e635" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="${W}" height="${H}" fill="url(#bg)"/>
  <rect width="${W}" height="${H}" fill="url(#glow)"/>
  <rect x="8" y="8" width="${W - 16}" height="${H - 16}" rx="40" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="2"/>

  <text x="72" y="130" font-family="Helvetica,Arial,sans-serif" font-size="26" letter-spacing="6" fill="#a3e635">${step}</text>
  <line x1="150" y1="120" x2="${W - 72}" y2="120" stroke="#ffffff" stroke-opacity="0.12" stroke-width="2"/>

  <text x="72" y="300" font-family="Helvetica,Arial,sans-serif" font-size="104" font-weight="bold" fill="#ffffff">${title}</text>

  <text x="72" y="400" font-family="Helvetica,Arial,sans-serif" font-size="26" fill="#ffffff" fill-opacity="0.42">${from}</text>
  <text x="72" y="452" font-family="Helvetica,Arial,sans-serif" font-size="26" fill="#a3e635">${to}</text>

  <circle cx="84" cy="540" r="10" fill="#a3e635"/>
  <line x1="94" y1="540" x2="${W - 160}" y2="540" stroke="#a3e635" stroke-opacity="0.45" stroke-width="3"/>
  <circle cx="${W - 150}" cy="540" r="10" fill="none" stroke="#a3e635" stroke-width="3"/>

  ${copy}
</svg>`;
}

const toDataUri = (svg: string) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg.replace(/\n\s*/g, " "))}`;

export function HandoffCarousel() {
  const items = useMemo(
    () =>
      HANDOFFS.map((handoff) => ({
        src: toDataUri(cardSvg(handoff)),
        title: `${handoff.step} — ${handoff.title}`,
        aspect: W / H,
      })),
    [],
  );

  return (
    <div className="relative">
      <LiquidGlassCarousel items={items} panelHeight={420} gap={26} background="#000000" entry />
      {/* The carousel paints to a canvas, so the copy is restated for readers
          who will never see it. */}
      <ul className="sr-only">
        {HANDOFFS.map((handoff) => (
          <li key={handoff.step}>
            {handoff.step} {handoff.title}: {handoff.from} to {handoff.to}. {handoff.body}
          </li>
        ))}
      </ul>
    </div>
  );
}
