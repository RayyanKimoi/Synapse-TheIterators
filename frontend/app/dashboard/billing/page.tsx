import { PageHeader, PreviewNote } from "@/components/dashboard/PageHeader";
import { TIERS, USAGE } from "@/lib/dashboard-data";

/**
 * Billing: the current plan, what the workspace has consumed against it, and
 * where it could move. UI only — no payment provider is wired.
 */

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** A ratio against a limit, drawn as a ring: accent arc on a same-ramp track. */
function UsageRing({ label, used, limit, unit }: (typeof USAGE)[number]) {
  const share = Math.max(0, Math.min(1, used / limit));
  const pct = Math.round(share * 100);
  const fmt = (value: number) =>
    `${value >= 1000 ? value.toLocaleString("en-US") : value}${unit}`;

  return (
    <div className="void-card void-card-hover flex items-center gap-5 rounded-2xl p-5">
      <div className="relative shrink-0">
        <svg viewBox="0 0 128 128" className="h-[104px] w-[104px] -rotate-90">
          <circle
            cx="64"
            cy="64"
            r={RADIUS}
            fill="none"
            stroke="hsl(var(--stream) / 0.15)"
            strokeWidth="9"
          />
          <circle
            cx="64"
            cy="64"
            r={RADIUS}
            fill="none"
            stroke="hsl(var(--stream))"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - share)}
            style={{ filter: "drop-shadow(0 0 6px hsl(var(--stream) / 0.6))" }}
          />
        </svg>
        <span className="absolute inset-0 grid place-items-center">
          <span className="font-head text-[20px] font-bold leading-none text-white">{pct}%</span>
        </span>
      </div>

      <div className="min-w-0">
        <p className="font-head text-[13.5px] font-semibold text-white">{label}</p>
        <p className="tabular mt-1.5 font-sans text-[12.5px] text-white/60">
          {fmt(used)} <span className="text-white/35">of {fmt(limit)}</span>
        </p>
        <p className="mt-1 font-sans text-[11px] text-white/40">Resets on the 1st</p>
      </div>
    </div>
  );
}

export default function BillingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-7">
      <PageHeader
        title="Billing"
        lede="What this workspace is consuming against its plan, and the tiers available to it."
      />
      <PreviewNote>
        Interface only — no payment provider is connected and the usage figures are sample data.
      </PreviewNote>

      <section aria-label="Usage this cycle" className="grid gap-3 pb-9 lg:grid-cols-3">
        {USAGE.map((meter) => (
          <UsageRing key={meter.label} {...meter} />
        ))}
      </section>

      <h2 className="pb-4 font-head text-[15px] font-semibold text-white">Plans</h2>
      <section className="grid gap-3 lg:grid-cols-3">
        {TIERS.map((tier) => (
          <div
            key={tier.id}
            className={`void-card void-card-hover flex flex-col rounded-2xl p-6 ${
              tier.current ? "border-stream/35" : ""
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-head text-[15px] font-semibold text-white">{tier.name}</h3>
              {tier.current && (
                <span className="rounded-md border border-stream/30 bg-stream/10 px-2 py-0.5 font-sans text-[10px] uppercase tracking-[0.1em] text-stream">
                  Current
                </span>
              )}
            </div>

            <p className="mt-4 flex items-baseline gap-1.5">
              <span className="font-head text-[30px] font-bold leading-none tracking-tight text-white">
                {tier.price}
              </span>
              <span className="font-sans text-[12px] text-white/45">{tier.cadence}</span>
            </p>

            <p className="mt-3 font-sans text-[12.5px] leading-relaxed text-white/50">
              {tier.blurb}
            </p>

            <ul className="mt-5 flex-1 space-y-2.5">
              {tier.features.map((feature) => (
                <li key={feature} className="flex items-start gap-2.5">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stream"
                  >
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span className="font-sans text-[12.5px] leading-snug text-white/70">
                    {feature}
                  </span>
                </li>
              ))}
            </ul>

            <button
              type="button"
              disabled={tier.current}
              className={`mt-6 h-9 w-full rounded-xl font-head text-[13px] font-semibold transition-opacity ${
                tier.current
                  ? "cursor-default border border-white/10 text-white/35"
                  : "bg-stream text-black hover:opacity-90"
              }`}
            >
              {tier.current ? "Your plan" : `Move to ${tier.name}`}
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
