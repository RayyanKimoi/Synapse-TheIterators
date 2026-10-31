// Builds the isometric "agent rack" figure for the landing page right rail.
//
// Object: one workstation chassis with its cover off, six agent cards in a cage,
// a mode lever on the bench and a dial gauge reading the critical path. Pull the
// lever and more cards go in flight at once — the machine IS the concurrency.
//
// Run: node scripts/anatomy/build-rack.mjs         (writes the React asset)
//      node scripts/anatomy/build-rack.mjs --page  (also writes a verify page)
//
// Numbers come from the two measured runs in CLAUDE_UPDATE.md: 35 000 ms
// sequential, 14 730 ms compiled warm with six nodes.

import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as k from "./iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, "..", "..");

const WIDTH = 620;
const HEIGHT = 440;

/* ---------------------------------------------------------------- world ---- */

const PAD = { x: -148, y: -82, w: 296, d: 172, r: 5 };
const PAD_H = 0.8;

const FOOT_H = 6;
const FLOOR = { x: -126, y: -64, w: 252, d: 134, r: 6 };
const FLOOR_H = 5;
const DECK = PAD_H + FOOT_H + FLOOR_H; // top face of the chassis floor

const PSU = { x: -118, y: -34, w: 48, d: 54, r: 3 };
const PSU_TOP = DECK + 32;
const FAN = [-94, -7];

const BACKPLANE = { x: -62, y: -58, w: 154, d: 6, r: 1 };
const BACKPLANE_TOP = DECK + 20;
const REAR_RAIL = { x: -62, y: -43, w: 154, d: 7, r: 1.5 };
const FRONT_RAIL = { x: -62, y: 18, w: 154, d: 7, r: 1.5 };
const RAIL_TOP = DECK + 5;

const CARDS = 6;
const CARD_PITCH = 18;
const CARD_X0 = -50;
const CARD_W = 4.6;
const CARD_Y = -36;
const CARD_D = 54;
const CARD_TOP = DECK + 46;
const SINK_TOP = CARD_TOP + 6;
const FLAG_LIFT = 13;
const cardAt = (index) => CARD_X0 + index * CARD_PITCH;

const POST = [106, -44];
const POST_TOP = DECK + 74;
const DIAL = [94, 10];
const DIAL_R = 17;
const DIAL_Z = DECK + 70;
const DIAL_H = 9;
const DIAL_TOP = DIAL_Z + DIAL_H;

const BAY = { x: 54, y: -38, w: 64, d: 32, r: 2.5 };
const BAY_TOP = DECK + 21;

const STRIP = { x: -64, y: 38, w: 158, d: 7, r: 1 };
const LEVER_RAIL_Y = [50, 59];
const LEVER_FROM = -58;
const LEVER_TO = 58;
const CARRIAGE = { x: -13, y: 47, w: 26, d: 17, r: 2.5 };
const CARRIAGE_TOP = DECK + 5.4;
const KNOB_H = 5.6;
const DETENTS = Array.from(
  { length: CARDS },
  (_, index) => LEVER_FROM + (index / (CARDS - 1)) * (LEVER_TO - LEVER_FROM),
);

// Two measured runs, linearly interpolated across the lanes between them.
const PATH_COLD = 35000;
const PATH_WARM = 14730;
const pathFor = (lanes) => PATH_COLD - ((PATH_COLD - PATH_WARM) * (lanes - 1)) / (CARDS - 1);

