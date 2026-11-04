// <kilowattlas-figure>: a small drawing of the installation that follows what
// is typed on the status page. A house with panels on its roof, or a rack on
// the ground, seen obliquely from above from the south-west, inside a compass
// ring on the ground. The house turns to the facing and the panel leans to the
// tilt, so numbers like "27°" and "225°" can be checked at a glance against
// what the owner sees out of the window. The house is solid: panels that face
// away from the viewer are hidden, as they are from the sun.
//
// With `interactive` it works the other way round as well: the panel's upper
// edge can be dragged to its tilt and the knob on the ring to its facing (or
// moved with the arrow keys), and the element reports the new value as a
// `tilt` or `azimuth` event with the degrees in `detail`.
//
// A plain custom element with Home Assistant's own theme variables, no build
// step. The same drawing is on kilowattlas.com under Edit my plant; the
// geometry below is kept identical to it.

// ---------------------------------------------------------------------------
// The geometry: everything is built in a small world (x east, y north, z up,
// the house's middle on the ground at the origin), turned to the facing and
// projected onto the drawing with a fixed camera. Pure functions, no DOM; the
// same functions turn a pointer position back into a tilt or a facing.
// ---------------------------------------------------------------------------

// ---- The camera ----
/** Where the viewer stands, as degrees west of due south. */
const VIEW_YAW = 20;
/** How far above the horizon the viewer looks down from. A panel that faces
 *  away is hidden once its tilt exceeds this. */
const VIEW_ELEVATION = 30;
/** Where the world's origin lands in the drawing, and how large the world is drawn. */
const CENTRE = { x: 160, y: 88 };
const SCALE = 1.3;
const VIEWBOX = { w: 320, h: 150 };

const rad = (deg) => (deg * Math.PI) / 180;
const SIN_YAW = Math.sin(rad(VIEW_YAW));
const COS_YAW = Math.cos(rad(VIEW_YAW));
const SIN_EL = Math.sin(rad(VIEW_ELEVATION));
const COS_EL = Math.cos(rad(VIEW_ELEVATION));
/** A unit vector from the scene towards the viewer. */
const TOWARD_CAMERA = [-COS_EL * SIN_YAW, -COS_EL * COS_YAW, SIN_EL];

/** World to drawing. Orthographic: no perspective, so sizes stay comparable. */
function project([x, y, z]) {
  const xr = x * COS_YAW - y * SIN_YAW;
  const yr = x * SIN_YAW + y * COS_YAW;
  return { x: CENTRE.x + xr * SCALE, y: CENTRE.y - (yr * SIN_EL + z * COS_EL) * SCALE };
}

/** Drawing back to the ground plane (z = 0): the inverse of `project`. */
function unprojectOnGround(p) {
  const xr = (p.x - CENTRE.x) / SCALE;
  const yr = (CENTRE.y - p.y) / SCALE / SIN_EL;
  return { x: xr * COS_YAW + yr * SIN_YAW, y: -xr * SIN_YAW + yr * COS_YAW };
}

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

/** The normal of a flat polygon (Newell's method), not normalised. */
function normalOf(poly) {
  let nx = 0;
  let ny = 0;
  let nz = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  return [nx, ny, nz];
}

const f1 = (n) => n.toFixed(1);
/** An SVG path through the projected corners. */
function pathOf(poly, close = true) {
  return (
    poly
      .map((v, i) => {
        const p = project(v);
        return `${i === 0 ? "M" : "L"}${f1(p.x)} ${f1(p.y)}`;
      })
      .join("") + (close ? "Z" : "")
  );
}

// ---- The things in the world ----
/** The compass ring on the ground, round the house. */
const RING = 66;
/** The house: half its width (along the ridge), half its depth (eave to
 *  eave), and the height of its walls. */
const HALF_WIDTH = 36;
const HALF_DEPTH = 26;
const WALL = 20;
/** A roof steeper than this is not drawn steeper: the panel then stands on
 *  brackets, at its own angle. */
