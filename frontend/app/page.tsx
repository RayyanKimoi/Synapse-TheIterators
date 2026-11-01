import Image from "next/image";
import Link from "next/link";
import { ArrowRight, GitBranch } from "lucide-react";

import { AgentMesh } from "@/components/landing/AgentMesh";
import { AgentPipeline } from "@/components/landing/AgentPipeline";
import { AgentRack } from "@/components/landing/AgentRack";
import { ScrollStage } from "@/components/landing/Motion";
import { LaptopShowcase } from "@/components/landing/LaptopShowcase";
import { StepsDeck } from "@/components/landing/StepsDeck";
import { Telemetry } from "@/components/landing/Telemetry";
import { ClosingPlasma } from "@/components/ui/closing-plasma";
import { FlightStatusCard } from "@/components/ui/flight-status-card";
import { ScrollBasedVelocity } from "@/components/ui/scroll-based-velocity";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV = [
  { href: "#execution", label: "Execution" },
  { href: "#optimization", label: "Optimization" },
];

const PILLARS = [
  {
    title: "Deterministic orchestration",
    body: "The workflow is parsed into an intermediate representation and a directed acyclic graph before a single token is spent. Cycles are rejected at compile time, not discovered at runtime.",
  },
  {
    title: "Parallel execution",
    body: "A ready-node scheduler dispatches each node the instant its last dependency clears, bounded by an explicit concurrency ceiling. Depth tiers label the canvas; they never gate dispatch.",
  },
  {
    title: "Cost optimization",
    body: "Semantic caching, speculative tool pre-fetching and prompt fusion each remove work the graph proves is redundant — under a budget circuit breaker that severs a branch before it overspends.",
  },
];

function Logo({ size = 38 }: { size?: number }) {
  return (
    <Image
      src="/synapse-logo.png"
      alt="SYNAPSE"
      width={size}
      height={size}
      priority
      style={{ width: size, height: size }}
    />
  );
}