const P = k.fitProjection(
  [
    ...k.boxCorners(PAD, 0, PAD_H),
    ...k.boxCorners(FLOOR, 0, DECK),
    [POST[0], POST[1], POST_TOP],
    [DIAL[0] - DIAL_R, DIAL[1] - DIAL_R, DIAL_TOP],
    [DIAL[0] + DIAL_R, DIAL[1] + DIAL_R, DIAL_TOP],
    [cardAt(0), CARD_Y, SINK_TOP + FLAG_LIFT + 6],
    [cardAt(CARDS - 1), CARD_Y + CARD_D, SINK_TOP + FLAG_LIFT + 6],
    [BAY.x + BAY.w, BAY.y, BAY_TOP],
  ],
  WIDTH,
  HEIGHT,
  { pad: 26, azimuth: 46 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (points) =>
  [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

/** A closed slot: the only honest way to draw a vent or a card socket. */
const slot = (plan, z) => k.planOutline(plan, z, P, 4);

/** A closed rectangle lying in a card's visible +x face, so chips read as chips. */
const faceRect = (x, y, z, d, h) =>
  k.pathOf([at([x, y, z]), at([x, y + d, z]), at([x, y + d, z + h]), at([x, y, z + h])], true);

/* ----------------------------------------------------------------- bench ---- */

function bench() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PAD, 0, PAD_H, P)}"/>`];
  out.push(S(k.slabOf(PAD, 0, PAD_H, P, 6), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(PAD, 6), PAD_H, P, 6), { tone: "faint" }));

  return out.join("");
}

