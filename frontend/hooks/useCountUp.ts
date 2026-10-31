"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

export const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Interpolates the displayed number toward `value` with GSAP and writes it
 * straight to the DOM node, so a 100 ms telemetry frame never costs a React
 * re-render per tick.
 *
 * Pass a module-level `format` so the effect's identity stays stable.
 */
export function useCountUp(
  value: number,
  format: (n: number) => string,
  duration = 0.35,
) {
  const ref = useRef<HTMLSpanElement>(null);
  const displayed = useRef(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    if (prefersReducedMotion()) {
      displayed.current = value;
      element.textContent = format(value);
      return;
    }

    const proxy = { n: displayed.current };
    const tween = gsap.to(proxy, {
      n: value,
      duration,
      ease: "power1.out",
      onUpdate: () => {
        element.textContent = format(proxy.n);
      },
    });

    return () => {
      // Keep whatever was on screen so the next tween starts from there.
      displayed.current = proxy.n;
      tween.kill();
    };
  }, [value, format, duration]);

  return ref;
}

export const formatMs = (n: number) => `${Math.round(n).toLocaleString()}`;
export const formatSeconds = (n: number) => `${(n / 1000).toFixed(2)}s`;
export const formatTokens = (n: number) => Math.round(n).toLocaleString();
export const formatUsd = (n: number) => `$${n.toFixed(5)}`;
export const formatPct = (n: number) => `${(n * 100).toFixed(1)}%`;
