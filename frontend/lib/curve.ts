/**
 * Monotone cubic (Fritsch–Carlson) spline, returned as an SVG path through
 * points already in screen coordinates. It smooths a stepped series into a
 * curve without the overshoot a plain Catmull-Rom would add: cumulative spend
 * and token counts only ever rise, so the line must never dip below a value it
 * has already reached or bulge above the next one.
 */
export function smoothLinePath(points: [number, number][]): string {
  // Collapse points sharing an x (a vertical step) down to their latest y, so
  // the slope maths never divides by a zero run.
  const p: [number, number][] = [];
  for (const [x, y] of points) {
    if (p.length && Math.abs(x - p[p.length - 1][0]) < 0.01) p[p.length - 1][1] = y;
    else p.push([x, y]);
  }
  const n = p.length;
  if (n < 2) return "";

  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    slope[i] = (p[i + 1][1] - p[i][1]) / (p[i + 1][0] - p[i][0]);
  }

  const m: number[] = new Array(n);
  m[0] = slope[0];
  m[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    // Flat or a local extremum: tangent 0, which keeps a plateau flat.
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }

  // Fritsch–Carlson limiter: clamp tangents so each segment stays monotone.
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / slope[i];
    const b = m[i + 1] / slope[i];
    const h = Math.hypot(a, b);
    if (h > 3) {
      const t = 3 / h;
      m[i] = t * a * slope[i];
      m[i + 1] = t * b * slope[i];
    }
  }

  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = p[i];
    const [x1, y1] = p[i + 1];
    const h = (x1 - x0) / 3;
    d +=
      ` C${(x0 + h).toFixed(1)},${(y0 + m[i] * h).toFixed(1)}` +
      ` ${(x1 - h).toFixed(1)},${(y1 - m[i + 1] * h).toFixed(1)}` +
      ` ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return d;
}