function chassis() {
  const out = [`<path class="iso-halo" d="${k.haloOf(FLOOR, 0, DECK, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(FLOOR, 15))) {
    out.push(S(k.cylinder(x, y, 7, PAD_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.6, PAD_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(FLOOR, PAD_H + FOOT_H, FLOOR_H, P, 8, 1.4), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(FLOOR, 5), DECK, P), { tone: "lo" }));

  // Corner bolts, each in its own ring.
  const bolts = k.corners(FLOOR, 11);
  out.push(L(bolts.map(([x, y]) => k.ring(x, y, 2.3, DECK, P, 16)).join(""), { tone: "lo" }));
  out.push(D(bolts.map(([x, y]) => at([x, y, DECK])), { size: 0.5 }));

  // Floor grille: eight closed slots, cut where the supply draws its air.
  const vents = [];
  for (let index = 0; index < 8; index++) {
    vents.push(slot({ x: -114 + index * 6.5, y: 34, w: 3.6, d: 24, r: 1.2 }, DECK));
  }
  out.push(L(vents.join(""), { tone: "faint" }));

  // Rear I/O: four connector shells on a bolted strip across the back.
  const io = { x: -52, y: -62, w: 108, d: 11, r: 1.5 };
  out.push(S(k.slabOf(io, DECK, 7, P, 3, 0.4), { tone: "mid" }));
  const shells = [];
  for (let index = 0; index < 4; index++) {
    shells.push(slot({ x: io.x + 8 + index * 24, y: io.y + 2.6, w: 16, d: 5.8, r: 1 }, DECK + 7));
  }
  out.push(L(shells.join(""), { tone: "faint" }));
  out.push(D([at([io.x + 3.5, io.y + io.d / 2, DECK + 7]), at([io.x + io.w - 3.5, io.y + io.d / 2, DECK + 7])], { size: 0.45, tone: "lo" }));

  // Engraved panel label — the figure's only words.
  out.push(k.faceTextSvg(k.topMatrix([DIAL[0] + 6, 4], DECK, P, "x"), "IN FLIGHT", { size: 3.4, tone: "lo", anchor: "middle" }));
  return out.join("");
}

function supply() {
  const out = [];
  out.push(S(k.slabOf(PSU, DECK, PSU_TOP - DECK - 1.4, P, 5, 0.7), { tone: "mid" }));
  out.push(S(k.slabOf(k.insetPlan(PSU, 1.4), PSU_TOP - 1.4, 1.4, P, 5, 0.5), { tone: "mid" }));

  // Fan grille: two rings, nine spokes, a bolted hub.
  out.push(L(k.ring(FAN[0], FAN[1], 17, PSU_TOP, P, 48), { tone: "lo" }));
  out.push(L(k.ring(FAN[0], FAN[1], 14.4, PSU_TOP, P, 48), { tone: "faint" }));
  const spokes = k.radialTicks(FAN[0], FAN[1], 14.4, 9, 1, PSU_TOP, [9.6, 9.6], P);
  out.push(L(spokes.major, { tone: "lo" }));
  out.push(S(k.cylinder(FAN[0], FAN[1], 4.6, PSU_TOP, 1.2, P, 24), { tone: "mid", crease: "lo" }));
  out.push(D([at([FAN[0], FAN[1], PSU_TOP + 1.2])], { size: 0.5 }));
  out.push(
    L(k.corners({ x: FAN[0] - 15, y: FAN[1] - 15, w: 30, d: 30 }, 0).map(([x, y]) => k.ring(x, y, 1.9, PSU_TOP, P, 12)).join(""), {
      tone: "faint",
    }),
  );
  out.push(D(k.corners({ x: FAN[0] - 15, y: FAN[1] - 15, w: 30, d: 30 }, 0).map(([x, y]) => at([x, y, PSU_TOP])), { size: 0.42, tone: "lo" }));

  // Vent band on the face the camera sees.
  const band = [];
  for (let index = 0; index < 6; index++) {
    band.push(faceRect(PSU.x + PSU.w, PSU.y + 6 + index * 5.6, DECK + 6, 3.4, PSU_TOP - DECK - 14));
  }
  out.push(L(band.join(""), { tone: "faint" }));

  // Label plate with three rule lines, screwed down at two corners.
  const plate = { x: PSU.x + 5, y: PSU.y + PSU.d - 17, w: 34, d: 12, r: 1 };
  out.push(S(k.slabOf(plate, PSU_TOP, 0.6, P, 3), { tone: "lo", crease: "none" }));
  out.push(
    L([3.5, 6, 8.5].map((offset) => k.lineOnTop([plate.x + 3, plate.y + offset], [plate.x + plate.w - 5, plate.y + offset], PSU_TOP + 0.6, P)).join(""), {
      tone: "faint",
      free: true,
    }),
  );
  out.push(D([at([plate.x + 1.8, plate.y + 1.8, PSU_TOP + 0.6]), at([plate.x + plate.w - 1.8, plate.y + plate.d - 1.8, PSU_TOP + 0.6])], { size: 0.4, tone: "lo" }));
  return out.join("");
}

function cage() {
  const out = [];
  out.push(S(k.slabOf(BACKPLANE, DECK, BACKPLANE_TOP - DECK, P, 3, 0.5), { tone: "mid" }));
  const sockets = [];
  for (let index = 0; index < CARDS; index++) {
    const x = cardAt(index);
    sockets.push(slot({ x: x - 3.4, y: BACKPLANE.y + 1.2, w: CARD_W + 2.8, d: 3.6, r: 0.8 }, BACKPLANE_TOP));
  }
  out.push(L(sockets.join(""), { tone: "faint" }));
  out.push(
    D([at([BACKPLANE.x + 3, BACKPLANE.y + 3, BACKPLANE_TOP]), at([BACKPLANE.x + BACKPLANE.w - 3, BACKPLANE.y + 3, BACKPLANE_TOP])], { size: 0.45 }),
  );

  for (const rail of [REAR_RAIL, FRONT_RAIL]) {
    out.push(S(k.slabOf(rail, DECK, RAIL_TOP - DECK, P, 3, 0.4), { tone: "mid" }));
    const guides = [];
    for (let index = 0; index < CARDS; index++) {
      guides.push(slot({ x: cardAt(index) - 1.2, y: rail.y + 1.4, w: CARD_W + 2.4, d: rail.d - 2.8, r: 0.7 }, RAIL_TOP));
    }
    out.push(L(guides.join(""), { tone: "faint" }));
    out.push(D([at([rail.x + 4, rail.y + rail.d / 2, RAIL_TOP]), at([rail.x + rail.w - 4, rail.y + rail.d / 2, RAIL_TOP])], { size: 0.42, tone: "lo" }));
  }
  return out.join("");
}

/** One agent card: board, chips on its visible face, heatsink, bracket and LED. */
function card(index) {
  const x = cardAt(index);
  const face = x + CARD_W; // the +x face is the one turned toward the camera
  const out = [];
  const board = { x, y: CARD_Y, w: CARD_W, d: CARD_D, r: 0.8 };
  out.push(S(k.slabOf(board, DECK + 2, CARD_TOP - DECK - 2, P, 3, 0.4), { tone: "mid" }));
  out.push(L(k.lineOnTop([x + CARD_W / 2, CARD_Y], [x + CARD_W / 2, CARD_Y + CARD_D], CARD_TOP, P), { tone: "faint" }));

  // The board is populated: an edge connector, two memory strips and three chips.
  out.push(L(faceRect(face, CARD_Y + 6, DECK + 3.4, 30, 2.6), { tone: "lo" }));
  out.push(L(faceRect(face, CARD_Y + 9, DECK + 9, 34, 2.2) + faceRect(face, CARD_Y + 9, DECK + 13, 34, 2.2), { tone: "faint" }));
  out.push(
    L(
      faceRect(face, CARD_Y + 34, DECK + 8, 12, 9) +
        faceRect(face, CARD_Y + 38, DECK + 20, 8, 6) +
        faceRect(face, CARD_Y + 8, DECK + 30, 9, 7) +
        faceRect(face, CARD_Y + 22, DECK + 34, 14, 8),
      { tone: "faint" },
    ),
  );

  // Heatsink block, finned across its top, with a boss for the flag rod.
  const sink = { x: x - 1.6, y: CARD_Y + 13, w: CARD_W + 3.2, d: 26, r: 1 };
  out.push(S(k.slabOf(sink, CARD_TOP, SINK_TOP - CARD_TOP, P, 3, 0.5), { tone: "hi", crease: "lo" }));
  const fins = k.topTicks(sink.y + 2.4, sink.y + sink.d - 2.4, 2.4, 4, sink.x + 0.4, SINK_TOP, [CARD_W + 2.4, CARD_W + 2.4], P, "y");
  out.push(L(fins.minor, { tone: "lo" }), L(fins.major, { tone: "mid" }));
  out.push(S(k.cylinder(x + CARD_W / 2, CARD_Y + 26, 2.9, SINK_TOP, 1.4, P, 20), { tone: "hi", crease: "lo" }));

  // A thin end flange at the I/O end, bolted down, carrying the status LED.
  const bracket = { x: x - 1.1, y: CARD_Y + CARD_D - 2.6, w: CARD_W + 2.2, d: 2.6, r: 0.6 };
  out.push(S(k.slabOf(bracket, DECK + 2, CARD_TOP + 2.4 - DECK - 2, P, 3, 0.3), { tone: "mid" }));
  out.push(D([at([x + CARD_W / 2, bracket.y + 1.3, DECK + 5])], { size: 0.4, tone: "lo" }));
  const lamp = [x + CARD_W / 2, CARD_Y + CARD_D - 7];
  out.push(L(k.ring(lamp[0], lamp[1], 1.5, CARD_TOP, P, 12), { tone: "lo" }));
  out.push(
    `<g data-part="led" data-lane="${index}" class="rack-led">${D([at([lamp[0], lamp[1], CARD_TOP])], { size: 0.85, tone: "hi" })}</g>`,
  );
  return out.join("");
}

/** The lit part: a flag on a rod, up when that lane is executing. */
function flag(index) {
  const x = cardAt(index) + CARD_W / 2;
  const y = CARD_Y + 26;
  const out = [];
  out.push(S(k.cylinder(x, y, 1.7, SINK_TOP + 1.4, FLAG_LIFT - 4, P, 16), { tone: "hi", crease: "none", lit: true }));
  out.push(S(k.slabOf({ x: x - 2.6, y: y - 5, w: 10, d: 10, r: 0.6 }, SINK_TOP + FLAG_LIFT - 4.4, 1.4, P, 3), { tone: "hi", lit: true }));
  return out.join("");
}

function lanes() {
  const out = [];
  for (let index = 0; index < CARDS; index++) {
    const x = cardAt(index) + CARD_W / 2;
    const d = k.lineOnTop([x, FRONT_RAIL.y + FRONT_RAIL.d], [x, STRIP.y - 1], DECK, P);
    out.push(
      `<g data-part="lane" data-lane="${index}" class="rack-lane">${L(d, { tone: "green", flow: true })}${D([at([x, STRIP.y - 1, DECK])], { size: 0.6, tone: "hi" })}</g>`,
    );
  }
  return out.join("");
}

function instrument() {
  const out = [];
  const base = { x: POST[0] - 9, y: POST[1] - 9, w: 18, d: 18, r: 2.5 };
  out.push(S(k.slabOf(base, DECK, 4, P, 4, 0.5), { tone: "mid" }));
  out.push(D(k.corners(base, 4).map(([x, y]) => at([x, y, DECK + 4])), { size: 0.42, tone: "lo" }));
  out.push(S(k.cylinder(POST[0], POST[1], 4.4, DECK + 4, POST_TOP - DECK - 4, P, 28), { tone: "mid", crease: "none" }));
  out.push(L([DIAL_Z - 16, DIAL_Z - 4].map((z) => k.sideArc(POST[0], POST[1], 4.4, z, P, 16)).join(""), { tone: "faint" }));

  // Collar, then the arm reaching forward to the dial.
  const collar = { x: POST[0] - 7, y: POST[1] - 7, w: 14, d: 14, r: 2.4 };
  out.push(S(k.slabOf(collar, POST_TOP - 12, 9, P, 4, 0.6), { tone: "mid" }));
  const thumb = [collar.x + 7, collar.y + collar.d + 2.6];
  out.push(S(k.slabOf({ x: thumb[0] - 1.4, y: collar.y + collar.d - 0.6, w: 2.8, d: 3, r: 0.8 }, POST_TOP - 10, 4, P, 2), { tone: "mid", crease: "none" }));
  out.push(S(k.cylinder(thumb[0], thumb[1], 2.6, POST_TOP - 12, 6, P, 20), { tone: "mid" }));
  out.push(L(k.knurl(thumb[0], thumb[1], 2.6, POST_TOP - 12, POST_TOP - 6, 18, P), { tone: "lo" }));

  const arm = { x: DIAL[0] + 2, y: POST[1] - 3, w: POST[0] - DIAL[0] - 1, d: 6, r: 2 };
  out.push(S(k.slabOf(arm, POST_TOP - 12, 4, P, 4, 0.5), { tone: "mid" }));
  out.push(D([at([arm.x + 4, POST[1], POST_TOP - 8]), at([arm.x + arm.w - 5, POST[1], POST_TOP - 8])], { size: 0.45 }));
  const stem = { x: DIAL[0] + 1, y: POST[1] - 2.4, w: 5, d: 4.8, r: 1.4 };
  out.push(S(k.slabOf(stem, DIAL_TOP - 4, POST_TOP - 12 - DIAL_TOP + 4, P, 3, 0.4), { tone: "mid" }));
  out.push(S(k.cylinder(DIAL[0] + 3.4, DIAL[1] - DIAL_R - 2, 2.6, DIAL_Z + 2, 5, P, 20), { tone: "mid" }));
  return out.join("");
}

function dial() {
  const [x, y] = DIAL;
  const out = [`<path class="iso-halo" d="${k.haloOf({ x: x - DIAL_R + 3, y: y - DIAL_R + 3, w: DIAL_R * 2 - 6, d: DIAL_R * 2 - 6, r: DIAL_R }, DIAL_Z, 0.1, P)}" style="filter:blur(5px)"/>`];
  out.push(S(k.cylinder(x, y, DIAL_R, DIAL_Z, DIAL_H, P, 64, 0.8), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(x, y, DIAL_R, DIAL_TOP - 3.2, DIAL_TOP, 80, P, 0.3), { tone: "lo" }));
  out.push(L(k.sideArc(x, y, DIAL_R, DIAL_TOP - 3.2, P, 40), { tone: "faint" }));
  out.push(L(k.ring(x, y, DIAL_R - 2.2, DIAL_TOP, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(x, y, DIAL_R - 3, 50, 5, DIAL_TOP, [1.2, 2.7], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  // Lane marks: one major tick per card, so the needle lands on a lane.
  out.push(L(k.ring(x, y, DIAL_R - 7.6, DIAL_TOP, P, 48), { tone: "faint" }));
  const lanes = k.radialTicks(x, y, DIAL_R - 3, CARDS - 1, 1, DIAL_TOP, [4.6, 4.6], P, 0, (Math.PI * 2 * (CARDS - 1)) / CARDS);
  out.push(L(lanes.major, { tone: "hi" }));
  out.push(L(k.ring(x, y, 1.7, DIAL_TOP, P, 16), { tone: "mid" }));
  // Crown and its lug on the bezel.
  out.push(S(k.slabOf({ x: x + DIAL_R - 1, y: y - 2.4, w: 5, d: 4.8, r: 1.2 }, DIAL_Z + 2, 5, P, 3), { tone: "mid" }));
  out.push(S(k.slabOf({ x: x + DIAL_R + 3.6, y: y - 3.2, w: 2.6, d: 6.4, r: 1.2 }, DIAL_Z + 1.2, 6.6, P, 3), { tone: "mid" }));
  return out.join("");
}

const needleAt = (turn) => {
  const angle = turn * Math.PI * 2;
  return k.lineOnTop(
    [DIAL[0] - Math.sin(angle) * 3.2, DIAL[1] + Math.cos(angle) * 3.2],
    [DIAL[0] + Math.sin(angle) * (DIAL_R - 4.4), DIAL[1] - Math.cos(angle) * (DIAL_R - 4.4)],
    DIAL_TOP + 0.2,
    P,
  );
};

function bay() {
  const out = [];
  out.push(S(k.slabOf(BAY, DECK, BAY_TOP - DECK, P, 3, 0.6), { tone: "mid" }));
  // Two sleds under a divider, each with a pull tab and a bolt.
  for (let index = 0; index < 2; index++) {
    const sled = { x: BAY.x + 4, y: BAY.y + 4 + index * 13, w: BAY.w - 8, d: 11, r: 1.2 };
    out.push(S(k.slabOf(sled, BAY_TOP, 1.6, P, 3, 0.4), { tone: "hi", crease: "lo" }));
    out.push(L(k.lineOnTop([sled.x + 5, sled.y + 2.4], [sled.x + sled.w - 14, sled.y + 2.4], BAY_TOP + 1.6, P), { tone: "faint", free: true }));
    out.push(S(k.slabOf({ x: sled.x + sled.w - 11, y: sled.y + 2.6, w: 8, d: 5.8, r: 1 }, BAY_TOP + 1.6, 1.2, P, 3), { tone: "mid", crease: "none" }));
    out.push(D([at([sled.x + 2.6, sled.y + sled.d / 2, BAY_TOP + 1.6])], { size: 0.45, tone: "lo" }));
  }
  out.push(L(k.planOutline(k.insetPlan(BAY, 2), BAY_TOP, P, 3), { tone: "faint" }));
  out.push(D(k.corners(BAY, 3).map(([x, y]) => at([x, y, BAY_TOP])), { size: 0.42, tone: "lo" }));
  return out.join("");
}

function lever() {
  const out = [];
  // Ruler strip behind the travel, ticked every 4 with a major every fifth.
  out.push(S(k.slabOf(STRIP, DECK, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(STRIP.x + 5, STRIP.x + STRIP.w - 5, 4, 5, STRIP.y + 1, DECK + 0.6, [2, 3.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(D([at([STRIP.x + 2.5, STRIP.y + 3.5, DECK + 0.6]), at([STRIP.x + STRIP.w - 2.5, STRIP.y + 3.5, DECK + 0.6])], { size: 0.45 }));

  for (const y of LEVER_RAIL_Y) {
    out.push(S(k.slabOf({ x: LEVER_FROM - 8, y, w: LEVER_TO - LEVER_FROM + 16, d: 4.4, r: 1 }, DECK, 2.6, P, 3, 0.4), { tone: "mid" }));
    out.push(D([LEVER_FROM - 3, LEVER_TO + 3].map((x) => at([x, y + 2.2, DECK + 2.6])), { size: 0.4 }));
  }
  for (const x of [LEVER_FROM - 13, LEVER_TO + 8]) {
    out.push(S(k.slabOf({ x, y: LEVER_RAIL_Y[0] - 2, w: 5, d: LEVER_RAIL_Y[1] - LEVER_RAIL_Y[0] + 8.4, r: 1.2 }, DECK, 7, P, 3, 0.5), { tone: "mid" }));
    out.push(D([at([x + 2.5, LEVER_RAIL_Y[0] + 0.5, DECK + 7]), at([x + 2.5, LEVER_RAIL_Y[1] + 3, DECK + 7])], { size: 0.45 }));
  }
  // Detent dots: one per lane, on the deck between the rails.
  out.push(D(DETENTS.map((x) => at([x, LEVER_RAIL_Y[0] + 6.5, DECK])), { size: 0.5, tone: "mid" }));
  return out.join("");
}

function carriage() {
  const out = [`<path class="iso-halo" d="${k.haloOf(k.insetPlan(CARRIAGE, 3), DECK + 2.6, 0.1, P)}" style="filter:blur(4px)"/>`];
  out.push(S(k.slabOf(CARRIAGE, DECK + 2.6, CARRIAGE_TOP - DECK - 2.6, P, 4, 0.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(CARRIAGE, 3), CARRIAGE_TOP, P, 4), { tone: "faint" }));
  out.push(D(k.corners(CARRIAGE, 4).map(([x, y]) => at([x, y, CARRIAGE_TOP])), { size: 0.4, tone: "lo" }));
  const knob = [CARRIAGE.x + CARRIAGE.w / 2, CARRIAGE.y + CARRIAGE.d / 2];
  out.push(S(k.cylinder(knob[0], knob[1], 6.2, CARRIAGE_TOP, KNOB_H, P, 32, 0.4), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(knob[0], knob[1], 6.2, CARRIAGE_TOP, CARRIAGE_TOP + KNOB_H, 34, P), { tone: "lo" }));
  out.push(L(k.lineOnTop([knob[0], knob[1]], [knob[0], knob[1] + 6.2], CARRIAGE_TOP + KNOB_H, P), { tone: "hi" }));
  out.push(D([at([knob[0], knob[1], CARRIAGE_TOP + KNOB_H])], { size: 0.5, tone: "hi" }));
  return out.join("");
}

/* ------------------------------------------------------------- assemble ---- */

const cards = Array.from({ length: CARDS }, (_, index) => index).sort(
  (a, b) => k.depthOf([cardAt(a), 0, 0], P) - k.depthOf([cardAt(b), 0, 0], P),
);

const body = [
  bench(),
  chassis(),
  lanes(),
  cage(),
  supply(),
  bay(),
  instrument(),
  ...cards.map(
    (index) =>
      card(index) +
      `<g data-part="flag" data-lane="${index}" class="rack-flag" transform="${k.translateAlong(P, [0, 0, 0])}">${flag(index)}</g>`,
  ),
  dial(),
  `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needleAt(0)}" style="stroke-width:1.1"/>`,
  lever(),
  `<g data-part="carriage" transform="${k.translateAlong(P, [DETENTS[0], 0, 0])}">${carriage()}</g>`,
];

