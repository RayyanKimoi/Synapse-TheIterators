"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { prefersReducedMotion } from "@/hooks/useCountUp";

/**
 * The page's only scroll loop.
 *
 * - `data-panel`  gets `--p`: how far the next panel has covered it (0..1).
 *                 The panel is pinned by CSS `position: sticky`, so nothing
 *                 here jacks the scroll and Lenis can drive it unchanged.
 * - `data-settle` gets `data-settled` once it arrives, which CSS turns into
 *                 the blur-to-sharp focus pull.
 * - `data-stream` gets `--stream-p`: progress down the whole document.
 */
export function ScrollStage({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;

    const arrivals = Array.from(el.querySelectorAll<HTMLElement>("[data-settle]"));
    const calm = prefersReducedMotion();

    if (calm) {
      for (const node of arrivals) node.setAttribute("data-settled", "");
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.setAttribute("data-settled", "");
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.01, rootMargin: "0px 0px -16% 0px" },
    );
    for (const node of arrivals) observer.observe(node);

    const panels = Array.from(el.querySelectorAll<HTMLElement>("[data-panel]"));
    const stream = el.querySelector<HTMLElement>("[data-stream]");
    let raf = 0;
    let queued = false;

    const frame = () => {
      queued = false;
      const view = window.innerHeight || 1;
      for (let index = 0; index < panels.length; index++) {
        const next = panels[index + 1];
        const covered = next
          ? 1 - Math.min(1, Math.max(0, next.getBoundingClientRect().top / view))
          : 0;
        panels[index].style.setProperty("--p", covered.toFixed(3));
      }
      if (stream) {
        const span = document.documentElement.scrollHeight - view;
        stream.style.setProperty("--stream-p", span > 0 ? (window.scrollY / span).toFixed(4) : "0");
      }
    };

    const onScroll = () => {
      if (queued) return;
      queued = true;
      raf = requestAnimationFrame(frame);
    };

    frame();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return <div ref={root}>{children}</div>;
}
