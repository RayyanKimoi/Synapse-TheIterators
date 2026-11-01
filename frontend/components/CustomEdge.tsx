"use client";

import { memo, useEffect, useRef } from "react";
import {
  BaseEdge,
  getBezierPath,
  getStraightPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import gsap from "gsap";

import { prefersReducedMotion } from "@/hooks/useCountUp";
import { BLOCKING_EDGE, STATE_STYLE } from "@/lib/node-state";
import type { NodeStatus } from "@/lib/types";

export type SynapseEdgeData = {
  upstream: NodeStatus;
  variant: "baseline" | "compiled";
  /** False until both endpoint nodes have faded in; drives the edge fade. */
  revealed?: boolean;
};

export type SynapseEdge = Edge<SynapseEdgeData, "synapse">;

/** Particle count and speed per upstream state — a cache hit should read as a
 *  burst, a normal generation as a steady trickle, the baseline as a crawl. */
function particleSpec(upstream: NodeStatus, variant: "baseline" | "compiled") {
  if (upstream === "CACHED") return { count: 3, duration: 0.42, radius: 3.4, stagger: 0.08 };
  if (upstream !== "RUNNING") return null;
  if (variant === "baseline") return { count: 1, duration: 2.4, radius: 2.2, stagger: 0 };
  return { count: 2, duration: 0.9, radius: 2.6, stagger: 0.3 };
}

function CustomEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<SynapseEdge>) {
  const upstream: NodeStatus = data?.upstream ?? "IDLE";
  const variant = data?.variant ?? "compiled";
  const revealed = data?.revealed ?? true;

  // The baseline lane draws rigid straight runs; the compiled lane curves,
  // which reads as routed rather than queued.
  const [path] =
    variant === "baseline"
      ? getStraightPath({ sourceX, sourceY, targetX, targetY })
      : getBezierPath({
          sourceX,
          sourceY,
          targetX,
          targetY,
          sourcePosition,
          targetPosition,
          curvature: 0.28,
        });

  const pathRef = useRef<SVGPathElement>(null);
  const groupRef = useRef<SVGGElement>(null);

  const stroke = upstream === "CACHED"
    ? STATE_STYLE.CACHED.edge
    : variant === "baseline" && upstream === "RUNNING"
      ? BLOCKING_EDGE
      : STATE_STYLE[upstream].edge;

  const flowClass =
    upstream === "CACHED"
      ? "edge-flow-fast"
      : upstream === "RUNNING"
        ? variant === "baseline"
          ? "edge-flow-slow"
          : "edge-flow"
        : "";

  // Particles ride the real geometry via getPointAtLength, so they track the
  // curve exactly instead of approximating it with a transform.
  useEffect(() => {
    const spec = particleSpec(upstream, variant);
    const measure = pathRef.current;
    const group = groupRef.current;
    if (!spec || !measure || !group) return;
    if (prefersReducedMotion()) return;

    const length = measure.getTotalLength();
    if (!Number.isFinite(length) || length <= 0) return;

    const dots = Array.from(group.querySelectorAll<SVGCircleElement>("circle"));
    const tweens = dots.map((dot, index) =>
      gsap.to(
        { t: 0 },
        {
          t: 1,
          duration: spec.duration,
          ease: "none",
          repeat: -1,
          delay: index * spec.stagger,
          onUpdate() {
            const point = measure.getPointAtLength(this.targets()[0].t * length);
            dot.setAttribute("cx", String(point.x));
            dot.setAttribute("cy", String(point.y));
          },
        },
      ),
    );

    const onVisibility = () =>
      tweens.forEach((tween) => (document.hidden ? tween.pause() : tween.resume()));
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      tweens.forEach((tween) => tween.kill());
    };
  }, [upstream, variant, path]);

  const spec = particleSpec(upstream, variant);

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        className={flowClass}
        style={{
          stroke,
          strokeWidth: upstream === "IDLE" ? 1.1 : upstream === "CACHED" ? 2.4 : 1.9,
          opacity: revealed ? (upstream === "IDLE" ? 0.5 : 1) : 0,
          transition: "opacity 450ms ease-out",
          filter:
            upstream === "CACHED" || upstream === "RUNNING"
              ? `drop-shadow(0 0 5px ${stroke})`
              : undefined,
        }}
      />

      {/* Invisible twin used purely for getPointAtLength measurements. */}
      <path ref={pathRef} d={path} fill="none" stroke="none" />

      {spec && revealed && (
        <g ref={groupRef} aria-hidden>
          {Array.from({ length: spec.count }).map((_, index) => (
            <circle
              key={index}
              r={spec.radius}
              fill={stroke}
              style={{ filter: `drop-shadow(0 0 6px ${stroke})` }}
            />
          ))}
        </g>
      )}
    </>
  );
}

export const CustomEdge = memo(CustomEdgeComponent);