const LABEL =
  "An open workstation chassis on a bench. Six agent cards stand in a cage on one backplane; " +
  "a lever on the bench opens lanes one at a time, each card's flag rises as its lane goes in flight, " +
  "and a dial gauge over the cage reads the critical path that is left.";

const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: LABEL, body });

const MODEL = {
  // The camera, resolved, so the page can move parts without the kit.
  camera: { origin: P.origin, ...k.cameraOf(P) },
  cards: CARDS,
  detents: DETENTS,
  reach: [LEVER_FROM - 4, LEVER_TO + 4],
  flagLift: FLAG_LIFT,
  needle: { dial: DIAL, radius: DIAL_R, top: DIAL_TOP + 0.2, hub: 3.2, tip: DIAL_R - 4.4 },
  path: { cold: PATH_COLD, warm: PATH_WARM },
  order: cards,
};

/* ---------------------------------------------------------------- output ---- */

const asset = `// GENERATED by scripts/anatomy/build-rack.mjs — do not edit by hand.
// Isometric agent-rack figure (anatomy skill). Re-run the script to change it.

export const RACK_MODEL = ${JSON.stringify(MODEL)};

export const RACK_SVG = ${JSON.stringify(svg)};

export const RACK_LABEL = ${JSON.stringify(LABEL)};
`;

