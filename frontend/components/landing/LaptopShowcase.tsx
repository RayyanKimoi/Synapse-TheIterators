"use client";

/**
 * A MacBook-style frame with a looping screen capture inside it.
 *
 * The clip is served from /public (drop the file in as laptop-demo.mp4; a .mov
 * fallback is also wired). It autoplays muted + looped, which every browser
 * allows without a gesture. If the file is missing the screen just stays black
 * behind the caption — nothing throws.
 */
export function LaptopShowcase() {
  return (
    <div data-settle className="settle relative mx-auto w-full max-w-4xl">
      {/* Lime ambient bloom behind the device, same accent as the stream. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-10 -top-10 bottom-0 -z-10 opacity-60 blur-3xl"
        style={{
          background:
            "radial-gradient(60% 55% at 50% 40%, hsl(83 78% 55% / 0.18), transparent 70%)",
        }}
      />

      {/* Screen: thin graphite bezel around a 16:10 display. */}
      <div className="relative rounded-[1.4rem] border border-white/15 bg-gradient-to-b from-neutral-800 to-neutral-900 p-[0.9%] shadow-[0_40px_90px_-30px_rgba(0,0,0,0.9)]">
        <div className="relative aspect-[16/10] overflow-hidden rounded-[0.85rem] bg-black">
          {/* Camera dot. */}
          <span
            aria-hidden
            className="absolute left-1/2 top-[7px] z-10 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-white/25"
          />
          <video
            className="h-full w-full object-cover"
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          >
            <source src="/laptop-demo.mp4" type="video/mp4" />
            <source src="/laptop-demo.mov" type="video/quicktime" />
          </video>
          {/* Faint screen sheen. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/[0.06] via-transparent to-transparent"
          />
        </div>
      </div>

      {/* Base + hinge: slightly wider than the lid, with a centred notch. */}
      <div className="relative mx-auto h-3.5 w-[106%] -translate-x-[2.83%] rounded-b-2xl bg-gradient-to-b from-neutral-600 to-neutral-800 shadow-[0_18px_30px_-14px_rgba(0,0,0,0.85)]">
        <div className="absolute left-1/2 top-0 h-2 w-28 -translate-x-1/2 rounded-b-xl bg-neutral-900/80" />
      </div>
      <div className="mx-auto h-1 w-[46%] rounded-b-md bg-black/60" />
    </div>
  );
}