export default function LandingPage() {
  return (
    <ScrollStage>
      <main className="relative min-h-screen overflow-x-clip bg-void font-sans text-white antialiased">
        {/* Ambient neon field behind the whole document. */}
        <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
          <ClosingPlasma
            className="h-full w-full"
            darkColorA="#a3e635"
            darkColorB="#0a1f0c"
            darkColorC="#000000"
            speed={0.55}
            turbulence={0.8}
            grain={0.35}
            sparkle={0.5}
            vignette={2}
            opacity={0.12}
            interactive={false}
          />
        </div>

        {/* The stream: one hairline the length of the page with a glow riding it. */}
        <div aria-hidden className="pointer-events-none fixed inset-y-0 left-6 z-40 w-px sm:left-10 lg:left-16">
          <div className="stream-rail absolute inset-0" />
          <div data-stream className="absolute inset-0">
            <span className="stream-head absolute left-1/2 h-16 w-px -translate-x-1/2 -translate-y-1/2 rounded-full" />
          </div>
        </div>

        <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-void/70 backdrop-blur-xl">
          <nav className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 pl-12 sm:gap-6 sm:px-6 sm:pl-20 lg:pl-28">
            <Link href="/" className="flex items-center gap-2.5">
              <Logo />
              <span className="font-head text-[17px] font-bold tracking-[-0.01em]">SYNAPSE</span>
            </Link>
            <span className="hidden font-sans text-[11px] uppercase tracking-[0.2em] text-white/45 sm:inline">
              Workflow compiler
            </span>
            <div className="ml-auto flex items-center gap-1">
              {NAV.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="hidden rounded-lg px-3 py-2 font-head text-[13px] font-medium text-white/60 transition-colors hover:text-white sm:inline-block"
                >
                  {item.label}
                </a>
              ))}
              <ThemeToggle className="ml-1" />
              <Link
                href="/dashboard"
                className="ml-2 inline-flex items-center gap-1.5 rounded-lg bg-stream px-3 py-2 font-head text-[13px] font-semibold text-black transition-opacity hover:opacity-90 sm:px-3.5"
              >
                Open the arena
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </nav>
        </header>

        {/* ---------------------------------------------------------- hero -- */}
        <section data-panel className="stack-panel z-10 flex min-h-screen items-center bg-void/[0.88]">
          <div className="mx-auto w-full max-w-7xl px-4 pb-8 pl-12 pt-8 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                Compiler · Runtime · Observability
              </p>
              <h1 className="mt-5 max-w-4xl font-head text-[clamp(2.1rem,4.6vw,3.5rem)] font-extrabold leading-[1.02] tracking-[-0.03em]">
                Deterministic orchestration
                <br />
                for agent workflows.
                <br />
                <span className="stream-text">Parallel by construction.</span>
              </h1>
              <p className="mt-5 max-w-2xl font-sans text-[16px] leading-relaxed text-white/60">
                SYNAPSE intercepts imperative agent scripts and compiles them into dependency-aware
                execution trees. Independent work runs concurrently, redundant work is never issued
                twice, and every pass is verified against the workflow&apos;s own correctness
                contract.
              </p>
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-2">
              <div
                data-settle
                className="settle glass relative overflow-hidden rounded-2xl border border-white/[0.07] bg-void/40 p-4"
                style={{ "--settle-at": "90ms" } as React.CSSProperties}
              >
                <div className="flex items-baseline justify-between font-sans text-[10px] uppercase tracking-[0.2em] text-white/55">
                  <span>Before · imperative</span>
                  <span className="text-white/40">1 slot</span>
                </div>
                <div className="mt-2 h-[252px]">
                  <AgentPipeline />
                </div>
              </div>

              <div
                data-settle
                className="settle glass glass-lime relative overflow-hidden rounded-2xl border border-white/[0.07] bg-void/40 p-4"
                style={{ "--settle-at": "170ms" } as React.CSSProperties}
              >
                <div className="flex items-baseline justify-between font-sans text-[10px] uppercase tracking-[0.2em] text-white/55">
                  <span>After · compiled</span>
                  <span className="stream-text">6 concurrent</span>
                </div>
                <div className="mt-2 h-[252px] overflow-hidden">
                  <AgentMesh />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Typographic transition between acts. */}
        <div
          aria-hidden
          className="relative z-30 overflow-hidden border-y border-white/[0.06] bg-void py-5 font-head text-[clamp(1.6rem,4vw,2.8rem)] font-extrabold uppercase tracking-[-0.02em] text-white/[0.09]"
        >
          <ScrollBasedVelocity text="Parallel execution · Semantic caching · Speculative prefetch · Prompt fusion · " />
        </div>

        {/* ------------------------------------------------- product demo -- */}
        <section className="relative z-40 border-t border-white/[0.06] bg-void py-20">
          <div className="mx-auto w-full max-w-7xl px-4 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle mx-auto max-w-3xl pb-10 text-center">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                See it run
              </p>
              <h2 className="mt-4 font-head text-[clamp(1.8rem,4vw,3rem)] font-extrabold leading-[1.04] tracking-[-0.028em]">
                The arena, in motion.
              </h2>
            </div>
            <LaptopShowcase />
          </div>
        </section>

        {/* ----------------------------------------------------- execution -- */}
        <section
          id="execution"
          data-panel
          className="stack-panel z-20 flex min-h-screen items-center border-t border-white/[0.06] bg-void"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-14 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle max-w-3xl">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                Measured, not projected
              </p>
              <h2 className="mt-4 font-head text-[clamp(1.8rem,4vw,3rem)] font-extrabold leading-[1.04] tracking-[-0.028em]">
                Two lanes. One clock.
              </h2>
              <p className="mt-4 font-sans text-[15px] leading-relaxed text-white/60">
                Telemetry streams over SSE as the run proceeds — node state, tokens and cost
                settling in real time against a correctness gate.
              </p>
            </div>

            <div
              data-settle
              className="settle mt-10"
              style={{ "--settle-at": "90ms" } as React.CSSProperties}
            >
              <Telemetry />
            </div>
          </div>
        </section>

        {/* -------------------------------------------------- optimization -- */}
        <section
          id="optimization"
          data-panel
          className="stack-panel z-30 flex min-h-screen items-center border-t border-white/[0.06] bg-void"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-14 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle max-w-3xl">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                Four optimization passes
              </p>
              <h2 className="mt-4 font-head text-[clamp(1.8rem,4vw,3rem)] font-extrabold leading-[1.04] tracking-[-0.028em]">
                Nothing here is a multiplier.
              </h2>
              <p className="mt-4 font-sans text-[15px] leading-relaxed text-white/60">
                Each pass is real code with a real failure mode, traced live until it could be
                proved. Two of them had their fabricated constants deleted on the way.
              </p>
            </div>

            <div className="mt-10">
              <StepsDeck />
            </div>
          </div>
        </section>

        {/* ------------------------------------------------- engine detail -- */}
        <section className="relative z-40 border-t border-white/[0.06] bg-void">
          <div className="mx-auto w-full max-w-7xl px-4 py-20 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle max-w-3xl">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                The execution engine
              </p>
              <h2 className="mt-4 font-head text-[clamp(1.6rem,3.4vw,2.5rem)] font-extrabold leading-[1.06] tracking-[-0.025em]">
                One machine. Six lanes open at once.
              </h2>
            </div>

            <div className="mt-10 grid gap-4 lg:grid-cols-[1.08fr_0.92fr] lg:items-start">
              <div
                data-settle
                className="settle"
                style={{ "--settle-at": "90ms" } as React.CSSProperties}
              >
                <AgentRack />
              </div>
              <div
                data-settle
                className="settle flex justify-center"
                style={{ "--settle-at": "150ms" } as React.CSSProperties}
              >
                <FlightStatusCard
                  departureCode="BASE"
                  arrivalCode="COMP"
                  departureCity="Sequential chain"
                  arrivalCity="Compiled tree"
                  departureTime="35 000 ms"
                  arrivalTime="14 730 ms"
                  eta="14 730 ms"
                  timezone="critical path"
                  nextEvent="Merge node"
                  nextEventTime="t+14.7s"
                  progress={57.9}
                  remainingTime="20 270 ms saved"
                />
              </div>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------- the thesis -- */}
        <section className="relative z-40 border-t border-white/[0.06] bg-void">
          <div className="mx-auto w-full max-w-7xl px-4 py-20 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <blockquote
              data-settle
              className="settle max-w-4xl font-serif text-[clamp(1.4rem,3.2vw,2.3rem)] leading-[1.3] tracking-[-0.01em] text-white/85"
            >
              Current pipelines are embarrassingly sequential by accident — agents calling APIs and
              waiting hundreds of milliseconds serially, compounding the critical path.
              <span className="stream-text"> A compiler does not accept that.</span>
            </blockquote>

            <dl className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.07] md:grid-cols-3">
              {PILLARS.map((pillar, index) => (
                <div
                  key={pillar.title}
                  data-settle
                  className="settle bg-void p-7"
                  style={{ "--settle-at": `${index * 90}ms` } as React.CSSProperties}
                >
                  <dt className="font-head text-[16px] font-bold tracking-tight text-white">
                    {pillar.title}
                  </dt>
                  <dd className="mt-3 font-sans text-[13px] leading-relaxed text-white/55">
                    {pillar.body}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ----------------------------------------------------------- cta -- */}
        <section className="relative z-40 border-t border-white/[0.06] bg-void/[0.93]">
          <div className="mx-auto w-full max-w-7xl px-4 py-20 pl-12 sm:px-6 sm:pl-20 lg:pl-28">
            <div data-settle className="settle glass glass-lime rounded-3xl border border-white/[0.07] p-8 sm:p-12">
              <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-white/50">
                Empirical proof, not a claim
              </p>
              {/* The one hero figure on the page, in the display face. */}
              <p className="metric mt-5 text-[clamp(4rem,13vw,9rem)] leading-[0.82] tracking-[-0.01em] text-white">
                57.9<span className="stream-text">%</span>
              </p>
              <p className="mt-4 max-w-xl font-sans text-[15px] leading-relaxed text-white/60">
                of the critical path eliminated on the reference workflow — 35 000 ms sequential
                against 14 730 ms compiled, both measured on the same engine and the same hardware.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-2 rounded-xl bg-stream px-5 py-3 font-head text-[14px] font-semibold text-black transition-opacity hover:opacity-90"
                >
                  Open the arena
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a
                  href="https://github.com"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/[0.12] px-5 py-3 font-head text-[14px] font-medium text-white/80 transition-colors hover:border-white/25 hover:text-white"
                >
                  <GitBranch className="h-4 w-4" />
                  Read the compiler
                </a>
              </div>
            </div>

            <footer className="mt-14 flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] pt-8 font-sans text-[12px] text-white/50">
              <span className="flex items-center gap-2.5">
                <Logo size={26} />
                SYNAPSE · Intelligent AI workflow compiler
              </span>
              <span className="font-head uppercase tracking-[0.2em]">The Iterators</span>
            </footer>
          </div>
        </section>
      </main>
    </ScrollStage>
  );
}
