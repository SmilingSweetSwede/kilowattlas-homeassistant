// Generated: `npm run build:ha-figure` in map_framework_2/frontend, from
// src/components/UI/PlantFigure.svelte. Do not edit. Includes the Svelte runtime,
// (c) Svelte contributors, MIT License, https://github.com/sveltejs/svelte
var nt = Object.defineProperty;
var lt = (e, t, n) => t in e ? nt(e, t, { enumerable: !0, configurable: !0, writable: !0, value: n }) : e[t] = n;
var we = (e, t, n) => lt(e, typeof t != "symbol" ? t + "" : t, n);
function ge() {
}
function Xe(e) {
  return e();
}
function Le() {
  return /* @__PURE__ */ Object.create(null);
}
function pe(e) {
  e.forEach(Xe);
}
function Ye(e) {
  return typeof e == "function";
}
function at(e, t) {
  return e != e ? t == t : e !== t || e && typeof e == "object" || typeof e == "function";
}
function ot(e) {
  return Object.keys(e).length === 0;
}
function Ie(e) {
  return e ?? "";
}
function w(e, t) {
  e.appendChild(t);
}
function st(e, t, n) {
  const a = rt(e);
  if (!a.getElementById(t)) {
    const o = Ze("style");
    o.id = t, o.textContent = n, it(a, o);
  }
}
function rt(e) {
  if (!e) return document;
  const t = e.getRootNode ? e.getRootNode() : e.ownerDocument;
  return t && /** @type {ShadowRoot} */
  t.host ? (
    /** @type {ShadowRoot} */
    t
  ) : e.ownerDocument;
}
function it(e, t) {
  return w(
    /** @type {Document} */
    e.head || e,
    t
  ), t.sheet;
}
function Q(e, t, n) {
  e.insertBefore(t, n || null);
}
function Y(e) {
  e.parentNode && e.parentNode.removeChild(e);
}
function ye(e, t) {
  for (let n = 0; n < e.length; n += 1)
    e[n] && e[n].d(t);
}
function Ze(e) {
  return document.createElement(e);
}
function M(e) {
  return document.createElementNS("http://www.w3.org/2000/svg", e);
}
function ie(e) {
  return document.createTextNode(e);
}
function Ke() {
  return ie("");
}
function R(e, t, n, a) {
  return e.addEventListener(t, n, a), () => e.removeEventListener(t, n, a);
}
function l(e, t, n) {
  n == null ? e.removeAttribute(t) : e.getAttribute(t) !== n && e.setAttribute(t, n);
}
function ct(e) {
  return Array.from(e.childNodes);
}
function Ee(e, t) {
  t = "" + t, e.data !== t && (e.data = /** @type {string} */
  t);
}
function j(e, t, n) {
  e.classList.toggle(t, !!n);
}
function ft(e, t, { bubbles: n = !1, cancelable: a = !1 } = {}) {
  return new CustomEvent(e, { detail: t, bubbles: n, cancelable: a });
}
let be;
function de(e) {
  be = e;
}
function ut() {
  if (!be) throw new Error("Function called outside component initialization");
  return be;
}
function ht() {
  const e = ut();
  return (t, n, { cancelable: a = !1 } = {}) => {
    const o = e.$$.callbacks[t];
    if (o) {
      const s = ft(
        /** @type {string} */
        t,
        n,
        { cancelable: a }
      );
      return o.slice().forEach((f) => {
        f.call(e, s);
      }), !s.defaultPrevented;
    }
    return !0;
  };
}
const oe = [], Se = [];
let fe = [];
const Oe = [], dt = /* @__PURE__ */ Promise.resolve();
let Ae = !1;
function gt() {
  Ae || (Ae = !0, dt.then(qe));
}
function Ne(e) {
  fe.push(e);
}
const Me = /* @__PURE__ */ new Set();
let le = 0;
function qe() {
  if (le !== 0)
    return;
  const e = be;
  do {
    try {
      for (; le < oe.length; ) {
        const t = oe[le];
        le++, de(t), bt(t.$$);
      }
    } catch (t) {
      throw oe.length = 0, le = 0, t;
    }
    for (de(null), oe.length = 0, le = 0; Se.length; ) Se.pop()();
    for (let t = 0; t < fe.length; t += 1) {
      const n = fe[t];
      Me.has(n) || (Me.add(n), n());
    }
    fe.length = 0;
  } while (oe.length);
  for (; Oe.length; )
    Oe.pop()();
  Ae = !1, Me.clear(), de(e);
}
function bt(e) {
  if (e.fragment !== null) {
    e.update(), pe(e.before_update);
    const t = e.dirty;
    e.dirty = [-1], e.fragment && e.fragment.p(e.ctx, t), e.after_update.forEach(Ne);
  }
}
function _t(e) {
  const t = [], n = [];
  fe.forEach((a) => e.indexOf(a) === -1 ? t.push(a) : n.push(a)), n.forEach((a) => a()), fe = t;
}
const vt = /* @__PURE__ */ new Set();
function pt(e, t) {
  e && e.i && (vt.delete(e), e.i(t));
}
function ae(e) {
  return (e == null ? void 0 : e.length) !== void 0 ? e : Array.from(e);
}
function mt(e, t, n) {
  const { fragment: a, after_update: o } = e.$$;
  a && a.m(t, n), Ne(() => {
    const s = e.$$.on_mount.map(Xe).filter(Ye);
    e.$$.on_destroy ? e.$$.on_destroy.push(...s) : pe(s), e.$$.on_mount = [];
  }), o.forEach(Ne);
}
function kt(e, t) {
  const n = e.$$;
  n.fragment !== null && (_t(n.after_update), pe(n.on_destroy), n.fragment && n.fragment.d(t), n.on_destroy = n.fragment = null, n.ctx = []);
}
function wt(e, t) {
  e.$$.dirty[0] === -1 && (oe.push(e), gt(), e.$$.dirty.fill(0)), e.$$.dirty[t / 31 | 0] |= 1 << t % 31;
}
function yt(e, t, n, a, o, s, f = null, h = [-1]) {
  const g = be;
  de(e);
  const u = e.$$ = {
    fragment: null,
    ctx: [],
    // state
    props: s,
    update: ge,
    not_equal: o,
    bound: Le(),
    // lifecycle
    on_mount: [],
    on_destroy: [],
    on_disconnect: [],
    before_update: [],
    after_update: [],
    context: new Map(t.context || (g ? g.$$.context : [])),
    // everything else
    callbacks: Le(),
    dirty: h,
    skip_bound: !1,
    root: t.target || g.$$.root
  };
  f && f(u.root);
  let d = !1;
  if (u.ctx = n ? n(e, t.props || {}, (b, v, ...p) => {
    const E = p.length ? p[0] : v;
    return u.ctx && o(u.ctx[b], u.ctx[b] = E) && (!u.skip_bound && u.bound[b] && u.bound[b](E), d && wt(e, b)), v;
  }) : [], u.update(), d = !0, pe(u.before_update), u.fragment = a ? a(u.ctx) : !1, t.target) {
    if (t.hydrate) {
      const b = ct(t.target);
      u.fragment && u.fragment.l(b), b.forEach(Y);
    } else
      u.fragment && u.fragment.c();
    t.intro && pt(e.$$.fragment), mt(e, t.target, t.anchor), qe();
  }
  de(g);
}
class Mt {
  constructor() {
    /**
     * ### PRIVATE API
     *
     * Do not use, may change at any time
     *
     * @type {any}
     */
    we(this, "$$");
    /**
     * ### PRIVATE API
     *
     * Do not use, may change at any time
     *
     * @type {any}
     */
    we(this, "$$set");
  }
  /** @returns {void} */
  $destroy() {
    kt(this, 1), this.$destroy = ge;
  }
  /**
   * @template {Extract<keyof Events, string>} K
   * @param {K} type
   * @param {((e: Events[K]) => void) | null | undefined} callback
   * @returns {() => void}
   */
  $on(t, n) {
    if (!Ye(n))
      return ge;
    const a = this.$$.callbacks[t] || (this.$$.callbacks[t] = []);
    return a.push(n), () => {
      const o = a.indexOf(n);
      o !== -1 && a.splice(o, 1);
    };
  }
  /**
   * @param {Partial<Props>} props
   * @returns {void}
   */
  $set(t) {
    this.$$set && !ot(t) && (this.$$.skip_bound = !0, this.$$set(t), this.$$.skip_bound = !1);
  }
}
const Et = "4";
typeof window < "u" && (window.__svelte || (window.__svelte = { v: /* @__PURE__ */ new Set() })).v.add(Et);
const Je = 20, Qe = 30, me = { x: 160, y: 88 }, ke = 1.3, De = { w: 320, h: 150 }, V = (e) => e * Math.PI / 180, _e = Math.sin(V(Je)), ve = Math.cos(V(Je)), ze = Math.sin(V(Qe)), Ce = Math.cos(V(Qe)), $e = [-Ce * _e, -Ce * ve, ze];
function X([e, t, n]) {
  const a = e * ve - t * _e, o = e * _e + t * ve;
  return { x: me.x + a * ke, y: me.y - (o * ze + n * Ce) * ke };
}
function St(e) {
  const t = (e.x - me.x) / ke, n = (me.y - e.y) / ke / ze;
  return { x: t * ve + n * _e, y: -t * _e + n * ve };
}
const ue = (e, t) => [e[0] + t[0], e[1] + t[1], e[2] + t[2]], $ = (e, t) => [e[0] * t, e[1] * t, e[2] * t], Te = (e, t) => e[0] * t[0] + e[1] * t[1] + e[2] * t[2], At = (e, t) => [e[0] - t[0], e[1] - t[1], e[2] - t[2]];
function Nt(e) {
  let t = 0, n = 0, a = 0;
  for (let o = 0; o < e.length; o++) {
    const s = e[o], f = e[(o + 1) % e.length];
    t += (s[1] - f[1]) * (s[2] + f[2]), n += (s[2] - f[2]) * (s[0] + f[0]), a += (s[0] - f[0]) * (s[1] + f[1]);
  }
  return [t, n, a];
}
const We = (e) => e.toFixed(1);
function se(e, t = !0) {
  return e.map((n, a) => {
    const o = X(n);
    return `${a === 0 ? "M" : "L"}${We(o.x)} ${We(o.y)}`;
  }).join("") + (t ? "Z" : "");
}
const re = 66, et = 36, ce = 26, O = 20, Ct = 50, Tt = 6;
function U(e, t = re) {
  return [t * Math.sin(V(e)), t * Math.cos(V(e)), 0];
}
const zt = 30;
function Lt(e, t) {
  const n = Math.min(e ?? 3, zt), a = n <= 5 ? 1 : n <= 16 ? 2 : 3, o = Math.ceil(n / a), s = Math.min(t.h / a, 12), f = Math.min(t.w / o, s / 1.3), h = [];
  for (let g = 0; g < n; g++) {
    const u = Math.floor(g / o), d = u === a - 1 ? n - o * (a - 1) : o;
    h.push({ x: (g % o - d / 2) * f, y: (u - a / 2) * s });
  }
  return { list: h, w: f, h: s };
}
function tt(e) {
  const t = V(e.azimuth), n = [Math.sin(t), Math.cos(t), 0], a = [Math.cos(t), -Math.sin(t), 0], o = V(e.tilt), s = [-Math.cos(o) * n[0], -Math.cos(o) * n[1], Math.sin(o)], f = [Math.sin(o) * n[0], Math.sin(o) * n[1], Math.cos(o)];
  if (e.ground) {
    const k = { w: 68, h: 36 }, S = k.h + 3;
    return { centre: [0, 0, Tt + S / 2 * Math.sin(o)], across: a, up: s, normal: f, facing: n, area: k, length: S, width: k.w + 3, pitch: 0 };
  }
  const h = Math.min(e.tilt, Ct), g = V(h), u = ce / Math.cos(g), d = { w: 2 * et - 8, h: u - 4 }, b = d.h + 2, v = O + ce * Math.tan(g), p = [n[0] * ce / 2, n[1] * ce / 2, (O + v) / 2], E = [Math.sin(g) * n[0], Math.sin(g) * n[1], Math.cos(g)], W = 1.2 + b / 2 * Math.sin(o - g);
  return { centre: ue(p, $(E, W)), across: a, up: s, normal: f, facing: n, area: d, length: b, width: d.w + 2, pitch: h };
}
function Fe(e, t, n, a, o) {
  const s = (f, h) => ue(e.centre, ue($(e.across, f), $(e.up, h)));
  return [s(t, n), s(a, n), s(a, o), s(t, o)];
}
function It(e) {
  const { facing: t, across: n } = e, a = V(e.pitch), o = O + ce * Math.tan(a), s = (b, v, p) => [
    t[0] * b + n[0] * v,
    t[1] * b + n[1] * v,
    p
  ], f = ce, h = et, g = [
    { kind: "wall", poly: [s(f, -h, 0), s(f, h, 0), s(f, h, O), s(f, -h, O)] },
    { kind: "wall", poly: [s(-f, -h, 0), s(-f, h, 0), s(-f, h, O), s(-f, -h, O)] },
    { kind: "gable", poly: [s(-f, h, 0), s(f, h, 0), s(f, h, O), s(0, h, o), s(-f, h, O)] },
    { kind: "gable", poly: [s(-f, -h, 0), s(f, -h, 0), s(f, -h, O), s(0, -h, o), s(-f, -h, O)] },
    { kind: "roof", poly: [s(f, -h, O), s(f, h, O), s(0, h, o), s(0, -h, o)] },
    { kind: "roof", poly: [s(-f, -h, O), s(-f, h, O), s(0, h, o), s(0, -h, o)] }
  ], u = [0, 0, O / 2], d = [];
  for (const b of g) {
    let v = Nt(b.poly);
    const p = $(b.poly.reduce(ue, [0, 0, 0]), 1 / b.poly.length);
    Te(v, At(p, u)) < 0 && (v = $(v, -1)), Te(v, $e) > 1e-6 && d.push({ d: se(b.poly), kind: b.kind });
  }
  return d;
}
function Kt(e) {
  const t = tt(e), n = { x: t.width / 2, y: t.length / 2 }, a = Fe(t, -n.x, -n.y, n.x, n.y), o = Te(t.normal, $e) > 1e-6, s = [];
  if (o) {
    const u = Lt(e.panels, t.area);
    for (const d of u.list)
      s.push(se(Fe(t, d.x + 0.4, d.y + 0.4, d.x + u.w - 0.4, d.y + u.h - 0.4)));
  }
  const f = [];
  if (e.ground)
    for (const u of a) {
      const d = [u[0], u[1], 0];
      f.push(se([u, d], !1));
    }
  const h = [];
  for (let u = 0; u < 360; u += 10) h.push(U(u));
  const g = ue(t.centre, $(t.up, n.y));
  return {
    ring: se(h),
    letters: {
      n: X(U(0, re + 13)),
      e: X(U(90, re + 13)),
      s: X(U(180, re + 13)),
      w: X(U(270, re + 13))
    },
    house: e.ground ? [] : It(t),
    posts: f,
    panel: { d: se(a), front: o },
    cells: s,
    tiltKnob: X(g),
    azimuthKnob: X(U(e.azimuth)),
    facingLine: se([U(e.azimuth, 0), U(e.azimuth, re)], !1)
  };
}
const je = 5;
function Ot(e) {
  const t = St(e), n = Math.atan2(t.x, t.y) * 180 / Math.PI;
  return (Math.round(n / je) * je + 360) % 360;
}
function Dt(e, t) {
  let n = 0, a = 1 / 0;
  for (let o = 0; o <= 90; o++) {
    const s = tt({ ...t, tilt: o }), f = X(ue(s.centre, $(s.up, s.length / 2))), h = (f.x - e.x) ** 2 + (f.y - e.y) ** 2;
    h < a && (n = o, a = h);
  }
  return n;
}
function Wt(e) {
  st(e, "svelte-1tabn13", ".pf.svelte-1tabn13.svelte-1tabn13{margin:0;padding:4px 8px 0;border:1px solid var(--clerk-border, rgba(0, 0, 0, 0.08));border-radius:10px;background:var(--clerk-surface-soft, #f9fafb)}svg.svelte-1tabn13.svelte-1tabn13{display:block;width:100%;max-width:380px;height:auto;margin:0 auto;color:var(--clerk-text-muted, #6b7280)}path.svelte-1tabn13.svelte-1tabn13,circle.svelte-1tabn13.svelte-1tabn13{fill:none;stroke-linecap:round;stroke-linejoin:round}.ring.svelte-1tabn13.svelte-1tabn13,.line.svelte-1tabn13.svelte-1tabn13{stroke:currentColor;stroke-width:1.5}.ring.svelte-1tabn13.svelte-1tabn13{stroke-dasharray:2 4}.facing.svelte-1tabn13.svelte-1tabn13{stroke:var(--clerk-accent, #3b82f6);stroke-width:1.5;stroke-dasharray:3 3}.wall.svelte-1tabn13.svelte-1tabn13,.gable.svelte-1tabn13.svelte-1tabn13,.roof.svelte-1tabn13.svelte-1tabn13{fill:var(--clerk-surface, #ffffff);stroke:currentColor;stroke-width:1.5}.gable.svelte-1tabn13.svelte-1tabn13{fill:color-mix(in srgb, currentColor 8%, var(--clerk-surface, #ffffff))}.roof.svelte-1tabn13.svelte-1tabn13{fill:color-mix(in srgb, currentColor 16%, var(--clerk-surface, #ffffff))}.panel.svelte-1tabn13.svelte-1tabn13{fill:var(--clerk-accent, #3b82f6);stroke:color-mix(in srgb, var(--clerk-accent, #3b82f6) 70%, #000);stroke-width:1;stroke-linejoin:miter}.panel.back.svelte-1tabn13.svelte-1tabn13{fill:color-mix(in srgb, currentColor 45%, var(--clerk-surface, #ffffff));stroke:currentColor}.cell.svelte-1tabn13.svelte-1tabn13{fill:var(--clerk-accent, #3b82f6);stroke:var(--clerk-surface, #ffffff);stroke-width:0.5;stroke-linejoin:miter;opacity:0.9}.handle.svelte-1tabn13.svelte-1tabn13{outline:none}.grab.svelte-1tabn13.svelte-1tabn13{fill:transparent;stroke:transparent;stroke-width:18;pointer-events:all}path.grab.svelte-1tabn13.svelte-1tabn13{fill:none;pointer-events:stroke;stroke-width:44}.knob.svelte-1tabn13.svelte-1tabn13{fill:var(--clerk-surface, #ffffff);stroke:var(--clerk-accent, #3b82f6);stroke-width:2;pointer-events:none}.draggable.svelte-1tabn13 .handle.svelte-1tabn13{cursor:grab;touch-action:none}.dragging.svelte-1tabn13 .handle.svelte-1tabn13{cursor:grabbing}.draggable.svelte-1tabn13 .handle:hover .knob.svelte-1tabn13,.handle.svelte-1tabn13:focus-visible .knob.svelte-1tabn13{stroke-width:3.5}svg.svelte-1tabn13:not(.draggable) .knob.svelte-1tabn13{display:none}.guess.svelte-1tabn13.svelte-1tabn13{opacity:0.4}text.svelte-1tabn13.svelte-1tabn13{font-family:inherit;font-size:10px;fill:currentColor;stroke:none}.points.svelte-1tabn13 text.svelte-1tabn13{font-weight:600}.value.svelte-1tabn13.svelte-1tabn13{font-size:11px;font-weight:700;fill:var(--clerk-text, #111827)}");
}
function Pe(e, t, n) {
  const a = e.slice();
  return a[39] = t[n], a;
}
function Re(e, t, n) {
  const a = e.slice();
  return a[39] = t[n], a;
}
function Ve(e, t, n) {
  const a = e.slice();
  return a[44] = t[n], a;
}
function Be(e) {
  let t, n, a;
  return {
    c() {
      t = M("path"), l(t, "class", n = Ie(
        /*face*/
        e[44].kind
      ) + " svelte-1tabn13"), l(t, "d", a = /*face*/
      e[44].d);
    },
    m(o, s) {
      Q(o, t, s);
    },
    p(o, s) {
      s[0] & /*scene*/
      4096 && n !== (n = Ie(
        /*face*/
        o[44].kind
      ) + " svelte-1tabn13") && l(t, "class", n), s[0] & /*scene*/
      4096 && a !== (a = /*face*/
      o[44].d) && l(t, "d", a);
    },
    d(o) {
      o && Y(t);
    }
  };
}
function He(e) {
  let t, n;
  return {
    c() {
      t = M("path"), l(t, "class", "line svelte-1tabn13"), l(t, "d", n = /*d*/
      e[39]);
    },
    m(a, o) {
      Q(a, t, o);
    },
    p(a, o) {
      o[0] & /*scene*/
      4096 && n !== (n = /*d*/
      a[39]) && l(t, "d", n);
    },
    d(a) {
      a && Y(t);
    }
  };
}
function xe(e) {
  let t, n;
  return {
    c() {
      t = M("path"), l(t, "class", "cell svelte-1tabn13"), l(t, "d", n = /*d*/
      e[39]);
    },
    m(a, o) {
      Q(a, t, o);
    },
    p(a, o) {
      o[0] & /*scene*/
      4096 && n !== (n = /*d*/
      a[39]) && l(t, "d", n);
    },
    d(a) {
      a && Y(t);
    }
  };
}
function Ge(e) {
  let t, n, a, o, s, f, h, g, u, d, b, v, p, E, W, F, k, S, A, y, z;
  return {
    c() {
      t = M("g"), n = M("path"), o = M("circle"), d = M("g"), b = M("circle"), E = M("circle"), l(n, "class", "grab svelte-1tabn13"), l(n, "d", a = /*scene*/
      e[12].ring), l(o, "class", "knob svelte-1tabn13"), l(o, "cx", s = /*f*/
      e[17](
        /*scene*/
        e[12].azimuthKnob.x
      )), l(o, "cy", f = /*f*/
      e[17](
        /*scene*/
        e[12].azimuthKnob.y
      )), l(o, "r", "4.5"), j(o, "guess", !/*facingKnown*/
      e[4]), l(t, "class", "handle svelte-1tabn13"), l(t, "role", "slider"), l(t, "tabindex", h = /*draggable*/
      e[10] ? 0 : -1), l(t, "aria-label", g = /*isSv*/
      e[0] ? "Väderstreck, grader" : "Facing, degrees"), l(t, "aria-valuemin", "0"), l(t, "aria-valuemax", "359"), l(
        t,
        "aria-valuenow",
        /*turn*/
        e[2]
      ), l(t, "aria-disabled", u = !/*draggable*/
      e[10]), l(b, "class", "grab svelte-1tabn13"), l(b, "cx", v = /*f*/
      e[17](
        /*scene*/
        e[12].tiltKnob.x
      )), l(b, "cy", p = /*f*/
      e[17](
        /*scene*/
        e[12].tiltKnob.y
      )), l(b, "r", "12"), l(E, "class", "knob svelte-1tabn13"), l(E, "cx", W = /*f*/
      e[17](
        /*scene*/
        e[12].tiltKnob.x
      )), l(E, "cy", F = /*f*/
      e[17](
        /*scene*/
        e[12].tiltKnob.y
      )), l(E, "r", "4.5"), l(d, "class", "handle svelte-1tabn13"), l(d, "role", "slider"), l(d, "tabindex", k = /*draggable*/
      e[10] ? 0 : -1), l(d, "aria-label", S = /*isSv*/
      e[0] ? "Lutning, grader" : "Tilt, degrees"), l(d, "aria-valuemin", "0"), l(d, "aria-valuemax", "90"), l(
        d,
        "aria-valuenow",
        /*deg*/
        e[3]
      ), l(d, "aria-disabled", A = !/*draggable*/
      e[10]);
    },
    m(_, m) {
      Q(_, t, m), w(t, n), w(t, o), Q(_, d, m), w(d, b), w(d, E), y || (z = [
        R(
          t,
          "pointerdown",
          /*pointerdown_handler*/
          e[27]
        ),
        R(
          t,
          "pointermove",
          /*pointermove_handler*/
          e[28]
        ),
        R(
          t,
          "pointerup",
          /*dragEnd*/
          e[15]
        ),
        R(
          t,
          "pointercancel",
          /*dragEnd*/
          e[15]
        ),
        R(
          t,
          "keydown",
          /*keydown_handler*/
          e[29]
        ),
        R(
          d,
          "pointerdown",
          /*pointerdown_handler_1*/
          e[30]
        ),
        R(
          d,
          "pointermove",
          /*pointermove_handler_1*/
          e[31]
        ),
        R(
          d,
          "pointerup",
          /*dragEnd*/
          e[15]
        ),
        R(
          d,
          "pointercancel",
          /*dragEnd*/
          e[15]
        ),
        R(
          d,
          "keydown",
          /*keydown_handler_1*/
          e[32]
        )
      ], y = !0);
    },
    p(_, m) {
      m[0] & /*scene*/
      4096 && a !== (a = /*scene*/
      _[12].ring) && l(n, "d", a), m[0] & /*scene*/
      4096 && s !== (s = /*f*/
      _[17](
        /*scene*/
        _[12].azimuthKnob.x
      )) && l(o, "cx", s), m[0] & /*scene*/
      4096 && f !== (f = /*f*/
      _[17](
        /*scene*/
        _[12].azimuthKnob.y
      )) && l(o, "cy", f), m[0] & /*facingKnown*/
      16 && j(o, "guess", !/*facingKnown*/
      _[4]), m[0] & /*draggable*/
      1024 && h !== (h = /*draggable*/
      _[10] ? 0 : -1) && l(t, "tabindex", h), m[0] & /*isSv*/
      1 && g !== (g = /*isSv*/
      _[0] ? "Väderstreck, grader" : "Facing, degrees") && l(t, "aria-label", g), m[0] & /*turn*/
      4 && l(
        t,
        "aria-valuenow",
        /*turn*/
        _[2]
      ), m[0] & /*draggable*/
      1024 && u !== (u = !/*draggable*/
      _[10]) && l(t, "aria-disabled", u), m[0] & /*scene*/
      4096 && v !== (v = /*f*/
      _[17](
        /*scene*/
        _[12].tiltKnob.x
      )) && l(b, "cx", v), m[0] & /*scene*/
      4096 && p !== (p = /*f*/
      _[17](
        /*scene*/
        _[12].tiltKnob.y
      )) && l(b, "cy", p), m[0] & /*scene*/
      4096 && W !== (W = /*f*/
      _[17](
        /*scene*/
        _[12].tiltKnob.x
      )) && l(E, "cx", W), m[0] & /*scene*/
      4096 && F !== (F = /*f*/
      _[17](
        /*scene*/
        _[12].tiltKnob.y
      )) && l(E, "cy", F), m[0] & /*draggable*/
      1024 && k !== (k = /*draggable*/
      _[10] ? 0 : -1) && l(d, "tabindex", k), m[0] & /*isSv*/
      1 && S !== (S = /*isSv*/
      _[0] ? "Lutning, grader" : "Tilt, degrees") && l(d, "aria-label", S), m[0] & /*deg*/
      8 && l(
        d,
        "aria-valuenow",
        /*deg*/
        _[3]
      ), m[0] & /*draggable*/
      1024 && A !== (A = !/*draggable*/
      _[10]) && l(d, "aria-disabled", A);
    },
    d(_) {
      _ && (Y(t), Y(d)), y = !1, pe(z);
    }
  };
}
function Ue(e) {
  let t, n;
  return {
    c() {
      t = M("text"), n = ie(
        /*countText*/
        e[7]
      ), l(t, "class", "value svelte-1tabn13"), l(t, "x", "10"), l(t, "y", "16");
    },
    m(a, o) {
      Q(a, t, o), w(t, n);
    },
    p(a, o) {
      o[0] & /*countText*/
      128 && Ee(
        n,
        /*countText*/
        a[7]
      );
    },
    d(a) {
      a && Y(t);
    }
  };
}
function Ft(e) {
  let t, n, a, o, s, f, h, g, u, d, b, v, p, E, W, F, k, S, A, y, z, _ = (
    /*isSv*/
    e[0] ? "Ö" : "E"
  ), m, ee, te, L, B = (
    /*isSv*/
    e[0] ? "V" : "W"
  ), he, Z, H, q, ne, P = ae(
    /*scene*/
    e[12].house
  ), N = [];
  for (let i = 0; i < P.length; i += 1)
    N[i] = Be(Ve(e, P, i));
  let x = ae(
    /*scene*/
    e[12].posts
  ), C = [];
  for (let i = 0; i < x.length; i += 1)
    C[i] = He(Re(e, x, i));
  let G = ae(
    /*scene*/
    e[12].cells
  ), T = [];
  for (let i = 0; i < G.length; i += 1)
    T[i] = xe(Pe(e, G, i));
  let I = (
    /*interactive*/
    e[1] && Ge(e)
  ), K = (
    /*count*/
    e[6] !== null && Ue(e)
  );
  return {
    c() {
      t = Ze("figure"), n = M("svg"), a = M("path"), s = M("path");
      for (let i = 0; i < N.length; i += 1)
        N[i].c();
      h = Ke();
      for (let i = 0; i < C.length; i += 1)
        C[i].c();
      g = M("g"), u = M("path"), b = M("g");
      for (let i = 0; i < T.length; i += 1)
        T[i].c();
      v = M("g"), p = M("text"), E = ie("N"), k = M("text"), S = ie("S"), z = M("text"), m = ie(_), L = M("text"), he = ie(B), I && I.c(), q = Ke(), K && K.c(), l(a, "class", "ring svelte-1tabn13"), l(a, "d", o = /*scene*/
      e[12].ring), l(s, "class", "facing svelte-1tabn13"), l(s, "d", f = /*scene*/
      e[12].facingLine), j(s, "guess", !/*facingKnown*/
      e[4]), l(u, "class", "panel svelte-1tabn13"), l(u, "d", d = /*scene*/
      e[12].panel.d), j(u, "back", !/*scene*/
      e[12].panel.front), l(b, "class", "svelte-1tabn13"), j(
        b,
        "guess",
        /*count*/
        e[6] === null && /*tiltKnown*/
        e[5]
      ), l(g, "class", "svelte-1tabn13"), j(g, "guess", !/*tiltKnown*/
      e[5]), l(p, "x", W = /*f*/
      e[17](
        /*scene*/
        e[12].letters.n.x
      )), l(p, "y", F = /*f*/
      e[17](
        /*scene*/
        e[12].letters.n.y + 3.5
      )), l(p, "text-anchor", "middle"), l(p, "class", "svelte-1tabn13"), l(k, "x", A = /*f*/
      e[17](
        /*scene*/
        e[12].letters.s.x
      )), l(k, "y", y = /*f*/
      e[17](
        /*scene*/
        e[12].letters.s.y + 3.5
      )), l(k, "text-anchor", "middle"), l(k, "class", "svelte-1tabn13"), l(z, "x", ee = /*f*/
      e[17](
        /*scene*/
        e[12].letters.e.x
      )), l(z, "y", te = /*f*/
      e[17](
        /*scene*/
        e[12].letters.e.y + 3.5
      )), l(z, "text-anchor", "middle"), l(z, "class", "svelte-1tabn13"), l(L, "x", Z = /*f*/
      e[17](
        /*scene*/
        e[12].letters.w.x
      )), l(L, "y", H = /*f*/
      e[17](
        /*scene*/
        e[12].letters.w.y + 3.5
      )), l(L, "text-anchor", "middle"), l(L, "class", "svelte-1tabn13"), l(v, "class", "points svelte-1tabn13"), l(n, "viewBox", "0 0 " + De.w + " " + De.h), l(n, "role", ne = /*interactive*/
      e[1] ? "group" : "img"), l(
        n,
        "aria-label",
        /*label*/
        e[11]
      ), l(n, "class", "svelte-1tabn13"), j(
        n,
        "draggable",
        /*draggable*/
        e[10]
      ), j(
        n,
        "dragging",
        /*dragging*/
        e[9] !== null
      ), l(t, "class", "pf svelte-1tabn13");
    },
    m(i, r) {
      Q(i, t, r), w(t, n), w(n, a), w(n, s);
      for (let c = 0; c < N.length; c += 1)
        N[c] && N[c].m(n, null);
      w(n, h);
      for (let c = 0; c < C.length; c += 1)
        C[c] && C[c].m(n, null);
      w(n, g), w(g, u), w(g, b);
      for (let c = 0; c < T.length; c += 1)
        T[c] && T[c].m(b, null);
      w(n, v), w(v, p), w(p, E), w(v, k), w(k, S), w(v, z), w(z, m), w(v, L), w(L, he), I && I.m(n, null), w(n, q), K && K.m(n, null), e[33](n);
    },
    p(i, r) {
      if (r[0] & /*scene*/
      4096 && o !== (o = /*scene*/
      i[12].ring) && l(a, "d", o), r[0] & /*scene*/
      4096 && f !== (f = /*scene*/
      i[12].facingLine) && l(s, "d", f), r[0] & /*facingKnown*/
      16 && j(s, "guess", !/*facingKnown*/
      i[4]), r[0] & /*scene*/
      4096) {
        P = ae(
          /*scene*/
          i[12].house
        );
        let c;
        for (c = 0; c < P.length; c += 1) {
          const D = Ve(i, P, c);
          N[c] ? N[c].p(D, r) : (N[c] = Be(D), N[c].c(), N[c].m(n, h));
        }
        for (; c < N.length; c += 1)
          N[c].d(1);
        N.length = P.length;
      }
      if (r[0] & /*scene*/
      4096) {
        x = ae(
          /*scene*/
          i[12].posts
        );
        let c;
        for (c = 0; c < x.length; c += 1) {
          const D = Re(i, x, c);
          C[c] ? C[c].p(D, r) : (C[c] = He(D), C[c].c(), C[c].m(n, g));
        }
        for (; c < C.length; c += 1)
          C[c].d(1);
        C.length = x.length;
      }
      if (r[0] & /*scene*/
      4096 && d !== (d = /*scene*/
      i[12].panel.d) && l(u, "d", d), r[0] & /*scene*/
      4096 && j(u, "back", !/*scene*/
      i[12].panel.front), r[0] & /*scene*/
      4096) {
        G = ae(
          /*scene*/
          i[12].cells
        );
        let c;
        for (c = 0; c < G.length; c += 1) {
          const D = Pe(i, G, c);
          T[c] ? T[c].p(D, r) : (T[c] = xe(D), T[c].c(), T[c].m(b, null));
        }
        for (; c < T.length; c += 1)
          T[c].d(1);
        T.length = G.length;
      }
      r[0] & /*count, tiltKnown*/
      96 && j(
        b,
        "guess",
        /*count*/
        i[6] === null && /*tiltKnown*/
        i[5]
      ), r[0] & /*tiltKnown*/
      32 && j(g, "guess", !/*tiltKnown*/
      i[5]), r[0] & /*scene*/
      4096 && W !== (W = /*f*/
      i[17](
        /*scene*/
        i[12].letters.n.x
      )) && l(p, "x", W), r[0] & /*scene*/
      4096 && F !== (F = /*f*/
      i[17](
        /*scene*/
        i[12].letters.n.y + 3.5
      )) && l(p, "y", F), r[0] & /*scene*/
      4096 && A !== (A = /*f*/
      i[17](
        /*scene*/
        i[12].letters.s.x
      )) && l(k, "x", A), r[0] & /*scene*/
      4096 && y !== (y = /*f*/
      i[17](
        /*scene*/
        i[12].letters.s.y + 3.5
      )) && l(k, "y", y), r[0] & /*isSv*/
      1 && _ !== (_ = /*isSv*/
      i[0] ? "Ö" : "E") && Ee(m, _), r[0] & /*scene*/
      4096 && ee !== (ee = /*f*/
      i[17](
        /*scene*/
        i[12].letters.e.x
      )) && l(z, "x", ee), r[0] & /*scene*/
      4096 && te !== (te = /*f*/
      i[17](
        /*scene*/
        i[12].letters.e.y + 3.5
      )) && l(z, "y", te), r[0] & /*isSv*/
      1 && B !== (B = /*isSv*/
      i[0] ? "V" : "W") && Ee(he, B), r[0] & /*scene*/
      4096 && Z !== (Z = /*f*/
      i[17](
        /*scene*/
        i[12].letters.w.x
      )) && l(L, "x", Z), r[0] & /*scene*/
      4096 && H !== (H = /*f*/
      i[17](
        /*scene*/
        i[12].letters.w.y + 3.5
      )) && l(L, "y", H), /*interactive*/
      i[1] ? I ? I.p(i, r) : (I = Ge(i), I.c(), I.m(n, q)) : I && (I.d(1), I = null), /*count*/
      i[6] !== null ? K ? K.p(i, r) : (K = Ue(i), K.c(), K.m(n, null)) : K && (K.d(1), K = null), r[0] & /*interactive*/
      2 && ne !== (ne = /*interactive*/
      i[1] ? "group" : "img") && l(n, "role", ne), r[0] & /*label*/
      2048 && l(
        n,
        "aria-label",
        /*label*/
        i[11]
      ), r[0] & /*draggable*/
      1024 && j(
        n,
        "draggable",
        /*draggable*/
        i[10]
      ), r[0] & /*dragging*/
      512 && j(
        n,
        "dragging",
        /*dragging*/
        i[9] !== null
      );
    },
    i: ge,
    o: ge,
    d(i) {
      i && Y(t), ye(N, i), ye(C, i), ye(T, i), I && I.d(), K && K.d(), e[33](null);
    }
  };
}
const jt = 30;
function Pt(e, t, n) {
  let a, o, s, f, h, g, u, d, b, v, p, E, W, { mount: F = null } = t, { tilt: k = null } = t, { azimuth: S = null } = t, { panels: A = null } = t, { isSv: y = !1 } = t, { interactive: z = !1 } = t, { disabled: _ = !1 } = t;
  const m = ht(), ee = ["N", "NÖ", "Ö", "SÖ", "S", "SV", "V", "NV"], te = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  let L, B = null;
  function he(r) {
    const c = L == null ? void 0 : L.getScreenCTM();
    return c ? new DOMPoint(r.clientX, r.clientY).matrixTransform(c.inverse()) : null;
  }
  function Z(r, c) {
    const D = he(c);
    if (!D) return;
    const J = r === "tilt" ? Dt(D, { ground: o, azimuth: g, panels: u }) : Ot(D);
    J !== (r === "tilt" ? s ? f : null : h ? g : null) && m(r, J);
  }
  function H(r, c) {
    if (a) {
      c.preventDefault(), n(9, B = r);
      try {
        c.currentTarget.setPointerCapture(c.pointerId);
      } catch {
      }
      r === "azimuth" && Z(r, c);
    }
  }
  function q(r, c) {
    B === r && Z(r, c);
  }
  function ne() {
    n(9, B = null);
  }
  function P(r, c) {
    if (!a) return;
    const D = c.shiftKey ? 10 : 1;
    let J = 0;
    if (c.key === "ArrowUp" || c.key === "ArrowRight") J = D;
    else if (c.key === "ArrowDown" || c.key === "ArrowLeft") J = -D;
    else return;
    c.preventDefault(), r === "tilt" ? m("tilt", Math.max(0, Math.min(90, f + J))) : m("azimuth", (g + J + 360) % 360);
  }
  const N = (r) => r.toFixed(1), x = (r) => H("azimuth", r), C = (r) => q("azimuth", r), G = (r) => P("azimuth", r), T = (r) => H("tilt", r), I = (r) => q("tilt", r), K = (r) => P("tilt", r);
  function i(r) {
    Se[r ? "unshift" : "push"](() => {
      L = r, n(8, L);
    });
  }
  return e.$$set = (r) => {
    "mount" in r && n(18, F = r.mount), "tilt" in r && n(19, k = r.tilt), "azimuth" in r && n(20, S = r.azimuth), "panels" in r && n(21, A = r.panels), "isSv" in r && n(0, y = r.isSv), "interactive" in r && n(1, z = r.interactive), "disabled" in r && n(22, _ = r.disabled);
  }, e.$$.update = () => {
    e.$$.dirty[0] & /*interactive, disabled*/
    4194306 && n(10, a = z && !_), e.$$.dirty[0] & /*mount*/
    262144 && n(23, o = F === "ground"), e.$$.dirty[0] & /*tilt*/
    524288 && n(5, s = k !== null && Number.isFinite(k) && k >= 0 && k <= 90), e.$$.dirty[0] & /*tiltKnown, tilt*/
    524320 && n(3, f = s ? k : jt), e.$$.dirty[0] & /*azimuth*/
    1048576 && n(4, h = S !== null && Number.isFinite(S) && S >= 0 && S <= 360), e.$$.dirty[0] & /*facingKnown, azimuth*/
    1048592 && n(2, g = h ? S % 360 : 180), e.$$.dirty[0] & /*panels*/
    2097152 && n(6, u = A !== null && Number.isInteger(A) && A > 0 ? A : null), e.$$.dirty[0] & /*ground, deg, turn, count*/
    8388684 && n(12, d = Kt({
      ground: o,
      tilt: f,
      azimuth: g,
      panels: u
    })), e.$$.dirty[0] & /*count, isSv*/
    65 && n(7, b = u === null ? "" : `${u.toLocaleString(y ? "sv-SE" : "en-GB")} ${y ? u === 1 ? "panel" : "paneler" : u === 1 ? "panel" : "panels"}`), e.$$.dirty[0] & /*isSv, turn*/
    5 && n(26, v = (y ? ee : te)[Math.round(g / 45) % 8]), e.$$.dirty[0] & /*tiltKnown, isSv, deg*/
    41 && n(25, p = s ? `${y ? "lutning" : "tilt"} ${f}°` : y ? "lutning ej angiven" : "tilt not stated"), e.$$.dirty[0] & /*facingKnown, isSv, turn, point*/
    67108885 && n(24, E = h ? `${y ? "vänd mot" : "facing"} ${g}° (${v})` : y ? "väderstreck ej angivet" : "facing not stated"), e.$$.dirty[0] & /*ground, isSv, count, countText, tiltText, facingText*/
    58720449 && n(11, W = [
      o ? y ? "Markmontage" : "Ground mount" : y ? "Takmontage" : "Rooftop",
      u !== null ? b : y ? "antal paneler ej angivet" : "panel count not stated",
      p,
      E
    ].join(", "));
  }, [
    y,
    z,
    g,
    f,
    h,
    s,
    u,
    b,
    L,
    B,
    a,
    W,
    d,
    H,
    q,
    ne,
    P,
    N,
    F,
    k,
    S,
    A,
    _,
    o,
    E,
    p,
    v,
    x,
    C,
    G,
    T,
    I,
    K,
    i
  ];
}
class Rt extends Mt {
  constructor(t) {
    super(), yt(
      this,
      t,
      Pt,
      Ft,
      at,
      {
        mount: 18,
        tilt: 19,
        azimuth: 20,
        panels: 21,
        isSv: 0,
        interactive: 1,
        disabled: 22
      },
      Wt,
      [-1, -1]
    );
  }
}
function Bt(e, t) {
  return new Rt({ target: e, props: t });
}
export {
  Bt as mountFigure
};
