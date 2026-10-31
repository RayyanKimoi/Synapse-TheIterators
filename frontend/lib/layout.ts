/**
 * Both canvases flow top-to-bottom. The baseline is a single file of nodes; the
 * compiled graph puts each topological tier on one row, so a parallel tier reads
 * as three cards side by side against the baseline's rigid column.
 */

const ROW_GAP = 132;
const COL_GAP = 238;

export type Position = { x: number; y: number };

export function sequentialLayout(sequence: string[]): Record<string, Position> {
  return Object.fromEntries(
    sequence.map((nodeId, index) => [nodeId, { x: 0, y: index * ROW_GAP }]),
  );
}

export function tierLayout(tiers: string[][]): Record<string, Position> {
  const positions: Record<string, Position> = {};
  tiers.forEach((tier, row) => {
    const offset = (tier.length - 1) / 2;
    tier.forEach((nodeId, column) => {
      positions[nodeId] = { x: (column - offset) * COL_GAP, y: row * ROW_GAP };
    });
  });
  return positions;
}