const MAX_ROOF_PITCH = 50;
/** The rack on the ground: its lower edge's height above the grass. */
const RACK_CLEARANCE = 6;

/** Where on the ring a facing lands. */
function ringAt(azimuth, radius = RING) {
  return [radius * Math.sin(rad(azimuth)), radius * Math.cos(rad(azimuth)), 0];
}

/**
 * The panels laid out as a grid in the panel's own plane: x across, y along
 * the slope with negative towards the lower edge.
 */
const MAX_DRAWN = 30;
function layoutCells(count, area) {
  const n = Math.min(count ?? 3, MAX_DRAWN);
  const rows = n <= 5 ? 1 : n <= 16 ? 2 : 3;
  const cols = Math.ceil(n / rows);
  const h = Math.min(area.h / rows, 12);
  const w = Math.min(area.w / cols, h / 1.3);
  const list = [];
  for (let i = 0; i < n; i++) {
    const row = Math.floor(i / cols);
    const inRow = row === rows - 1 ? n - cols * (rows - 1) : cols;
    list.push({ x: ((i % cols) - inRow / 2) * w, y: (row - rows / 2) * h });
  }
  return { list, w, h };
}

/**
 * The panel's frame: where its middle is, and the directions across it
 * (across) and up its slope (up), given the tilt, the facing and what it
 * stands on. `input` is { ground, tilt, azimuth, panels }.
 */
function panelFrame(input) {
  const a = rad(input.azimuth);
  const facing = [Math.sin(a), Math.cos(a), 0];
  const across = [Math.cos(a), -Math.sin(a), 0];
  const t = rad(input.tilt);
  // Up the slope: away from the facing and upwards.
  const up = [-Math.cos(t) * facing[0], -Math.cos(t) * facing[1], Math.sin(t)];
  const normal = [Math.sin(t) * facing[0], Math.sin(t) * facing[1], Math.cos(t)];

  if (input.ground) {
    const area = { w: 68, h: 36 };
    const length = area.h + 3;
    const centre = [0, 0, RACK_CLEARANCE + (length / 2) * Math.sin(t)];
    return { centre, across, up, normal, facing, area, length, width: area.w + 3, pitch: 0 };
  }
  // On a roof: the slope has the panel's tilt up to the steepest roof drawn;
  // beyond that the panel stands on brackets above the slope.
  const pitch = Math.min(input.tilt, MAX_ROOF_PITCH);
  const p = rad(pitch);
  const slopeLength = HALF_DEPTH / Math.cos(p);
  const area = { w: 2 * HALF_WIDTH - 8, h: slopeLength - 4 };
  const length = area.h + 2;
  const ridgeHeight = WALL + HALF_DEPTH * Math.tan(p);
  const slopeMiddle = [
    (facing[0] * HALF_DEPTH) / 2,
    (facing[1] * HALF_DEPTH) / 2,
    (WALL + ridgeHeight) / 2,
  ];
  const roofNormal = [Math.sin(p) * facing[0], Math.sin(p) * facing[1], Math.cos(p)];
  // Lifted just off the tiles, and further when on brackets so the lower
  // edge still rests on the roof.
  const lift = 1.2 + (length / 2) * Math.sin(t - p);
  const centre = add(slopeMiddle, scale(roofNormal, lift));
  return { centre, across, up, normal, facing, area, length, width: area.w + 2, pitch };
}

/** The corners of a rectangle in the panel's plane. */
function quadIn(frame, x0, y0, x1, y1) {
  const at = (x, y) => add(frame.centre, add(scale(frame.across, x), scale(frame.up, y)));
  return [at(x0, y0), at(x1, y0), at(x1, y1), at(x0, y1)];
}