writeFileSync(join(FRONTEND, "components", "landing", "rack-figure.ts"), asset);
console.log("wrote components/landing/rack-figure.ts");

if (process.argv.includes("--page")) {
  const theme = process.argv.includes("--light") ? "light" : "dark";
  const lanes = Number(process.argv.find((arg) => arg.startsWith("--lanes="))?.slice(8) ?? CARDS);
  const live = `
const P = ${JSON.stringify(P)};
const M = ${JSON.stringify(MODEL)};
const svg = document.querySelector(".iso-stage svg");
const lanes = ${lanes};
const needleAt = (turn) => {
  const a = turn * Math.PI * 2;
  return lineOnTop([M.needle.dial[0] - Math.sin(a) * M.needle.hub, M.needle.dial[1] + Math.cos(a) * M.needle.hub],
    [M.needle.dial[0] + Math.sin(a) * M.needle.tip, M.needle.dial[1] - Math.cos(a) * M.needle.tip], M.needle.top, P);
};
svg.querySelector('[data-part="carriage"]').setAttribute("transform", translateAlong(P, [M.detents[lanes - 1], 0, 0]));
svg.querySelector('[data-part="needle"]').setAttribute("d", needleAt(((lanes - 1) / (M.cards - 1)) * 0.75));
svg.querySelectorAll('[data-part="flag"]').forEach((node) => {
  const on = Number(node.dataset.lane) < lanes;
  node.setAttribute("transform", translateAlong(P, [0, 0, on ? 0 : -M.flagLift]));
});
svg.querySelectorAll('[data-part="lane"],[data-part="led"]').forEach((node) => {
  node.style.opacity = Number(node.dataset.lane) < lanes ? "1" : "0.12";
});
`;
  const page = k.plateHtml({
    fig: "Fig 1",
    title: "Agent rack",
    hint: "Hover to open lanes",
    readout: `${lanes} in flight · ${Math.round(pathFor(lanes)).toLocaleString("en-US")} ms critical path`,
    keys: [
      { mark: "lit", label: "Flags and needle: what moves when a lane goes in flight" },
      { mark: "green", label: "Dispatch lanes from the backplane to each card" },
    ],
    caption: LABEL,
    body: `<div class="iso-stage" tabindex="0">${svg}</div>`,
  });
  const out = join(HERE, theme === "light" ? "rack-light.html" : "rack.html");
  writeFileSync(out, k.pageHtml({ title: "Agent rack", theme, body: page, script: await kitSource() + live, width: 680 }));
  console.log("wrote", out);
}

async function kitSource() {
  const { kitScript } = await import("file:///C:/Users/rayyy/.claude/skills/anatomy/scripts/inline-kit.mjs");
  return kitScript();
}