/** The house's faces, turned to the facing; back faces are dropped here. */
function houseFaces(frame) {
  const f = frame.facing;
  const w = frame.across;
  const p = rad(frame.pitch);
  const ridge = WALL + HALF_DEPTH * Math.tan(p);
  const at = (along, side, z) => [f[0] * along + w[0] * side, f[1] * along + w[1] * side, z];
  const D = HALF_DEPTH;
  const W = HALF_WIDTH;
  const faces = [
    { kind: "wall", poly: [at(D, -W, 0), at(D, W, 0), at(D, W, WALL), at(D, -W, WALL)] },
    { kind: "wall", poly: [at(-D, -W, 0), at(-D, W, 0), at(-D, W, WALL), at(-D, -W, WALL)] },
    { kind: "gable", poly: [at(-D, W, 0), at(D, W, 0), at(D, W, WALL), at(0, W, ridge), at(-D, W, WALL)] },
    { kind: "gable", poly: [at(-D, -W, 0), at(D, -W, 0), at(D, -W, WALL), at(0, -W, ridge), at(-D, -W, WALL)] },
    { kind: "roof", poly: [at(D, -W, WALL), at(D, W, WALL), at(0, W, ridge), at(0, -W, ridge)] },
    { kind: "roof", poly: [at(-D, -W, WALL), at(-D, W, WALL), at(0, W, ridge), at(0, -W, ridge)] },
  ];
  const inside = [0, 0, WALL / 2];
  const out = [];
  for (const face of faces) {
    // The house is convex, so a face is seen exactly when its outward normal
    // has a part towards the viewer. The winding above is not consistent, so
    // the normal is turned outwards first.
    let n = normalOf(face.poly);
    const centroid = scale(face.poly.reduce(add, [0, 0, 0]), 1 / face.poly.length);
    if (dot(n, sub(centroid, inside)) < 0) n = scale(n, -1);
    if (dot(n, TOWARD_CAMERA) > 1e-6) out.push({ d: pathOf(face.poly), kind: face.kind });
  }
  return out;
}

/**
 * Everything to draw for one { ground, tilt (0-90), azimuth (0-360, 0 =
 * north), panels (count or null) }: paths for the ring, the house's visible
 * faces, the rack's posts, the panel and its cells, and where the handles and
 * the compass letters sit.
 */
function buildScene(input) {
  const frame = panelFrame(input);
  const half = { x: frame.width / 2, y: frame.length / 2 };
  const outline = quadIn(frame, -half.x, -half.y, half.x, half.y);
  const front = dot(frame.normal, TOWARD_CAMERA) > 1e-6;

  const cells = [];
  if (front) {
    const grid = layoutCells(input.panels, frame.area);
    for (const c of grid.list) {
      cells.push(pathOf(quadIn(frame, c.x + 0.4, c.y + 0.4, c.x + grid.w - 0.4, c.y + grid.h - 0.4)));
    }
  }

  const posts = [];
  if (input.ground) {
    // Four posts, under the panel's corners.
    for (const corner of outline) {
      posts.push(pathOf([corner, [corner[0], corner[1], 0]], false));
    }
  }

  // The ring, as a polygon dense enough to pass for an ellipse.
  const ringPoints = [];
  for (let a = 0; a < 360; a += 10) ringPoints.push(ringAt(a));

  const highEdge = add(frame.centre, scale(frame.up, half.y));

  return {
    ring: pathOf(ringPoints),
    letters: {
      n: project(ringAt(0, RING + 13)),
      e: project(ringAt(90, RING + 13)),
      s: project(ringAt(180, RING + 13)),
      w: project(ringAt(270, RING + 13)),
    },
    house: input.ground ? [] : houseFaces(frame),
    posts,
    panel: { d: pathOf(outline), front },
    cells,
    tiltKnob: project(highEdge),
    azimuthKnob: project(ringAt(input.azimuth)),
    facingLine: pathOf([ringAt(input.azimuth, 0), ringAt(input.azimuth, RING)], false),
  };
}

// ---- Pointer to value ----
/** A finger is less exact than a keyboard: dragging the facing moves in steps. */
const AZIMUTH_STEP = 5;

/** The facing at which the ring's knob sits under p. */
function azimuthToward(p) {
  const g = unprojectOnGround(p);
  const angle = (Math.atan2(g.x, g.y) * 180) / Math.PI;
  return (Math.round(angle / AZIMUTH_STEP) * AZIMUTH_STEP + 360) % 360;
}

/**
 * The tilt at which the panel's upper edge comes closest to p. The edge does
 * not move on a simple curve (on a roof it climbs with the ridge), so every
 * whole degree is tried.
 */
function tiltToward(p, input) {
  let best = 0;
  let bestMiss = Infinity;
  for (let t = 0; t <= 90; t++) {
    const frame = panelFrame({ ...input, tilt: t });
    const knob = project(add(frame.centre, scale(frame.up, frame.length / 2)));
    const miss = (knob.x - p.x) ** 2 + (knob.y - p.y) ** 2;
    if (miss < bestMiss) {
      best = t;
      bestMiss = miss;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// The element
// ---------------------------------------------------------------------------

// Drawn with a typical roof until a tilt is given, so the figure is never empty.
const DEFAULT_TILT = 30;
const POINTS_SV = ["N", "NÖ", "Ö", "SÖ", "S", "SV", "V", "NV"];
const POINTS_EN = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

const STYLE = `
  :host { display: block; }
  figure {
    margin: 0;
    padding: 4px 8px 0;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 10px;
    background: var(--secondary-background-color, #f5f5f5);
  }
  svg {
    display: block;
    width: 100%;
    max-width: 380px;
    height: auto;
    margin: 0 auto;
    color: var(--secondary-text-color, #727272);
  }
  path, circle { fill: none; stroke-linecap: round; stroke-linejoin: round; }
  .ring, .line { stroke: currentColor; stroke-width: 1.5; }
  .ring { stroke-dasharray: 2 4; }
  .facing { stroke: var(--primary-color, #03a9f4); stroke-width: 1.5; stroke-dasharray: 3 3; }
  /* The house: the walls in the card colour, the roof and the gable end
     shaded a touch so the shape reads as a box. */
  .wall, .gable, .roof { fill: var(--card-background-color, #fff); stroke: currentColor; stroke-width: 1.5; }
  .gable { fill: color-mix(in srgb, currentColor 8%, var(--card-background-color, #fff)); }
  .roof { fill: color-mix(in srgb, currentColor 16%, var(--card-background-color, #fff)); }
  /* The panel is the one thing drawn in colour: it is what the numbers are about. */
  .panel {
    fill: var(--primary-color, #03a9f4);
    stroke: color-mix(in srgb, var(--primary-color, #03a9f4) 70%, #000);
    stroke-width: 1; stroke-linejoin: miter;
  }
  .panel.back { fill: color-mix(in srgb, currentColor 45%, var(--card-background-color, #fff)); stroke: currentColor; }
  .cell {
    fill: var(--primary-color, #03a9f4); stroke: var(--card-background-color, #fff);
    stroke-width: 0.5; stroke-linejoin: miter; opacity: 0.9;
  }
  /* What can be dragged. The grab area is larger than what is drawn, so a
     finger finds it; it is invisible but still catches the pointer. */
  .handle { outline: none; }
  .grab { fill: transparent; stroke: transparent; stroke-width: 18; pointer-events: all; }
  /* The ring's grab is the band only, so the house and the tilt's knob inside
     it stay free. Wide enough that a press a little outside still counts. */
  path.grab { fill: none; pointer-events: stroke; stroke-width: 44; }
  .knob {
    fill: var(--card-background-color, #fff);
    stroke: var(--primary-color, #03a9f4);
    stroke-width: 2;
    pointer-events: none;
  }
  .draggable .handle { cursor: grab; touch-action: none; }
  .dragging .handle { cursor: grabbing; }
  .draggable .handle:hover .knob,
  .handle:focus-visible .knob { stroke-width: 3.5; }
  svg:not(.draggable) .knob { display: none; }
  /* Not stated yet: drawn, but as a suggestion. */
  .guess { opacity: 0.4; }
  text { font-family: inherit; font-size: 10px; fill: currentColor; stroke: none; }
  .points text { font-weight: 600; }
  .value { font-size: 11px; font-weight: 700; fill: var(--primary-text-color, #212121); }
`;

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

class KilowattlasFigure extends HTMLElement {
  constructor() {
    super();
    /** "rooftop", "ground" or null. */
    this._mount = null;
    /** Degrees from horizontal, 0-90, or null when not stated. */
    this._tilt = null;
    /** Which way the panels face, in degrees: 0 = north, 90 = east, or null. */
    this._azimuth = null;
    /** How many panels there are, or null. */
    this._panels = null;
    this._isSv = false;
    /** Whether the panel and the knob can be dragged. */
    this._interactive = false;
    this._disabled = false;
    this._dragging = null;
    this._build();
  }

  // Properties: each one redraws. Setting them from the page is the whole API.
  get mount() { return this._mount; }
  set mount(v) { this._mount = v; this._update(); }
  get tilt() { return this._tilt; }
  set tilt(v) { this._tilt = v; this._update(); }
  get azimuth() { return this._azimuth; }
  set azimuth(v) { this._azimuth = v; this._update(); }
  get panels() { return this._panels; }
  set panels(v) { this._panels = v; this._update(); }
  get isSv() { return this._isSv; }
  set isSv(v) { this._isSv = Boolean(v); this._update(); }
  get interactive() { return this._interactive; }
  set interactive(v) { this._interactive = Boolean(v); this._update(); }
  get disabled() { return this._disabled; }
  set disabled(v) { this._disabled = Boolean(v); this._update(); }

  /** Several at once, with one redraw. */
  setProps(props) {
    for (const [key, value] of Object.entries(props)) this[`_${key}`] = value;
    this._update();
  }

  // The drawing is built once; `_update` moves its parts. The handles must
  // keep their identity across updates, or a drag loses its pointer capture.
  _build() {
    const root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    const figure = document.createElement("figure");
    const svg = svgEl("svg", { viewBox: `0 0 ${VIEWBOX.w} ${VIEWBOX.h}` });

    // The ground: the compass ring and the facing. The facing line is drawn
    // before the house, so it runs out from under it.
    const ring = svgEl("path", { class: "ring" });
    const facing = svgEl("path", { class: "facing" });
    // The house or the rack, then the panel on it.
    const house = svgEl("g");
    const posts = svgEl("g");
    const panelGroup = svgEl("g");
    const panel = svgEl("path", { class: "panel" });
    const cells = svgEl("g");
    panelGroup.append(panel, cells);
    // After the house, so a tall roof does not hide the N.
    const points = svgEl("g", { class: "points" });
    const letters = {};
    for (const key of ["n", "s", "e", "w"]) {
      letters[key] = svgEl("text", { "text-anchor": "middle" });
      points.append(letters[key]);
    }
    // The knob on the ring is the handle for the facing; pressing anywhere
    // on the ring moves it there.
    const azimuthHandle = svgEl("g", { class: "handle", role: "slider", "aria-valuemin": "0", "aria-valuemax": "359" });
    const azimuthGrab = svgEl("path", { class: "grab" });
    const azimuthKnob = svgEl("circle", { class: "knob", r: "4.5" });
    azimuthHandle.append(azimuthGrab, azimuthKnob);
    // The panel's upper edge is the handle for the tilt.
    const tiltHandle = svgEl("g", { class: "handle", role: "slider", "aria-valuemin": "0", "aria-valuemax": "90" });
    const tiltGrab = svgEl("circle", { class: "grab", r: "12" });
    const tiltKnob = svgEl("circle", { class: "knob", r: "4.5" });
    tiltHandle.append(tiltGrab, tiltKnob);
    const value = svgEl("text", { class: "value", x: "10", y: "16" });

    svg.append(ring, facing, house, posts, panelGroup, points, azimuthHandle, tiltHandle, value);
    figure.append(svg);
    root.append(style, figure);

    this._el = {
      svg, ring, facing, house, posts, panelGroup, panel, cells, letters,
      azimuthHandle, azimuthGrab, azimuthKnob, tiltHandle, tiltKnob, value,
    };
    this._wireHandle(azimuthHandle, "azimuth");
    this._wireHandle(tiltHandle, "tilt");
    this._update();
  }

  _wireHandle(handle, what) {
    handle.addEventListener("pointerdown", (e) => this._dragStart(what, e));
    handle.addEventListener("pointermove", (e) => this._dragMove(what, e));
    handle.addEventListener("pointerup", () => this._dragEnd());
    handle.addEventListener("pointercancel", () => this._dragEnd());
    handle.addEventListener("keydown", (e) => this._nudge(what, e));
  }

  /** What the drawing is of, after filling in what is not stated. */
  _state() {
    const ground = this._mount === "ground";
    const tilt = this._tilt;
    const tiltKnown = tilt !== null && Number.isFinite(tilt) && tilt >= 0 && tilt <= 90;
    const deg = tiltKnown ? tilt : DEFAULT_TILT;
    const azimuth = this._azimuth;
    const facingKnown = azimuth !== null && Number.isFinite(azimuth) && azimuth >= 0 && azimuth <= 360;
    // South until a facing is given: where panels in Sweden usually look.
    const turn = facingKnown ? azimuth % 360 : 180;
    const panels = this._panels;
    const count = panels !== null && Number.isInteger(panels) && panels > 0 ? panels : null;
    return { ground, tiltKnown, deg, facingKnown, turn, count };
  }

  _update() {
    if (!this._el) return;
    const el = this._el;
    const sv = this._isSv;
    const { ground, tiltKnown, deg, facingKnown, turn, count } = this._state();
    const draggable = this._interactive && !this._disabled;
    const scene = buildScene({ ground, tilt: deg, azimuth: turn, panels: count });

    el.ring.setAttribute("d", scene.ring);
    el.facing.setAttribute("d", scene.facingLine);
    el.facing.classList.toggle("guess", !facingKnown);

    el.house.replaceChildren(...scene.house.map((face) => svgEl("path", { class: face.kind, d: face.d })));
    el.posts.replaceChildren(...scene.posts.map((d) => svgEl("path", { class: "line", d })));

    el.panelGroup.classList.toggle("guess", !tiltKnown);
    el.panel.setAttribute("d", scene.panel.d);
    el.panel.classList.toggle("back", !scene.panel.front);
    el.cells.classList.toggle("guess", count === null && tiltKnown);
    el.cells.replaceChildren(...scene.cells.map((d) => svgEl("path", { class: "cell", d })));

    const letter = { n: "N", s: "S", e: sv ? "Ö" : "E", w: sv ? "V" : "W" };
    for (const key of ["n", "s", "e", "w"]) {
      const p = scene.letters[key];
      el.letters[key].setAttribute("x", f1(p.x));
      el.letters[key].setAttribute("y", f1(p.y + 3.5));
      el.letters[key].textContent = letter[key];
    }

    // One string, so the space between the number and the word survives.
    const countText =
      count === null
        ? ""
        : `${count.toLocaleString(sv ? "sv-SE" : "en-GB")} ${sv ? (count === 1 ? "panel" : "paneler") : count === 1 ? "panel" : "panels"}`;
    el.value.textContent = countText;
    el.value.style.display = count === null ? "none" : "";

    const point = (sv ? POINTS_SV : POINTS_EN)[Math.round(turn / 45) % 8];
    const tiltText = tiltKnown ? `${sv ? "lutning" : "tilt"} ${deg}°` : sv ? "lutning ej angiven" : "tilt not stated";
    const facingText = facingKnown
      ? `${sv ? "vänd mot" : "facing"} ${turn}° (${point})`
      : sv ? "väderstreck ej angivet" : "facing not stated";
    const label = [
      ground ? (sv ? "Markmontage" : "Ground mount") : sv ? "Takmontage" : "Rooftop",
      count !== null ? countText : sv ? "antal paneler ej angivet" : "panel count not stated",
      tiltText,
      facingText,
    ].join(", ");
    el.svg.setAttribute("role", this._interactive ? "group" : "img");
    el.svg.setAttribute("aria-label", label);
    el.svg.classList.toggle("draggable", draggable);
    el.svg.classList.toggle("dragging", this._dragging !== null);

    el.azimuthHandle.style.display = this._interactive ? "" : "none";
    el.tiltHandle.style.display = this._interactive ? "" : "none";
    el.azimuthGrab.setAttribute("d", scene.ring);
    el.azimuthKnob.setAttribute("cx", f1(scene.azimuthKnob.x));
    el.azimuthKnob.setAttribute("cy", f1(scene.azimuthKnob.y));
    el.azimuthKnob.classList.toggle("guess", !facingKnown);
    for (const node of el.tiltHandle.children) {
      node.setAttribute("cx", f1(scene.tiltKnob.x));
      node.setAttribute("cy", f1(scene.tiltKnob.y));
    }
    const slider = (handle, text, now) => {
      handle.setAttribute("tabindex", draggable ? "0" : "-1");
      handle.setAttribute("aria-label", text);
      handle.setAttribute("aria-valuenow", String(now));
      handle.setAttribute("aria-disabled", String(!draggable));
    };
    slider(el.azimuthHandle, sv ? "Väderstreck, grader" : "Facing, degrees", turn);
    slider(el.tiltHandle, sv ? "Lutning, grader" : "Tilt, degrees", deg);
  }

  // ---- Dragging ----
  /** Where the pointer is, in the drawing's own coordinates. */
  _pointerAt(e) {
    const matrix = this._el.svg.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
  }

  _report(what, e) {
    const p = this._pointerAt(e);
    if (!p) return;
    const { ground, tiltKnown, deg, facingKnown, turn, count } = this._state();
    const value = what === "tilt" ? tiltToward(p, { ground, azimuth: turn, panels: count }) : azimuthToward(p);
    const current = what === "tilt" ? (tiltKnown ? deg : null) : facingKnown ? turn : null;
    if (value !== current) this._emit(what, value);
  }

  _emit(what, value) {
    this.dispatchEvent(new CustomEvent(what, { detail: value }));
  }

  _dragStart(what, e) {
    if (!(this._interactive && !this._disabled)) return;
    e.preventDefault();
    this._dragging = what;
    try {
      // Keeps the drag alive when the pointer leaves the handle.
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch (_err) {
      // No such pointer (it is already gone): the drag still works while the
      // pointer stays over the handle.
    }
    this._el.svg.classList.add("dragging");
    // A press on the ring is a choice in itself; the panel only moves once it
    // is dragged, so a stray touch on it changes nothing.
    if (what === "azimuth") this._report(what, e);
  }

  _dragMove(what, e) {
    if (this._dragging === what) this._report(what, e);
  }

  _dragEnd() {
    this._dragging = null;
    this._el.svg.classList.remove("dragging");
  }

  /** Arrow keys: one degree, ten with Shift. The facing goes round; the tilt stops. */
  _nudge(what, e) {
    if (!(this._interactive && !this._disabled)) return;
    const by = e.shiftKey ? 10 : 1;
    let step = 0;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") step = by;
    else if (e.key === "ArrowDown" || e.key === "ArrowLeft") step = -by;
    else return;
    e.preventDefault();
    const { deg, turn } = this._state();
    if (what === "tilt") this._emit("tilt", Math.max(0, Math.min(90, deg + step)));
    else this._emit("azimuth", (turn + step + 360) % 360);
  }
}

if (!customElements.get("kilowattlas-figure")) {
  customElements.define("kilowattlas-figure", KilowattlasFigure);
}
