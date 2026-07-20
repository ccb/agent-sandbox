/* GENERATED FILE -- do not edit. The reel at app/prototypes/
   retro-animations.html is the single source of truth; re-run
   app/gen_figures.py after changing it (build_dist.py does).

   window.TombFigures: the illustration-card registry for the terminal.
     .has(key)              -- is there a card for this key?
     .render(key, parent)   -- build the card's svg/canvas inside *parent*
   Cards tick on one shared 12 fps step clock; only the newest MAX_LIVE
   rendered cards keep animating (older ones freeze on their last frame),
   and disconnected nodes drop off the clock automatically. */
(() => {
  "use strict";
  const META = {"autarch": ["svg", 640, 420], "autarch-c": ["svg", 640, 420], "autarch-e": ["svg", 640, 420], "bats": ["canvas", 640, 300], "bats-c": ["svg", 640, 360], "blade": ["canvas", 640, 360], "boots": ["svg", 640, 360], "canopic-c": ["svg", 640, 400], "centipede": ["svg", 640, 360], "chimney-f": ["svg", 640, 360], "chimney-g": ["svg", 640, 360], "chimney-h": ["svg", 640, 360], "core": ["svg", 640, 360], "critch": ["svg", 640, 360], "cyl-a": ["svg", 640, 400], "cyl-c": ["svg", 640, 400], "cyl-o": ["svg", 640, 400], "cyl-v": ["svg", 640, 400], "cylinders": ["svg", 640, 400], "cylinders-b": ["svg", 640, 400], "dagger": ["svg", 640, 360], "epitaph": ["svg", 640, 400], "ext1c": ["svg", 640, 400], "ext1e": ["svg", 640, 400], "flask": ["svg", 640, 360], "flood": ["svg", 640, 360], "fungus": ["svg", 640, 360], "glowstone": ["canvas", 640, 300], "glowstone-b": ["canvas", 640, 300], "glowstone-c": ["canvas", 640, 300], "guts-a": ["svg", 640, 360], "guts-b": ["svg", 640, 360], "guts-c": ["svg", 640, 360], "hound": ["svg", 640, 360], "jackal": ["svg", 640, 360], "jar-baboon": ["svg", 640, 300], "jar-falcon": ["svg", 640, 300], "jar-human": ["svg", 640, 300], "jar-jackal": ["svg", 640, 300], "jar-mantis": ["svg", 640, 300], "manifest": ["svg", 640, 360], "mem-bath": ["svg", 640, 360], "mem-embalm": ["svg", 640, 360], "mem-kestrel": ["svg", 640, 360], "mem-mother": ["svg", 640, 360], "mem-raising": ["svg", 640, 360], "mystic-b": ["svg", 640, 400], "mystic-c": ["svg", 640, 400], "mystic-f": ["svg", 640, 400], "resp": ["svg", 640, 360], "road": ["svg", 640, 400], "seal": ["svg", 640, 400], "seal-b": ["svg", 640, 400], "shard": ["svg", 640, 360], "silas": ["svg", 640, 400], "spawn-a": ["svg", 640, 360], "spawn-b": ["svg", 640, 360], "spawn-c": ["svg", 640, 360], "sphere-b": ["svg", 640, 420], "sphere-d": ["svg", 640, 420], "sphere-e": ["svg", 640, 420], "sphere-f": ["svg", 640, 420], "tank": ["svg", 640, 360], "tank-f": ["svg", 640, 360], "tesseract": ["canvas", 640, 360], "tesseract-u": ["canvas", 640, 360], "ulfire": ["svg", 640, 360], "wagon": ["svg", 640, 360], "youth-a": ["svg", 640, 360], "youth-b": ["svg", 640, 360], "youth-c": ["svg", 640, 360], "youth-d": ["svg", 640, 360], "zoxen": ["svg", 640, 360], "zoxen-b": ["svg", 640, 360]};
  const FIG = {
    _defs: {}, _uid: 0, _ticks: [], _timer: null, _target: null,
    MAX_LIVE: 3,
    keys() { return Object.keys(this._defs); },
    has(key) { return Object.prototype.hasOwnProperty.call(this._defs, key); },
    meta(key) { return META[key]; },
    _define(key, kind, build) { this._defs[key] = build; },
    _clock(fn) {
      fn(0);
      if (FIG.reducedMotion || !FIG._target) return;
      FIG._ticks.push({ fn, t: 0, node: FIG._target });
      const seen = [];
      for (let i = FIG._ticks.length - 1; i >= 0; i--) {
        const n = FIG._ticks[i].node;
        if (!seen.includes(n)) seen.push(n);
        if (seen.indexOf(n) >= FIG.MAX_LIVE) FIG._ticks.splice(i, 1);
      }
      if (!FIG._timer) FIG._timer = setInterval(FIG._tickAll, 1000 / 12);
    },
    _tickAll() {
      for (let i = FIG._ticks.length - 1; i >= 0; i--) {
        const e = FIG._ticks[i];
        if (!e.node.isConnected) { FIG._ticks.splice(i, 1); continue; }
        try { e.fn(++e.t); } catch (err) { FIG._ticks.splice(i, 1); }
      }
      if (!FIG._ticks.length) { clearInterval(FIG._timer); FIG._timer = null; }
    },
    render(key, parent) {
      const meta = META[key], build = this._defs[key];
      if (!meta || !build) return null;
      const [kind, w, h] = meta;
      let node;
      if (kind === "canvas") {
        node = document.createElement("canvas");
        node.width = w; node.height = h;
      } else {
        node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        node.setAttribute("viewBox", "0 0 " + w + " " + h);
      }
      parent.appendChild(node);
      this._target = node;
      try { build(node); } finally { this._target = null; }
      return node;
    },
  };
  FIG.reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.TombFigures = FIG;

  const PH = "#4db8ff", PH_DIM = "#24587c", PH_BRIGHT = "#dff2ff",
        FUNGUS = "#ff9a3c", BG = "#010304";
  const reduced = FIG.reducedMotion;
  const FPS = 12; // Rod Lord cadence: nothing tweens, everything steps
  function clock(fn) { FIG._clock(fn); }

  /* ---------------- shared wireframe plumbing ---------------- */
  function drawEdges(ctx, pts, edges, color, glow) {
    ctx.strokeStyle = color; ctx.lineWidth = 1.5;
    ctx.shadowColor = color; ctx.shadowBlur = glow;
    ctx.beginPath();
    for (const [a, b] of edges) { ctx.moveTo(pts[a][0], pts[a][1]); ctx.lineTo(pts[b][0], pts[b][1]); }
    ctx.stroke();
  }
  const rot = (x, y, a) => [x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a)];
  function lerpHex(c1, c2, k) {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const a = p(c1), b = p(c2);
    return "rgb(" + a.map((v, i) => Math.round(v + (b[i] - v) * k)).join(",") + ")";
  }
  function tess4() {
    const verts = [], edges = [];
    for (let i = 0; i < 16; i++) verts.push([1, 2, 4, 8].map(b2 => (i & b2) ? 1 : -1));
    for (let i = 0; i < 16; i++) for (const b2 of [1, 2, 4, 8])
      if (!(i & b2)) edges.push([i, i | b2]);
    return { verts, edges };
  }
  function project4(verts, a, b) {
    return verts.map(v => {
      let [x, y, z, w] = v;
      [x, w] = rot(x, w, a); [y, z] = rot(y, z, b); [z, w] = rot(z, w, a * .5);
      const s4 = 1.6 / (2.6 - w);
      x *= s4; y *= s4; z *= s4;
      const s3 = 300 / (4 - z * 1.2);
      return { p: [320 + x * s3, 180 + y * s3], w };
    });
  }

  /* ---------------- 01: tesseract, gilt by depth ---------------- */
  FIG._define("tesseract", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const GOLD = "#ffd76a";
    const { verts, edges } = tess4();
    clock(t => {
      const a = (t % 96) * Math.PI / 48, b = (t % 144) * Math.PI / 72;
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const pts = project4(verts, a, b);
      // the gilding lives on the w-axis: far cell phosphor, near cell gold
      edges.slice().sort((e1, e2) =>
        (pts[e1[0]].w + pts[e1[1]].w) - (pts[e2[0]].w + pts[e2[1]].w))
        .forEach(([i, j]) => {
          const k = ((pts[i].w + pts[j].w) / 2 + 1) / 2;
          drawEdges(ctx, pts.map(q => q.p), [[i, j]],
            lerpHex(PH_DIM, GOLD, Math.max(0, Math.min(1, k))), 3 + k * 8);
        });
      pts.forEach(q => { if (q.w > .55) {                  // gilt rivets, near corners
        ctx.fillStyle = GOLD; ctx.shadowColor = GOLD; ctx.shadowBlur = 8;
        ctx.beginPath(); ctx.arc(q.p[0], q.p[1], 2.2, 0, Math.PI * 2); ctx.fill();
      } });
      ctx.shadowBlur = 0; ctx.font = "11px ui-monospace, monospace";
      ctx.fillStyle = PH_DIM;
      ctx.fillText("GILT: HONEST. GEOMETRY: NOT.", 18, 340);
      ctx.fillStyle = GOLD;
      ctx.fillText("W-AXIS: " + ((a * 180 / Math.PI) % 360 | 0) + "°", 520, 340);
    });
  });

  /* ---------------- 01-D: the ninth angle ---------------- */
  FIG._define("tesseract-u", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const HUES = ["#ff5a5a", "#ff9a3c", "#ffd76a", "#7fff9e", "#4db8ff",
      "#7a7aff", "#c07aff", "#dff2ff"];
    const { verts, edges } = tess4();
    clock(t => {
      const T = t % 192;
      const found = T >= 150 && T < 174;                   // the ninth angle, briefly
      const Tf = found ? 150 : T;
      const a = Tf * Math.PI / 48, b = Tf * Math.PI / 72;
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const pts = project4(verts, a, b);
      edges.slice().sort((e1, e2) =>
        (pts[e1[0]].w + pts[e1[1]].w) - (pts[e2[0]].w + pts[e2[1]].w))
        .forEach(([i, j]) => {
          const k = ((pts[i].w + pts[j].w) / 2 + 1) / 2;
          drawEdges(ctx, pts.map(q => q.p), [[i, j]],
            HUES[Math.max(0, Math.min(7, Math.floor(k * 7.99)))], 6);
        });
      ctx.font = "11px ui-monospace, monospace";
      if (found) {                                         // the compartment, seen
        const innerE = edges.filter(([i, j]) => pts[i].w + pts[j].w < 0);
        drawEdges(ctx, pts.map(q => q.p), innerE,
          (t % 2) ? "#ff5a5a" : "#c07aff", 18);
        ctx.fillStyle = (t % 2) ? "#c07aff" : "#ff5a5a";
        ctx.fillText("THE ANGLE: FOUND. COMPARTMENT: VISIBLE.", 18, 340);
      } else {
        ctx.fillStyle = PH_DIM;
        ctx.fillText("SEARCHING FOR THE ANGLE" + ".".repeat(1 + (t % 3)), 18, 340);
      }
      ctx.fillStyle = found ? "#dff2ff" : PH_DIM;
      ctx.fillText("W-AXIS: " + ((a * 180 / Math.PI) % 360 | 0) + "°", 520, 340);
    });
  });

  /* ---------------- 02: the prismatic blade ---------------- */
  FIG._define("blade", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const V = [], E = [];
    const box = (x0,x1,y0,y1,z0,z1) => {
      const n = V.length;
      for (const x of [x0,x1]) for (const y of [y0,y1]) for (const z of [z0,z1]) V.push([x,y,z]);
      [[0,1],[2,3],[4,5],[6,7],[0,2],[1,3],[4,6],[5,7],[0,4],[1,5],[2,6],[3,7]]
        .forEach(([a,b]) => E.push([n+a, n+b]));
    };
    // the blade: a tip, a mid facet-ring, and a square ricasso section
    const tip = V.length; V.push([0, -1.95, 0]);
    const ring = (y, w, d) => { const n = V.length;
      V.push([-w, y, 0], [0, y, d], [w, y, 0], [0, y, -d]);
      for (let k = 0; k < 4; k++) E.push([n + k, n + (k + 1) % 4]); return n; };
    const m = ring(-0.7, 0.22, 0.06);
    const r = ring(0.85, 0.3, 0.09);
    for (let k = 0; k < 4; k++) { E.push([tip, m + k]); E.push([m + k, r + k]); }
    box(-0.55, 0.55, 0.85, 1.0, -0.12, 0.12);   // guard
    box(-0.1, 0.1, 1.0, 1.62, -0.1, 0.1);       // grip
    box(-0.2, 0.2, 1.62, 1.8, -0.16, 0.16);     // pommel
    const GLEAM = [[tip, m + 1], [m + 1, r + 1]]; // the facet that bends light
    clock(t => {
      const a = (t % 180) * Math.PI / 90, tilt = 0.5;
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const pts = V.map(([x, y, z]) => {
        [x, z] = rot(x, z, a);
        [y, z] = rot(y, z, tilt * .4);
        const s = 168 / (4.2 - z);
        return [320 + x * s, 172 + y * s];
      });
      drawEdges(ctx, pts, E, PH, 8);
      // THE ANGLE: once per turn the flat catches the light, and the blade
      // does what prisms do on album covers.
      const phase = ((a / Math.PI) % 2 + 2) % 2;          // 0..2, one turn
      const k = Math.max(0, 1 - Math.abs(phase - 1.5) / 0.22); // the window
      const kq = Math.round(k * 6) / 6;                    // quantized, of course
      const hit = pts[m + 1];                              // the mid facet
      if (kq > 0) {
        // the incoming beam, white, from the dark
        ctx.strokeStyle = PH_BRIGHT; ctx.lineWidth = 2;
        ctx.shadowColor = PH_BRIGHT; ctx.shadowBlur = 10; ctx.globalAlpha = kq;
        ctx.beginPath(); ctx.moveTo(0, hit[1] - 70); ctx.lineTo(hit[0], hit[1]); ctx.stroke();
        // the fan: six bands, diverging to the right edge
        const HUES = [0, 30, 55, 120, 210, 275];
        HUES.forEach((h, i) => {
          const y1 = hit[1] - 46 + i * 16, y2 = y1 + 16;
          ctx.fillStyle = `hsl(${h} 95% 60%)`;
          ctx.globalAlpha = kq * .5; ctx.shadowBlur = 0;
          ctx.beginPath();
          ctx.moveTo(hit[0], hit[1]);
          ctx.lineTo(640, y1); ctx.lineTo(640, y2);
          ctx.closePath(); ctx.fill();
        });
        ctx.globalAlpha = 1;
        drawEdges(ctx, pts, GLEAM, PH_BRIGHT, 14);
      } else {
        const hue = (t * 30) % 360; // between angles: the gleam idles
        drawEdges(ctx, pts, GLEAM, `hsl(${hue} 90% 70%)`, 12);
      }
      ctx.shadowBlur = 0; ctx.globalAlpha = 1;
      ctx.fillStyle = PH_DIM; ctx.font = "11px ui-monospace, monospace";
      ctx.fillText("EDGE: BENDS LIGHT", 18, 340);
      ctx.fillText(kq > 0 ? "REFRACTION: THE ANGLE" : "HILT: SNAPS ONCE", 490, 340);
    });
  });

  /* ---------------- SVG helpers (litho cards) ---------------- */
  const NS = "http://www.w3.org/2000/svg";
  // Leo Hunt's halftone: a dot-screen pattern per svg, used as the gel fill
  function stipple(svg, id, color, r) {
    id = id + "-f" + (++FIG._uid);
    const defs = document.createElementNS(NS, "defs");
    const pat = document.createElementNS(NS, "pattern");
    pat.setAttribute("id", id); pat.setAttribute("width", 7); pat.setAttribute("height", 7);
    pat.setAttribute("patternUnits", "userSpaceOnUse");
    [[1.7, 1.7], [5.2, 5.2]].forEach(([cx, cy]) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", r || 1);
      c.setAttribute("fill", color); c.setAttribute("opacity", .55);
      pat.appendChild(c);
    });
    defs.appendChild(pat); svg.appendChild(defs);
    return `url(#${id})`;
  }
  function el(svg, name, attrs) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    svg.appendChild(n); return n;
  }
  function label(svg, x, y, size, color) {
    return el(svg, "text", { x, y, fill: color, "font-size": size,
      "font-family": "ui-monospace, monospace", "letter-spacing": "1.5" });
  }
  // mask-slot text: reveal letter by letter on the step clock
  function typeOn(node, text, t, t0, cps) {
    const n = Math.max(0, Math.min(text.length, Math.floor((t - t0) * cps)));
    node.textContent = text.slice(0, n) + (n < text.length && n > 0 ? "_" : "");
  }
  // the bright-edged wipe: returns a fn(t) that positions the sweep
  function wipe(svg, w, h, t0, dur) {
    const g = el(svg, "g", {});
    const cover = el(g, "rect", { x: 0, y: 0, width: w, height: h, fill: BG });
    const edge = el(g, "rect", { x: 0, y: 0, width: 3, height: h, fill: PH_BRIGHT });
    return (t) => {
      const k = Math.max(0, Math.min(1, (t - t0) / dur));
      const x = k * w;
      cover.setAttribute("x", x); cover.setAttribute("width", Math.max(0, w - x));
      edge.setAttribute("x", Math.min(x, w - 3));
      edge.setAttribute("opacity", k >= 1 ? 0 : 1);
    };
  }

    // each jar's stopper is the animal's head, in angular litho line
    function headGlyph(svg, kind, cx) {
      const P = (pts, extra) => el(svg, "polyline",
        Object.assign({ points: pts, fill: "none", stroke: PH, "stroke-width": 1.4 }, extra || {}));
      const dot = (x, y) => el(svg, "circle", { cx: x, cy: y, r: 1.8, fill: PH_BRIGHT });
      if (kind === "BABOON") {
        P(`${cx-10},262 ${cx},256 ${cx+10},262`);                    // dome
        P(`${cx-10},262 ${cx-14},288`); P(`${cx+10},262 ${cx+14},288`); // mane
        P(`${cx-8},268 ${cx+8},268`);                                // the brow
        P(`${cx-6},272 ${cx-6},290 ${cx+6},290 ${cx+6},272`);        // deep muzzle
        dot(cx-3, 286); dot(cx+3, 286);
      } else if (kind === "HUMAN") {
        P(`${cx-14},290 ${cx-10},262 ${cx},256 ${cx+10},262 ${cx+14},290`); // nemes
        P(`${cx-5},268 ${cx+5},268`);                                // brow
        P(`${cx},270 ${cx-2},278 ${cx+2},278`);                      // nose
        P(`${cx-3},284 ${cx+3},284`);                                // mouth
      } else if (kind === "MANTIS") {
        P(`${cx-12},262 ${cx+12},262 ${cx},284 ${cx-12},262`);       // the triangle
        el(svg, "circle", { cx: cx-8, cy: 265, r: 3, fill: "none", stroke: PH });
        el(svg, "circle", { cx: cx+8, cy: 265, r: 3, fill: "none", stroke: PH });
        P(`${cx-6},262 ${cx-13},252`); P(`${cx+6},262 ${cx+13},252`); // antennae
        P(`${cx},284 ${cx},290`);
      } else if (kind === "FALCON") {
        // a raptor displayed: wings outstretched, head turned aside
        P(`${cx-3},268 ${cx-14},261 ${cx-27},258 ${cx-23},264 ${cx-18},263 ` +
          `${cx-14},268 ${cx-10},267 ${cx-5},273`);                  // left wing, stepped feathers
        P(`${cx+3},268 ${cx+14},261 ${cx+27},258 ${cx+23},264 ${cx+18},263 ` +
          `${cx+14},268 ${cx+10},267 ${cx+5},273`);                  // right wing
        P(`${cx-4},270 ${cx},264 ${cx+4},270 ${cx},281 ${cx-4},270`); // the body
        P(`${cx},264 ${cx-3},259 ${cx-8},257 ${cx-12},260 ${cx-7},261`); // head aside, hooked beak
        P(`${cx-3},281 ${cx-5},290`); P(`${cx},282 ${cx},290`);
        P(`${cx+3},281 ${cx+5},290`);                                 // the tail fan
        dot(cx-6, 258);
      } else { // JACKAL
        P(`${cx-9},272 ${cx-13},258 ${cx-4},268`);                   // ear
        P(`${cx+3},268 ${cx+7},258 ${cx+10},272`);                   // ear
        P(`${cx+10},272 ${cx+9},280 ${cx-2},282 ${cx-16},288 ${cx-22},290 ` +
          `${cx-15},281 ${cx-9},272`);                               // skull to snout
        dot(cx-2, 276);
      }
    }

  /* ---------------- 04: PTHALO-JACKAL ---------------- */
  FIG._define("jackal", "svg", function (svg) {
    el(svg, "rect", { x:0, y:0, width:640, height:360, fill: BG });
    el(svg, "line", { x1:16, y1:34, x2:624, y2:34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "FAUNA / DESERT / CAUTIOUS, CLEVER, HUNGRY";
    // the jackal, from the 2e reference: prowling LEFT, head low, ears
    // swept back, grin bared, brush tail trailing -- and SWAYING as it goes
    const JDOTS = stipple(svg, "dots-jackal", PH, 1);
    const BODY = [];
    const B = (name, attrs) => { const n = el(svg, name, attrs); BODY.push(n); return n; };
    // top contour: nose -> stop -> skull -> ears -> shoulder -> hip -> tail base
    B("polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      "108,154 120,146 138,140 150,134 158,130 " +
      "162,128 152,84 172,110 " +          // ear one, swept back
      "178,112 198,80 212,108 " +          // ear two
      "232,116 268,112 306,120 352,124 392,130 412,142 416,150" });
    // underside: jaw -> throat -> chest -> belly -> flank
    B("polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      "108,154 112,166 128,172 152,170 182,158 216,150 242,162 258,184 " +
      "308,190 350,188 372,176 396,160" });
    // the grin, zigzag, bared
    B("polyline", { fill: "none", stroke: PH, "stroke-width": 1.2,
      points: "114,160 119,167 124,159 129,167 134,159 139,166 144,161 149,167" });
    // the eye: yellow, slanted, and frankly doing sums
    B("polygon", { points: "138,138 147,133 156,138 147,142",
      fill: "#ffd76a", stroke: "#ffd76a", "stroke-width": 1 });
    B("circle", { cx: 149, cy: 138, r: 1.7, fill: BG });
    // the coat: FUR now, not spikes -- fine paired strokes leaning back
    // along the spine, longest over the neck and shoulder
    const SPINE = [
      [216, 121], [226, 118], [236, 115], [246, 113], [256, 112], [266, 112],
      [278, 113], [290, 116], [302, 119], [314, 120], [326, 121], [338, 122],
      [350, 124], [362, 125], [374, 127], [386, 129],
    ];
    SPINE.forEach(([x, y], i) => {
      const len = i < 6 ? 10 - i : 5;
      B("line", { x1: x, y1: y, x2: x - 4, y2: y - len, stroke: PH,
        "stroke-width": 1 });
      B("line", { x1: x + 5, y1: y + 1, x2: x + 1, y2: y - len + 2,
        stroke: PH_DIM, "stroke-width": 1 });
    });
    // the brush tail, low and trailing, halftoned
    B("polygon", { fill: JDOTS, stroke: PH, "stroke-width": 1.4, points:
      "416,150 448,180 490,214 526,232 542,242 524,246 480,228 440,198 408,164" });
    // the legs, WALKING and no longer sticks: a rounded THIGH stroke into a
    // finer SHIN, far pair dimmed for depth, all on the gait clock
    const LEGS = [
      { ax: 250, ay: 178, ph: 0.0, near: 1, knee: -9 },   // near fore
      { ax: 262, ay: 182, ph: 0.5, near: 0, knee: -9 },   // far fore
      { ax: 370, ay: 178, ph: 0.55, near: 1, knee: 12 },  // near hind (hocked)
      { ax: 396, ay: 160, ph: 0.05, near: 0, knee: 12 },  // far hind
    ].map(cfg => Object.assign(cfg, {
      thigh: el(svg, "polyline", { fill: "none", stroke: PH,
        "stroke-width": cfg.near ? 5.5 : 3.6, "stroke-linecap": "round",
        opacity: cfg.near ? 1 : .5 }),
      shin: el(svg, "polyline", { fill: "none", stroke: PH,
        "stroke-width": cfg.near ? 2.6 : 1.8, "stroke-linecap": "round",
        opacity: cfg.near ? 1 : .5 }),
    }));
    // the ground: a band of ticks sliding rightward under the walk
    const gGround = document.createElementNS(NS, "g");
    for (let x = 44; x < 600; x += 16) {
      const l = document.createElementNS(NS, "line");
      l.setAttribute("x1", x); l.setAttribute("y1", 276);
      l.setAttribute("x2", x + 7); l.setAttribute("y2", 276);
      l.setAttribute("stroke", PH_DIM); gGround.appendChild(l);
    }
    svg.appendChild(gGround);
    // cycling callouts with leader lines
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 90, 10, PH);
    call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [148, 139], text: "EYES: DOING SUMS" },
      { at: [310, 122], text: "COAT: PTHALO No.9" },
      { at: [108, 154], text: "NOSE: FINDS MEAT AT TWO ROOMS" },
      { at: [526, 232], text: "EXIT: ALWAYS PREPARED" },
    ];
    // the PATIENCE gauge
    label(svg, 24, 322, 10, PH_DIM).textContent = "PATIENCE";
    const cells = Array.from({ length: 10 }, (_, i) =>
      el(svg, "rect", { x: 100 + i * 18, y: 312, width: 14, height: 12, fill: PH, "fill-opacity": .8 }));
    const verdict = label(svg, 300, 322, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "PTHALO-JACKAL (PACK, VIGOROUS)", T, 4, 1.4);
      // the prowl: the body BOBS and the shoulders ROLL over planted feet
      const bob = [0, 1, 2, 1, 0, -1, -2, -1][t % 8] * .8;
      const roll = ((t % 16) < 8 ? 1 : -1) * 0.7;
      const TR = `translate(0 ${bob}) rotate(${roll} 270 170)`;
      BODY.forEach(n => n.setAttribute("transform", TR));
      // the walk: sixteen poses per stride, feet planted or swinging
      LEGS.forEach(L => {
        const th = ((t % 16) / 16 + L.ph) * Math.PI * 2;
        const ay = L.ay + bob;
        const fx = L.ax - 34 + 20 * Math.cos(th);
        const fy = 274 - Math.max(0, Math.sin(th)) * 12;
        const kx = (L.ax + fx) / 2 + L.knee, ky = (ay + fy) / 2 + 8;
        L.thigh.setAttribute("points", `${L.ax},${ay} ${kx},${ky}`);
        L.shin.setAttribute("points",
          `${kx},${ky} ${fx},${fy} ${fx - 9},${fy + 2}`);
      });
      gGround.setAttribute("transform", `translate(${(t * 4) % 16}, 0)`);
      const c = CALLS[Math.floor(T / 22) % CALLS.length];
      if (T > 16) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,86 448,86`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      const left = Math.max(0, 10 - Math.floor(Math.max(0, T - 20) / 9));
      cells.forEach((r, i) => r.setAttribute("fill-opacity", i < left ? .8 : .08));
      verdict.textContent = left === 0
        ? "TRIBUTE ACCEPTED: PEACE, PURCHASED DEEP"
        : left <= 3 ? "ADVICE: PRODUCE THE DATES" : "";
    });
  });

  /* ---------------- 05: the wheel of bats ---------------- */
  FIG._define("bats", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const N = 40, bats = Array.from({ length: N }, (_, i) => ({
      ph: (i / N) * Math.PI * 2, r: 46 + (i * 37 % 34), wob: (i * 13 % 7) - 3 }));
    clock(t => {
      const T = t % 200, wheeling = T < 150, scatter = (T - 150) / 50;
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      // the tomb, far below, minimal
      ctx.strokeStyle = PH_DIM; ctx.shadowColor = PH; ctx.shadowBlur = 4;
      ctx.strokeRect(290, 210, 60, 70);
      ctx.beginPath(); ctx.moveTo(305, 280); ctx.lineTo(305, 258); ctx.lineTo(318, 258);
      ctx.lineTo(318, 280); ctx.stroke();
      // the horizon's molten line
      ctx.strokeStyle = FUNGUS; ctx.beginPath(); ctx.moveTo(0, 281); ctx.lineTo(640, 281); ctx.stroke();
      // the wheel
      ctx.strokeStyle = PH; ctx.shadowBlur = 6; ctx.lineWidth = 1.4;
      const a0 = T * .35;
      for (const b of bats) {
        let x, y;
        if (wheeling) {
          x = 320 + Math.cos(a0 + b.ph) * (b.r + b.wob * Math.sin(T * .7 + b.ph));
          y = 120 + Math.sin(a0 + b.ph) * (b.r * .42);
        } else {
          x = 320 + Math.cos(b.ph) * (b.r + scatter * 420);
          y = 120 + Math.sin(b.ph) * (b.r * .42) + scatter * (b.ph > Math.PI ? -30 : 60) * .4;
        }
        const flap = ((t + b.wob) % 4 < 2) ? 3.5 : 1.2;
        ctx.globalAlpha = wheeling ? 1 : Math.max(0, 1 - scatter);
        ctx.beginPath();
        ctx.moveTo(x - 4, y - flap); ctx.lineTo(x, y); ctx.lineTo(x + 4, y - flap);
        ctx.stroke();
      }
      ctx.globalAlpha = 1; ctx.shadowBlur = 0;
      ctx.fillStyle = PH_DIM; ctx.font = "11px ui-monospace, monospace";
      ctx.fillText(wheeling ? "TURN " + (Math.floor(T / 15) + 1) + " OF 10" :
        "TOWARD THE HORIZON'S MOLTEN LINE", 18, 288);
    });
  });

  /* ---------------- 06: the burial cylinders (factory fallback) ----------------
     Re-stamped from cylCard (CCB): canon station order and contents, shown
     mid-scavenge -- cerulean and amber down, boots and igniter still kept. */
  FIG._define("cylinders", "svg", function (svg) {
    cylCard(svg, "g", ["CERULEAN", "AMBER"],
      "THE BURIAL CYLINDERS",
      "KIT OUTLASTS ITS OWNERS.");
  });

  /* ---- the burial-cylinder factory (CCB): one card per combination of
     broken cylinders. Stations hold canon order -- cerulean, amber,
     viridian, orange -- each drawn sealed (tenant, kit signature, bubbles)
     or burst (stump, hue-tinted spill, shards, slump; the orange one vents
     spores). 06-C/A/V/O below are the four first-break states; deeper
     combinations stamp from this same mold when wanted. ---- */
  function cylCard(svg, uid, broken, hdrText, footText) {
    const AMBERH = "#ffd06a", VIRIDIANH = "#4ee0a8";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "GUARD ISSUE / " +
      ["INTACT", "ONE BURST", "TWO BURST", "THREE BURST", "ALL BURST"][broken.length];
    const CYLS = [
      { cx: 105, hue: PH, name: "CERULEAN",
        kept: "CERULEAN: A PRISMATIC BLADE AT REST",
        gone: "CERULEAN: BURST -- THE BLADE RANG FREE" },
      { cx: 245, hue: AMBERH, name: "AMBER",
        kept: "AMBER: A RESPIRATOR, STILL SEALED",
        gone: "AMBER: BURST -- MASK UP" },
      { cx: 385, hue: VIRIDIANH, name: "VIRIDIAN",
        kept: "VIRIDIAN: MAGNETIC BOOTS, GUARD ISSUE",
        gone: "VIRIDIAN: BURST -- THE BOOTS LET GO" },
      { cx: 525, hue: FUNGUS, name: "ORANGE",
        kept: "ORANGE: A PLASMA-IGNITER -- AND A BLOOM",
        gone: "ORANGE: VENTED -- THE BLOOM IS LOOSE" },
    ];
    const bubbles = [], spores = [], tents = [], tipSpores = [];
    const groups = CYLS.map((c, i) => {
      c.down = broken.indexOf(c.name) >= 0;
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      const put = (nn, a) => { const q = document.createElementNS(NS, nn);
        for (const k in a) q.setAttribute(k, a[k]); g.appendChild(q); return q; };
      const gel = stipple(svg, "gel" + uid + i, c.hue, 1);
      if (!c.down) {
        put("rect", { x: c.cx - 32, y: 130, width: 64, height: 186, fill: gel });
        put("line", { x1: c.cx - 34, y1: 122, x2: c.cx - 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
        put("line", { x1: c.cx + 34, y1: 122, x2: c.cx + 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 122, rx: 34, ry: 9, fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 318, rx: 34, ry: 9, fill: "none", stroke: PH });
        // the tenant, at an attention no order will relieve
        put("circle", { cx: c.cx, cy: 165, r: 7, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
        put("polyline", { points: `${c.cx - 11},178 ${c.cx + 11},178 ${c.cx + 8},240 ${c.cx + 6},296 ` +
          `${c.cx - 6},296 ${c.cx - 8},240 ${c.cx - 11},178`, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
        put("line", { x1: c.cx - 9, y1: 196, x2: c.cx + 7, y2: 212, stroke: PH_DIM });
        put("line", { x1: c.cx + 9, y1: 196, x2: c.cx - 7, y2: 212, stroke: PH_DIM });
        // each guard's kit, sealed in with him
        if (c.name === "CERULEAN") {                          // the blade, shouldered
          put("line", { x1: c.cx + 10, y1: 160, x2: c.cx + 22, y2: 236, stroke: PH_BRIGHT, "stroke-width": 1.5 });
          put("line", { x1: c.cx + 13, y1: 172, x2: c.cx + 21, y2: 167, stroke: c.hue });
          put("line", { x1: c.cx + 16, y1: 190, x2: c.cx + 24, y2: 185, stroke: c.hue });
        }
        if (c.name === "AMBER")                               // the respirator, strapped on
          put("path", { d: `M ${c.cx - 6} 166 Q ${c.cx} 174 ${c.cx + 6} 166 L ${c.cx + 4} 171 ` +
            `Q ${c.cx} 177 ${c.cx - 4} 171 Z`, fill: c.hue, stroke: "none", opacity: .9 });
        if (c.name === "VIRIDIAN") {                          // the boots, still gripping
          put("rect", { x: c.cx - 10, y: 298, width: 8, height: 7, fill: "none", stroke: c.hue, "stroke-width": 1.2 });
          put("rect", { x: c.cx + 2, y: 298, width: 8, height: 7, fill: "none", stroke: c.hue, "stroke-width": 1.2 });
        }
        if (c.name === "ORANGE")                              // the bloom, veining
          [[-22, 300, -14, 250, -20, 214], [0, 306, 4, 262, -2, 226], [20, 300, 14, 246, 22, 208]]
            .forEach(v => put("polyline", { points:
              `${c.cx + v[0]},${v[1]} ${c.cx + v[2]},${v[3]} ${c.cx + v[4]},${v[5]}`,
              fill: "none", stroke: FUNGUS, "stroke-width": 1 }));
        for (let b = 0; b < 3; b++)
          bubbles.push({ q: el(svg, "circle", { cx: c.cx + (b - 1) * 12, cy: 300, r: 2,
            fill: "none", stroke: c.hue, opacity: .8 }), phase: i * 31 + b * 57 });
      } else {
        // burst: a jagged stump, shards, the spill, the slumped dead
        put("polyline", { points: `${c.cx - 34},318 ${c.cx - 34},236 ${c.cx - 22},252 ${c.cx - 12},230 ` +
          `${c.cx},248 ${c.cx + 12},226 ${c.cx + 22},250 ${c.cx + 34},232 ${c.cx + 34},318`,
          fill: "none", stroke: PH, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 318, rx: 34, ry: 9, fill: "none", stroke: PH });
        put("ellipse", { cx: c.cx, cy: 336, rx: 52, ry: 8, fill: gel, stroke: "none" });
        [[-48, 300, -40, 290], [44, 306, 52, 296], [40, 316, 50, 314]].forEach(v =>
          put("line", { x1: c.cx + v[0], y1: v[1], x2: c.cx + v[2], y2: v[3], stroke: PH_BRIGHT }));
        put("polyline", { points: `${c.cx - 20},306 ${c.cx - 6},296 ${c.cx + 10},304 ${c.cx + 20},298`,
          fill: "none", stroke: PH_DIM, "stroke-width": 1.6 }); // the slump
        if (c.name === "ORANGE") {                            // vented: airborne now
          for (let s = 0; s < 10; s++)
            spores.push({ q: el(svg, "circle", { r: s % 3 ? 1.4 : 2, fill: FUNGUS }),
              x: c.cx + (s - 4.5) * 11, phase: s * 37 + i * 11 });
          const JAG = [247, 232, 248, 228, 244];              // glass height per lane
          for (let s = 0; s < 5; s++) {                       // and the bloom climbs,
            const w = { x: c.cx + (s - 2) * 13, ph: s * 1.9,  // rooted on the base oval
              h: 90 + (s % 3) * 22, split: JAG[s],
              lo: el(svg, "polyline", { fill: "none", stroke: "#ffc9a0",
                "stroke-width": 1.6, opacity: .7 }),          // seen through the glass
              hi: el(svg, "polyline", { fill: "none", stroke: FUNGUS,
                "stroke-width": 1.6 }) };                     // open air above the jag
            tents.push(w);
            for (let d = 0; d < 2; d++)                       // spores off the tips
              tipSpores.push({ w, phase: s * 23 + d * 29,
                q: el(svg, "circle", { r: 1.5, fill: FUNGUS }) });
          }
        }
      }
      const cap = label(svg, c.cx, 362, 10, c.down ? PH_DIM : c.hue);
      cap.setAttribute("text-anchor", "middle");
      cap.textContent = c.name;
      return { g, c };
    });
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, hdrText, T, 4, 1.4);
      groups.forEach(({ g }, i) => g.setAttribute("opacity", T > 10 + i * 7 ? 1 : 0));
      bubbles.forEach(b => b.q.setAttribute("cy", 300 - ((t * 3 + b.phase) % 156)));
      spores.forEach(s => {                                   // the loose bloom
        const k = (t * 2 + s.phase) % 120;
        s.q.setAttribute("cx", s.x + Math.sin((t + s.phase) * .25) * 10);
        s.q.setAttribute("cy", 320 - k * 1.6);
        s.q.setAttribute("opacity", k > 100 ? 0 : .35 + (k % 3) * .2);
      });
      tents.forEach(w => {                                    // wriggling, 11-B-wise
        const lo = [], hi = [];
        for (let q = 0; q <= 8; q++) {
          const u = q / 8;
          const x = w.x + Math.sin(t * .22 + q * .9 + w.ph) * (2 + u * 9);
          const y = 318 - u * w.h;
          if (y >= w.split) lo.push(`${x},${y}`);             // behind the glass
          if (y <= w.split + w.h / 8) hi.push(`${x},${y}`);   // out in the air
          if (q === 8) { w.tipX = x; w.tipY = y; }
        }
        w.lo.setAttribute("points", lo.join(" "));
        w.hi.setAttribute("points", hi.join(" "));
      });
      tipSpores.forEach(sp => {                               // the tips, seeding
        const k = (t * 2 + sp.phase) % 54;
        sp.q.setAttribute("cx", (sp.w.tipX || 0) + Math.sin((t + sp.phase) * .3) * 5);
        sp.q.setAttribute("cy", (sp.w.tipY || 0) - 4 - k);
        sp.q.setAttribute("opacity", k > 44 ? 0 : .5 + ((t + sp.phase) % 3) * .2);
      });
      const k = Math.floor(T / 26) % CYLS.length;
      if (T > 40) {
        const c = CYLS[k];
        callLead.setAttribute("points", `${c.cx},${c.down ? 230 : 116} ${c.cx},58 448,58`);
        call.textContent = c.down ? c.gone : c.kept;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, footText, T, 120, 1.6);
    });
  }

  /* ---------------- 06-C: the cylinders, cerulean down ---------------- */
  FIG._define("cyl-c", "svg", function (svg) {
    cylCard(svg, "c", ["CERULEAN"],
      "THE BURIAL CYLINDERS, CERULEAN DOWN",
      "THE BLADE FIRST. AMBER NEXT, IF YOU LIKE BREATHING.");
  });

  /* ---------------- 06-A: the cylinders, amber down ---------------- */
  FIG._define("cyl-a", "svg", function (svg) {
    cylCard(svg, "a", ["AMBER"],
      "THE BURIAL CYLINDERS, AMBER DOWN",
      "AMBER FIRST. EXACTLY AS THE MANUAL WOULD HAVE IT.");
  });

  /* ---------------- 06-V: the cylinders, viridian down ---------------- */
  FIG._define("cyl-v", "svg", function (svg) {
    cylCard(svg, "v", ["VIRIDIAN"],
      "THE BURIAL CYLINDERS, VIRIDIAN DOWN",
      "BOOTS FIRST: A SCAVENGER WHO PLANS AHEAD.");
  });

  /* ---------------- 06-O: the cylinders, orange down ---------------- */
  FIG._define("cyl-o", "svg", function (svg) {
    cylCard(svg, "o", ["ORANGE"],
      "THE BURIAL CYLINDERS, ORANGE DOWN",
      "ORANGE FIRST. THE BLOOM THANKS YOU FOR YOUR LUNGS.");
  });

  /* ---------------- 38: the magnetic boots ---------------- */
  FIG._define("boots", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "GUARD ISSUE / FEET / ANCHOR";
    const VIR = "#4ee0a8";                                    // viridian issue
    const BDOTS2 = stipple(svg, "dots-boots38", VIR, .85);
    // the ferrous deck
    el(svg, "line", { x1: 60, y1: 300, x2: 580, y2: 300, stroke: PH, "stroke-width": 1.6 });
    for (let x = 72; x < 580; x += 26)
      el(svg, "line", { x1: x, y1: 300, x2: x - 9, y2: 311, stroke: PH_DIM });
    // the boot, per reference: tall buckled cuff, long boxy toe, slab sole
    const BOOT = "0,-8 4,-40 2,-72 40,-72 42,-40 78,-16 86,-12 86,0 0,0";
    const mkBoot = () => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      const put = (nn, a) => { const q = document.createElementNS(NS, nn);
        for (const k in a) q.setAttribute(k, a[k]); g.appendChild(q); return q; };
      put("polygon", { points: BOOT, fill: BDOTS2, stroke: VIR, "stroke-width": 1.6 });
      put("rect", { x: 0, y: 0, width: 86, height: 7, fill: "#2e7a5e",
        "fill-opacity": .9, stroke: VIR, "stroke-width": 1.2 });  // the magnet sole
      put("line", { x1: 5, y1: -58, x2: 39, y2: -58, stroke: VIR });  // cuff bands
      put("rect", { x: 14, y: -62, width: 13, height: 7, fill: BG, stroke: VIR });
      put("line", { x1: 5, y1: -42, x2: 40, y2: -42, stroke: VIR });
      put("rect", { x: 14, y: -46, width: 13, height: 7, fill: BG, stroke: VIR });
      put("line", { x1: 50, y1: -28, x2: 66, y2: -19, stroke: VIR });  // instep strap
      put("rect", { x: 53, y: -30, width: 10, height: 6, fill: BG, stroke: VIR });
      return g;
    };
    const left = mkBoot(); left.setAttribute("transform", "translate(150 293)");
    const right = mkBoot();
    // the field, bright white against the deck
    const arcs = [];
    [0, 1].forEach(b => [10, 17, 24].forEach((r, i) =>
      arcs.push({ b, r, i, q: el(svg, "path", { fill: "none", stroke: PH_BRIGHT,
        "stroke-width": 1.7, "stroke-dasharray": "3 3" }) })));
    const grudge = [0, 1, 2].map(() => el(svg, "line",
      { stroke: PH_BRIGHT, "stroke-dasharray": "2 3", opacity: 0 }));
    const click = label(svg, 0, 326, 11, PH_BRIGHT); click.setAttribute("text-anchor", "middle");
    const clickBar = el(svg, "line", { y1: 302, y2: 302, stroke: PH_BRIGHT,
      "stroke-width": 2.5, opacity: 0 });
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [193, 296], text: "SOLE: MAGNET-METAL, DULL" },
      { at: [193, 308], text: "GRIP: FERROUS, TOTAL" },
      { at: [504, 254], text: "RELEASE: GRUDGING", track: true },
    ];
    const foot = label(svg, 320, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "THE MAGNETIC BOOTS", T, 4, 1.4);
      let bx = 320, by = 0, strain = 0;
      if (T < 34) { bx = 320; by = 0; }
      else if (T < 64) { by = -Math.round(((T - 34) / 30) * 14 / 2) * 2; strain = 1; }
      else if (T < 92) {
        const k = (T - 64) / 28;
        bx = 320 + Math.round(90 * k / 4) * 4;
        by = -14 - Math.round(Math.sin(k * Math.PI) * 30 / 2) * 2;
      } else { bx = 410; by = 0; }
      right.setAttribute("transform", `translate(${bx} ${293 + by})`);
      const beat = Math.floor(t / 6);
      arcs.forEach(a => {
        const cx = a.b ? bx + 43 : 193;
        const on = a.b ? (T < 34 || T >= 92) : true;
        a.q.setAttribute("d", `M ${cx - a.r} 300 Q ${cx} ${300 + a.r * .8} ${cx + a.r} 300`);
        a.q.setAttribute("opacity", on ? .65 + ((beat + a.i) % 3 === 0 ? .35 : 0) : 0);
      });
      grudge.forEach((n, i) => {                              // the field, refusing
        if (!strain) { n.setAttribute("opacity", 0); return; }
        const gx = 328 + i * 32;
        n.setAttribute("x1", gx); n.setAttribute("x2", gx);
        n.setAttribute("y1", 300); n.setAttribute("y2", 300 + by);
        n.setAttribute("opacity", (t + i) % 2 ? .9 : .4);
      });
      const clicked = T >= 92 && T < 104;
      click.setAttribute("x", bx + 43);
      click.textContent = clicked ? "CLICK." : "";
      clickBar.setAttribute("x1", bx + 2); clickBar.setAttribute("x2", bx + 84);
      clickBar.setAttribute("opacity", clicked && t % 2 ? .9 : 0);
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 16) {
        // a tracking call follows the boot; the text end stays anchored
        const ax = c.track ? bx + 43 : c.at[0];
        const ay = c.track ? 293 + by - 78 : c.at[1];
        callLead.setAttribute("points", `${ax},${ay} 504,58 512,58`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "THE CLICK MEANS IT.", T, 116, 1.5);
    });
  });

  /* ---------------- 39: the respirator ---------------- */
  FIG._define("resp", "svg", function (svg) {
    const YEL = "#ffd76a";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "GUARD ISSUE / FACE / SEALED";
    const RDOTS = stipple(svg, "dots-resp", YEL, .85);        // amber-issue yellow
    // the mannequin head that wears it
    el(svg, "ellipse", { cx: 320, cy: 168, rx: 60, ry: 76, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.4 });
    el(svg, "line", { x1: 298, y1: 240, x2: 294, y2: 300, stroke: PH_DIM, "stroke-width": 1.4 });
    el(svg, "line", { x1: 342, y1: 240, x2: 346, y2: 300, stroke: PH_DIM, "stroke-width": 1.4 });
    [297, 343].forEach(ex => {                                // brows and eyes, above it
      el(svg, "path", { d: `M ${ex - 9} 140 Q ${ex} 134 ${ex + 9} 140`,
        fill: "none", stroke: PH_DIM });
      el(svg, "ellipse", { cx: ex, cy: 152, rx: 8, ry: 4, fill: "none", stroke: PH_DIM });
      el(svg, "circle", { cx: ex, cy: 152, r: 1.6, fill: PH_DIM });
    });
    // straps, buckled at the temples -- amber issue, like the cup
    el(svg, "line", { x1: 296, y1: 184, x2: 266, y2: 152, stroke: YEL, "stroke-width": 2 });
    el(svg, "line", { x1: 344, y1: 184, x2: 374, y2: 152, stroke: YEL, "stroke-width": 2 });
    el(svg, "line", { x1: 292, y1: 230, x2: 263, y2: 206, stroke: YEL, "stroke-width": 2 });
    el(svg, "line", { x1: 348, y1: 230, x2: 377, y2: 206, stroke: YEL, "stroke-width": 2 });
    el(svg, "rect", { x: 259, y: 144, width: 11, height: 9, fill: BG, stroke: YEL });
    el(svg, "rect", { x: 370, y: 144, width: 11, height: 9, fill: BG, stroke: YEL });
    // the half-mask: cup, nose wedge, central grille, chin exhaust
    el(svg, "path", { d: "M 320 160 L 298 184 Q 280 202 286 226 Q 294 250 320 258 " +
      "Q 346 250 354 226 Q 360 202 342 184 Z", fill: RDOTS, stroke: YEL, "stroke-width": 1.8 });
    el(svg, "polygon", { points: "313,178 320,166 327,178", fill: BG,
      stroke: YEL, "stroke-width": 1.3 });
    const spinners = [];
    const grille = (cx, cy, r) => {                           // the fan grille
      el(svg, "circle", { cx, cy, r, fill: BG, stroke: YEL, "stroke-width": 1.8 });
      el(svg, "circle", { cx, cy, r: r * .76, fill: "none", stroke: PH_DIM });
      const bl = el(svg, "g", {});                            // the blades, spinning --
      for (let a = 0; a < 10; a++) {                          // fungus-orange, like
        const th = a * Math.PI / 5 + .31;                     // what they catch
        el(bl, "line", { x1: cx + Math.cos(th) * r * .2, y1: cy + Math.sin(th) * r * .2,
          x2: cx + Math.cos(th) * r * .66, y2: cy + Math.sin(th) * r * .66, stroke: FUNGUS });
      }
      el(svg, "circle", { cx, cy, r: r * .13, fill: FUNGUS });
      spinners.push({ bl, cx, cy, k: spinners.length });
    };
    grille(320, 224, 19);
    [311, 317, 323, 329].forEach(x =>                         // the chin exhaust
      el(svg, "line", { x1: x, y1: 259, x2: x, y2: 267, stroke: PH_DIM }));
    [[250, 216], [390, 216]].forEach(([cx, cy]) => {          // the twin cartridges
      el(svg, "rect", { x: cx > 320 ? cx - 32 : cx + 18, y: 208, width: 16, height: 14,
        fill: BG, stroke: PH, "stroke-width": 1.2 });         // the port stub
      grille(cx, cy, 30);
      el(svg, "circle", { cx, cy, r: 26, fill: "none", stroke: YEL,
        "stroke-dasharray": "6 4", opacity: .8 });            // the banded rim
    });
    el(svg, "ellipse", { cx: 320, cy: 190, rx: 126, ry: 108, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "4 4", opacity: .6 });  // the seal
    const spores = Array.from({ length: 14 }, (_, j) =>
      ({ j, q: el(svg, "circle", { r: j % 3 ? 1.6 : 2.2, fill: FUNGUS }) }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [390, 216], text: "FILTERS: TWIN, FAN-GRILLED" },
      { at: [320, 160], text: "SEAL: FOUR THOUSAND YEARS, HOLDING" },
      { at: [446, 190], text: "AIR INSIDE: CLEAN, IN A PLACE THAT ISN'T" },
    ];
    const foot = label(svg, 320, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "THE RESPIRATOR", T, 4, 1.4);
      spinners.forEach(sp => sp.bl.setAttribute("transform",
        `rotate(${(Math.floor(t / 2) * (sp.k % 2 ? -8 : 8) + sp.k * 12) % 360} ${sp.cx} ${sp.cy})`));
      spores.forEach(s => {
        const j = s.j;
        const x = ((t * (1.4 + (j % 3) * .7) + j * 61) % 700) - 30;
        const y0 = 52 + ((j * 37) % 280);
        let y = y0 + Math.round(Math.sin((t + j * 7) * .18) * 6 / 2) * 2;
        const dx = (x - 320) / 126;
        if (Math.abs(dx) < 1) {                               // the spores PART
          const by = 108 * Math.sqrt(1 - dx * dx);
          const side = y0 >= 190 ? 1 : -1;
          if (Math.abs(y - 190) < by + 8) y = 190 + side * (by + 8);
        }
        s.q.setAttribute("cx", x); s.q.setAttribute("cy", y);
        s.q.setAttribute("opacity", .4 + ((t + j) % 3) * .2);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 16) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,58 448,58`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "IT KEPT ITS SEAL. THE GUARD DID NOT.", T, 112, 1.5);
    });
  });

  /* ---------------- 40: the flask of embalming gel ---------------- */
  FIG._define("flask", "svg", function (svg) {
    const VIR = "#4ee0a8", YEL = "#ffd76a";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE HOUND TANK / THREE DOSES";
    const GDOTS = stipple(svg, "dots-flask", VIR, 1.1);
    // the glow, breathing behind everything
    const rings = [95, 125, 155].map(r => el(svg, "circle",
      { cx: 320, cy: 218, r, fill: "none", stroke: YEL, opacity: 0 }));
    // the gel, then the glass over it
    el(svg, "path", { d: "M 268 196 Q 254 224 258 246 Q 266 286 320 286 " +
      "Q 374 286 382 246 Q 386 224 372 196 Z", fill: GDOTS, stroke: "none" });
    const surface = el(svg, "line", { x1: 268, y1: 196, x2: 372, y2: 196,
      stroke: YEL, "stroke-width": 1.5 });
    el(svg, "path", { d: "M 306 140 Q 252 168 252 226 Q 252 290 320 290 " +
      "Q 388 290 388 226 Q 388 168 334 140", fill: "none", stroke: PH,
      "stroke-width": 1.8 });                                 // the bulb
    el(svg, "line", { x1: 306, y1: 94, x2: 306, y2: 140, stroke: PH, "stroke-width": 1.8 });
    el(svg, "line", { x1: 334, y1: 94, x2: 334, y2: 140, stroke: PH, "stroke-width": 1.8 });
    el(svg, "rect", { x: 300, y: 78, width: 40, height: 16, fill: BG,
      stroke: PH, "stroke-width": 1.5 });                     // the stopper
    el(svg, "rect", { x: 310, y: 68, width: 20, height: 10, fill: BG,
      stroke: PH_DIM, "stroke-width": 1.3 });
    [82, 88].forEach(y => el(svg, "line", { x1: 303, y1: y, x2: 337, y2: y, stroke: PH_DIM }));
    const bubbles = Array.from({ length: 4 }, (_, j) =>
      ({ j, q: el(svg, "circle", { r: 2, fill: "none", stroke: VIR, opacity: .8 }) }));
    label(svg, 24, 346, 10, PH_DIM).textContent = "DOSES";
    Array.from({ length: 3 }, (_, i) =>
      el(svg, "rect", { x: 84 + i * 20, y: 336, width: 16, height: 12,
        fill: VIR, "fill-opacity": .8 }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [320, 78], text: "STOPPER: HOLDING, MOSTLY" },
      { at: [355, 240], text: "CONTENTS: LAMP-OIL, HONEY, AGE" },
      { at: [415, 160], text: "GLOW: ITS OWN" },
    ];
    const foot = label(svg, 320, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "THE FLASK OF EMBALMING GEL", T, 4, 1.4);
      const pulse = .6 + ((Math.floor(t / 5) % 3) / 2) * .4;
      rings.forEach((n, i) => n.setAttribute("opacity", [.16, .10, .06][i] * pulse * 2.2));
      const tl = [0, 2, 3, 2, 0, -2, -3, -2][Math.floor(t / 9) % 8];  // the slosh
      surface.setAttribute("y1", 196 + tl); surface.setAttribute("y2", 196 - tl);
      bubbles.forEach(b => {
        const y = 280 - ((t * 2 + b.j * 34) % 78);
        b.q.setAttribute("cx", 296 + (b.j * 17) % 50); b.q.setAttribute("cy", y);
        b.q.setAttribute("opacity", y < 204 ? 0 : .8);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 16) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,58 448,58`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "CAUTION: NON-POTABLE, FLAMMABLE.", T, 112, 1.5);
    });
  });

  /* ---------------- 08: the glowstone (interactive) ---------------- */
  FIG._define("glowstone", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const YELLOW = "#ffd76a";
    // the shard: an irregular faceted lump, hand-plotted
    const OUTLINE = [[250,128],[286,84],[338,72],[386,96],[402,142],[376,184],[318,198],[268,176]];
    const FACETS = [[1,6],[2,5],[0,4],[3,7]];
    let lit = false, k = 0, lastT = 0;
    function draw(t) {
      lastT = t;
      // the glow steps toward its target, one increment per tick
      k = Math.max(0, Math.min(6, k + (lit ? 1 : -1)));
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const kk = k / 6;
      if (kk > 0) { // the LIGHT: a radial wash of warm yellow, then the rings
        const halo = ctx.createRadialGradient(324, 138, 8, 324, 138, 84 + k * 26);
        halo.addColorStop(0, `rgba(255,215,106,${.30 * kk})`);
        halo.addColorStop(.45, `rgba(255,215,106,${.13 * kk})`);
        halo.addColorStop(1, "rgba(255,215,106,0)");
        ctx.fillStyle = halo;
        ctx.beginPath(); ctx.arc(324, 138, 84 + k * 26, 0, Math.PI * 2); ctx.fill();
        for (let r = 1; r <= k; r++) { // concentric rings, quantized, fading out
          ctx.strokeStyle = YELLOW; ctx.globalAlpha = .2 * kk * (1 - r / 8);
          ctx.beginPath(); ctx.arc(324, 138, 60 + r * 22, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
      const mix = kk > .5 ? YELLOW : kk > 0 ? PH : PH_DIM;
      ctx.strokeStyle = mix; ctx.lineWidth = 1.6;
      ctx.shadowColor = mix; ctx.shadowBlur = 4 + k * 4;
      ctx.beginPath();
      OUTLINE.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
      ctx.closePath(); ctx.stroke();
      FACETS.forEach(([a, b]) => { ctx.beginPath();
        ctx.moveTo(OUTLINE[a][0], OUTLINE[a][1]); ctx.lineTo(OUTLINE[b][0], OUTLINE[b][1]); ctx.stroke(); });
      // the switch
      ctx.shadowBlur = 0;
      ctx.strokeStyle = PH; ctx.strokeRect(270, 238, 100, 22);
      ctx.fillStyle = lit ? YELLOW : PH_DIM;
      ctx.fillRect(lit ? 322 : 274, 242, 44, 14);
      ctx.fillStyle = PH_DIM; ctx.font = "11px ui-monospace, monospace";
      ctx.textAlign = "right"; ctx.fillText("DOUSED", 262, 253);
      ctx.textAlign = "left"; ctx.fillText("LIT", 378, 253);
      // the ledger: attention, accruing
      const att = Math.round(kk * 10);
      ctx.fillText("ATTENTION: " + "|".repeat(att) + ".".repeat(10 - att), 18, 288);
      ctx.textAlign = "right";
      ctx.fillText(lit ? "> LIGHT GLOWSTONE" : "> DOUSE GLOWSTONE", 622, 288);
      ctx.textAlign = "left";
      ctx.fillStyle = kk === 1 ? YELLOW : PH_DIM;
      ctx.fillText(kk === 1 ? "LIGHT IS DEAR; ATTENTION DEARER" : "", 18, 24);
    }
    cv.addEventListener("pointerdown", () => { lit = !lit; if (reduced) draw(lastT + 1); });
    clock(t => { if (t && t % 48 === 0) lit = !lit; draw(t); }); // it demos itself
  });

  /* ---------------- 08-B: the glowstone, off ---------------- */
  FIG._define("glowstone-b", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const OUTLINE = [[250,128],[286,84],[338,72],[386,96],[402,142],[376,184],[318,198],[268,176]];
    const FACETS = [[1,6],[2,5],[0,4],[3,7]];
    const QUIPS = [
      "COLD LAZULITE, FACTORY SET TO OFF.",
      "ONE MOVING PART. NOBODY HAS MOVED IT.",
      "A STONE THAT TAKES INSTRUCTION. RARE.",
    ];
    clock(t => {
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      // the shard, asleep
      ctx.strokeStyle = PH_DIM; ctx.lineWidth = 1.6;
      ctx.shadowColor = PH_DIM; ctx.shadowBlur = 3;
      ctx.beginPath();
      OUTLINE.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
      ctx.closePath(); ctx.stroke();
      FACETS.forEach(([a, b]) => { ctx.beginPath();
        ctx.moveTo(OUTLINE[a][0], OUTLINE[a][1]); ctx.lineTo(OUTLINE[b][0], OUTLINE[b][1]); ctx.stroke(); });
      // once in a while one facet glints -- proof of life, not light
      if (Math.floor(t / 3) % 20 === 0) {
        const [a, b] = FACETS[Math.floor(t / 60) % FACETS.length];
        ctx.strokeStyle = PH; ctx.shadowColor = PH; ctx.shadowBlur = 6;
        ctx.beginPath(); ctx.moveTo(OUTLINE[a][0], OUTLINE[a][1]);
        ctx.lineTo(OUTLINE[b][0], OUTLINE[b][1]); ctx.stroke();
      }
      ctx.shadowBlur = 0;
      // the amenity
      ctx.strokeStyle = PH; ctx.strokeRect(270, 238, 100, 22);
      ctx.fillStyle = PH_DIM; ctx.fillRect(274, 242, 44, 14);
      ctx.font = "11px ui-monospace, monospace";
      ctx.fillStyle = PH_BRIGHT;
      ctx.textAlign = "right"; ctx.fillText("DOUSED", 262, 253);
      ctx.fillStyle = PH_DIM;
      ctx.textAlign = "left"; ctx.fillText("LIT", 378, 253);
      // the chevron, tapping on the glass above the switch
      const bob = Math.floor(t / 4) % 2 ? 2 : 0;
      ctx.fillStyle = PH;
      ctx.beginPath();
      ctx.moveTo(313, 220 + bob); ctx.lineTo(327, 220 + bob); ctx.lineTo(320, 230 + bob);
      ctx.closePath(); ctx.fill();
      // the dry commentary
      ctx.fillStyle = PH_DIM;
      ctx.fillText(QUIPS[Math.floor(t / 40) % QUIPS.length], 18, 24);
      ctx.fillText("ATTENTION: ..........", 18, 288);
      // the prompt: the whole point of the card
      const cur = Math.floor(t / 5) % 2 ? "_" : " ";
      ctx.textAlign = "right"; ctx.fillStyle = PH_BRIGHT;
      ctx.fillText("> LIGHT GLOWSTONE" + cur, 622, 288);
      ctx.textAlign = "left";
    });
  });

  /* ---------------- 08-C: the glowstone, lit ---------------- */
  FIG._define("glowstone-c", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const YELLOW = "#ffd76a";
    const OUTLINE = [[250,128],[286,84],[338,72],[386,96],[402,142],[376,184],[318,198],[268,176]];
    const FACETS = [[1,6],[2,5],[0,4],[3,7]];
    clock(t => {
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const k = 5 + (Math.floor(t / 8) % 2);              // the burn breathes
      const kk = k / 6;
      const halo = ctx.createRadialGradient(324, 138, 8, 324, 138, 84 + k * 26);
      halo.addColorStop(0, `rgba(255,215,106,${.30 * kk})`);
      halo.addColorStop(.45, `rgba(255,215,106,${.13 * kk})`);
      halo.addColorStop(1, "rgba(255,215,106,0)");
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(324, 138, 84 + k * 26, 0, Math.PI * 2); ctx.fill();
      for (let r = 1; r <= k; r++) {
        ctx.strokeStyle = YELLOW; ctx.globalAlpha = .2 * kk * (1 - r / 8);
        ctx.beginPath(); ctx.arc(324, 138, 60 + r * 22, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.strokeStyle = YELLOW; ctx.lineWidth = 1.6;
      ctx.shadowColor = YELLOW; ctx.shadowBlur = 4 + k * 4;
      ctx.beginPath();
      OUTLINE.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
      ctx.closePath(); ctx.stroke();
      FACETS.forEach(([a, b]) => { ctx.beginPath();
        ctx.moveTo(OUTLINE[a][0], OUTLINE[a][1]); ctx.lineTo(OUTLINE[b][0], OUTLINE[b][1]); ctx.stroke(); });
      ctx.shadowBlur = 0;
      // the switch, thrown
      ctx.strokeStyle = PH; ctx.strokeRect(270, 238, 100, 22);
      ctx.fillStyle = YELLOW; ctx.fillRect(322, 242, 44, 14);
      ctx.font = "11px ui-monospace, monospace";
      ctx.fillStyle = PH_DIM;
      ctx.textAlign = "right"; ctx.fillText("DOUSED", 262, 253);
      ctx.fillStyle = YELLOW;
      ctx.textAlign = "left"; ctx.fillText("LIT", 378, 253);
      // the ledger, running
      const att = 9 + Math.floor(t / 12) % 2;
      ctx.fillStyle = PH_DIM;
      ctx.fillText("ATTENTION: " + "|".repeat(att) + ".".repeat(10 - att), 18, 288);
      const cur = Math.floor(t / 5) % 2 ? "_" : " ";
      ctx.textAlign = "right"; ctx.fillStyle = PH_BRIGHT;
      ctx.fillText("> DOUSE GLOWSTONE" + cur, 622, 288);
      ctx.textAlign = "left";
      ctx.fillStyle = YELLOW;
      ctx.fillText("LIGHT IS DEAR; ATTENTION DEARER", 18, 24);
    });
  });


  /* ---------------- 09: Silas, the synthetic archivist ---------------- */
  FIG._define("silas", "svg", function (svg) {
    const YELLOW = "#ffd76a";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "EYELESS WISDOM / MENDICANT";
    const RDOTS = stipple(svg, "dots-silas", YELLOW, 1);
    // THE ROBE, properly draped: peaked hood, shoulder caps, corded waist,
    // an A-line fall of folds to a dusted hem -- yellow so the dust shows
    el(svg, "polygon", { points:
      "198,80 226,92 240,114 246,152 252,172 " +      // hood front, to shoulder
      "262,186 268,214 258,222 " +                    // the sleeve's upper reach
      "252,240 250,330 134,330 " +                    // robe front, hem
      "128,244 140,186 156,150 166,108",              // the back fall
      fill: RDOTS, stroke: YELLOW, "stroke-width": 1.6 });
    // fold lines, falling from the shoulders
    [[172, 190, 162, 328], [196, 196, 192, 330], [220, 198, 224, 330]].forEach(f =>
      el(svg, "polyline", { fill: "none", stroke: YELLOW, "stroke-width": .8,
        opacity: .6, points: `${f[0]},${f[1]} ${f[2]},${f[3]}` }));
    // the cord at the waist, knotted, ends hanging
    el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.2,
      points: "138,240 250,236" });
    el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1,
      points: "206,238 202,262 208,280" });
    el(svg, "rect", { x: 134, y: 322, width: 116, height: 8, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "2 3" });   // the dust hem
    // THE HOOD'S INTERIOR, and the plated skull in profile (after the ref:
    // panel plates, a deep socketed eye, the ear ring, a grilled mouth)
    el(svg, "polygon", { points: "202,88 232,100 242,130 238,160 212,170 192,150 190,112",
      fill: BG, stroke: "none" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      "198,148 194,122 204,106 222,102 236,112 242,126 " +   // the cranium dome
      "240,134 246,140 242,146 " +                           // brow step, nose flat
      "236,150 238,162 224,168 208,166 200,158 198,148" });  // lip, jaw, home
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "202,112 222,106 236,118" });                  // plate seam one
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "196,132 212,128 220,132" });                  // plate seam two
    el(svg, "circle", { cx: 208, cy: 110, r: 1.3, fill: PH_DIM });
    el(svg, "circle", { cx: 228, cy: 110, r: 1.3, fill: PH_DIM });
    el(svg, "circle", { cx: 230, cy: 132, r: 6.5, fill: BG,
      stroke: PH_DIM, "stroke-width": 1.4 });                // the deep socket
    const eye = el(svg, "circle", { cx: 231, cy: 132, r: 2.6, fill: PH_BRIGHT });
    el(svg, "circle", { cx: 201, cy: 144, r: 6, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.3 });                // the ear ring
    el(svg, "circle", { cx: 201, cy: 144, r: 1.2, fill: PH_DIM });
    [[233, 152], [237, 154], [231, 158]].forEach(([x, y]) => // the mouth grille
      el(svg, "line", { x1: x, y1: y, x2: x + 5, y2: y + 1, stroke: PH_DIM }));
    const port = el(svg, "circle", { cx: 210, cy: 172, r: 2.8, fill: "none",
      stroke: FUNGUS, "stroke-width": 1.3 });                // beneath the jaw
    // THE SLEEVE, wide and draped, and the bare synth forearm out of it
    el(svg, "polygon", { points: "258,184 322,206 316,232 254,220",
      fill: RDOTS, stroke: YELLOW, "stroke-width": 1.4 });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
      points: "322,208 398,200" });                          // forearm strut, upper
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
      points: "318,226 398,214" });                          // forearm strut, lower
    el(svg, "line", { x1: 348, y1: 205, x2: 348, y2: 221, stroke: PH_DIM }); // a coupling
    el(svg, "circle", { cx: 402, cy: 207, r: 4.5, fill: "none",
      stroke: PH, "stroke-width": 1.4 });                    // the wrist joint
    // THE HAND, fully outlined: a plated palm and four jointed fingers
    el(svg, "polygon", { points: "406,200 422,196 428,206 424,216 408,216",
      fill: "none", stroke: PH, "stroke-width": 1.4 });      // the palm plate
    [[422,197,444,188,447,192,424,203],
     [426,203,452,199,453,204,427,208],
     [426,209,450,211,449,216,425,213],
     [423,214,442,222,440,226,421,218]].forEach(q =>
      el(svg, "polygon", { points: `${q[0]},${q[1]} ${q[2]},${q[3]} ${q[4]},${q[5]} ${q[6]},${q[7]}`,
        fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.1 }));
    [[422,200],[426,205],[426,211],[422,216]].forEach(([x, y]) =>
      el(svg, "circle", { cx: x, cy: y, r: 1.3, fill: PH }));  // the knuckles
    // the lattice: a crystal net on the right wall
    const NODES = [];
    for (let c = 0; c < 4; c++) for (let r = 0; r < 5; r++)
      NODES.push([452 + c * 50 + (r % 2) * 14, 78 + r * 62]);
    const EDGES = [];
    NODES.forEach(([x, y], i) => NODES.forEach(([X, Y], j) => {
      if (j > i && Math.hypot(X - x, Y - y) < 78) EDGES.push([i, j]);
    }));
    EDGES.forEach(([a, b]) => el(svg, "line", { x1: NODES[a][0], y1: NODES[a][1],
      x2: NODES[b][0], y2: NODES[b][1], stroke: PH_DIM }));
    NODES.forEach(([x, y]) => el(svg, "circle", { cx: x, cy: y, r: 1.8, fill: PH }));
    // the bright threads: lattice -> fingertips -> up the forearm -> UNDER
    // the sleeve (unseen) -> re-emerging at the neck to walk the skull's
    // panel circuits, ending behind the eye. The robe segments are the gap.
    const HAND = [450, 202];
    const EXT = [
      HAND, [404, 210], [356, 213], [322, 216],   // hand, wrist, forearm, sleeve
      [268, 194], [228, 172],                     // under the robe: UNSEEN
      [206, 162], [201, 144], [214, 128], [224, 106], [231, 132],  // the circuits
    ];
    const EXT_HIDDEN = new Set([3, 4]);           // the segments beneath the cloth
    const PATHS = [
      [NODES[19], NODES[14], NODES[9], NODES[2]],
      [NODES[5], NODES[6], NODES[7], NODES[2]],
      [NODES[16], NODES[12], NODES[8], NODES[2]],
    ].map(base => {
      const path = base.concat(EXT);
      const baseSegs = base.length; // lattice + approach segments, all visible
      const hidden = new Set([...EXT_HIDDEN].map(k => k + baseSegs));
      return { path, hidden };
    });
    let eyeArrival = false;
    const pulses = PATHS.map((pp, i) => ({
      ...pp, off: i * 37,
      dot: el(svg, "circle", { cx: 0, cy: 0, r: 2.4, fill: PH_BRIGHT }),
      tail: el(svg, "line", { x1: 0, y1: 0, x2: 0, y2: 0, stroke: PH_BRIGHT,
        "stroke-width": 1.4 }),
    }));
    // callouts + the ledger of remembered days
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 62, 10, PH);
    const CALLS = [
      { at: [190, 270], text: "ROBES: YELLOW, SO THE DUST SHOWS" },
      { at: [448, 202], text: "FINGERTIPS: THE RIGHT KIND" },
      { at: [210, 172], text: "PORT: BENEATH THE JAW. FUNGUS-READY" },
      { at: [231, 132], text: "EYES: OPTIONAL, PER THE ORDER" },
    ];
    label(svg, 16, 372, 10, PH_DIM).textContent = "THE AUTARCH, IN ORDER:";
    const ledger = label(svg, 190, 372, 10, YELLOW);
    const foot = label(svg, 320, 392, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "SILAS (SYNTHETIC ARCHIVIST, VIGOR 2)", T, 4, 1.4);
      eye.setAttribute("opacity", (t % 34) < 31 ? 1 : .15);   // the long blink
      eye.setAttribute("r", eyeArrival ? 3.8 : 2.6);          // a day, arriving
      eye.setAttribute("fill", eyeArrival ? "#ffd76a" : PH_BRIGHT);
      port.setAttribute("opacity", (t % 34) < 31 ? .6 : 1);
      eyeArrival = false;
      pulses.forEach(p => {
        const segs = p.path.length - 1, total = segs * 7;
        const k = (t + p.off) % total, si = Math.floor(k / 7), f = (k % 7) / 7;
        const [ax, ay] = p.path[si], [bx, by] = p.path[si + 1];
        const x = ax + (bx - ax) * f, y = ay + (by - ay) * f;
        const seen = p.hidden.has(si) ? 0 : 1;  // beneath the robe: unseen
        p.dot.setAttribute("opacity", seen); p.tail.setAttribute("opacity", seen);
        p.dot.setAttribute("cx", x); p.dot.setAttribute("cy", y);
        p.tail.setAttribute("x1", ax + (bx - ax) * Math.max(0, f - .4));
        p.tail.setAttribute("y1", ay + (by - ay) * Math.max(0, f - .4));
        p.tail.setAttribute("x2", x); p.tail.setAttribute("y2", y);
        if (si === segs - 1) eyeArrival = true;  // a day, arriving
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 150,66 146,66`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      const days = Math.min(10, Math.floor(T / 18));
      ledger.textContent = "#".repeat(days) + ".".repeat(10 - days) +
        (days === 10 ? "  (NEVER QUITE DONE)" : "");
      typeOn(foot, "A MAN IS NOT DONE DYING UNTIL HE IS DONE BEING REMEMBERED.", T, 130, 1.8);
    });
  });


  /* ---------------- 10: the synth-hound, preserved ---------------- */
  FIG._define("hound", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "MACHINA / HALL OF HOUNDS / IN GEL";
    // THE TANK: plexiglas, corner bolts, the gel a luminous stipple field
    const GEL = stipple(svg, "gel-hound", PH, .9);
    el(svg, "rect", { x: 36, y: 52, width: 568, height: 252, fill: GEL,
      stroke: PH, "stroke-width": 2 });
    [[44,60],[596,60],[44,296],[596,296]].forEach(([x, y]) =>
      el(svg, "circle", { cx: x, cy: y, r: 2.2, fill: "none", stroke: PH_DIM }));
    el(svg, "line", { x1: 96, y1: 60, x2: 66, y2: 296, stroke: PH_BRIGHT,
      opacity: .18, "stroke-width": 6 });                    // the glass glare
    // THE SPECIMEN, floating: everything in one group so it drifts whole
    const gg = document.createElementNS(NS, "g"); svg.appendChild(gg);
    const H = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); gg.appendChild(n); return n; };
    // the specimen, SLEEK: a racing hound's silhouette -- arched loin,
    // deep chest, hard belly tuck, long neck, narrow muzzle, ears folded
    // back along the skull (rose ears, not antennae)
    H("polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      "196,138 226,124 262,126 300,136 348,158 396,178 " +   // croup to skull
      "492,212" });                                          // the long taper to the nose
    H("polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      "492,212 486,222 448,210 424,202 412,196 " +           // jaw, back to throat
      "392,190 356,196 330,206 " +                           // the DEEP chest
      "282,176 244,170 214,166 " +                           // the tuck, and the waist
      "196,158 190,150 196,138" });                          // the rear, closed
    H("polyline", { fill: "none", stroke: PH, "stroke-width": 1,
      points: "458,210 463,218 468,208 473,218 478,210 483,219" }); // needle teeth
    // the ears: small triangles folded back along the neck
    H("polygon", { points: "396,178 376,162 390,172", fill: PH,
      "fill-opacity": .5, stroke: PH, "stroke-width": 1.2 });
    H("polygon", { points: "404,182 388,164 400,176", fill: "none",
      stroke: PH_DIM, "stroke-width": 1.1 });
    H("circle", { cx: 428, cy: 193, r: 7, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.6 });                // the goggle, unlit
    H("circle", { cx: 430, cy: 194, r: 2.6, fill: PH_DIM, opacity: .35 });
    // ROBOT PARTS: vertebra ticks down the neck, shoulder actuator, hip
    // cylinder, access hatch, a throat hose -- Autarchy pattern
    [[352,161],[364,166],[376,171],[388,176]].forEach(([x, y]) =>
      H("line", { x1: x, y1: y - 4, x2: x - 3, y2: y + 4, stroke: PH_DIM }));
    H("circle", { cx: 306, cy: 162, r: 8, fill: "none", stroke: PH, "stroke-width": 1.4 });
    H("circle", { cx: 306, cy: 162, r: 2.6, fill: "none", stroke: PH_DIM }); // shoulder
    H("rect", { x: 200, y: 138, width: 24, height: 13, fill: "none",
      stroke: PH, "stroke-width": 1.3 });                    // the hip cylinder
    H("line", { x1: 207, y1: 138, x2: 207, y2: 151, stroke: PH_DIM });
    H("rect", { x: 254, y: 146, width: 20, height: 11, fill: "none",
      stroke: PH_DIM });                                     // the access hatch
    H("circle", { cx: 258, cy: 149, r: .9, fill: PH_DIM });
    H("polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "4 3",
      points: "414,198 396,216 366,210 344,202" });          // the throat hose
    [242, 268, 294].forEach(x =>
      H("circle", { cx: x, cy: 136 + (x - 242) * .18, r: 1.1, fill: PH_DIM }));
    // heraldry, someone else's, on the flank
    H("polygon", { points: "262,164 276,164 269,176", fill: PH, "fill-opacity": .7 });
    H("circle", { cx: 292, cy: 172, r: 4, fill: PH, "fill-opacity": .7 });
    // the LIMP legs: long and fine, piston thighs into strut shins, hanging
    [[322,204,332,244,326,282],[306,198,298,236,304,274],
     [214,166,226,208,216,250],[200,162,192,202,198,244]].forEach(([ax,ay,kx,ky,fx,fy], i) => {
      const near = i % 2 === 0;
      H("polyline", { fill: "none", stroke: PH, "stroke-linecap": "round",
        "stroke-width": near ? 4 : 2.8, opacity: near ? 1 : .5,
        points: `${ax},${ay} ${kx},${ky}` });
      H("polyline", { fill: "none", stroke: PH, "stroke-linecap": "round",
        "stroke-width": near ? 2 : 1.5, opacity: near ? 1 : .5,
        points: `${kx},${ky} ${fx},${fy} ${fx + 6},${fy + 4}` });
      H("circle", { cx: kx, cy: ky, r: 2.2, fill: "none", stroke: PH_DIM });
      H("line", { x1: (ax + kx) / 2 - 3, y1: (ay + ky) / 2,
        x2: (ax + kx) / 2 + 3, y2: (ay + ky) / 2, stroke: PH_DIM }); // piston collar
    });
    // the tail: a long fine cable, drifting low
    H("polyline", { fill: "none", stroke: PH, "stroke-width": 1.2, points:
      "192,150 156,166 132,196 126,232" });
    [[170,158],[142,182],[128,214]].forEach(([x, y]) =>
      H("line", { x1: x - 3, y1: y - 3, x2: x + 3, y2: y + 3, stroke: PH_DIM }));
    // bubbles, rising through the gel on the step clock
    const bubbles = Array.from({ length: 7 }, (_, i) =>
      ({ q: el(svg, "circle", { cx: 80 + i * 78, cy: 0, r: 1.8, fill: "none",
        stroke: PH, opacity: .7 }), phase: i * 41 }));
    // callouts + the preservation ledger
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 48, 10, PH);
    const CALLS = [
      { at: [428, 193], text: "EYE: DARK, AND BEST LEFT SO" },
      { at: [292, 172], text: "PANELS: SOMEONE ELSE'S HERALDRY" },
      { at: [212, 144], text: "HIP: PISTON-HOCKED, AUTARCHY PATTERN" },
      { at: [126, 232], text: "TAIL: A CABLE. THE LEASH RING IS GONE" },
    ];
    label(svg, 24, 334, 10, PH_DIM).textContent = "PRESERVATION";
    const cells = Array.from({ length: 10 }, (_, i) =>
      el(svg, "rect", { x: 128 + i * 18, y: 324, width: 14, height: 12,
        fill: PH, "fill-opacity": .8 }));
    const verdict = label(svg, 330, 328, 10, FUNGUS);
    const verdict2 = label(svg, 330, 342, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "SYNTH-HOUND (PRESERVED SPECIMEN)", T, 4, 1.4);
      // the drift: millimetres, on the tank's own slow currents
      const drift = [0, 1, 2, 3, 3, 2, 1, 0, -1, -2, -3, -2, -1, 0][Math.floor(t / 4) % 14];
      gg.setAttribute("transform",
        `translate(0 ${drift * 1.1}) rotate(${drift * .35} 320 190)`);
      bubbles.forEach(b => b.q.setAttribute("cy", 296 - ((t * 2 + b.phase) % 236)));
      const c = CALLS[Math.floor(T / 28) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 170,52 176,52`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      cells.forEach((r, i) => r.setAttribute("fill-opacity",
        i < 10 ? .8 : .08));                                 // four thousand years, holding
      typeOn(verdict, "FOUR THOUSAND YEARS, HOLDING.", T, 90, 1.6);
      typeOn(verdict2, "DO NOT LIGHT THE GEL.", T, 110, 1.6);
    });
  });


  /* ---------------- 12: friend's fungus ---------------- */
  FIG._define("fungus", "svg", function (svg) {
    const PINK = "#ff5fd7";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "SUMMIT / STATE GIFT";
    const PDOTS = stipple(svg, "dots-pink", PINK, 1.2);
    // the mound it grows from
    el(svg, "ellipse", { cx: 320, cy: 302, rx: 110, ry: 13, fill: PDOTS,
      stroke: PH_DIM });
    // the cluster: one tall, two middling, two buttons -- angular litho caps
    const shroom = (cx, capY, capW, stemW, spot) => {
      el(svg, "polygon", { points:
        `${cx - stemW},304 ${cx + stemW},304 ${cx + stemW - 2},${capY + 12} ${cx - stemW + 2},${capY + 12}`,
        fill: "none", stroke: PINK, "stroke-width": 1.4 });
      el(svg, "polygon", { points:
        `${cx - capW},${capY + 14} ${cx - capW * .55},${capY - 8} ${cx},${capY - 16} ` +
        `${cx + capW * .55},${capY - 8} ${cx + capW},${capY + 14}`,
        fill: PDOTS, stroke: PINK, "stroke-width": 1.6 });
      for (let g = 1; g < 4; g++)                     // the gills beneath
        el(svg, "line", { x1: cx - capW + g * (capW / 2), y1: capY + 13,
          x2: cx - capW + g * (capW / 2) + 3, y2: capY + 6, stroke: PH_DIM });
      if (spot) [[-capW * .4, -2], [capW * .3, -8], [0, 4]].forEach(([dx, dy]) =>
        el(svg, "circle", { cx: cx + dx, cy: capY + dy, r: 2.2, fill: BG,
          stroke: PINK, "stroke-width": 1 }));
      return [cx, capY - 16];                         // the apex, for the rings
    };
    const apexes = [
      shroom(320, 168, 36, 6, true),     // tall and slender now
      shroom(250, 214, 24, 4.5, true),
      shroom(392, 224, 22, 4, false),
      shroom(286, 268, 11, 2.6, false),
      shroom(356, 274, 10, 2.4, false),
    ];

    // agreeability, radiating: two staggered rings per big cap
    const rings = [];
    apexes.slice(0, 3).forEach(([x, y], i) => {
      for (let k = 0; k < 2; k++)
        rings.push({ x, y: y - 4, off: i * 9 + k * 14,
          q: el(svg, "circle", { cx: x, cy: y - 4, r: 8, fill: "none",
            stroke: PINK, "stroke-width": 1.2 }) });
    });
    // spores, rising with a sway -- and among them, briefly, small smiles
    const spores = Array.from({ length: 9 }, (_, i) =>
      ({ x: 240 + (i * 53) % 180, ph: i * 31,
         q: el(svg, "circle", { r: 1.4, fill: PINK, opacity: .8 }) }));
    const smiles = [[262, 150], [352, 120], [312, 96]].map(([x, y], i) =>
      ({ off: i * 40, q: el(svg, "path", { d:
        `M ${x - 5} ${y} Q ${x} ${y + 6} ${x + 5} ${y}`,
        fill: "none", stroke: PINK, "stroke-width": 1.3 }) }));
    // callouts + the agreeability gauge
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [320, 154], text: "CAPS: PINK, SOFT, FAINTLY WARM" },
      { at: [250, 200], text: "DOSAGE: A CRUMB IS A MICRODOSE" },
      { at: [392, 212], text: "EFFECT: EXTREME AGREEABILITY, FOR HOURS" },
      { at: [320, 302], text: "KEPT IN THE MYSTIC'S CLASPED HANDS" },
    ];
    label(svg, 24, 334, 10, PH_DIM).textContent = "AGREEABILITY";
    const cells = Array.from({ length: 10 }, (_, i) =>
      el(svg, "rect", { x: 128 + i * 18, y: 324, width: 14, height: 12,
        fill: PINK, "fill-opacity": .08 }));
    const foot = label(svg, 400, 334, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 180;
      doWipe(T);
      typeOn(hdr, "FRIEND'S FUNGUS (PINK, HALLUCINOGENIC)", T, 4, 1.4);
      rings.forEach(r => {
        const k = ((t + r.off) % 28) / 28;             // out, fading, again
        r.q.setAttribute("r", 8 + k * 44);
        r.q.setAttribute("opacity", Math.max(0, .8 - k));
      });
      spores.forEach(sp => {
        const k = (t * 2 + sp.ph) % 220;
        sp.q.setAttribute("cx", sp.x + Math.sin((t + sp.ph) * .25) * 7);
        sp.q.setAttribute("cy", 290 - k);
        sp.q.setAttribute("opacity", k > 200 ? 0 : .85);
      });
      smiles.forEach(sm =>                             // they mean well
        sm.q.setAttribute("opacity", ((t + sm.off) % 80) < 12 ? .9 : 0));
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 448,58 454,58`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      const on = Math.min(10, Math.floor(T / 14));
      cells.forEach((r, i) => r.setAttribute("fill-opacity", i < on ? .8 : .08));
      typeOn(foot, "MEANT FOR SOMEONE LONELIER THAN YOU.", T, 140, 1.6);
    });
  });


  /* ---------------- 13: the Autarch ---------------- */
  FIG._define("autarch", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "FALLEN AUTARCHY / STONE / PATIENT";
    const ADOTS = stipple(svg, "dots-autarch", PH, .9);
    // THE HALO, as carved: a disc edged with flame-spikes, lightning bolts
    // cut into its field, the whole thing stepping like a lighthouse
    const CX = 320, CY = 180;
    el(svg, "circle", { cx: CX, cy: CY, r: 118, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.4 });
    const spikes = Array.from({ length: 20 }, (_, i) => {
      const a = i * Math.PI / 10;
      return el(svg, "polygon", { fill: PH, "fill-opacity": .45, stroke: PH,
        "stroke-width": 1, points:
        `${CX + Math.cos(a - .07) * 118},${CY + Math.sin(a - .07) * 118} ` +
        `${CX + Math.cos(a + .04) * (142 + (i % 2) * 18)},${CY + Math.sin(a + .04) * (142 + (i % 2) * 18)} ` +
        `${CX + Math.cos(a + .13) * 118},${CY + Math.sin(a + .13) * 118}` });
    });
    const bolts = Array.from({ length: 8 }, (_, i) => {
      const a = i * Math.PI / 4 + .4;
      const pts = [70, 82, 94, 106, 116].map((r, k) => {
        const aa = a + (k % 2 ? .11 : -.07);
        return `${CX + Math.cos(aa) * r},${CY + Math.sin(aa) * r}`;
      });
      return el(svg, "polyline", { fill: "none", stroke: PH,
        "stroke-width": 1.6, points: pts.join(" ") });
    });
    // THE FACE: cracked stone, stippled, hollow-eyed
    el(svg, "polygon", { points:
      "272,128 368,128 382,160 380,224 366,258 274,258 260,224 258,160",
      fill: ADOTS, stroke: PH, "stroke-width": 1.8 });
    [0, 1, 2].forEach(r =>                                   // the knit cap rows
      el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
        Array.from({ length: 9 }, (_, k) =>
          `${272 + k * 12},${132 + r * 7 + (k % 2) * 3}`).join(" ") }));
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, opacity: .7,
      points: "300,158 306,180 298,204" });                  // a crack
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, opacity: .7,
      points: "352,150 346,176 354,196 348,214" });          // another
    // the eyes, CLOSED at last: soft lids where the hollows were
    el(svg, "path", { d: "M 284 190 Q 296 197 308 190", fill: "none",
      stroke: PH, "stroke-width": 1.6 });
    el(svg, "path", { d: "M 332 190 Q 344 197 356 190", fill: "none",
      stroke: PH, "stroke-width": 1.6 });
    el(svg, "path", { d: "M 286 183 Q 296 179 306 183", fill: "none",
      stroke: PH_DIM });                                     // the softened brows
    el(svg, "path", { d: "M 334 183 Q 344 179 354 183", fill: "none",
      stroke: PH_DIM });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
      points: "318,196 316,222 310,230 330,230 324,222 322,196" }); // the nose
    el(svg, "polyline", { fill: "none", stroke: PH, points: "306,244 334,244" });
    el(svg, "path", { d: "M 298 240 Q 304 234 310 240", fill: "none", stroke: PH_DIM });
    el(svg, "path", { d: "M 330 240 Q 336 234 342 240", fill: "none", stroke: PH_DIM });
    // THE BEARD: rows of court curls, shimmering downward as if being read
    const curls = [];
    for (let r = 0; r < 6; r++) for (let k = 0; k < 8 - (r > 3 ? 1 : 0); k++)
      curls.push({ r, q: el(svg, "circle", {
        cx: 286 + k * 10 + (r % 2) * 5, cy: 268 + r * 13, r: 4.4,
        fill: "none", stroke: PH, "stroke-width": 1.1 }) });
    el(svg, "rect", { x: 282, y: 300, width: 78, height: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.2 });             // the collar band
    // the shoulders
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "268,258 218,290 186,340 176,392" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "372,258 422,290 454,340 464,392" });
    const foot = label(svg, 320, 410, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "NASSAK AN-RAH (AT REST)", T, 4, 1.4);
      // one slow breath through the whole stone; nothing else moves
      const br = [0, 1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1, 0][Math.floor(t / 4) % 14] / 6;
      spikes.forEach(sp => sp.setAttribute("fill-opacity", .3 + br * .2));
      bolts.forEach(b => { b.setAttribute("opacity", .4 + br * .25);
        b.setAttribute("stroke", PH); b.setAttribute("stroke-width", 1.6); });
      curls.forEach(c => c.q.setAttribute("opacity", .5 + br * .3));
      typeOn(foot, "DREAMING SOMETHING KIND, FOUR THOUSAND YEARS IN.", T, 130, 1.8);
    });
  });

  /* ---------------- 14-16: the jars, close up ---------------- */
  function jarCard(svg, id, title, drawHead, drawInside, CALLS, footText, tick) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 300, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const JD = stipple(svg, id + "-dots", PH, 1);
    // the jar, large, at the left: body, throat, and the head as stopper
    el(svg, "polygon", { points: "150,270 290,270 272,120 168,120",
      fill: JD, stroke: PH, "stroke-width": 1.8 });
    el(svg, "line", { x1: 162, y1: 140, x2: 278, y2: 140, stroke: PH_DIM });
    const parts = { svg, JD, hx: 220, hy: 118 };             // stopper origin
    drawHead(parts);
    drawInside(parts);
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 64, 10, PH); call.setAttribute("text-anchor", "end");
    const foot = label(svg, 430, 286, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 300, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, title, T, 4, 1.4);
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,60 448,60`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, footText, T, 110, 1.6);
      tick(t, T, parts);
    });
  }

  // 14: THE MANTIS JAR -- split, budding, listening
  FIG._define("jar-mantis", "svg", function (svg) {
    jarCard(svg, "jar-mantis", "THE MANTIS JAR (SPLIT, LISTENING)",
    (P) => {
      el(P.svg, "polygon", { points: "180,64 260,64 224,118 216,118 180,64",
        fill: P.JD, stroke: PH, "stroke-width": 1.6 });      // the head, point DOWN
      P.eyeL = el(P.svg, "circle", { cx: 192, cy: 76, r: 8, fill: "none", stroke: PH_BRIGHT });
      P.eyeR = el(P.svg, "circle", { cx: 248, cy: 76, r: 8, fill: "none", stroke: PH_BRIGHT });
      [[-3,-2],[2,3],[3,-3]].forEach(([dx, dy]) => {
        el(P.svg, "circle", { cx: 192 + dx, cy: 76 + dy, r: 1, fill: PH });
        el(P.svg, "circle", { cx: 248 + dx, cy: 76 + dy, r: 1, fill: PH });
      });
      el(P.svg, "line", { x1: 214, y1: 108, x2: 226, y2: 108, stroke: PH_DIM }); // the mouthparts
      P.antL = el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.2 });
      P.antR = el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.2 });
    },
    (P) => {
      P.crack = el(P.svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.6 });
      el(P.svg, "circle", { cx: 236, cy: 196, r: 6, fill: FUNGUS,
        "fill-opacity": .4, stroke: FUNGUS });               // the bud in the split
      P.rings = Array.from({ length: 3 }, () =>
        el(P.svg, "circle", { cx: 220, cy: 96, r: 10, fill: "none",
          stroke: PH_BRIGHT, opacity: 0 }));
      label(P.svg, 24, 286, 10, PH_DIM).textContent = "SONG";
      P.cells = Array.from({ length: 8 }, (_, i) =>
        el(P.svg, "rect", { x: 66 + i * 15, y: 276, width: 11, height: 11,
          fill: FUNGUS, "fill-opacity": .08 }));
    },
    [
      { at: [248, 76], text: "EYES: COMPOUND. THE FACETS STILL COUNT" },
      { at: [232, 190], text: "THE SPLIT: SOMETHING BUDS IN IT" },
      { at: [220, 96], text: "IT AMPLIFIES. MAKE NO SOUND HERE" },
    ],
    "IT LISTENS. THEN IT SINGS.",
    (t, T, P) => {
      const tw = (t % 14) < 3 ? 6 : 0;                       // the twitch
      P.antL.setAttribute("points", `188,64 ${176 - tw},38 ${170 - tw},26`);
      P.antR.setAttribute("points", `252,64 ${264 + tw},40 ${272 + tw},28`);
      const cw = Math.floor((t % 40) / 8);                   // the crack creeps
      P.crack.setAttribute("points",
        `226,122 ${230 + cw},160 ${224 + cw},198 ${232 + cw * 2},240`);
      const singing = (T % 80) > 62;
      P.rings.forEach((r, i) => {
        const k = singing ? ((t * 2 + i * 9) % 28) / 28 : 1;
        r.setAttribute("r", 10 + k * 60);
        r.setAttribute("opacity", singing ? Math.max(0, .8 - k) : 0);
      });
      const on = Math.min(8, Math.floor((T % 80) / 9));
      P.cells.forEach((r, i) => r.setAttribute("fill-opacity", i < on ? .8 : .08));
    });
  });

  // 15: THE JACKAL JAR -- the brain, strangely
  FIG._define("jar-jackal", "svg", function (svg) {
    jarCard(svg, "jar-jackal", "THE JACKAL JAR (THE BRAIN, STRANGELY)",
    (P) => {
      P.earL = el(P.svg, "polygon", { fill: PH, "fill-opacity": .4,
        stroke: PH, "stroke-width": 1.4 });
      P.earR = el(P.svg, "polygon", { fill: "none", stroke: PH, "stroke-width": 1.4 });
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
        "196,118 190,96 202,78 232,72 254,84 " +
        "268,92 284,100 280,108 262,108 244,112 236,118" }); // skull to long snout
      el(P.svg, "circle", { cx: 232, cy: 88, r: 2.4, fill: PH_BRIGHT });
      el(P.svg, "line", { x1: 282, y1: 104, x2: 288, y2: 106, stroke: PH_DIM });
    },
    (P) => {
      el(P.svg, "rect", { x: 178, y: 160, width: 86, height: 74, fill: BG,
        stroke: PH_DIM, "stroke-dasharray": "4 3" });        // the cutaway window
      P.brain = el(P.svg, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.5,
        d: "M 190 210 Q 182 196 190 186 Q 196 176 208 176 Q 214 168 226 172 " +
           "Q 238 168 246 178 Q 258 182 256 196 Q 262 208 250 216 Q 242 226 " +
           "228 222 Q 214 228 204 220 Q 192 220 190 210 Z " +   // the lobed outline
           "M 222 172 Q 218 190 224 200 Q 220 210 224 222 " +   // the fissure
           "M 196 192 Q 204 188 202 198 M 198 208 Q 208 204 206 214 " +
           "M 208 182 Q 214 186 210 192 " +                     // gyri, left
           "M 236 184 Q 230 190 238 194 M 244 198 Q 236 204 244 210 " +
           "M 232 212 Q 240 216 234 221" });                    // gyri, right
      P.pulses = Array.from({ length: 2 }, () =>
        el(P.svg, "circle", { cx: 221, cy: 198, r: 8, fill: "none",
          stroke: FUNGUS, opacity: 0 }));
    },
    [
      { at: [202, 60], text: "EARS: STILL LISTENING" },
      { at: [221, 198], text: "CONTENTS: HIS THOUGHTS, JARRED" },
      { at: [284, 100], text: "TASTE: SOMEBODY'S BIOGRAPHY" },
    ],
    "APPETITES AND THOUGHTS, JARRED SEPARATELY. BOTH GOT UP.",
    (t, T, P) => {
      const tw = (t % 22) < 3 ? 8 : 0;                       // one ear pricks
      P.earL.setAttribute("points", `202,80 ${188 - tw},34 214,70`);
      P.earR.setAttribute("points", `226,74 ${240 + tw / 2},30 246,68`);
      P.pulses.forEach((q, i) => {                            // a thought, not yours
        const k = ((t * 2 + i * 14) % 30) / 30;
        q.setAttribute("r", 8 + k * 34);
        q.setAttribute("opacity", Math.max(0, .7 - k));
      });
    });
  });

  // 16: THE FALCON JAR -- the coil, turning
  FIG._define("jar-falcon", "svg", function (svg) {
    jarCard(svg, "jar-falcon", "THE FALCON JAR (THE COIL, CURED)",
    (P) => {
      // a proper falcon: compact skull, slim neck, and a strongly
      // decurved hook of a beak with the tomial notch
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
        "238,118 244,94 236,72 214,60 192,64 182,72 " +      // crown to the cere
        "170,76 160,84 156,94 " +                            // the hook, curving down
        "162,98 168,94 " +                                   // ...and back under
        "174,99 178,96 " +                                   // the tomial tooth
        "192,102 204,108 208,118" });                        // jaw, chin, slim throat
      el(P.svg, "line", { x1: 182, y1: 78, x2: 172, y2: 82,
        stroke: PH_DIM });                                   // the cere line
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.8,
        points: "198,84 202,98" });                          // the malar teardrop
      P.eye = el(P.svg, "circle", { cx: 198, cy: 78, r: 3.2, fill: PH_BRIGHT });
      el(P.svg, "circle", { cx: 198, cy: 78, r: 5.2, fill: "none", stroke: PH_DIM });
      P.lid = el(P.svg, "line", { x1: 192, y1: 78, x2: 205, y2: 78,
        stroke: PH_DIM, "stroke-width": 6, opacity: 0 });    // the nictitating blink
    },
    (P) => {
      el(P.svg, "rect", { x: 178, y: 160, width: 86, height: 74, fill: BG,
        stroke: PH_DIM, "stroke-dasharray": "4 3" });        // the cutaway window
      P.coil = el(P.svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.8 });
    },
    [
      { at: [158, 92], text: "BEAK: CEREMONIAL, STILL SHARP" },
      { at: [221, 198], text: "CONTENTS: THE COIL. TRIBUTE, IDEALLY" },
      { at: [220, 118], text: "LAST WORN AS A HELM, BY SOMETHING BLIND" },
    ],
    "FOOD, TECHNICALLY. TRIBUTE, IDEALLY.",
    (t, T, P) => {
      P.lid.setAttribute("opacity", (t % 26) < 3 ? .9 : 0);  // the slow blink
      const a0 = t * .06;                                    // the coil, by degrees
      const pts = Array.from({ length: 26 }, (_, k) => {
        const a = a0 + k * .5, r = 4 + k * 1.35;
        return `${221 + Math.cos(a) * r},${198 + Math.sin(a) * r * .75}`;
      });
      P.coil.setAttribute("points", pts.join(" "));
    });
  });

  // 29: THE BABOON JAR -- the lungs, kept working
  FIG._define("jar-baboon", "svg", function (svg) {
    jarCard(svg, "jar-baboon", "THE BABOON JAR (THE LUNGS, KEPT)",
    (P) => {
      // frontal, per 18's glyph and the mandrill reference: dome, ruff,
      // heavy brow, close-set eyes, the long ridged nose, the nostril pad
      el(P.svg, "path", { fill: "none", stroke: PH, "stroke-width": 1.6,
        d: "M 188 74 Q 190 48 220 44 Q 250 48 252 74" });    // the dome
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
        points: "188,74 178,92 172,118" });                  // ruff, left
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
        points: "252,74 262,92 268,118" });                  // ruff, right
      [[180, 86, 170, 90], [176, 100, 166, 104],            // mane tufts
       [260, 86, 270, 90], [264, 100, 274, 104]].forEach(([x1, y1, x2, y2]) =>
        el(P.svg, "line", { x1, y1, x2, y2, stroke: PH_DIM }));
      el(P.svg, "line", { x1: 200, y1: 80, x2: 240, y2: 80,
        stroke: PH, "stroke-width": 2 });                    // the brow shelf
      el(P.svg, "circle", { cx: 206, cy: 88, r: 2.4, fill: PH_BRIGHT });
      el(P.svg, "circle", { cx: 234, cy: 88, r: 2.4, fill: PH_BRIGHT });
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
        points: "216,86 214,110" });                         // the nose ridge
      el(P.svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
        points: "224,86 226,110" });
      ["M 212 92 Q 202 100 208 110", "M 206 90 Q 192 100 200 112",
       "M 200 88 Q 184 100 194 114",                         // cheek flanges, ridged
       "M 228 92 Q 238 100 232 110", "M 234 90 Q 248 100 240 112",
       "M 240 88 Q 256 100 246 114"].forEach(d =>
        el(P.svg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.2, d }));
      el(P.svg, "path", { fill: P.JD, stroke: PH, "stroke-width": 1.6,
        d: "M 210 110 Q 220 106 230 110 Q 234 116 228 119 L 212 119 " +
           "Q 206 116 210 110 Z" });                         // the nostril pad
      el(P.svg, "circle", { cx: 215, cy: 114, r: 1.2, fill: PH_BRIGHT });
      el(P.svg, "circle", { cx: 225, cy: 114, r: 1.2, fill: PH_BRIGHT });
      P.puffs = Array.from({ length: 3 }, () =>
        el(P.svg, "circle", { r: 2, fill: "none",
          stroke: PH_DIM, opacity: 0 }));                    // breath, inside the throat
    },
    (P) => {
      el(P.svg, "rect", { x: 178, y: 160, width: 86, height: 74, fill: BG,
        stroke: PH_DIM, "stroke-dasharray": "4 3" });        // the cutaway window
      el(P.svg, "polyline", { fill: "none", stroke: FUNGUS,
        "stroke-width": 1.5, points: "219,166 219,181 214,187" });  // trachea, left bronchus
      el(P.svg, "polyline", { fill: "none", stroke: FUNGUS,
        "stroke-width": 1.5, points: "223,166 223,181 228,187" });  // ...right bronchus
      P.lungs = el(P.svg, "g", {});
      el(P.lungs, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.6,
        d: "M 214 190 Q 212 182 205 184 Q 194 190 192 205 " +
           "Q 190 220 199 224 Q 210 227 214 220 Z" });       // left lung
      el(P.lungs, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.6,
        d: "M 228 190 Q 230 182 237 184 Q 248 190 250 205 " +
           "Q 252 220 243 224 Q 232 227 228 220 Z" });       // right lung
      P.count = label(P.svg, 24, 286, 10, PH_DIM);
    },
    [
      { at: [214, 80], text: "BROW: DISAPPROVING, PROFESSIONALLY" },
      { at: [221, 206], text: "CONTENTS: THE LUNGS. STILL AT WORK" },
      { at: [221, 132], text: "THE GLASS FOGS FROM THE INSIDE" },
    ],
    "FOUR THOUSAND YEARS. STILL COUNTING BREATHS.",
    (t, T, P) => {
      // the tide -- and every cycle, one held breath (T 120..136)
      const held = T >= 120 && T < 136;
      const k = held ? 1 : Math.sin(t * .35);
      P.lungs.setAttribute("transform", "translate(221 205) scale(" +
        (1 + k * .05) + " " + (1 + k * .09) + ") translate(-221 -205)");
      const exhale = !held && k < -.6;
      P.puffs.forEach((n, i) => {
        const q = ((t * 2 + i * 6) % 18) / 18;
        n.setAttribute("cx", 221 + (i - 1) * 9);
        n.setAttribute("cy", 138 - q * 12);
        n.setAttribute("r", 1.5 + q * 3);
        n.setAttribute("opacity", exhale ? Math.max(0, .6 - q * .5) : 0);
      });
      P.count.textContent = "BREATHS SINCE INTERMENT: " +
        (147460000000 + Math.floor(t / 12));
    });
  });

  // 30: THE HUMAN JAR -- his own face, young, not smiling
  FIG._define("jar-human", "svg", function (svg) {
    jarCard(svg, "jar-human", "THE HUMAN JAR (HIS OWN FACE, YOUNG)",
    (P) => {
      el(P.svg, "path", { fill: P.JD, stroke: PH, "stroke-width": 1.6,
        d: "M 220 44 Q 250 44 252 78 Q 252 104 236 114 Q 228 120 220 120 " +
           "Q 212 120 204 114 Q 188 104 188 78 Q 190 44 220 44 Z" });
      el(P.svg, "line", { x1: 192, y1: 60, x2: 248, y2: 60,
        stroke: PH, "stroke-width": 1.8 });                  // the diadem band
      el(P.svg, "polygon", { points: "188,60 180,118 194,118 196,74",
        fill: P.JD, stroke: PH, "stroke-width": 1.4 });      // the fall, left
      el(P.svg, "polygon", { points: "252,60 260,118 246,118 244,74",
        fill: P.JD, stroke: PH, "stroke-width": 1.4 });      // the fall, right
      P.lidL = el(P.svg, "path", { fill: "none", stroke: PH_BRIGHT,
        "stroke-width": 1.5, d: "M 200 80 Q 207 85 214 80" });   // lids, carved shut
      P.lidR = el(P.svg, "path", { fill: "none", stroke: PH_BRIGHT,
        "stroke-width": 1.5, d: "M 226 80 Q 233 85 240 80" });
      P.slitL = el(P.svg, "line", { x1: 203, y1: 84, x2: 211, y2: 84,
        stroke: PH_BRIGHT, "stroke-width": 1, opacity: 0 });     // ...check anyway
      P.slitR = el(P.svg, "line", { x1: 229, y1: 84, x2: 237, y2: 84,
        stroke: PH_BRIGHT, "stroke-width": 1, opacity: 0 });
      el(P.svg, "polyline", { fill: "none", stroke: PH,
        points: "220,86 218,96 222,98" });                   // the nose
      el(P.svg, "line", { x1: 212, y1: 106, x2: 228, y2: 106,
        stroke: PH, "stroke-width": 1.6 });                  // the mouth. it is a line.
    },
    (P) => {
      el(P.svg, "rect", { x: 178, y: 160, width: 86, height: 74, fill: BG,
        stroke: PH_DIM, "stroke-dasharray": "4 3" });        // the cutaway window
      el(P.svg, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.6,
        d: "M 192 182 Q 212 175 230 181 Q 235 183 233 189 " +
           "Q 218 203 201 214 Q 190 220 187 211 Q 183 196 186 189 " +
           "Q 188 183 192 182 Z" });                         // the major lobe
      el(P.svg, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.6,
        d: "M 239 186 Q 245 180 253 185 Q 259 189 254 195 " +
           "Q 247 201 241 198 Q 236 193 239 186 Z" });       // the lesser, pointed
      P.drops = Array.from({ length: 2 }, () =>
        el(P.svg, "circle", { r: 1.6, fill: FUNGUS, opacity: 0 }));
      P.pool = el(P.svg, "line", { x1: 231, y1: 231, x2: 241, y2: 231,
        stroke: FUNGUS, "stroke-width": 1.4, opacity: .5 });
    },
    [
      { at: [220, 52], text: "THE FACE: HIS OWN, YOUNG. NOT SMILING" },
      { at: [221, 196], text: "CONTENTS: THE LIVER. GRUDGES INTACT" },
      { at: [240, 80], text: "THE LIDS: CARVED SHUT. CHECK ANYWAY" },
    ],
    "THE ONLY JAR WITH ITS OWNER'S FACE. IT ISN'T FLATTERED.",
    (t, T, P) => {
      const flicker = (t % 46) < 2;                          // they should not do that
      P.slitL.setAttribute("opacity", flicker ? .9 : 0);
      P.slitR.setAttribute("opacity", flicker ? .9 : 0);
      P.lidL.setAttribute("opacity", flicker ? .3 : 1);
      P.lidR.setAttribute("opacity", flicker ? .3 : 1);
      P.drops.forEach((n, i) => {                            // geology-paced drip
        const q = ((t + i * 24) % 48) / 48;
        n.setAttribute("cx", 236); n.setAttribute("cy", 202 + q * 27);
        n.setAttribute("opacity", q > .1 ? .8 - q * .5 : 0);
      });
      P.pool.setAttribute("x1", 236 - 5 - (t % 48) / 12);
      P.pool.setAttribute("x2", 236 + 5 + (t % 48) / 12);
    });
  });


  /* ---------------- 31: the synth-hunting dagger ---------------- */
  FIG._define("dagger", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "EXOTICA / WEAPONS-GRADE PHILOSOPHY";
    // the dagger MACHINED: faceted blade, hex pommel, point right
    const blade = el(svg, "g", { transform: "translate(108 150)" });
    el(blade, "polygon", { points: "0,-11 118,-7 160,0 118,7 0,11",
      fill: "none", stroke: PH, "stroke-width": 1.8 });
    el(blade, "line", { x1: 8, y1: 0, x2: 146, y2: 0, stroke: PH_DIM }); // the fuller
    el(blade, "rect", { x: -16, y: -21, width: 16, height: 42, fill: "none",
      stroke: PH, "stroke-width": 1.6 });                    // crossguard
    el(blade, "polygon", { points: "-16,-9 -64,-8 -72,0 -64,8 -16,9",
      fill: "none", stroke: PH, "stroke-width": 1.5 });      // grip, full-handed
    el(blade, "polygon", { points: "-72,0 -82,-8 -94,0 -82,8",
      fill: "none", stroke: PH, "stroke-width": 1.5 });      // hex pommel
    const hot = el(blade, "polygon", { points: "0,-11 118,-7 160,0 118,7 0,11",
      fill: "none", stroke: FUNGUS, "stroke-width": 1.2, opacity: 0 });
    // the argument's escort: glyphs that ring the blade when the paradox
    // deploys, then fly downrange and ring the glitching synth
    const ORB_LOGIC = "∀∃∧∨¬→⊢≡", ORB_GLITCH = "▓▒░█╳╪≠∅";
    const orbit = Array.from({ length: 8 }, () => label(svg, 0, 0, 11, FUNGUS));
    // the statement, assembling beneath the blade
    const stmt = label(svg, 172, 202, 12, PH_BRIGHT); stmt.setAttribute("text-anchor", "middle");
    const phase = label(svg, 24, 66, 10, FUNGUS);
    // the synth downrange: sliced into rows so it can shear
    const SY = 430, rows = [];
    for (let i = 0; i < 10; i++) {
      const g = el(svg, "g", {});
      rows.push(g);
    }
    const rowSeg = (g, d) => el(g, "path", { fill: "none", stroke: PH, "stroke-width": 1.5, d });
    rowSeg(rows[0], `M ${SY - 10} 96 Q ${SY} 84 ${SY + 10} 96`);          // crown
    rowSeg(rows[1], `M ${SY - 12} 108 L ${SY + 12} 108 M ${SY - 5} 102 L ${SY + 5} 102`);
    rowSeg(rows[2], `M ${SY - 9} 120 L ${SY - 11} 130 M ${SY + 9} 120 L ${SY + 11} 130`);
    rowSeg(rows[3], `M ${SY - 12} 142 L ${SY + 12} 142`);                 // shoulders
    rowSeg(rows[4], `M ${SY - 14} 160 L ${SY + 14} 160 M ${SY - 13} 152 L ${SY + 13} 152`);
    rowSeg(rows[5], `M ${SY - 15} 178 L ${SY + 15} 178`);
    rowSeg(rows[6], `M ${SY - 15} 196 L ${SY + 15} 196`);
    rowSeg(rows[7], `M ${SY - 14} 214 L ${SY + 14} 214`);
    rowSeg(rows[8], `M ${SY - 12} 232 L ${SY - 10} 252 M ${SY + 12} 232 L ${SY + 10} 252`);
    rowSeg(rows[9], `M ${SY - 12} 262 L ${SY - 12} 276 M ${SY + 12} 262 L ${SY + 12} 276`);
    const GLITCH = "▓▒░█▚▞╳╪≠∅◊⌇";
    const debris = Array.from({ length: 8 }, () => {
      const n = label(svg, 0, 0, 11, FUNGUS); n.setAttribute("opacity", 0); return n;
    });
    label(svg, 396, 320, 10, PH_DIM).textContent = "TARGET COHERENCE";
    const cbar = el(svg, "rect", { x: 396, y: 328, height: 8, fill: PH,
      "fill-opacity": .6 });
    const foot = label(svg, 190, 330, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 210;
      doWipe(T);
      typeOn(hdr, "THE SYNTH-HUNTING DAGGER", T, 4, 1.4);
      const LOGIC = "∀x: SYNTH(x) → OBEY(x)";
      const PARA = "OBEY(x) → ¬OBEY(x)  ⊢ ⊥";
      if (T < 90) {
        phase.textContent = "PHASE ONE: LOGIC";
        stmt.setAttribute("fill", PH_BRIGHT);
        typeOn(stmt, LOGIC, T, 16, 1.2);
        hot.setAttribute("opacity", 0);
      } else if (T < 130) {
        phase.textContent = "PHASE TWO: PARADOX";
        stmt.setAttribute("fill", FUNGUS);
        typeOn(stmt, PARA, T, 92, 1.5);
        hot.setAttribute("opacity", (t % 4) < 2 ? .9 : .3);
      } else {
        phase.textContent = "PHASE THREE: GLITCH";
        stmt.setAttribute("fill", FUNGUS);
        stmt.textContent = PARA;
        hot.setAttribute("opacity", (t % 2) ? .9 : .4);
      }
      const glitch = T >= 130;
      // paradox: ring the blade; glitch: the ring flies to the target
      const flyK = T < 130 ? 0 : Math.min(1, (T - 130) / 12);
      const ocx = 172 + (SY - 172) * flyK, ocy = 150 + 30 * flyK;
      const orx = 115 - 55 * flyK, ory = 48 + 52 * flyK;
      orbit.forEach((n, i) => {
        if (T < 92) { n.setAttribute("opacity", 0); return; }
        const a = i * Math.PI / 4 + t * (T < 130 ? .09 : .16);
        n.setAttribute("x", ocx + Math.cos(a) * orx);
        n.setAttribute("y", ocy + Math.sin(a) * ory);
        n.textContent = (T < 130 ? ORB_LOGIC : ORB_GLITCH)[(i + Math.floor(t / 3)) % 8];
        n.setAttribute("opacity", .4 + ((t + i) % 6 < 3 ? .5 : 0));
      });
      rows.forEach((g, i) => {
        const dx = glitch ? (((t * 7 + i * 13) % 5) - 2) * 6 : 0;
        const drop = glitch && ((t + i * 3) % 11) < 2;
        g.setAttribute("transform", `translate(${dx} 0)`);
        g.setAttribute("opacity", drop ? .15 : 1);
      });
      debris.forEach((n, j) => {
        if (!glitch) { n.setAttribute("opacity", 0); return; }
        const q = ((t * 2 + j * 9) % 24) / 24;
        n.setAttribute("x", SY - 40 + ((j * 37) % 80));
        n.setAttribute("y", 100 + q * 180);
        n.textContent = GLITCH[(Math.floor(t / 2) + j) % GLITCH.length];
        n.setAttribute("opacity", Math.max(0, .9 - q));
      });
      const coh = T < 130 ? 1 : Math.max(0, 1 - (T - 130) / 70);
      cbar.setAttribute("width", 200 * coh);
      typeOn(foot, "IT DOES NOT CUT SYNTHS. IT CONVINCES THEM.", T, 150, 1.8);
    });
  });

  /* ---------------- 32: the ego-core, formatted ---------------- */
  FIG._define("core", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "EXOTICA / FORMAT: AUTARCH-PROPRIETARY";
    // the reader cradle: two brackets holding the spindle
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "96,140 84,140 84,250 96,250" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "204,140 216,140 216,250 204,250" });
    const spin = el(svg, "g", {});
    el(spin, "polygon", { points: "0,-48 13,-13 9,32 0,48 -9,32 -13,-13",
      fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.7 });
    const facets = Array.from({ length: 4 }, (_, i) =>
      el(spin, "line", { x1: -12, y1: -30 + i * 20, x2: 12, y2: -24 + i * 20,
        stroke: PH_DIM }));
    // probe leads to the panel
    el(svg, "path", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "4 3",
      d: "M 216 195 Q 250 195 262 180" });
    // the memory map panel
    el(svg, "rect", { x: 262, y: 90, width: 348, height: 160, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "4 3" });
    label(svg, 272, 84, 10, PH_DIM).textContent = "MEMORY MAP";
    const SECTORS = [
      ["SECTOR 0001: THE BATH", "KEPT"],
      ["SECTOR 0002: THE HAND ON THE NECK", "KEPT"],
      ["SECTOR 0003: THE KESTREL", "KEPT"],
      ["SECTOR 0117: THE DECREES", "DELETED"],
      ["SECTOR 2210: TEN THOUSAND BANNERS", "DELETED"],
      ["SECTOR 4402: THE CONQUESTS", "DELETED"],
      ["SECTOR 9999: THE DAY I CHOSE", "KEPT"],
    ];
    const lines = Array.from({ length: 5 }, (_, i) => {
      const a = label(svg, 274, 116 + i * 26, 10, PH);
      const b = label(svg, 598, 116 + i * 26, 10, PH); b.setAttribute("text-anchor", "end");
      return [a, b];
    });
    // the usage bar: what four thousand years kept
    label(svg, 24, 300, 10, PH_DIM).textContent = "USAGE";
    const cells = Array.from({ length: 24 }, (_, i) =>
      el(svg, "rect", { x: 84 + i * 22, y: 290, width: 16, height: 12,
        fill: "none", stroke: PH_DIM }));
    const KEPT = [0, 1, 2, 23];                              // four bright sectors
    const foot = label(svg, 320, 340, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "THE EGO-CORE (THE SOUL, FORMATTED)", T, 4, 1.4);
      spin.setAttribute("transform", `translate(150 195) rotate(${(Math.floor(t / 6) * 30) % 360})`);
      const top = Math.floor(T / 22) % SECTORS.length;       // the scroll
      lines.forEach(([a, b], i) => {
        const it = SECTORS[(top + i) % SECTORS.length];
        a.textContent = it[0];
        b.textContent = it[1];
        const kept = it[1] === "KEPT";
        b.setAttribute("fill", kept ? FUNGUS : PH_DIM);
        a.setAttribute("opacity", kept ? 1 : .45);
        // the reading line glows as the facet passes it
        a.setAttribute("fill", i === (t % 5) ? PH_BRIGHT : PH);
      });
      cells.forEach((r, i) => {
        const kept = KEPT.includes(i);
        r.setAttribute("fill", kept ? FUNGUS : "none");
        r.setAttribute("fill-opacity", kept ? .7 : 0);
        r.setAttribute("stroke", kept ? FUNGUS : PH_DIM);
        // deleted sectors: struck through
        r.setAttribute("stroke-dasharray", kept ? "" : "3 3");
      });
      typeOn(foot,
        "TEN THOUSAND BANNERS, DELETED TO MAKE ROOM FOR A BATH.", T, 120, 1.8);
    });
  });

  /* ---------------- 33: the ulfire lantern ---------------- */
  FIG._define("ulfire", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE TOMB, X-RAYED / PERMISSION: NONE";
    el(svg, "line", { x1: 0, y1: 306, x2: 640, y2: 306, stroke: PH, "stroke-width": 1.4 });
    const HUES = ["#ff5a5a", "#ff9a3c", "#ffd76a", "#7fff9e", "#4db8ff",
      "#7a7aff", "#c07aff", "#dff2ff"];
    // the slab, solid
    el(svg, "polygon", { points: "240,306 500,306 480,88 366,60 260,88",
      fill: "none", stroke: PH, "stroke-width": 1.8 });
    const grain = stipple(svg, "dots-ulfire", PH, .7);
    const rock = el(svg, "polygon", { points: "240,306 500,306 480,88 366,60 260,88",
      fill: grain, "fill-opacity": .5, stroke: "none" });
    // the anatomy, clipped to the cone
    const clip = el(svg, "clipPath", { id: "xraywedge-ulfire" });
    const wedge = el(clip, "polygon", {});
    const inner = el(svg, "g", { "clip-path": "url(#xraywedge-ulfire)" });
    el(inner, "polygon", { points: "240,306 500,306 480,88 366,60 260,88",
      fill: BG, stroke: "none" });                           // the stone forgets
    [[290, 252, 56, 38], [366, 252, 56, 38], [290, 200, 56, 38],
     [366, 200, 56, 38], [328, 148, 56, 38]].forEach(([x, y, w, h]) =>
      el(inner, "rect", { x, y, width: w, height: h, fill: "none",
        stroke: PH_BRIGHT, "stroke-width": 1.2, "stroke-dasharray": "4 2" }));
    const sph = el(inner, "circle", { cx: 366, cy: 122, r: 15, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.4 });
    el(inner, "line", { x1: 366, y1: 107, x2: 366, y2: 66, stroke: PH_DIM,
      "stroke-dasharray": "2 3" });
    ["M 366 122 Q 340 160 316 252 M 366 122 Q 390 170 400 252",
     "M 366 122 L 366 66 M 366 122 Q 330 140 300 200 M 366 122 Q 402 140 422 200"]
      .forEach(d => el(inner, "path", { fill: "none", stroke: FUNGUS,
        "stroke-width": 1.3, opacity: .75, d }));
    const pulses = Array.from({ length: 3 }, () =>
      el(inner, "circle", { r: 2.2, fill: FUNGUS, opacity: 0 }));
    el(inner, "circle", { cx: 366, cy: 62, r: 4, fill: "none", stroke: FUNGUS,
      "stroke-width": 1.3 });
    // the lantern, classic, held low at the left
    const lg = el(svg, "g", { transform: "translate(92 306) scale(.92)" });
    el(lg, "polygon", { points: "-26,0 26,0 20,-14 -20,-14", fill: "none",
      stroke: PH, "stroke-width": 1.6 });
    el(lg, "path", { fill: "none", stroke: PH, "stroke-width": 1.7,
      d: "M -17 -16 Q -27 -44 -17 -70 L 17 -70 Q 27 -44 17 -16 Z" });
    el(lg, "line", { x1: -17, y1: -18, x2: 17, y2: -68, stroke: PH_DIM });
    el(lg, "line", { x1: 17, y1: -18, x2: -17, y2: -68, stroke: PH_DIM });
    el(lg, "rect", { x: -13, y: -78, width: 26, height: 8, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    el(lg, "rect", { x: -16, y: -86, width: 32, height: 8, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    el(lg, "path", { fill: "none", stroke: PH, "stroke-width": 1.6,
      d: "M -20 -86 Q 0 -104 20 -86 Z" });
    [-8, 0, 8].forEach(x => el(lg, "line", { x1: x, y1: -90, x2: x, y2: -96,
      stroke: PH_DIM }));
    el(lg, "path", { fill: "none", stroke: PH, "stroke-width": 1.3,
      d: "M -14 -100 Q 0 -150 14 -100" });
    el(lg, "path", { fill: "none", stroke: PH, "stroke-width": 1.4,
      d: "M -22 -8 Q -38 -50 -20 -88" });
    el(lg, "path", { fill: "none", stroke: PH, "stroke-width": 1.4,
      d: "M 22 -8 Q 38 -50 20 -88" });
    const flame = el(lg, "path", { fill: "none", "stroke-width": 1.8,
      d: "M 0 -22 Q -8 -38 0 -58 Q 8 -40 0 -22 Z" });
    const glow = el(lg, "circle", { cx: 0, cy: -42, r: 15, fill: "none" });
    const bTop = el(svg, "line", { "stroke-width": 1.2 });
    const bBot = el(svg, "line", { "stroke-width": 1.2 });
    const dropL = el(svg, "line", { "stroke-width": 1, "stroke-dasharray": "3 4" });
    const dropR = el(svg, "line", { "stroke-width": 1, "stroke-dasharray": "3 4" });
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 64, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [366, 122], text: "ROOT: THE COFFIN" },
      { at: [366, 62], text: "SUMMIT: THE MYSTIC" },
      { at: [300, 220], text: "WHERE IT SHINES, STONE FORGETS TO BE SOLID" },
    ];
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "THE ULFIRE LANTERN", T, 4, 1.4);
      const hue = HUES[t % HUES.length];
      flame.setAttribute("stroke", hue);
      glow.setAttribute("stroke", HUES[(t + 3) % HUES.length]);
      glow.setAttribute("r", 13 + (t % 4));
      glow.setAttribute("opacity", .5);
      // the cone sweeps the slab: an x-ray window on the move
      const ph2 = Math.sin(t * .06);
      const cx = 370 + ph2 * 110;                            // where it points
      const apex = [104, 250];
      const half = 72;
      // the reveal hangs from the beam tips (CCB): each beam ends at a
      // tip, a vertical drops straight down from it to the ground, and
      // the x-ray window is exactly the band between the two drops
      const tipY = 66;
      wedge.setAttribute("points",
        `${cx - half},${tipY} ${cx + half},${tipY} ` +
        `${cx + half},306 ${cx - half},306`);
      [bTop, bBot].forEach((L, i) => {
        L.setAttribute("x1", apex[0]); L.setAttribute("y1", apex[1]);
        L.setAttribute("x2", cx + (i ? half : -half)); L.setAttribute("y2", tipY);
        L.setAttribute("stroke", HUES[(t + i * 4) % HUES.length]);
        L.setAttribute("opacity", .8);
      });
      [dropL, dropR].forEach((L, i) => {
        const x = cx + (i ? half : -half);
        L.setAttribute("x1", x); L.setAttribute("y1", tipY);
        L.setAttribute("x2", x); L.setAttribute("y2", 306);
        L.setAttribute("stroke", HUES[(t + i * 4) % HUES.length]);
        L.setAttribute("opacity", .55);
      });
      pulses.forEach((p, i) => {
        const q = ((t * 2 + i * 16) % 48) / 48;
        p.setAttribute("cx", 366 + Math.sin(q * 8 + i) * 8 * (1 - q));
        p.setAttribute("cy", 122 - q * 58);
        p.setAttribute("opacity", Math.max(0, .9 - q * .6));
      });
      const c = CALLS[Math.floor(T / 36) % CALLS.length];
      if (T > 30) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,60 448,60`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "LEAD WOULD STOP IT. THE TOMB DID NOT THINK OF THAT.", T, 130, 1.9);
    });
  });

  /* ---------------- 34: the crystal shard ---------------- */
  FIG._define("shard", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "SHARD / BALLISTICS, TERMINAL";
    // the summit's edge -- and the cliff face, closed to the ground
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "640,86 540,86 512,96 500,110 496,150 504,196 494,240 502,274 498,300" });
    el(svg, "line", { x1: 0, y1: 300, x2: 640, y2: 300, stroke: PH, "stroke-width": 1.4 });
    const GLASS = "#cfefff";
    // the faller, per card 20: segments, legs, and feelers
    const segs = Array.from({ length: 8 }, () => el(svg, "ellipse",
      { rx: 6, ry: 4, fill: "none", stroke: GLASS, "stroke-width": 1.2, opacity: 0 }));
    const legs = Array.from({ length: 16 }, () => el(svg, "line",
      { stroke: "#9fd9f2", "stroke-width": 1, opacity: 0 }));
    const feelers = [0, 1].map(() => el(svg, "line",
      { stroke: GLASS, "stroke-width": 1.1, opacity: 0 }));
    const arc = el(svg, "path", { fill: "none", stroke: PH_DIM,
      "stroke-dasharray": "3 5" });
    const burst = Array.from({ length: 10 }, () => el(svg, "line",
      { stroke: GLASS, "stroke-width": 1.3, opacity: 0 }));
    const litter = Array.from({ length: 14 }, () => el(svg, "polyline",
      { fill: "none", stroke: PH_DIM, opacity: 0 }));
    // what survived: a crystal, planted point-up
    const hero = el(svg, "g", { opacity: 0 });
    const heroShape = el(hero, "polygon", { fill: "none", stroke: PH_BRIGHT,
      "stroke-width": 1.7 });
    const heroFacet = el(hero, "line", { stroke: PH_DIM });
    const ring = el(svg, "circle", { fill: "none", stroke: FUNGUS,
      "stroke-width": 1.2, opacity: 0 });
    const count = label(svg, 24, 330, 10, PH_DIM);
    const foot = label(svg, 400, 330, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const fx = T => 500 - T * 5.2, fy = T => 110 + T * T * .2;
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE CRYSTAL SHARD (THE FALL, FORGED)", T, 4, 1.4);
      const IMPACT = 34;
      const falling = T >= 6 && T < IMPACT;
      const ft = Math.min(T - 6, IMPACT - 3);
      segs.forEach((n, i) => {
        const u = Math.max(0, ft - i * .8);
        const cx = fx(u), cy = fy(u);
        n.setAttribute("cx", cx); n.setAttribute("cy", cy);
        n.setAttribute("opacity", falling ? .9 : 0);
        [0, 1].forEach(k => {
          const L = legs[i * 2 + k];
          const flail = ((t + i + k) % 4 < 2 ? 4 : -4);
          L.setAttribute("x1", cx - 2 + k * 4); L.setAttribute("y1", cy + 3);
          L.setAttribute("x2", cx - 6 + k * 12 + flail); L.setAttribute("y2", cy + 10);
          L.setAttribute("opacity", falling ? .7 : 0);
        });
      });
      const hx = fx(ft), hy = fy(ft);
      feelers.forEach((n, k) => {
        n.setAttribute("x1", hx + 4); n.setAttribute("y1", hy - 2);
        n.setAttribute("x2", hx + 15); n.setAttribute("y2", hy - 9 + k * 10);
        n.setAttribute("opacity", falling ? .9 : 0);
      });
      let d = "M 500 110";
      for (let u = 0; u <= 31; u += 3.1) d += ` L ${fx(u)} ${fy(u)}`;
      arc.setAttribute("d", d);
      arc.setAttribute("opacity", T >= 6 ? .6 : 0);
      const ix = fx(31), iy = 300;
      burst.forEach((n, i) => {
        const a = i * Math.PI / 5, r = Math.min(28, Math.max(0, (T - IMPACT) * 7));
        n.setAttribute("x1", ix); n.setAttribute("y1", iy);
        n.setAttribute("x2", ix + Math.cos(a) * r); n.setAttribute("y2", iy - Math.abs(Math.sin(a)) * r);
        n.setAttribute("opacity", T >= IMPACT && T < IMPACT + 8 ? .9 : 0);
      });
      litter.forEach((n, i) => {                             // centred on the landing
        const lx = ix - 85 + (i * 37) % 170, ly = 300 - (i % 3) * 4;
        n.setAttribute("points", `${lx},${ly} ${lx + 5},${ly - 6} ${lx + 10},${ly}`);
        n.setAttribute("opacity", T >= IMPACT + 4 ? .7 : 0);
      });
      heroShape.setAttribute("points",
        `${ix + 4},266 ${ix - 6},292 ${ix - 2},300 ${ix + 12},300 ${ix + 15},288`);
      heroFacet.setAttribute("x1", ix + 4); heroFacet.setAttribute("y1", 266);
      heroFacet.setAttribute("x2", ix + 5); heroFacet.setAttribute("y2", 300);
      hero.setAttribute("opacity", T >= IMPACT + 8 ? 1 : 0);
      ring.setAttribute("cx", ix + 5); ring.setAttribute("cy", 286);
      ring.setAttribute("r", 24 + (t % 6));
      ring.setAttribute("opacity", T >= IMPACT + 12 && t % 6 < 4 ? .8 : 0);
      count.textContent = T >= IMPACT + 12 ? "SURVIVORS: 1 OF ~400" : "";
      typeOn(foot, "THE FALL THAT KILLED IT FORGED A KNIFE.", T, IMPACT + 20, 1.8);
    });
  });

  /* ---------------- 35: critch -- the advice, grinning ---------------- */
  FIG._define("critch", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "CRITCH / THE LAUGH, PROFESSIONAL";
    // the face, frontal, per the reference: skull, ears, crest, ruff,
    // eyes, the tapering muzzle, the nose pad -- golden where fur catches
    const face = el(svg, "g", { transform: "translate(320 60)" });
    const F = (d, w, glow) => el(face, "path", { fill: "none",
      stroke: glow ? PH_BRIGHT : PH, "stroke-width": w || 1.5, d });
    const gold = d => el(face, "path", { fill: "none", stroke: FUNGUS,
      "stroke-width": 1.2, d });
    // ears, great and round, fuzzed on the inner edge
    F("M -68 92 Q -104 66 -96 24 Q -90 2 -64 8 Q -40 16 -34 52", 1.6);
    F("M 68 92 Q 104 66 96 24 Q 90 2 64 8 Q 40 16 34 52", 1.6);
    el(face, "polyline", { fill: "none", stroke: PH_DIM, points:
      "-84,56 -78,48 -74,56 -68,46 -64,54" });
    el(face, "polyline", { fill: "none", stroke: PH_DIM, points:
      "84,56 78,48 74,56 68,46 64,54" });
    // the skull and cheeks, tapering to the muzzle
    F("M -66 90 Q -70 130 -42 158 Q -26 176 -14 184", 1.7);
    F("M 66 90 Q 70 130 42 158 Q 26 176 14 184", 1.7);
    F("M -34 50 Q 0 30 34 50", 1.6);                        // the brow dome
    // the crest, golden, standing
    gold("M -26 40 L -20 20 M -12 34 L -8 12 M 2 32 L 4 10 M 16 34 L 22 16 M 28 42 L 36 26");
    // the ruff at the jaw, golden
    gold("M -58 122 L -74 132 M -52 140 L -68 152 M 58 122 L 74 132 M 52 140 L 68 152");
    // the spots
    [[-44, 96], [-28, 82], [44, 96], [28, 82], [-52, 116], [52, 116]].forEach(
      ([cx, cy]) => el(face, "circle", { cx, cy, r: 1.6, fill: FUNGUS,
        "fill-opacity": .8 }));
    // eyes: set close, angled, lit
    F("M -40 96 Q -26 88 -14 98 Q -26 104 -40 96 Z", 1.4);
    F("M 40 96 Q 26 88 14 98 Q 26 104 40 96 Z", 1.4);
    const eyeL = el(face, "circle", { cx: -26, cy: 96, r: 2.4, fill: PH_BRIGHT });
    const eyeR = el(face, "circle", { cx: 26, cy: 96, r: 2.4, fill: PH_BRIGHT });
    // the muzzle, tapering; the nose pad
    F("M -14 108 Q -10 150 -8 168", 1.3);
    F("M 14 108 Q 10 150 8 168", 1.3);
    F("M -8 168 Q 0 164 8 168 Q 12 182 0 186 Q -12 182 -8 168 Z", 1.6);
    el(face, "circle", { cx: -4, cy: 175, r: 1.3, fill: BG, stroke: PH_BRIGHT });
    el(face, "circle", { cx: 4, cy: 175, r: 1.3, fill: BG, stroke: PH_BRIGHT });
    // the mouth, in two minds: a line, then the famous grin
    const shut = el(face, "path", { fill: "none", stroke: PH, "stroke-width": 1.5,
      d: "M -14 184 Q 0 192 14 184" });
    const grin = el(face, "g", { opacity: 0 });
    el(grin, "path", { fill: "none", stroke: PH, "stroke-width": 1.6,
      d: "M -30 168 Q -34 196 -16 214 Q 0 226 16 214 Q 34 196 30 168" });
    el(grin, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.2,
      points: "-26,176 -20,188 -14,176 -8,186 -2,176 4,186 10,176 16,188 22,176" });
    el(grin, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.2,
      points: "-16,212 -10,202 -4,212 2,202 8,212 14,204" });
    const eyeSquintL = el(face, "path", { fill: "none", stroke: PH,
      "stroke-width": 1.6, opacity: 0, d: "M -40 96 Q -26 92 -14 98" });
    const eyeSquintR = el(face, "path", { fill: "none", stroke: PH,
      "stroke-width": 1.6, opacity: 0, d: "M 40 96 Q 26 92 14 98" });
    const quote = label(svg, 320, 322, 10, PH_BRIGHT); quote.setAttribute("text-anchor", "middle");
    const foot = label(svg, 320, 344, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "CRITCH (THE ADVICE)", T, 4, 1.4);
      const grinning = (T % 80) >= 34;
      // the ears prick first, then the jaw commits
      face.setAttribute("transform",
        `translate(320 60) rotate(${grinning ? 2 : 0} 0 120)`);
      grin.setAttribute("opacity", grinning ? 1 : 0);
      shut.setAttribute("opacity", grinning ? 0 : 1);
      eyeSquintL.setAttribute("opacity", grinning ? 1 : 0);
      eyeSquintR.setAttribute("opacity", grinning ? 1 : 0);
      eyeL.setAttribute("opacity", grinning ? 0 : 1);
      eyeR.setAttribute("opacity", grinning ? 0 : 1);
      typeOn(quote, '"TOMB PAYS BETTER THAN THE ROAD --', T, 40, 1.6);
      typeOn(foot, '-- IF THE TOMB LETS YOU KEEP IT."', T, 84, 1.6);
    });
  });

  /* ---------------- 36: the zoxen, in life ---------------- */
  FIG._define("zoxen", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "ZOXEN / THE MEMORIAL, PLAYED HOURLY";
    el(svg, "line", { x1: 0, y1: 296, x2: 640, y2: 296, stroke: PH, "stroke-width": 1.4 });
    const grain = stipple(svg, "dots-zoxen", PH, .7);
    // below: the pair as they are, half-buried by the heeled wagon
    const now = el(svg, "g", {});
    const wg = el(now, "g", { transform: "translate(500 296) rotate(-9) scale(.8)" });
    el(wg, "line", { x1: -80, y1: -22, x2: 84, y2: -22, stroke: PH, "stroke-width": 1.6 });
    [-64, -22, 20, 62].forEach(x =>
      el(wg, "path", { fill: "none", stroke: PH, "stroke-width": 1.4,
        d: `M ${x} -22 Q ${x + 21} -74 ${x + 42} -22` }));
    [[-52, -6], [52, -6]].forEach(([cx, cy]) =>
      el(wg, "circle", { cx, cy, r: 16, fill: "none", stroke: PH, "stroke-width": 1.4 }));
    const zr = el(now, "g", { transform: "translate(190 296)" });
    el(zr, "path", { fill: "none", stroke: PH, "stroke-width": 1.6,
      d: "M -54 0 Q -58 -26 -40 -38 Q -12 -50 16 -42 Q 42 -34 46 -12 Q 47 -4 42 0" });
    el(zr, "path", { fill: "none", stroke: PH, "stroke-width": 1.4,
      d: "M -40 -36 Q -56 -34 -62 -22 Q -74 -20 -78 -12 Q -78 -4 -68 -4 Q -60 -4 -58 -10" });
    el(zr, "path", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.4,
      d: "M -60 -26 Q -72 -34 -68 -44 M -54 -26 Q -46 -38 -36 -40" });
    const zf = el(now, "g", { transform: "translate(330 296)" });
    el(zf, "path", { fill: "none", stroke: PH, "stroke-width": 1.6,
      d: "M -46 0 Q -50 -20 -28 -28 Q 2 -36 28 -28 Q 44 -20 46 0" });
    el(zf, "path", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.4,
      d: "M -62 -8 Q -68 -20 -60 -26" });
    el(now, "polygon", { fill: grain, "fill-opacity": .75, points:
      "120,296 254,296 240,282 200,276 152,280 130,288" });
    el(now, "polygon", { fill: grain, "fill-opacity": .75, points:
      "272,296 392,296 382,284 330,278 288,284" });
    // above: the mirage -- the yoked team hauling, in dashes, in the shimmer
    const ghost = el(svg, "g", {});
    const gw = el(ghost, "g", { transform: "translate(430 170) scale(.8)" });
    el(gw, "line", { x1: -60, y1: 0, x2: 78, y2: 0, stroke: PH_DIM,
      "stroke-width": 1.4, "stroke-dasharray": "5 4" });
    [-48, -8, 32].forEach(x =>
      el(gw, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.3,
        "stroke-dasharray": "5 4", d: `M ${x} 0 Q ${x + 23} -48 ${x + 46} 0` }));
    [[-38, 14], [56, 14]].forEach(([cx, cy]) =>
      el(gw, "circle", { cx, cy, r: 14, fill: "none", stroke: PH_DIM,
        "stroke-width": 1.3, "stroke-dasharray": "4 3" }));
    const team = el(ghost, "g", {});
    const gLegs = [];
    [[300, 0], [220, 1]].forEach(([bx, k]) => {
      const g = el(team, "g", { transform: `translate(${bx} 184)` });
      el(g, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.4,
        "stroke-dasharray": "5 4",
        d: "M -34 0 Q -38 -24 -18 -32 Q 8 -40 26 -30 Q 38 -22 36 0" });
      el(g, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.3,
        "stroke-dasharray": "5 4",
        d: "M -34 -26 Q -46 -26 -52 -14 Q -58 -12 -60 -6" });
      el(g, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.2,
        d: "M -46 -24 Q -54 -32 -50 -38 M -42 -24 Q -36 -34 -28 -34" });
      [0, 1, 2, 3].forEach(i => gLegs.push([g, i, k]));
    });
    const legEls = gLegs.map(([g]) => el(g, "line",
      { stroke: PH_DIM, "stroke-width": 1.2, "stroke-dasharray": "3 2" }));
    el(ghost, "line", { x1: 336, y1: 176, x2: 370, y2: 172, stroke: PH_DIM,
      "stroke-dasharray": "3 3" });                          // the ghost tongue
    const shimmer = Array.from({ length: 2 }, (_, i) => el(svg, "path",
      { fill: "none", stroke: PH_DIM, opacity: .3 }));
    const motto = label(svg, 320, 120, 13, PH_BRIGHT); motto.setAttribute("text-anchor", "middle");
    const foot = label(svg, 320, 340, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE ZOXEN, IN LIFE", T, 4, 1.4);
      // the mirage breathes: strongest between the gusts
      const breath = .25 + Math.max(0, Math.sin(t * .12)) * .6;
      ghost.setAttribute("opacity", breath);
      legEls.forEach((L, j) => {
        const [g, i] = [gLegs[j][0], gLegs[j][1]];
        const sw = ((t + i + gLegs[j][2]) % 4) < 2 ? 5 : -5; // marching in place
        L.setAttribute("x1", -26 + i * 18); L.setAttribute("y1", 0);
        L.setAttribute("x2", -26 + i * 18 + sw); L.setAttribute("y2", 22);
      });
      shimmer.forEach((n, i) => {
        const y = 216 + i * 12, ph2 = t * .5 + i * 2;
        n.setAttribute("d", `M 140 ${y} q 30 ${Math.sin(ph2) * 4} 60 0 ` +
          `q 30 ${Math.sin(ph2 + 1) * 4} 60 0 q 30 ${Math.sin(ph2 + 2) * 4} 60 0 ` +
          `q 30 ${Math.sin(ph2 + 3) * 4} 60 0`);
      });
      // the proverb arrives whole; the proof is typed out below
      motto.textContent = T > 20
        ? "THE ROAD TO GNOMON IS WALKED ONLY BY THE DESPERATE." : "";
      typeOn(foot, "LAST NIGHT, THIS WAS PROVEN AGAIN.", T, 110, 1.6);
    });
  });

  /* ---------------- 36-B: the zoxen -- butchery, annotated ---------------- */
  FIG._define("zoxen-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "ZOXEN / TWO CUTS BEFORE THE SAND";
    el(svg, "line", { x1: 0, y1: 288, x2: 640, y2: 288, stroke: PH, "stroke-width": 1.4 });
    const grain = stipple(svg, "dots-zoxen-b", PH, .7);
    // the wagon, small, stage right
    const wg = el(svg, "g", { transform: "translate(544 288) rotate(-9) scale(.7)" });
    el(wg, "line", { x1: -80, y1: -22, x2: 84, y2: -22, stroke: PH_DIM, "stroke-width": 1.6 });
    [-64, -22, 20, 62].forEach(x =>
      el(wg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.4,
        d: `M ${x} -22 Q ${x + 21} -74 ${x + 42} -22` }));
    [[-52, -6], [52, -6]].forEach(([cx, cy]) =>
      el(wg, "circle", { cx, cy, r: 16, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 }));
    // the subject pair, half-buried; the near one keeps its flank offered
    const zr = el(svg, "g", { transform: "translate(240 288) scale(1.35)" });
    el(zr, "path", { fill: "none", stroke: PH, "stroke-width": 1.5,
      d: "M -54 0 Q -58 -26 -40 -38 Q -12 -50 16 -42 Q 42 -34 46 -12 Q 47 -4 42 0" });
    el(zr, "path", { fill: "none", stroke: PH, "stroke-width": 1.3,
      d: "M -40 -36 Q -56 -34 -62 -22 Q -74 -20 -78 -12 Q -78 -4 -68 -4 Q -60 -4 -58 -10" });
    el(zr, "circle", { cx: -64, cy: -16, r: 1.6, fill: PH_BRIGHT });
    el(zr, "path", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.3,
      d: "M -60 -26 Q -72 -34 -68 -44" });
    el(zr, "path", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.3,
      d: "M -54 -26 Q -46 -38 -36 -40" });
    const zf = el(svg, "g", { transform: "translate(430 288)" });
    el(zf, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.5,
      d: "M -46 0 Q -50 -20 -28 -28 Q 2 -36 28 -28 Q 44 -20 46 0" });
    el(zf, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.3,
      d: "M -62 -8 Q -68 -20 -60 -26" });
    // the sand, holding both
    el(svg, "polygon", { fill: grain, "fill-opacity": .75, points:
      "150,288 340,288 322,270 258,262 190,270 160,280" });
    el(svg, "polygon", { fill: grain, "fill-opacity": .75, points:
      "372,288 490,288 478,276 430,272 388,278" });
    // the annotations, on what the sand has not claimed
    const cutH = el(svg, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.4,
      "stroke-dasharray": "5 4", d: "M 258 234 Q 276 252 270 276", opacity: 0 });
    const cutB = el(svg, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.4,
      "stroke-dasharray": "5 4", d: "M 202 236 Q 210 254 206 274", opacity: 0 });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3",
      points: "268,252 360,140 368,140" });
    label(svg, 372, 144, 10, PH).textContent = "HAUNCH (TRAIL FOOD)";
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3",
      points: "206,252 120,120 128,120" });
    label(svg, 132, 124, 10, PH).textContent = "BLOOD (2 DOSES, WARM)";
    const haunch = el(svg, "g", { opacity: 0 });
    el(haunch, "path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.5,
      d: "M 260 240 Q 282 254 274 278 Q 258 286 248 272 Q 246 252 260 240 Z" });
    const drops = Array.from({ length: 2 }, () => el(svg, "circle",
      { r: 1.8, fill: FUNGUS, opacity: 0 }));
    const scent = Array.from({ length: 3 }, () => el(svg, "path",
      { fill: "none", stroke: FUNGUS, "stroke-width": 1, opacity: 0 }));
    const ear = el(svg, "g", { opacity: 0 });
    el(ear, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "614,180 604,152 624,166" });
    label(svg, 540, 202, 9, PH_DIM).textContent = "DOWNWIND:";
    const who = label(svg, 540, 216, 9, FUNGUS);
    const foot = label(svg, 320, 340, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 180;
      doWipe(T);
      typeOn(hdr, "BUTCHERY, ANNOTATED", T, 4, 1.4);
      cutB.setAttribute("opacity", T > 24 ? (T < 34 ? t % 2 : 1) : 0);
      cutH.setAttribute("opacity", T > 40 ? (T < 50 ? t % 2 : 1) : 0);
      const off = Math.min(30, Math.max(0, (T - 56) * 1.5));
      haunch.setAttribute("transform", `translate(${off * 1.4} ${-off * .5})`);
      haunch.setAttribute("opacity", T > 56 ? 1 : 0);
      drops.forEach((n, i) => {
        n.setAttribute("cx", 206 + i * 4);
        n.setAttribute("cy", 256 + ((t * 3 + i * 12) % 30));
        n.setAttribute("opacity", T > 30 ? .8 : 0);
      });
      scent.forEach((n, i) => {
        const q = ((t * 2 + i * 10) % 30) / 30;
        const sx = 270 + q * 300, sy = 236 - q * 40 - i * 8;
        n.setAttribute("d", `M ${sx} ${sy} q 6 -5 12 0 q 6 5 12 0`);
        n.setAttribute("opacity", T > 60 ? Math.max(0, .8 - q * .6) : 0);
      });
      ear.setAttribute("opacity", T > 84 ? 1 : 0);
      ear.setAttribute("transform", (t % 14) < 2 && T > 84 ? "translate(0 -3)" : "");
      who.textContent = T > 90 ? "EVERYTHING." : "";
      typeOn(foot, "FOOD, HONESTLY -- AND ANYTHING WITH A NOSE WILL KNOW.", T, 120, 1.9);
    });
  });

  /* ---- memFrame: the memory-playback frame (the 41-45 series, CCB) ----
     A crystal facet set in the Hall of Memory's chosen tiling: the facet's
     own shape tessellated fine across the dark (it tiles true, with
     v1=(0,216), v2=(360,108)), banks waking as a diagonal wavefront sweeps
     through. Everything remembered inside is drawn in solid fills that
     breathe like the zoxen mirage; anything that still exists today is
     brightest; wear is notched into the lower edge. ---- */
  function memFrame(svg, clsText, wear) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = clsText;
    const HEXP = (cx, cy, k) => [[-210, 0], [-150, -108], [150, -108], [210, 0],
      [150, 108], [-150, 108]].map(([px, py]) =>
      `${cx + px * k},${cy + py * k}`).join(" ");
    const inside = (dx, dy, pad) => Math.abs(dy) <= 108 + pad &&
      Math.abs(dx) <= 210 + pad - 60 * Math.max(0, Math.abs(dy) - pad) / 108;
    const cells = [], K = .15;
    for (let i = -9; i <= 9; i++) for (let j = -14; j <= 14; j++) {
      const cx = 320 + i * 360 * K, cy = 196 + (i * 108 + j * 216) * K;
      if (cy < 52 || cy > 322 || cx < -30 || cx > 670) continue;
      if (inside(cx - 320, cy - 196, 14)) continue;
      const base = .05 + ((i * 7 + j * 13 + 200) % 5) * .016;
      cells.push({ base, cx, cy, q: el(svg, "polygon",
        { points: HEXP(cx, cy, K * .9), fill: PH, "fill-opacity": base }) });
    }
    el(svg, "polygon", { points: "110,196 170,88 470,88 530,196 470,304 170,304",
      fill: PH, "fill-opacity": .08, stroke: PH_BRIGHT, "stroke-width": 1.5 });
    el(svg, "polygon", { points: "122,196 176,98 464,98 518,196 464,294 176,294",
      fill: PH, "fill-opacity": .05, stroke: PH_DIM, opacity: .5 });
    for (let w = 0; w < wear; w++)                             // the wear, notched
      el(svg, "line", { x1: 184 + w * 9, y1: 300,
        x2: 184 + w * 9, y2: w % 4 === 2 ? 312 : 308, stroke: PH_DIM, opacity: .85 });
    const glint = el(svg, "circle", { r: 2, fill: PH_BRIGHT, opacity: 0 });
    const ghost = el(svg, "g", {});                            // the memory itself
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const MCORN = [[110, 196], [170, 88], [470, 88], [530, 196], [470, 304], [170, 304]];
    return { hdr, ghost, foot, tick: (t) => {
      const front = ((t * 4) % 1000) - 30;                     // the wavefront
      cells.forEach(c2 => {
        const d = Math.abs(c2.cx + c2.cy - front);
        c2.q.setAttribute("fill-opacity",
          d < 44 ? c2.base + .15 * (1 - d / 44) : c2.base);
      });
      const c = MCORN[Math.floor(t / 22) % 6];
      glint.setAttribute("cx", c[0]); glint.setAttribute("cy", c[1]);
      glint.setAttribute("opacity", (t % 22) < 3 ? .9 : 0);
      ghost.setAttribute("opacity", .35 + Math.max(0, Math.sin(t * .1)) * .55);
    } };
  }

  /* ---------------- 41: remember -- his mother ---------------- */
  FIG._define("mem-mother", "svg", function (svg) {
    const F = memFrame(svg, "HALL OF MEMORY / WEAR: NEARLY THROUGH", 13);
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    // the light behind them, breathing
    const glow = [105, 70, 40].map((r, i) => el(F.ghost, "circle",
      { cx: 330, cy: 182, r, fill: PH, "fill-opacity": [.04, .07, .11][i] }));
    // the mother, a dark shape leaning in from the upper left
    el(F.ghost, "path", { fill: I1, d:
      "M 226 170 Q 216 114 268 102 Q 306 98 318 128 L 331 159 L 322 180 L 324 192 " +
      "Q 314 200 300 198 Q 262 198 226 170 Z" });
    el(F.ghost, "path", { fill: I1, d:
      "M 226 168 Q 212 202 220 244 Q 240 258 258 248 Q 236 220 240 190 Z" });  // her hair
    el(F.ghost, "path", { d:
      "M 316 126 Q 326 142 331 157 Q 324 165 327 171 Q 320 176 324 182 Q 322 188 312 195",
      fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.8 }); // the lit edge: brow,
    el(F.ghost, "circle", { cx: 314, cy: 148, r: 1.6, fill: BG });  // nose, lips -- and
    el(F.ghost, "path", { d: "M 306 148 Q 312 152 318 150", fill: "none",
      stroke: BG, "stroke-width": 1.4 });                      // her closed eye
    // the child, looking up out of the glow
    el(F.ghost, "circle", { cx: 356, cy: 206, r: 22, fill: I3 });
    el(F.ghost, "path", { d: "M 340 190 Q 352 183 366 191", fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.6 });               // the lit brow
    el(F.ghost, "circle", { cx: 345, cy: 203, r: 2, fill: BG });   // the open eye,
    el(F.ghost, "path", { d: "M 340 197 Q 345 194 350 197", fill: "none",
      stroke: BG, "stroke-width": 1.4 });                      // watching her
    el(F.ghost, "path", { d: "M 364 200 Q 370 206 364 212", fill: "none",
      stroke: BG, "stroke-width": 1.4 });                      // the ear
    el(F.ghost, "path", { fill: I2, d:
      "M 338 224 Q 314 234 312 256 Q 330 274 362 270 Q 390 260 386 234 Q 378 222 360 220 Z" });
    // THE HAND -- four fingers following the curve of the small head
    const hand = el(F.ghost, "g", {});
    el(hand, "path", { d: "M 26 12 Q 48 30 62 54", fill: "none", stroke: I2,
      "stroke-width": 9, "stroke-linecap": "round" });         // the forearm
    el(hand, "path", { fill: I4, d:
      "M 14 -8 Q 27 -7 28 4 Q 27 16 16 15 Q 20 4 14 -8 Z" }); // the back of the hand
    ["M 18 -6 Q 0 -9 -6 -4", "M 19 0 Q 0 -2 -7 3",
     "M 19 6 Q 1 5 -6 10", "M 18 12 Q 3 12 -3 16"].forEach(d =>
      el(hand, "path", { d, fill: "none", stroke: I4, "stroke-width": 4.2,
        "stroke-linecap": "round" }));                         // the fingers, cupping
    el(hand, "path", { d: "M 24 14 Q 20 22 11 24", fill: "none", stroke: I4,
      "stroke-width": 4.6, "stroke-linecap": "round" });       // the thumb, beneath
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(F.hdr, "REMEMBER: HIS MOTHER", T, 4, 1.4);
      F.tick(t);
      glow.forEach((g2, i) => g2.setAttribute("fill-opacity",
        [.04, .07, .11][i] * (.7 + (Math.floor(t / 5) % 3) * .2)));
      const HOME = [372, 210], AWAY = [400, 234];             // a short, gentle settle
      let hx = AWAY[0], hy = AWAY[1], on = 1;
      if (T < 12) { on = 0; }
      else if (T < 40) { const k = (T - 12) / 28;
        hx = AWAY[0] + Math.round((HOME[0] - AWAY[0]) * k / 2) * 2;
        hy = AWAY[1] + Math.round((HOME[1] - AWAY[1]) * k / 2) * 2; }
      else if (T < 104) { hx = HOME[0]; hy = HOME[1] + (T >= 60 && T < 74 ? 2 : 0); }
      else if (T < 128) { const k = (T - 104) / 24;
        hx = HOME[0] + Math.round((AWAY[0] - HOME[0]) * k / 2) * 2;
        hy = HOME[1] + Math.round((AWAY[1] - HOME[1]) * k / 2) * 2; }
      else on = 0;
      hand.setAttribute("transform", `translate(${hx} ${hy})`);
      hand.setAttribute("opacity", on);
      typeOn(F.foot, "THE MOST CONSULTED BANK IN THE LATTICE.", T, 110, 1.5);
    });
  });

  /* ---------------- 42: remember -- the bath ---------------- */
  FIG._define("mem-bath", "svg", function (svg) {
    const F = memFrame(svg, "HALL OF MEMORY / WEAR: HEAVY", 9);
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    // the tub, a filled vessel
    el(F.ghost, "path", { fill: I2, d:
      "M 210 216 L 430 216 Q 434 264 390 274 L 250 274 Q 206 264 210 216 Z" });
    el(F.ghost, "path", { fill: I3, d:
      "M 218 216 L 422 216 L 419 229 Q 320 240 221 229 Z" });  // the warm water
    // clawfoot feet, with some pride in them: a scroll, a ball, three claws
    [[248, 274, -1], [392, 274, 1]].forEach(([fx, fy, dir]) => {
      el(F.ghost, "path", { fill: "none", stroke: I2, "stroke-width": 3,
        "stroke-linecap": "round",
        d: `M ${fx} ${fy} Q ${fx - 6 * dir} ${fy + 8} ${fx - 2 * dir} ${fy + 14} ` +
           `Q ${fx + 2 * dir} ${fy + 19} ${fx + 7 * dir} ${fy + 15}` });
      el(F.ghost, "circle", { cx: fx + 5 * dir, cy: fy + 17, r: 3, fill: I3 });
      [[3, 0], [6, 2], [9, 5]].forEach(([dx, dy]) =>
        el(F.ghost, "line", { x1: fx + (dx + 1) * dir, y1: fy + 13 + dy,
          x2: fx + (dx + 4) * dir, y2: fy + 17 + dy, stroke: I2,
          "stroke-width": 1.6 }));
    });
    // the king, water to the chin
    el(F.ghost, "circle", { cx: 320, cy: 198, r: 16, fill: I4 });
    el(F.ghost, "path", { d: "M 310 196 Q 314 199 318 197", fill: "none",
      stroke: BG, "stroke-width": 1.6 });                      // closed eyes
    el(F.ghost, "path", { d: "M 322 196 Q 326 199 330 197", fill: "none",
      stroke: BG, "stroke-width": 1.6 });
    el(F.ghost, "path", { d: "M 306 190 Q 318 180 336 190 L 332 184 Q 320 176 308 184 Z",
      fill: I2 });                                             // wet hair
    // warmth, ringing off him on the step clock
    const rings = Array.from({ length: 3 }, () =>
      el(F.ghost, "ellipse", { cx: 320, cy: 216, fill: "none", stroke: I4,
        "stroke-width": 1.6 }));
    // steam, in solid slow ribbons, beside his head
    const steam = Array.from({ length: 3 }, () =>
      el(F.ghost, "polyline", { fill: "none", stroke: I2, "stroke-width": 2.5,
        "stroke-linecap": "round", opacity: .5 }));
    // the one solid thing: the drop, and where it lands
    const drop = el(svg, "circle", { r: 2, fill: PH_BRIGHT, opacity: 0 });
    const splash = el(svg, "circle", { cx: 330, cy: 215, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.2, opacity: 0 });
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(F.hdr, "REMEMBER: THE BATH", T, 4, 1.4);
      F.tick(t);
      rings.forEach((n, i) => {
        const k = (t * 2 + i * 20) % 60;
        n.setAttribute("rx", 20 + k); n.setAttribute("ry", 3 + k * .14);
        n.setAttribute("opacity", Math.max(0, .7 - k / 60));
      });
      steam.forEach((s, i) => {
        const x0 = [250, 286, 392][i], up = (t * 2 + i * 17) % 36;
        s.setAttribute("points", Array.from({ length: 4 }, (_, q) =>
          `${x0 + Math.sin(t * .18 + q + i * 2) * 5},${206 - up - q * 12}`).join(" "));
        s.setAttribute("opacity", .5 - up / 100);
      });
      const D = t % 34;                                       // the weeping, kept
      if (D < 6) {
        drop.setAttribute("cx", 328 + D * .4); drop.setAttribute("cy", 203 + D * 2);
        drop.setAttribute("opacity", 1);
        splash.setAttribute("opacity", 0);
      } else if (D < 14) {
        drop.setAttribute("opacity", 0);
        splash.setAttribute("r", 2 + (D - 6) * 1.4);
        splash.setAttribute("opacity", .8 - (D - 6) * .1);
      } else { drop.setAttribute("opacity", 0); splash.setAttribute("opacity", 0); }
      typeOn(F.foot, "THE CRYSTAL KEEPS THE WEEPING WITH THE WARMTH.", T, 106, 1.5);
    });
  });

  /* ---------------- 43: remember -- the kestrel ---------------- */
  FIG._define("mem-kestrel", "svg", function (svg) {
    const F = memFrame(svg, "HALL OF MEMORY / WEAR: WORN SMOOTH", 7);
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    // the old king in profile, dropped low so the cast stays in-crystal
    el(F.ghost, "path", { fill: I1, d:
      "M 176 202 Q 166 240 158 296 L 250 296 Q 240 260 226 232 Q 214 208 196 200 Z" });
    el(F.ghost, "circle", { cx: 190, cy: 184, r: 17, fill: I2 });   // his head
    el(F.ghost, "path", { fill: I2, d: "M 204 176 L 215 185 L 204 191 Z" });  // the profile
    el(F.ghost, "path", { fill: I1, d:
      "M 198 194 Q 207 208 196 213 Q 187 206 190 196 Z" });    // the beard
    el(F.ghost, "path", { d: "M 176 174 Q 186 164 200 168", fill: "none",
      stroke: I1, "stroke-width": 3, "stroke-linecap": "round" });  // what hair is left
    const armG = el(F.ghost, "g", {});                         // the casting arm
    el(armG, "path", { d: "M 210 228 Q 250 242 284 252", fill: "none",
      stroke: I2, "stroke-width": 13, "stroke-linecap": "round" });  // the arm, held out
    el(armG, "path", { d: "M 270 248 Q 296 256 320 258", fill: "none",
      stroke: I3, "stroke-width": 16, "stroke-linecap": "round" });  // the gauntlet
    el(armG, "path", { d: "M 264 236 L 272 262", fill: "none",
      stroke: I3, "stroke-width": 6, "stroke-linecap": "round" });   // its flared cuff
    el(armG, "circle", { cx: 328, cy: 258, r: 9, fill: I3 });        // the fist
    el(armG, "path", { d: "M 330 267 Q 336 280 328 290", fill: "none",
      stroke: I1, "stroke-width": 2 });                              // the jesses
    el(F.ghost, "path", { d: "M 176 236 Q 172 244 178 250", fill: "none",
      stroke: I1, "stroke-width": 2 });                        // sleeve folds
    el(F.ghost, "path", { d: "M 196 234 Q 192 242 198 248", fill: "none",
      stroke: I1, "stroke-width": 2 });
    // the kestrel, arriving with everything spread
    const bird = el(F.ghost, "g", {});
    const mkWing = (mir) => {
      const g = el(bird, "g", {});
      const M = (x) => mir ? 12 - x : x;
      el(g, "path", { fill: I3, d:
        `M ${M(-4)} -34 L ${M(-56)} -58 L ${M(-74)} -50 L ${M(-48)} -28 ` +
        `Q ${M(-20)} -22 ${M(-4)} -26 Z` });
      [[-56, -58, -84, -66], [-59, -54, -88, -56], [-61, -49, -88, -45],
       [-62, -44, -84, -36]].forEach(([x1, y1, x2, y2]) =>
        el(g, "line", { x1: M(x1), y1, x2: M(x2), y2, stroke: I3,
          "stroke-width": 3, "stroke-linecap": "round" }));    // the fingered tips
      [[-40, -30, -46, -16], [-28, -27, -32, -13], [-16, -25, -18, -11]]
        .forEach(([x1, y1, x2, y2]) =>
        el(g, "line", { x1: M(x1), y1, x2: M(x2), y2, stroke: I2,
          "stroke-width": 2.5, "stroke-linecap": "round" }));  // the secondaries
      return g;
    };
    const wingL = mkWing(false), wingR = mkWing(true);
    const folded = el(bird, "path", { fill: "none", stroke: I3, "stroke-width": 3,
      "stroke-linecap": "round", opacity: 0,
      d: "M -8 -30 Q 6 -36 18 -26 M -6 -24 Q 6 -30 16 -21" }); // wings, put away
    el(bird, "path", { d: "M -2 0 L -2 -12 M 6 0 L 6 -12", fill: "none",
      stroke: I2, "stroke-width": 2.5 });                      // the legs, reaching
    el(bird, "path", { fill: I4, d:
      "M -12 -14 Q -16 -34 2 -40 Q 20 -38 20 -20 Q 18 -10 4 -8 Q -8 -8 -12 -14 Z" });
    el(bird, "circle", { cx: 8, cy: -46, r: 8, fill: I4 });    // the head
    el(bird, "path", { d: "M 15 -48 L 21 -45", fill: "none", stroke: I3,
      "stroke-width": 2.5, "stroke-linecap": "round" });       // the beak
    el(bird, "circle", { cx: 10, cy: -48, r: 1.2, fill: BG }); // the eye
    el(bird, "path", { d: "M 0 -9 L -11 13 M 3 -9 L -3 17 M 6 -9 L 7 18 M 9 -9 L 13 14",
      fill: "none", stroke: I2, "stroke-width": 3,
      "stroke-linecap": "round" });                            // the fanned tail
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 180;
      doWipe(T);
      typeOn(F.hdr, "REMEMBER: THE KESTREL", T, 4, 1.4);
      F.tick(t);
      const att = Math.floor(T / 45), A = T % 45;              // four tries a cycle
      const last = att === 3;
      const OFF = [410, 236];
      // the cast (CCB): no wobble -- the ARM lifts and throws the bird
      let lift = 0;
      if (!last) {
        if (A >= 18 && A < 26) lift = -Math.floor((A - 18) / 2) * 4 - 4;
        else if (A >= 26 && A < 32) lift = -16;
        else if (A >= 32 && A < 40) lift = -16 + (Math.floor((A - 32) / 2) + 1) * 4;
      }
      armG.setAttribute("transform", `rotate(${lift} 210 228)`);
      const rad = lift * Math.PI / 180;                        // the fist, mid-cast
      const px = 210 + 114 * Math.cos(rad) - 20 * Math.sin(rad);
      const py = 228 + 114 * Math.sin(rad) + 20 * Math.cos(rad);
      let bx, by, wings;
      if (A < 12) { const k = A / 12;                          // beating in
        bx = OFF[0] + Math.round((px - OFF[0]) * k / 2) * 2;
        by = OFF[1] + Math.round((py - OFF[1]) * k / 2) * 2;
        wings = "beat";
      } else if (A < 14) { bx = Math.round(px); by = Math.round(py);
        wings = "hold"; }                                      // the brake, all spread
      else if (last || A < 26) {                               // perched, riding the fist
        bx = Math.round(px / 2) * 2; by = Math.round(py / 2) * 2;
        wings = "fold";
      } else {                                                 // thrown -- and kept
        const k = Math.min(1, (A - 26) / 16);                  // inside the crystal
        bx = Math.round((325 + 91 * k) / 2) * 2;
        by = Math.round((216 - 32 * k - 20 * Math.sin(k * Math.PI)) / 2) * 2;
        wings = "beat";
      }
      bird.setAttribute("transform", `translate(${bx} ${by})`);
      if (wings === "fold") {                                  // put away, perched
        wingL.setAttribute("opacity", 0); wingR.setAttribute("opacity", 0);
        folded.setAttribute("opacity", 1);
      } else {
        folded.setAttribute("opacity", 0);
        wingL.setAttribute("opacity", 1); wingR.setAttribute("opacity", 1);
        const a = wings === "beat" ? ((t % 4) < 2 ? -14 : 16) : 0;
        wingL.setAttribute("transform", `rotate(${a} -4 -30)`);
        wingR.setAttribute("transform", `rotate(${-a} 16 -30)`);
      }
      typeOn(F.foot, "HE OUTLIVED EVERYONE WHO WOULD HAVE LAUGHED.", T, 136, 1.5);
    });
  });

  /* ---------------- 44: remember -- the raising ---------------- */
  FIG._define("mem-raising", "svg", function (svg) {
    const F = memFrame(svg, "HALL OF MEMORY / WEAR: LIGHT", 3);
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    const A1 = "#7b5c2e", A2 = "#a97f3e";
    el(F.ghost, "rect", { x: 162, y: 282, width: 316, height: 14, fill: I1 });
    // the bannermen, a frieze in profile
    const men = [];
    const flags = [];
    for (let i = 0; i < 5; i++) {
      const bx = 190 + i * 52;
      const g = el(F.ghost, "g", {});
      el(g, "path", { fill: i % 2 ? I2 : I3, d:
        `M ${bx - 13} 282 L ${bx - 9} 226 Q ${bx} 218 ${bx + 9} 226 L ${bx + 13} 282 Z` });
      el(g, "circle", { cx: bx + 3, cy: 210, r: 8, fill: I4 });
      if (i % 3 === 0)                                         // the hats disagree
        el(g, "polygon", { points: `${bx - 4},206 ${bx + 4},184 ${bx + 11},206`, fill: I2 });
      else if (i % 3 === 1)
        el(g, "rect", { x: bx - 5, y: 197, width: 17, height: 7, fill: I1 });
      else {
        el(g, "line", { x1: bx + 3, y1: 202, x2: bx + 1, y2: 184, stroke: I2,
          "stroke-width": 2.5 });
        el(g, "path", { d: `M ${bx + 1} 184 Q ${bx - 6} 180 ${bx - 9} 186`,
          fill: "none", stroke: A2, "stroke-width": 2 });      // the plume
      }
      const top = 124 + (i % 2) * 16;
      el(g, "line", { x1: bx + 17, y1: 282, x2: bx + 17, y2: top, stroke: I3,
        "stroke-width": 1.8 });
      flags.push({ q: el(g, "polygon", { fill: i % 2 ? A2 : A1 }), x: bx + 17,
        y: top, i });
      men.push(g);
    }
    // the young Autarch, and the staff that waits
    el(F.ghost, "path", { fill: I3, d:
      "M 440 282 L 444 224 Q 452 214 462 224 L 468 282 Z" });
    el(F.ghost, "path", { d: "M 442 276 L 466 276", stroke: A2, "stroke-width": 2,
      fill: "none" });                                         // the hem, trimmed in sand
    el(F.ghost, "circle", { cx: 449, cy: 206, r: 9, fill: I4 });
    el(F.ghost, "path", { fill: I4, d: "M 441 202 L 435 208 L 441 211 Z" });  // his profile
    [[452, 190], [458, 194]].forEach(([sx, sy]) => {
      el(F.ghost, "line", { x1: 451, y1: 198, x2: sx, y2: sy, stroke: I4,
        "stroke-width": 1.3 });
      el(F.ghost, "circle", { cx: sx, cy: sy, r: 1.6, fill: A2 });
    });
    el(F.ghost, "line", { x1: 428, y1: 282, x2: 428, y2: 208, stroke: A2,
      "stroke-width": 3 });                                    // the staff
    el(F.ghost, "circle", { cx: 428, cy: 203, r: 4, fill: A2 });
    el(F.ghost, "path", { d: "M 446 232 Q 440 234 436 233", fill: "none",
      stroke: I3, "stroke-width": 6, "stroke-linecap": "round" });  // his reaching arm
    const fist = el(F.ghost, "circle", { cx: 434, cy: 233, r: 5, fill: I4 });
    const grip = el(F.ghost, "circle", { cx: 440, cy: 238, r: 5, fill: I3, opacity: 0 });
    const vice = label(svg, 452, 156, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(F.hdr, "REMEMBER: THE RAISING", T, 4, 1.4);
      F.tick(t);
      men.forEach((g, i) => g.setAttribute("transform",
        `translate(0 ${((t + i * 3) % 6) < 3 ? 0 : -1})`));    // marching in place
      flags.forEach(f => {                                     // the banners ripple
        const fl = ((t + f.i * 2) % 6) < 3 ? 4 : -3;
        f.q.setAttribute("points",
          `${f.x},${f.y} ${f.x + 40},${f.y + 12 + fl} ${f.x},${f.y + 26}`);
      });
      const shake = T < 90 ? [2, -1, 1, -2][t % 4] : 0;        // too hard to take it
      fist.setAttribute("cx", 434 + shake);
      fist.setAttribute("cy", 233 + (shake ? [0, 1, -1, 0][t % 4] : 0));
      grip.setAttribute("opacity", T >= 90 ? 1 : 0);           // the other hand closes
      vice.textContent = T >= 92 && T < 148 ? "THE VICE." : "";
      typeOn(F.foot, "HIS HISTORIANS WOULD CALL IT THE VICE.", T, 110, 1.5);
    });
  });

  /* ---------------- 45: remember -- the embalming ---------------- */
  FIG._define("mem-embalm", "svg", function (svg) {
    const F = memFrame(svg, "HALL OF MEMORY / WEAR: STUDIED", 6);
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    const HEADS = ["BABOON", "HUMAN", "MANTIS", "FALCON", "JACKAL"];
    const jarAt = (x, y, kind, fill) => {
      el(F.ghost, "polygon", { points: `${x - 15},${y + 26} ${x + 15},${y + 26} ` +
        `${x + 11},${y} ${x - 11},${y}`, fill });
      el(F.ghost, "rect", { x: x - 12, y: y - 4, width: 24, height: 5, fill });
      el(F.ghost, "circle", { cx: x, cy: y - 13, r: 7, fill });
      if (kind === "BABOON") el(F.ghost, "path", { fill: "none", stroke: BG,
        "stroke-width": 1.4, d: `M ${x - 5} ${y - 12} Q ${x} ${y - 7} ${x + 5} ${y - 12}` });
      if (kind === "HUMAN") [[x - 2.5, y - 14], [x + 2.5, y - 14]].forEach(([ex, ey]) =>
        el(F.ghost, "circle", { cx: ex, cy: ey, r: 1, fill: BG }));
      if (kind === "MANTIS") [[-4, -26], [4, -26]].forEach(([dx, dy]) =>
        el(F.ghost, "line", { x1: x + dx * .4, y1: y - 18, x2: x + dx, y2: y + dy,
          stroke: fill, "stroke-width": 1.4 }));
      if (kind === "FALCON") el(F.ghost, "path", { fill: "none", stroke: BG,
        "stroke-width": 1.4, d: `M ${x + 3} ${y - 15} q 5 2 1 6` });
      if (kind === "JACKAL") [[-5, 0], [5, 0]].forEach(([dx]) =>
        el(F.ghost, "polygon", { points: `${x + dx - 3},${y - 18} ${x + dx},${y - 27} ` +
          `${x + dx + 3},${y - 18}`, fill }));
    };
    // the bier, and the old king supine
    el(F.ghost, "rect", { x: 196, y: 224, width: 244, height: 9, fill: I1 });
    [[212, 233], [424, 233]].forEach(([lx, ly]) => el(F.ghost, "line",
      { x1: lx, y1: ly, x2: lx, y2: ly + 18, stroke: I1, "stroke-width": 4 }));
    el(F.ghost, "circle", { cx: 216, cy: 210, r: 11, fill: I4 });   // his head
    el(F.ghost, "path", { fill: I3, d:
      "M 228 204 L 380 206 Q 420 208 430 216 L 430 222 L 228 222 Z" });
    el(F.ghost, "path", { fill: I3, d: "M 292 197 Q 304 192 314 198 L 312 205 L 294 205 Z" });
    // the organs, marked where they wait
    const OPOS = [[266, 213], [292, 213], [222, 206], [324, 214], [210, 203]];
    OPOS.forEach(([ox, oy]) => el(F.ghost, "circle", { cx: ox, cy: oy, r: 2.6, fill: I4 }));
    // the five jars, ranked -- each tagged with what it takes (CCB: the
    // organ in place of the number), per the lattice's canon order
    const ORGANS = ["LUNGS", "LIVER", "EYES", "INTESTINES", "BRAIN"];
    const JX = [184, 252, 320, 388, 456];
    JX.forEach((jx, i) => jarAt(jx, 262, HEADS[i], I2));
    const tags = JX.map(jx => { const n = label(svg, jx, 302, 7.5, FUNGUS);
      n.setAttribute("text-anchor", "middle"); return n; });
    // the boy, small, watching
    el(F.ghost, "circle", { cx: 158, cy: 276, r: 8, fill: I2 });
    el(F.ghost, "path", { fill: I2, d: "M 146 296 Q 148 284 158 283 Q 168 284 170 296 Z" });
    const payload = el(svg, "circle", { r: 3, fill: PH_BRIGHT, opacity: 0 });
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(F.hdr, "REMEMBER: THE EMBALMING", T, 4, 1.4);
      F.tick(t);
      const step = Math.floor((T - 24) / 30), f = ((T - 24) % 30) / 30;
      if (step >= 0 && step < 5 && f < .6) {                   // the payload, arcing
        const k = f / .6;
        const [ox, oy] = OPOS[step], jx = JX[step];
        payload.setAttribute("cx", ox + (jx - ox) * k);
        payload.setAttribute("cy", oy + (246 - oy) * k - Math.sin(k * Math.PI) * 34);
        payload.setAttribute("opacity", 1);
      } else payload.setAttribute("opacity", 0);
      tags.forEach((n, i) => { n.textContent =
        (step > i || (step === i && f >= .6)) && T >= 24 ? ORGANS[i] : ""; });
      typeOn(F.foot, "HIS FATHER'S INNARDS FORETOLD HIS FATE.", T, 162, 1.9);
    });
  });

  /* ---------------- 46: the statues, by touch ---------------- */
  FIG._define("youth-a", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF YOUTH / PITCH DARK / TOUCH";
    const GLASS = "#cfefff";
    // the ceiling, heard not seen
    const seethe = Array.from({ length: 30 }, (_, i) => el(svg, "polyline",
      { fill: "none", stroke: PH_DIM, "stroke-width": 1, opacity: .12,
        points: `${14 + i * 21},52 ${20 + i * 21},46 ${26 + i * 21},52` }));
    const ell2 = (cx2, cy2, rx2, ry2, n) => Array.from({ length: n + 1 }, (_, i) => {
      const a = -Math.PI / 2 + i * 2 * Math.PI / n;
      return [cx2 + Math.cos(a) * rx2, cy2 + Math.sin(a) * ry2];
    });
    const STAT = [
      { paths: [ell2(150, 262, 46, 28, 22),
          [[116, 250], [150, 240], [184, 250]],
          [[112, 264], [150, 254], [188, 264]],
          [[120, 278], [150, 270], [180, 278]],
          ell2(150, 226, 13, 12, 12)],
        lx: 150, s: "AN INFANT." },
      { paths: [[[296, 306], [298, 240], [290, 232], [292, 212], [302, 200],
          [318, 196], [334, 200], [344, 212], [346, 232], [338, 240], [340, 306]],
          [[298, 252], [284, 268], [286, 276]],
          [[338, 252], [352, 268], [350, 276]]],
        lx: 318, s: "A BOY." },
      { paths: [[[452, 306], [456, 214], [446, 204], [448, 186], [460, 174],
          [478, 170], [494, 176], [502, 190], [500, 206], [490, 214], [494, 306]],
          [[456, 226], [438, 202], [428, 172], [434, 166]],
          [[494, 228], [510, 244], [512, 260]]],
        lx: 476, s: "LARGER THAN LIFE." },
    ];
    const strokes = [];
    STAT.forEach((st, si) => st.paths.forEach(pts =>
      strokes.push({ si, pts, q: el(svg, "polyline",
        { fill: "none", stroke: PH, "stroke-width": 1.6, opacity: .85 }) })));
    const total = strokes.reduce((a, s2) => a + s2.pts.length, 0);
    const hand = el(svg, "g", { opacity: 0 });
    el(hand, "circle", { r: 4, fill: "none", stroke: GLASS, "stroke-width": 1.4 });
    [[-3, -6], [1, -7], [4, -5]].forEach(([dx, dy]) =>
      el(hand, "line", { x1: 0, y1: 0, x2: dx * 1.8, y2: dy * 1.8, stroke: GLASS,
        "stroke-width": 1.2 }));
    const names = STAT.map(st => { const n = label(svg, st.lx, 328, 10, FUNGUS);
      n.setAttribute("text-anchor", "middle"); return n; });
    const plinth = STAT.map(st => el(svg, "line", { x1: st.lx - 52, y1: 308,
      x2: st.lx + 52, y2: 308, stroke: PH_DIM, opacity: 0 }));
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "> FEEL STATUES", T, 4, 1.6);
      seethe.forEach((q, i) => q.setAttribute("opacity",
        .06 + ((t + i * 3) % 11 < 2 ? .1 : 0)));
      const reach = Math.max(0, (T - 14) * (total / 130));
      let acc = 0, hx = null, hy = null;
      strokes.forEach(s2 => {
        const kk = Math.max(0, Math.min(s2.pts.length, reach - acc));
        s2.q.setAttribute("points",
          s2.pts.slice(0, Math.ceil(kk)).map(p => p.join(",")).join(" "));
        if (kk > 0 && kk < s2.pts.length) {
          const p = s2.pts[Math.floor(kk)]; hx = p[0]; hy = p[1];
        }
        acc += s2.pts.length;
      });
      hand.setAttribute("opacity", hx !== null ? .9 : 0);
      if (hx !== null) hand.setAttribute("transform",
        `translate(${hx + 10} ${hy + 12}) rotate(-24)`);
      let upto = 0;
      STAT.forEach((st, si) => {
        upto += st.paths.reduce((a, p) => a + p.length, 0);
        const done = reach >= upto;
        names[si].textContent = done ? st.s : "";
        plinth[si].setAttribute("opacity", done ? .6 : 0);
      });
      typeOn(foot, "COLD, SMOOTH STONE. YOU CANNOT SEE A THING.", T, 152, 1.9);
    });
  });

  /* ---------------- 47: the adoration ---------------- */
  FIG._define("youth-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF YOUTH / LIT, FOR NOW";
    const GLASS = "#cfefff";
    const I1 = "#1b4055", I2 = "#25567a", I3 = "#33739c", I4 = "#4a97c6";
    el(svg, "line", { x1: 0, y1: 312, x2: 640, y2: 312, stroke: PH_DIM });
    const cone = el(svg, "polygon", { fill: PH, "fill-opacity": .07,
      points: "320,330 80,64 560,64" });
    const scene = el(svg, "g", {});
    [[150, 44], [320, 34], [478, 40]].forEach(([x, h]) => el(scene, "rect",
      { x: x - 44, y: 312 - h, width: 88, height: h, fill: I1, stroke: PH_DIM }));
    // the infant, swaddled
    el(scene, "ellipse", { cx: 150, cy: 246, rx: 40, ry: 24, fill: I3 });
    el(scene, "circle", { cx: 150, cy: 216, r: 12, fill: I3 });
    el(scene, "path", { fill: "none", stroke: GLASS, "stroke-width": 1.3,
      opacity: .9, d: "M 114 240 Q 150 228 186 240 M 118 252 Q 150 242 184 252" });
    // the child, palm raised
    el(scene, "path", { fill: I2, d: "M 296 278 L 298 216 Q 298 202 312 198 " +
      "L 328 198 Q 342 202 342 216 L 344 278 Z" });
    el(scene, "circle", { cx: 320, cy: 184, r: 13, fill: I2 });
    el(scene, "path", { fill: I2, d: "M 342 224 L 362 204 L 368 210 L 350 232 Z" });
    el(scene, "circle", { cx: 366, cy: 205, r: 5, fill: I4 });  // the palm, adored
    // the youth
    el(scene, "path", { fill: I3, d: "M 436 272 L 440 196 Q 440 180 456 176 " +
      "L 474 176 Q 490 180 490 196 L 494 272 Z" });
    el(scene, "circle", { cx: 465, cy: 162, r: 14, fill: I3 });
    el(scene, "path", { fill: "none", stroke: GLASS, "stroke-width": 1.3,
      opacity: .9, d: "M 472 150 Q 480 158 476 170" });         // the profile line
    const stone = el(svg, "circle", { cx: 320, cy: 330, r: 5, fill: PH_BRIGHT });
    const bats = Array.from({ length: 5 }, (_, i) => {
      const g = el(svg, "g", { opacity: 0 });
      el(g, "path", { fill: "#01070c", stroke: PH_DIM, "stroke-width": 1, d:
        "M -16 0 Q -8 -8 0 0 Q 8 -8 16 0 Q 8 4 0 2 Q -8 4 -16 0 Z" });
      return { g, ph: i * 37 };
    });
    const plq = [["THE INFANT", 150], ["THE CHILD", 320], ["THE YOUTH", 478]]
      .map(([s2, x], i) => { const n = label(svg, x, 304, 8, PH_DIM);
        n.setAttribute("text-anchor", "middle"); return { n, s2, t0: 22 + i * 16 }; });
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "THE ADORATION", T, 4, 1.4);
      let dim = 0;
      bats.forEach((b, i) => {
        const x = (t * (3.2 + (i % 3) * .8) + b.ph * 9) % 900 - 130;
        const y = 70 + (i % 3) * 26 + Math.sin((t + b.ph) * .2) * 8;
        b.g.setAttribute("opacity", x > -40 && x < 680 ? .95 : 0);
        const flap = Math.sin(t * .9 + i) * .5 + 1.1;
        b.g.setAttribute("transform", `translate(${x} ${y}) scale(1.3 ${flap})`);
        if (x > 240 && x < 400) dim = Math.max(dim, .5);
      });
      cone.setAttribute("fill-opacity", (.06 + Math.sin(t * .7) * .012) * (1 - dim));
      scene.setAttribute("opacity", 1 - dim * .5);
      stone.setAttribute("opacity", .7 + Math.sin(t * .8) * .3);
      plq.forEach(p2 => typeOn(p2.n, p2.s2, T, p2.t0, 2));
      typeOn(foot, "SWADDLED AND ADORED. THE VAULT ANSWERS THE GLOW.", T, 96, 1.9);
    });
  });

  /* ---------------- 48: the lesson ---------------- */
  FIG._define("youth-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF YOUTH / THE VAULT ANSWERS";
    const GLASS = "#cfefff";
    const ROOST = [];
    for (let r = 0; r < 3; r++) for (let c = 0; c < 13; c++)
      ROOST.push([44 + c * 44 + (r % 2) * 22, 52 + r * 15]);
    // you, and the stone held up
    el(svg, "circle", { cx: 148, cy: 296, r: 9, fill: PH_DIM });
    el(svg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 3,
      d: "M 148 305 L 148 336 M 148 314 L 176 288" });
    const cone = el(svg, "polygon", { fill: PH, "fill-opacity": 0,
      points: "180,284 60,80 430,80" });
    const stone = el(svg, "circle", { cx: 180, cy: 284, r: 5, fill: PH_BRIGHT });
    const bats = ROOST.map(([rx, ry], i) => {
      const q = el(svg, "polyline", { fill: "none", stroke: GLASS,
        "stroke-width": 1.4, opacity: .55 });
      return { q, rx, ry, i };
    });
    const cmd = label(svg, 24, 330, 10, GLASS);
    label(svg, 452, 350, 10, PH_DIM).textContent = "REGRET";
    const cells = Array.from({ length: 6 }, (_, i) => el(svg, "rect",
      { x: 516 + i * 16, y: 340, width: 12, height: 11, fill: GLASS,
        "fill-opacity": .08 }));
    const foot = label(svg, 624, 316, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 132;
      doWipe(T);
      typeOn(hdr, "THE LESSON", T, 4, 1.4);
      const lit = T >= 10;
      typeOn(cmd, "> LIGHT GLOWSTONE", T, 8, 2.4);
      cone.setAttribute("fill-opacity", lit ? .06 + Math.sin(t * .8) * .015 : 0);
      stone.setAttribute("opacity", lit ? 1 : .2);
      let closest = 1e9;
      bats.forEach(b => {
        const t0 = 18 + (b.i % 17) * 3;
        let x = b.rx, y = b.ry, spread = 5;
        if (T >= t0) {                                         // the descent
          const k = Math.min(1, (T - t0) / 30);
          const ang = T * .22 + b.i * 1.7;
          const rad = 150 - k * 105 + Math.sin(T * .3 + b.i) * 9;
          x = b.rx + (180 + Math.cos(ang) * rad - b.rx) * k;
          y = b.ry + (270 + Math.sin(ang) * rad * .55 - b.ry) * k;
          spread = 7;
        }
        const fl = Math.sin(t * 1.1 + b.i) * 3;
        b.q.setAttribute("points",
          `${x - spread},${y + fl * .4} ${x},${y - 3 - fl} ${x + spread},${y + fl * .4}`);
        const d2 = Math.hypot(x - 180, y - 284);
        if (d2 < closest) closest = d2;
      });
      const on = T < 10 ? 0
        : Math.min(6, Math.max(0, Math.round((190 - closest) / 28)));
      cells.forEach((r2, i) => r2.setAttribute("fill-opacity", i < on ? .8 : .08));
      typeOn(foot, "WHAT ROOSTS HERE HATES A LAMP WORSE THAN A SHOUT.", T, 64, 2);
    });
  });

  /* ---------------- 49: the manifest ---------------- */
  FIG._define("manifest", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE WAGON'S HOLD / PAPERWORK";
    const GLASS = "#cfefff";
    // the page
    el(svg, "rect", { x: 88, y: 52, width: 464, height: 274, fill: GLASS,
      "fill-opacity": .05, stroke: PH_DIM });
    for (let y = 108; y <= 300; y += 24)
      el(svg, "line", { x1: 104, y1: y, x2: 536, y2: y, stroke: PH_DIM, opacity: .25 });
    const title = label(svg, 320, 78, 10, PH); title.setAttribute("text-anchor", "middle");
    const sub = label(svg, 320, 94, 8, PH_DIM); sub.setAttribute("text-anchor", "middle");
    // saffron: a bound bale
    el(svg, "ellipse", { cx: 122, cy: 126, rx: 12, ry: 8, fill: "none",
      stroke: FUNGUS, "stroke-width": 1.5 });
    [-5, 0, 5].forEach(dx => el(svg, "line", { x1: 122 + dx, y1: 119,
      x2: 122 + dx, y2: 133, stroke: FUNGUS, opacity: .7 }));
    // dates: a cluster
    [[116, 176], [124, 172], [130, 178]].forEach(([x, y]) =>
      el(svg, "ellipse", { cx: x, cy: y, rx: 4.5, ry: 6, fill: "#b36b2a" }));
    // silk: a loose coil
    el(svg, "path", { d: "M 110 228 q 8 -12 16 0 q 8 12 16 0 q 6 -9 12 -2",
      fill: "none", stroke: GLASS, "stroke-width": 1.5, opacity: .8 });
    const rows = [
      ["SAFFRON, ONE BALE", "A SEASON'S WATER", 2, 130],
      ["DATES, ONE CRATE", "A MONTH OF MEALS", 2, 178],
      ["SPIDER-SILK, ONE BOLT", "LIGHT, AND KNOWS IT", 1, 226],
    ].map(([name, worth, slots, y], i) => {
      const n = label(svg, 148, y, 10, PH);
      const w = label(svg, 536, y, 9, PH_DIM); w.setAttribute("text-anchor", "end");
      el(svg, "line", { x1: 148, y1: y + 4, x2: 536, y2: y + 4, stroke: PH_DIM,
        "stroke-dasharray": "2 5", opacity: .5 });
      const boxes = Array.from({ length: 3 }, (_, b) => el(svg, "rect",
        { x: 148 + b * 13, y: y + 10, width: 9, height: 9, fill: PH,
          "fill-opacity": .06, stroke: PH_DIM }));
      return { n, w, name, worth, slots, boxes, t0: 30 + i * 26 };
    });
    label(svg, 148, 264, 8, PH_DIM).textContent =
      "SLOTS SHOWN ACTUAL SIZE. THE BALE KNOWS ITS WEIGHT.";
    // the stamp
    const stamp = el(svg, "g", { transform: "rotate(-11 320 296)", opacity: 0 });
    el(stamp, "rect", { x: 208, y: 278, width: 224, height: 30, fill: "none",
      stroke: "#ff5a5a", "stroke-width": 2 });
    const stx = label(stamp, 320, 298, 11, "#ff5a5a");
    stx.setAttribute("text-anchor", "middle");
    stx.textContent = "CONSIGNEE: THE SAND";
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE MANIFEST", T, 4, 1.4);
      typeOn(title, "MANIFEST -- FOR THE SOUKS OF GNOMON", T, 8, 2);
      typeOn(sub, "NINTH DAY. TOMORROW, GNOMON.", T, 22, 2);
      rows.forEach(r => {
        typeOn(r.n, r.name, T, r.t0, 2);
        typeOn(r.w, r.worth, T, r.t0 + 10, 2);
        r.boxes.forEach((b, i2) => b.setAttribute("fill-opacity",
          T > r.t0 + 14 + i2 * 3 && i2 < r.slots ? .7 : .06));
      });
      stamp.setAttribute("opacity", T > 118 ? (T < 122 ? (T % 2 ? 1 : .3) : .9) : 0);
      typeOn(foot, "THE CACKLEMAW DO NOT TRADE.", T, 132, 1.8);
    });
  });

  // the kennel kit (CCB: every dog its own dog) -- one body, parametric
  // head carriage, ears, tail set, gait, and build. Faces +x, ~70 x 59.
  const HEADS = {
    up:   { d: "Q 16 -25 19 -29 L 23 -31 Q 26 -32 28 -31 L 35 -28 " +
               "L 34 -25 L 25 -23 Q 20 -16 17 -9 ", eye: [31, -29], ear: [22, -31] },
    fwd:  { d: "Q 17 -23 22 -25 Q 28 -27 34 -26 L 38 -24 L 33 -21 " +
               "L 24 -19 Q 20 -14 17 -9 ", eye: [33, -24], ear: [25, -26] },
    down: { d: "Q 16 -21 21 -18 Q 27 -15 33 -12 L 36 -9 L 31 -6 " +
               "L 23 -10 Q 19 -10 17 -8 ", eye: [31, -10], ear: [21, -18] },
  };
  const TAILS = {
    droop: "Q -27 0 -30 8 Q -32 12 -34 11 Q -33 3 -29 -4 Q -26 -10 -24 -12 ",
    flag:  "L -28 -7 L -40 -11 L -40 -14 L -29 -11 L -24 -12 ",
    curl:  "Q -28 -6 -31 -11 Q -33 -17 -29 -20 Q -25 -21 -24 -17 " +
           "Q -27 -17 -27 -14 Q -26 -12 -24 -12 ",
  };
  const FORE = {
    stand:  "L 12 10 L 12 25 L 9 25 L 8 10 L 7 4 L 5 10 L 4 25 L 1 25 L 1 10 L 1 2 ",
    stride: "L 13 12 L 16 26 L 13 26 L 9 12 L 8 6 L 4 12 L 1 25 L -2 25 L 0 10 L 1 2 ",
    reach:  "L 14 8 L 22 22 L 19 24 L 10 12 L 8 6 L 2 14 L -4 24 L -7 22 L -2 10 L 1 2 ",
  };
  const HIND = {
    stand:  "L -13 2 L -14 12 L -15 24 L -18 24 L -17 10 L -18 2 " +
            "L -20 8 L -22 12 L -23 23 L -26 23 L -25 10 L -24 -4 ",
    stride: "L -14 2 L -12 12 L -18 24 L -21 24 L -16 10 L -18 2 " +
            "L -22 8 L -27 12 L -25 22 L -28 22 L -31 10 L -25 2 L -24 -4 ",
    reach:  "L -13 4 L -16 14 L -24 24 L -27 23 L -20 12 L -19 2 " +
            "L -23 6 L -28 14 L -34 22 L -36 20 L -30 10 L -26 0 L -24 -4 ",
  };
  function houndSil2(parent, o) {
    const g = el(parent, "g", {});
    const back = o.heavy ? "Q -12 -15 -2 -14 Q 8 -14 12 -18 "
                         : "Q -12 -17 -2 -16 Q 8 -16 12 -19 ";
    const chest = o.heavy ? "Q 15 -1 11 5 " : "Q 15 -2 10 4 ";
    const waist = o.heavy ? "Q -5 0 -12 -4 " : "Q -6 -4 -12 -6 ";
    const H = HEADS[o.head];
    const d = "M -24 -12 " + back + H.d + chest +
      FORE[o.gait] + waist + HIND[o.gait] + TAILS[o.tail] + "Z";
    el(g, "path", { d, fill: "#1b4055", stroke: "#9fd9f2", "stroke-width": 1.3 });
    if (o.ears) el(g, "polygon", { fill: "#1b4055", stroke: "#9fd9f2",
      "stroke-width": 1, points:
      `${H.ear[0]},${H.ear[1]} ${H.ear[0] - 3},${H.ear[1] - 8} ${H.ear[0] + 4},${H.ear[1] - 1}` });
    [-2, 3, 8].forEach(rx => el(g, "path", { fill: "none", stroke: "#9fd9f2",
      "stroke-width": 1, opacity: .8, d: `M ${rx} -14 q 4 8 1 20` }));
    [[-18, 12], [-27, 12]].forEach(([hx, hy]) =>
      el(g, "circle", { cx: hx, cy: hy, r: 1.4, fill: FUNGUS }));
    const eye = el(g, "circle", { cx: H.eye[0], cy: H.eye[1], r: 1.8, fill: "#ff5a5a" });
    return { g, eye };
  }
  const PACK = [
    { head: "up",   ears: 0, tail: "droop", gait: "stride" },
    { head: "fwd",  ears: 1, tail: "flag",  gait: "stand" },
    { head: "up",   ears: 1, tail: "curl",  gait: "stand", heavy: 1 },
    { head: "down", ears: 0, tail: "droop", gait: "stride" },
    { head: "fwd",  ears: 0, tail: "flag",  gait: "reach" },
    { head: "up",   ears: 0, tail: "flag",  gait: "stand", heavy: 1 },
    { head: "down", ears: 1, tail: "flag",  gait: "stand" },
    { head: "up",   ears: 1, tail: "droop", gait: "reach" },
    { head: "fwd",  ears: 1, tail: "curl",  gait: "stride" },
    { head: "down", ears: 0, tail: "curl",  gait: "stand" },
  ];

  /* ---------------- 50: the tank, in section ---------------- */
  FIG._define("tank", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF HOUNDS / IN SECTION";
    const GLASS = "#cfefff", HONEY = "#ffd76a";
    el(svg, "rect", { x: 140, y: 72, width: 380, height: 234, fill: "none",
      stroke: PH, "stroke-width": 2 });
    for (let y = 76; y < 306; y += 12) {
      el(svg, "line", { x1: 128, y1: y + 10, x2: 140, y2: y, stroke: PH_DIM,
        opacity: .5 });
      el(svg, "line", { x1: 520, y1: y, x2: 532, y2: y + 10, stroke: PH_DIM,
        opacity: .5 });
    }
    el(svg, "rect", { x: 142, y: 94, width: 376, height: 210, fill: HONEY,
      "fill-opacity": .09 });
    const meniscus = el(svg, "polyline", { fill: "none", stroke: HONEY,
      "stroke-width": 1.5, opacity: .7 });
    // crazing at the corners
    [[142, 304], [518, 304]].forEach(([cx2, cy2]) => [0, 1, 2].forEach(k =>
      el(svg, "line", { x1: cx2, y1: cy2,
        x2: cx2 + (cx2 < 300 ? 1 : -1) * (14 + k * 9), y2: cy2 - 8 - k * 7,
        stroke: GLASS, opacity: .5 })));
    // ten coursers, two ranks, mid-stride
    const hounds = [];
    for (let r = 0; r < 2; r++) for (let c = 0; c < 5; c++) {
      const { g, eye } = houndSil2(svg, PACK[r * 5 + c]);
      hounds.push({ g, eye, x: 196 + c * 68, y: 142 + r * 84, ph: (r * 5 + c) * 1.3 });
    }
    const bubbles = Array.from({ length: 8 }, (_, i) => ({ ph: i * 53,
      x: 160 + (i * 47) % 340,
      q: el(svg, "circle", { r: 1.5 + (i % 3), fill: "none", stroke: HONEY,
        opacity: .5 }) }));
    const callouts = [
      [214, 60, 222, 118, "LENSES: OPEN", 40],
      [438, 60, 438, 118, "GEL: OLD HONEY, LUMINOUS", 18],
      [196, 340, 152, 302, "PLEXIGLAS: CRAZED", 62],
      [452, 340, 452, 232, "HOUNDS: TEN (10)", 84],
    ].map(([tx2, ty2, px2, py2, s2, t0]) => {
      const L2 = el(svg, "line", { x1: tx2, y1: ty2 + (ty2 < 200 ? 4 : -12),
        x2: px2, y2: py2, stroke: PH_DIM, opacity: 0 });
      const n = label(svg, tx2, ty2, 9, PH); n.setAttribute("text-anchor", "middle");
      return { L2, n, s2, t0 };
    });
    const dwg = label(svg, 512, 296, 7, PH_DIM); dwg.setAttribute("text-anchor", "end");
    dwg.textContent = "DWG 7-K / KENNEL & BENCH JOINT WORKS";
    const foot = label(svg, 624, 354, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "THE TANK, IN SECTION", T, 4, 1.6);
      const mp = [];
      for (let x = 142; x <= 518; x += 20)
        mp.push(`${x},${94 + Math.sin(x * .05 + t * .12) * 2}`);
      meniscus.setAttribute("points", mp.join(" "));
      hounds.forEach(h => {
        h.g.setAttribute("transform",
          `translate(${h.x + Math.sin((t + h.ph * 9) * .04) * 2} ` +
          `${h.y + Math.sin((t + h.ph * 13) * .05) * 2.5}) scale(.85) ` +
          `rotate(${Math.sin((t + h.ph) * .03) * 3})`);
        h.eye.setAttribute("opacity", .6 + Math.sin(t * .1 + h.ph) * .4);
      });
      bubbles.forEach(b => {
        const k = (t * .9 + b.ph) % 210;
        b.q.setAttribute("cx", b.x + Math.sin(k * .08) * 4);
        b.q.setAttribute("cy", 300 - k);
        b.q.setAttribute("opacity", k > 190 ? 0 : .45);
      });
      callouts.forEach(c => {
        typeOn(c.n, c.s2, T, c.t0, 2);
        c.L2.setAttribute("opacity", T > c.t0 + 4 ? .7 : 0);
      });
      typeOn(foot, "PERFECTLY PRESERVED. THE LENSES ARE OPEN.", T, 110, 1.9);
    });
  });

  /* ---------------- 51: the flood ---------------- */
  FIG._define("flood", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF HOUNDS / ONE GOOD BLOW";
    const GLASS = "#cfefff", HONEY = "#ffd76a";
    el(svg, "line", { x1: 0, y1: 316, x2: 640, y2: 316, stroke: PH_DIM });
    const gel = el(svg, "rect", { x: 414, y: 82, width: 212, height: 232,
      fill: HONEY, "fill-opacity": .12 });
    const still = [[452, 140], [560, 128], [472, 224], [576, 236]].map(([x, y], i) => {
      const { g } = houndSil2(svg, PACK[[1, 0, 6, 7][i]]);
      return { g, x, y, ph: i * 2 };
    });
    el(svg, "rect", { x: 412, y: 80, width: 216, height: 236, fill: "none",
      stroke: GLASS, "stroke-width": 2.5 });                   // the frame keeps
    const face = el(svg, "g", {});
    const cracks = [];
    for (let r = 0; r < 8; r++) {
      const a = r * Math.PI / 4 + .3, len = 40 + (r % 3) * 26;
      const mx = 500 + Math.cos(a) * len * .5, my = 198 + Math.sin(a) * len * .5;
      const ex = 500 + Math.cos(a + .35) * len, ey = 198 + Math.sin(a + .35) * len;
      cracks.push(el(face, "line", { x1: 500, y1: 198, x2: mx, y2: my,
        stroke: GLASS, "stroke-width": 1.2, opacity: 0 }));
      cracks.push(el(face, "line", { x1: mx, y1: my, x2: ex, y2: ey,
        stroke: GLASS, "stroke-width": 1, opacity: 0 }));
    }
    const star = el(svg, "polygon", { fill: PH_BRIGHT, opacity: 0, points:
      "500,186 504,194 513,192 506,199 512,206 502,203 498,212 496,202 " +
      "486,204 494,196 488,189 497,193" });
    const crackTx = label(svg, 520, 182, 10, PH_BRIGHT);
    const wavePoly = el(svg, "polygon", { fill: HONEY, "fill-opacity": .16,
      opacity: 0 });
    const crest = el(svg, "polyline", { fill: "none", stroke: HONEY, opacity: 0,
      "stroke-width": 1.6 });
    const pool = el(svg, "rect", { x: 0, y: 300, width: 640, height: 16,
      fill: HONEY, "fill-opacity": 0 });
    const shards = Array.from({ length: 6 }, () => el(svg, "polygon",
      { fill: "none", stroke: GLASS, opacity: 0, points: "0,0 10,4 4,12" }));
    const tumb = Array.from({ length: 10 }, (_, i) => {
      const { g } = houndSil2(svg, PACK[i]);      // the WHOLE kennel washes out
      g.setAttribute("opacity", 0);
      return g;
    });
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "THE FLOOD", T, 4, 1.4);
      const pre = T < 54;
      face.setAttribute("opacity", pre ? 1 : 0);
      gel.setAttribute("fill-opacity", pre ? .12 : .02);
      const nshow = Math.max(0, (T - 30) * .8);
      cracks.forEach((c, i) => c.setAttribute("opacity",
        pre && i < nshow ? .9 : 0));
      star.setAttribute("opacity", T >= 30 && T < 38 ? (T % 2 ? 1 : .4) : 0);
      if (T >= 30 && T < 54) typeOn(crackTx, "CRACK.", T, 30, 2);
      else crackTx.textContent = "";
      still.forEach(s => {
        s.g.setAttribute("opacity", pre ? 1 : 0);
        s.g.setAttribute("transform",
          `translate(${s.x} ${s.y + Math.sin((t + s.ph * 7) * .05) * 2.5}) ` +
          `scale(.8) rotate(${Math.sin((t + s.ph) * .04) * 4})`);
      });
      const Tf = Math.min(T, 112);
      const fx = 620 - Math.max(0, Tf - 54) * 9.6;             // the front
      const flooding = T >= 54 && T < 112;
      wavePoly.setAttribute("opacity", flooding ? 1 : 0);
      crest.setAttribute("opacity", flooding ? .8 : 0);
      if (flooding) {
        const top = [];
        for (let x = 628; x >= fx; x -= 16) {
          const hump = 34 * Math.exp(-Math.pow((x - fx) / 70, 2));
          top.push(`${x},${294 - hump + Math.sin(x * .1 + t * .6) * 3}`);
        }
        top.push(`${fx},316`);
        wavePoly.setAttribute("points", `628,316 ${top.join(" ")}`);
        crest.setAttribute("points", top.join(" "));
      }
      pool.setAttribute("fill-opacity", T >= 112
        ? Math.min(.15, .10 + (T - 112) * .01) : (flooding ? .10 : 0));
      shards.forEach((s2, i) => {                           // glass, in the tank
        const k = T - 54;
        s2.setAttribute("opacity", flooding && k < 30 ? .8 : 0);
        s2.setAttribute("transform", `translate(${448 + i * 32} ` +
          `${Math.min(190 + i * 9 + k * 7, 306)}) rotate(${k * 30 + i * 60})`);
      });
      const REST = [64, 122, 180, 236, 292, 350, 408, 464, 522, 578];
      const ANG = [12, -165, 95, -8, 178, -95, 25, 142, -30, 78];
      tumb.forEach((g2, i) => {
        g2.setAttribute("opacity", T >= 54 ? 1 : 0);
        const settled = T >= 112;
        const x = Math.max(fx + 30 + i * 34, REST[i]);
        const y = settled ? 298 + (i % 3) * 4 : 292 + Math.sin(T * .5 + i * 2) * 4;
        const rot = settled ? ANG[i] : Math.min(T - 54, 58) * (22 + i * 7);
        g2.setAttribute("transform", `translate(${x} ${y}) scale(.7) rotate(${rot})`);
      });
      typeOn(foot, "THE KENNEL, DECANTED.", T, 126, 1.8);
    });
  });

  /* ---------------- 52: the tank, decanted ---------------- */
  FIG._define("tank-f", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF HOUNDS / AFTERMATH";
    const GLASS = "#cfefff", HONEY = "#ffd76a";
    el(svg, "line", { x1: 0, y1: 316, x2: 640, y2: 316, stroke: PH_DIM });
    el(svg, "rect", { x: 412, y: 80, width: 216, height: 236, fill: "none",
      stroke: GLASS, "stroke-width": 2.5, opacity: .8 });      // the frame keeps
    Array.from({ length: 7 }, (_, i) => el(svg, "polygon",     // glass, where it fell
      { fill: "none", stroke: GLASS, opacity: .5, points: "0,0 10,4 4,12",
        transform: `translate(${430 + i * 28} ${300 + (i % 3) * 5}) rotate(${i * 47})` }));
    const pool = el(svg, "rect", { x: 0, y: 298, width: 640, height: 18,
      fill: HONEY, "fill-opacity": .14 });
    const meniscus = el(svg, "polyline", { fill: "none", stroke: HONEY,
      "stroke-width": 1.2, opacity: .6 });
    const REST = [64, 122, 180, 236, 292, 350, 408, 464, 522, 578];
    const ANG = [12, -165, 95, -8, 178, -95, 25, 142, -30, 78];
    const pack = REST.map((rx, i) => {
      const { g, eye } = houndSil2(svg, PACK[i]);
      g.setAttribute("transform",
        `translate(${rx} ${298 + (i % 3) * 4}) scale(.7) rotate(${ANG[i]})`);
      return { eye, i };
    });
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 140;
      doWipe(T);
      typeOn(hdr, "THE TANK, DECANTED", T, 4, 1.6);
      const mp = [];
      for (let x = 0; x <= 640; x += 24)
        mp.push(`${x},${298 + Math.sin(x * .04 + t * .1) * 1.5}`);
      meniscus.setAttribute("points", mp.join(" "));
      pool.setAttribute("fill-opacity", .12 + Math.sin(t * .15) * .03);
      pack.forEach(p => p.eye.setAttribute("opacity",          // the lenses, still open
        (Math.floor(t / 4) + p.i) % 9 ? .9 : .15));
      typeOn(foot, "THE KENNEL, DECANTED.", T, 72, 1.8);
    });
  });

  /* ---------------- 53: the lesson, learned ---------------- */
  FIG._define("youth-d", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF YOUTH / TUTORIAL: DOUSE";
    const GLASS = "#cfefff";
    const ROOST = [];
    for (let r = 0; r < 3; r++) for (let c = 0; c < 13; c++)
      ROOST.push([44 + c * 44 + (r % 2) * 22, 52 + r * 15]);
    el(svg, "circle", { cx: 148, cy: 296, r: 9, fill: PH_DIM });
    el(svg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 3,
      d: "M 148 305 L 148 336 M 148 314 L 176 288" });
    const cone = el(svg, "polygon", { fill: PH, "fill-opacity": 0,
      points: "180,284 60,80 430,80" });
    const stone = el(svg, "circle", { cx: 180, cy: 284, r: 5, fill: PH_BRIGHT });
    const bats = ROOST.map(([rx, ry], i) => {
      const q = el(svg, "polyline", { fill: "none", stroke: GLASS,
        "stroke-width": 1.4, opacity: .55 });
      return { q, rx, ry, i };
    });
    const cmd = label(svg, 24, 330, 10, GLASS);
    label(svg, 452, 350, 10, PH_DIM).textContent = "REGRET";
    const cells = Array.from({ length: 6 }, (_, i) => el(svg, "rect",
      { x: 516 + i * 16, y: 340, width: 12, height: 11, fill: GLASS,
        "fill-opacity": .08 }));
    const settle = label(svg, 320, 200, 9, PH_DIM);
    settle.setAttribute("text-anchor", "middle");
    const foot = label(svg, 624, 316, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "THE LESSON, LEARNED", T, 4, 1.6);
      const lit = T < 16;
      typeOn(cmd, "> DOUSE GLOWSTONE. QUICKLY.", T, 4, 2.4);
      cone.setAttribute("fill-opacity", lit ? .06 + Math.sin(t * .8) * .015 : 0);
      stone.setAttribute("opacity", lit ? 1 : .2);
      bats.forEach(b => {
        let x, y, spread = 7;
        if (lit) {                                             // the swarm, in office
          const ang = T * .22 + b.i * 1.7;
          const rad = 45 + Math.sin(T * .3 + b.i) * 9;
          x = 180 + Math.cos(ang) * rad;
          y = 270 + Math.sin(ang) * rad * .55;
        } else {                                               // the retreat
          const kk = Math.min(1, Math.max(0, (T - 16 - (b.i % 11)) / 26));
          const ang = 16 * .22 + b.i * 1.7;
          const rad = 45 + Math.sin(16 * .3 + b.i) * 9;
          const ax = 180 + Math.cos(ang) * rad;
          const ay = 270 + Math.sin(ang) * rad * .55;
          x = ax + (b.rx - ax) * kk; y = ay + (b.ry - ay) * kk;
          spread = 7 - kk * 2;
        }
        const fl = Math.sin(t * 1.1 + b.i) * 3;
        b.q.setAttribute("points",
          `${x - spread},${y + fl * .4} ${x},${y - 3 - fl} ${x + spread},${y + fl * .4}`);
      });
      const on = lit ? 6 : Math.max(0, 6 - Math.floor((T - 16) / 5));
      cells.forEach((r2, i) => r2.setAttribute("fill-opacity", i < on ? .8 : .08));
      settle.textContent = T >= 58 && T < 146 ? "THE VAULT SETTLES. GRUDGINGLY." : "";
      typeOn(foot, "NO LIGHT, NO FURTHER OPINIONS.", T, 88, 2);
    });
  });

  /* ---------------- 54: the wind-wagon, under sail (kept, unwired) ---------------- */
  FIG._define("wagon", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE ROAD TO GNOMON / IN LIFE";
    const GLASS = "#cfefff";
    el(svg, "circle", { cx: 560, cy: 84, r: 22, fill: GLASS, "fill-opacity": .12 });
    const duneB = el(svg, "polyline", { fill: "none", stroke: PH_DIM, opacity: .5 });
    const duneF = el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      "stroke-width": 1.6 });
    const rig = el(svg, "g", {});
    // the zoxen pair, patient in life as in death
    const zox = [0, 1].map(i => {
      const g = el(rig, "g", {});
      const legsN = [0, 1, 2, 3].map(() => el(g, "line",
        { stroke: "#25567a", "stroke-width": 3.4 }));
      el(g, "ellipse", { cx: 0, cy: 0, rx: 26, ry: 13, fill: "#33739c" });
      el(g, "circle", { cx: 26, cy: -8, r: 7, fill: "#33739c" });
      el(g, "line", { x1: 30, y1: -14, x2: 38, y2: -22, stroke: PH_DIM,
        "stroke-width": 2 });                                  // a horn
      return { g, legsN, x: 120 + i * 74, y: 268 + i * 5 };
    });
    const trace = el(svg, "line", { stroke: PH_DIM, opacity: .8 });
    const wag = el(svg, "g", {});
    el(wag, "path", { fill: "#25567a", d: "M 300 240 L 470 240 L 486 268 L 292 268 Z" });
    [316, 348, 380, 412, 444].forEach(x => el(wag, "line",
      { x1: x, y1: 240, x2: x - 6, y2: 268, stroke: "#9fb7c9", opacity: .6 }));
    el(wag, "line", { x1: 396, y1: 240, x2: 396, y2: 128, stroke: "#9fb7c9",
      "stroke-width": 3 });
    const sail = el(wag, "path", { fill: GLASS, "fill-opacity": .16, stroke: GLASS,
      "stroke-width": 1.4 });
    const pennant = el(wag, "polyline", { fill: "none", stroke: FUNGUS,
      "stroke-width": 2 });
    const wheels = [336, 452].map(x => {
      const g = el(wag, "g", {});
      el(g, "circle", { cx: 0, cy: 0, r: 20, fill: "none", stroke: PH,
        "stroke-width": 2 });
      const spokes = [0, 1, 2].map(() => el(g, "line",
        { stroke: PH_DIM, "stroke-width": 1.6 }));
      return { g, spokes, x, y: 286 };
    });
    const dust = Array.from({ length: 9 }, (_, i) => ({ ph: i * 31,
      q: el(svg, "circle", { r: 2 + (i % 3), fill: PH_DIM, opacity: 0 }) }));
    const foot = label(svg, 624, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "THE WIND-WAGON, UNDER SAIL", T, 4, 1.6);
      [[duneB, 236, 90, .8, 10], [duneF, 300, 60, 2.2, 16]].forEach(
        ([q, y0, wl, sp, amp]) => {
          const pts = [];
          for (let x = -40; x <= 680; x += 20)
            pts.push(`${x},${y0 - Math.abs(Math.sin((x + t * sp * 3) * Math.PI /
              (wl * 3))) * amp}`);
          q.setAttribute("points", pts.join(" "));
        });
      const bob = Math.sin(t * .4) * 2.5;
      rig.setAttribute("transform", `translate(0 ${bob})`);
      zox.forEach((z, i) => {
        z.g.setAttribute("transform",
          `translate(${z.x} ${z.y + Math.sin(t * .5 + i) * 2})`);
        z.legsN.forEach((L2, k) => {
          const sw = Math.sin(t * .55 + k * 1.6 + i) * 12;
          L2.setAttribute("x1", -16 + k * 11); L2.setAttribute("y1", 8);
          L2.setAttribute("x2", -16 + k * 11 + sw); L2.setAttribute("y2", 30);
        });
      });
      trace.setAttribute("x1", 214); trace.setAttribute("y1", 268 + bob);
      trace.setAttribute("x2", 300); trace.setAttribute("y2", 252 + bob);
      const belly = 24 + Math.sin(t * .33) * 5 + Math.sin(t * 1.1) * 2;
      sail.setAttribute("d",
        `M 396 132 L 396 236 Q ${396 - 62 - belly} 200 ${396 - 40} 136 Z`);
      const pp = [];
      for (let k = 0; k <= 4; k++)
        pp.push(`${396 - k * 12},${126 + Math.sin(t * .9 - k) * 3.5}`);
      pennant.setAttribute("points", pp.join(" "));
      wheels.forEach((w, i) => {
        w.g.setAttribute("transform", `translate(${w.x} ${w.y})`);
        w.spokes.forEach((s2, k) => {
          const a = t * .45 + k * Math.PI / 3 + i;
          s2.setAttribute("x1", Math.cos(a) * 18); s2.setAttribute("y1", Math.sin(a) * 18);
          s2.setAttribute("x2", -Math.cos(a) * 18); s2.setAttribute("y2", -Math.sin(a) * 18);
        });
      });
      dust.forEach(d2 => {
        const k = (t * 6 + d2.ph) % 200;
        d2.q.setAttribute("cx", 480 + k);
        d2.q.setAttribute("cy", 296 - k * .12 + Math.sin(k * .1) * 4);
        d2.q.setAttribute("opacity", Math.max(0, .5 - k / 220));
      });
      typeOn(foot, "BUILT TO OUTRUN ANYTHING ON THE ROAD. IT NEARLY DID.", T, 96, 1.9);
    });
  });

  /* ---------------- 23-25: the spawn of brain, three takes ---------------- */
  // the body: a risen brain -- bumpy lobed outline with gyri, stippled
  function brainBody(svg, g, cx, cy, rx, ry, DOTS) {
    const ing = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); g.appendChild(n); return n; };
    let d = `M ${cx - rx} ${cy}`;
    const N = 12;
    for (let i = 1; i <= N; i++) {
      const a0 = Math.PI + (i - .5) * 2 * Math.PI / N, a1 = Math.PI + i * 2 * Math.PI / N;
      const bump = 1.18 + (i % 3) * .06;
      d += ` Q ${cx + Math.cos(a0) * rx * bump} ${cy + Math.sin(a0) * ry * bump}` +
           ` ${cx + Math.cos(a1) * rx} ${cy + Math.sin(a1) * ry}`;
    }
    ing("path", { d: d + " Z", fill: DOTS, stroke: FUNGUS, "stroke-width": 1.7 });
    // the gyri: S-squiggles scattered through the mass
    [[-.5,-.4],[.1,-.55],[.55,-.3],[-.6,.15],[0,.05],[.55,.25],[-.3,.5],[.25,.55]]
      .forEach(([fx, fy], i) => {
        const x = cx + fx * rx, y = cy + fy * ry, s2 = 10 + (i % 3) * 3;
        ing("path", { fill: "none", stroke: FUNGUS, "stroke-width": 1.2, d:
          `M ${x - s2} ${y} Q ${x - s2 / 2} ${y - s2} ${x} ${y} Q ${x + s2 / 2} ${y + s2} ${x + s2} ${y}` });
      });
  }
  // the jar head, worn: tall ears, long snout, one carved eye
  function jarHead(svg, g, hx, hy) {
    const ing = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); g.appendChild(n); return n; };
    const earL = ing("polygon", { fill: PH, "fill-opacity": .4, stroke: PH,
      "stroke-width": 1.3 });
    const earR = ing("polygon", { fill: "none", stroke: PH, "stroke-width": 1.3 });
    ing("polyline", { fill: "none", stroke: PH, "stroke-width": 1.6, points:
      `${hx - 16},${hy + 34} ${hx - 20},${hy + 12} ${hx - 12},${hy - 6} ` +
      `${hx + 8},${hy - 12} ${hx + 24},${hy - 4} ${hx + 60},${hy + 10} ` +
      `${hx + 56},${hy + 18} ${hx + 22},${hy + 12} ${hx + 12},${hy + 18} ${hx + 16},${hy + 34}` });
    ing("circle", { cx: hx + 8, cy: hy + 2, r: 2.2, fill: PH_BRIGHT });
    // the pale neck band
    ing("polyline", { fill: "none", stroke: PH_DIM, points:
      `${hx - 14},${hy + 26} ${hx + 2},${hy + 30} ${hx + 14},${hy + 26}` });
    return { earL, earR, hx, hy };
  }
  function prickEars(H, tw) {
    H.earL.setAttribute("points",
      `${H.hx - 14},${H.hy - 4} ${H.hx - 22 - tw * .4},${H.hy - 46 - tw} ${H.hx - 2},${H.hy - 10}`);
    H.earR.setAttribute("points",
      `${H.hx + 2},${H.hy - 10} ${H.hx + 4 + tw * .3},${H.hy - 44 - tw} ${H.hx + 16},${H.hy - 8}`);
  }
  // a wading-bird leg: hip -> backward knee -> shank -> splayed toes
  function birdLeg(nT, nS, hipx, hipy, k, lift) {
    const kx = hipx + 6 + k * 6, ky = hipy + 42 - lift * .4;
    const fx = hipx - 8 + k * 26, fy = 308 - lift;
    nT.setAttribute("points", `${hipx},${hipy} ${kx},${ky}`);
    nS.setAttribute("points",
      `${kx},${ky} ${fx},${fy} ${fx - 10},${fy + 4} M0,0`.replace(" M0,0", "") +
      ` ${fx},${fy} ${fx + 10},${fy + 4} ${fx},${fy} ${fx + 2},${fy + 6}`);
  }

  // 23: THE LISTENER
  FIG._define("spawn-a", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "sa-dots", PH, 1.2);
    const gg = document.createElementNS(NS, "g"); svg.appendChild(gg);
    const legT1 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 3.4,
      "stroke-linecap": "round" });
    const legS1 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.8 });
    const legT2 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 2.6,
      "stroke-linecap": "round", opacity: .5 });
    const legS2 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4, opacity: .5 });
    birdLeg(legT1, legS1, 300, 236, 0, 0);
    birdLeg(legT2, legS2, 336, 232, .8, 0);
    brainBody(svg, gg, 320, 190, 78, 62, stipple(svg, "sa-orange", FUNGUS, 1.2));
    const H = jarHead(svg, gg, 312, 90);
    // the fungal fringe at the neck
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
      "290,132 296,142 302,132 310,144 318,132 326,142 334,130 342,140 350,132" })
      .setAttribute("transform", "translate(0,0)");
    const ripL = Array.from({ length: 2 }, () => el(svg, "path", { fill: "none",
      stroke: FUNGUS, "stroke-width": 1.4, opacity: 0 }));
    const ripR = Array.from({ length: 2 }, () => el(svg, "path", { fill: "none",
      stroke: FUNGUS, "stroke-width": 1.4, opacity: 0 }));
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    for (let x = 60; x < 600; x += 16)
      el(svg, "line", { x1: x, y1: 312, x2: x + 7, y2: 312, stroke: PH_DIM });
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "SPAWN OF BRAIN (IT HEARD THAT)", T, 4, 1.4);
      const phase = Math.floor(T / 40) % 4;                    // sounds alternate sides
      const side = phase === 1 ? -1 : phase === 3 ? 1 : 0;
      const lean = side * 5;
      gg.setAttribute("transform", `rotate(${lean} 320 300)`);
      prickEars(H, side !== 0 ? 8 : 0);
      [[ripL, 70, -1], [ripR, 570, 1]].forEach(([rips, x, dir]) => {
        rips.forEach((r, i) => {
          const on = (dir === -1 && side === -1) || (dir === 1 && side === 1);
          const k = ((t * 2 + i * 10) % 24) / 24;
          r.setAttribute("d", `M ${x + dir * 14 * (1 + k)} 186 ` +
            `Q ${x + dir * (26 + k * 26)} 206 ${x + dir * 14 * (1 + k)} 226`);
          r.setAttribute("opacity", on ? Math.max(0, .9 - k) : 0);
        });
      });
      typeOn(foot, "NO EYES UNDER THE JAR. IT DOES NOT NEED THEM.", T, 112, 1.6);
    });
  });

  // 24: MID-STEP -- the head holds level while everything else jounces
  FIG._define("spawn-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "sb-dots", PH, 1.2);
    const legT1 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 3.4,
      "stroke-linecap": "round" });
    const legS1 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.8 });
    const legT2 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 2.6,
      "stroke-linecap": "round", opacity: .5 });
    const legS2 = el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4, opacity: .5 });
    const gBody = document.createElementNS(NS, "g"); svg.appendChild(gBody);
    brainBody(svg, gBody, 320, 190, 78, 62, stipple(svg, "sb-orange", FUNGUS, 1.2));
    const gHead = document.createElementNS(NS, "g"); svg.appendChild(gHead);
    const H = jarHead(svg, gHead, 312, 90);
    prickEars(H, 0);
    const gGround = document.createElementNS(NS, "g");
    for (let x = 44; x < 600; x += 16) {
      const l = document.createElementNS(NS, "line");
      l.setAttribute("x1", x); l.setAttribute("y1", 312);
      l.setAttribute("x2", x + 7); l.setAttribute("y2", 312);
      l.setAttribute("stroke", PH_DIM); gGround.appendChild(l);
    }
    svg.appendChild(gGround);
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "SPAWN OF BRAIN (MID-STEP)", T, 4, 1.4);
      const th = (t % 16) / 16 * Math.PI * 2;
      birdLeg(legT1, legS1, 300, 236, Math.cos(th) * .8,
        Math.max(0, Math.sin(th)) * 20);
      birdLeg(legT2, legS2, 336, 232, Math.cos(th + Math.PI) * .8,
        Math.max(0, Math.sin(th + Math.PI)) * 20);
      const jounce = [0, 2, 4, 2, 0, 2, 4, 2][t % 8];          // the body takes it
      gBody.setAttribute("transform",
        `translate(0 ${jounce}) rotate(${jounce - 2} 320 190)`);
      gHead.setAttribute("transform", "translate(0 0)");        // the head refuses to
      gGround.setAttribute("transform", `translate(${-(t * 4) % 16} 0)`);
      typeOn(foot, "THE HEAD HOLDS LEVEL. THE REST NEGOTIATES.", T, 104, 1.6);
    });
  });

  // 25: FELLED -- as the game finds it
  FIG._define("spawn-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "sc-dots", PH, 1.2);
    for (let x = 60; x < 600; x += 16)
      el(svg, "line", { x1: x, y1: 292, x2: x + 7, y2: 292, stroke: PH_DIM });
    // the body, down: the brain mass squashed against the ground
    const gg = document.createElementNS(NS, "g"); svg.appendChild(gg);
    brainBody(svg, gg, 300, 246, 88, 44, stipple(svg, "sc-orange", FUNGUS, 1.2));
    // the legs, where the stride left them
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 3,
      "stroke-linecap": "round", points: "356,244 408,232 446,252" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.8,
      points: "446,252 486,246 496,252 486,258 446,258" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 2.6,
      "stroke-linecap": "round", opacity: .6, points: "344,268 390,276 428,270" });
    // the jar, rolled to its side, rocking itself still
    const gJar = document.createElementNS(NS, "g"); svg.appendChild(gJar);
    const jh = jarHead(svg, gJar, 0, 0);
    prickEars(jh, 0);
    // the last thoughts, pulsing out and fading
    const pulses = Array.from({ length: 2 }, () =>
      el(svg, "circle", { cx: 300, cy: 240, r: 10, fill: "none",
        stroke: FUNGUS, opacity: 0 }));
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 180;
      doWipe(T);
      typeOn(hdr, "SPAWN OF BRAIN (AS FOUND)", T, 4, 1.4);
      const settle = Math.max(0, 1 - T / 50);                  // the rocking dies
      const rock = Math.sin(t * .55) * 14 * settle;
      gJar.setAttribute("transform",
        `translate(150 258) rotate(${78 + rock} 0 20)`);
      pulses.forEach((q, i) => {                               // the thought, winding down
        const k = ((t * 2 + i * 12) % 26) / 26;
        const strength = Math.max(0, 1 - T / 110);
        q.setAttribute("r", 10 + k * 34);
        q.setAttribute("opacity", Math.max(0, (.7 - k) * strength));
      });
      typeOn(foot, "FELLED MID-STEP. THE JAR ROLLED TO ITS SIDE.", T, 120, 1.6);
    });
  });


  /* ---------------- 26-28: the spawn of guts, three takes ---------------- */
  // the gut palette: phosphor greens, one shade per organ (CCB); the
  // falcon jar stays blue
  const G_COLLAR = "#49e08b", G_ARM = "#6fe762", G_SKIRT = "#3ed4a4",
        G_DRIP = "#aaffcc", G_DIM = "#2c8f5e";
  let _gutN = 0;
  // the falcon-jar helm: a tall cone with the falcon's head at the peak
  function gutsHelm(g) {
    const ing = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); g.appendChild(n); return n; };
    ing("polygon", { points: "292,118 348,118 336,52 306,52", fill: "none",
      stroke: PH, "stroke-width": 1.6 });
    ing("line", { x1: 300, y1: 92, x2: 341, y2: 92, stroke: PH_DIM });
    ing("polyline", { fill: "none", stroke: PH, "stroke-width": 1.5, points:
      "306,52 308,38 318,28 332,28 342,36 " +               // the dome
      "358,46 346,50 340,46 " +                             // the SHARP hook, down and back
      "334,52 322,52 336,52" });                            // jaw home
    ing("circle", { cx: 328, cy: 36, r: 1.8, fill: PH_BRIGHT });
  }
  // the face and collar: eye-cluster over a torus of gut
  function gutsFace(svg, DOTS) {
    el(svg, "polygon", { points: "288,118 352,118 358,158 344,176 296,176 282,156",
      fill: DOTS, stroke: PH, "stroke-width": 1.5 });
    const eyes = [[306,134,5],[322,130,6],[338,136,5],[300,148,4],[316,146,7],
      [334,150,4],[322,162,4]].map(([x, y, r]) => ({
        ball: el(svg, "circle", { cx: x, cy: y, r, fill: BG, stroke: PH_BRIGHT,
          "stroke-width": 1.3 }),
        pupil: el(svg, "circle", { cx: x + 1, cy: y + 1, r: r * .4, fill: PH }),
      }));
    // the collar: a fat ring of gut, scalloped, green, inclined to drip
    const GD = stipple(svg, "gutdots" + (_gutN++), G_COLLAR, 1.1);
    el(svg, "ellipse", { cx: 320, cy: 190, rx: 62, ry: 24, fill: GD,
      stroke: G_COLLAR, "stroke-width": 1.7 });
    el(svg, "ellipse", { cx: 320, cy: 186, rx: 34, ry: 12, fill: BG,
      stroke: G_DIM });
    const scallops = el(svg, "polyline", { fill: "none", stroke: G_DIM, points:
      Array.from({ length: 9 }, (_, k) =>
        `${262 + k * 15},${210 + (k % 2) * 5}`).join(" ") });
    return eyes;
  }
  // the tendril skirt: re-drawn per tick, always moving
  function gutsSkirt(svg, n) {
    return Array.from({ length: n }, (_, i) =>
      ({ x0: 284 + i * 12, ph: i * 1.3,
         q: el(svg, "polyline", { fill: "none", stroke: G_SKIRT,
           "stroke-width": i % 2 ? 1.6 : 2.4 }) }));
  }
  function skirtTick(skirt, t, droop) {
    skirt.forEach(s2 => {
      const w1 = Math.sin(t * .3 + s2.ph) * 7, w2 = Math.sin(t * .22 + s2.ph * 2) * 10;
      s2.q.setAttribute("points",
        `${s2.x0},206 ${s2.x0 + w1},${240 + droop} ` +
        `${s2.x0 - w2},${272 + droop} ${s2.x0 + w2 * .6},${300 + droop} ` +
        `${s2.x0 + w2 * .6 + 8},${302 + droop}`);
    });
  }
  // the gut-arm: an INTESTINE, rooted at the collar and reaching the floor
  // -- a continuous tube with transverse creases (haustra), ending pooled
  function gutsArm(svg) {
    const C = [[266, 192], [238, 200], [212, 220], [196, 250], [192, 280], [198, 302]];
    const wall = (side) => {
      const pts = C.map(([x, y], k) => {
        const [x0, y0] = C[Math.max(0, k - 1)], [x1, y1] = C[Math.min(C.length - 1, k + 1)];
        const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
        const w2 = 10 - k * .6;
        return `${x - dy / len * w2 * side},${y + dx / len * w2 * side}`;
      });
      el(svg, "polyline", { fill: "none", stroke: G_ARM, "stroke-width": 1.6,
        points: pts.join(" ") });
      return pts;
    };
    const L = wall(1), R = wall(-1);
    // the haustral creases: paired arcs across the tube, every half-segment
    for (let k = 0; k < C.length - 1; k++) {
      for (const f of [0.33, 0.66, 1]) {
        const x = C[k][0] + (C[k + 1][0] - C[k][0]) * f;
        const y = C[k][1] + (C[k + 1][1] - C[k][1]) * f;
        const dx = C[k + 1][0] - C[k][0], dy = C[k + 1][1] - C[k][1];
        const len = Math.hypot(dx, dy) || 1, w2 = 9 - k * .6;
        el(svg, "path", { fill: "none", stroke: G_DIM, d:
          `M ${x - dy / len * w2} ${y + dx / len * w2} ` +
          `Q ${x + dx / len * 4} ${y + dy / len * 4} ` +
          `${x + dy / len * w2} ${y - dx / len * w2}` });
      }
    }
    // the end, pooled on the floor
    el(svg, "ellipse", { cx: 202, cy: 306, rx: 15, ry: 5.5, fill: "none",
      stroke: G_ARM, "stroke-width": 1.5 });
    el(svg, "ellipse", { cx: 214, cy: 310, rx: 24, ry: 4, fill: "none",
      stroke: G_DIM });
    return [];
  }

  // 26: THE SWAY
  FIG._define("guts-a", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "ga-dots", PH, 1.2);
    for (let x = 60; x < 600; x += 16)
      el(svg, "line", { x1: x, y1: 314, x2: x + 7, y2: 314, stroke: PH_DIM });
    const gg = document.createElementNS(NS, "g"); svg.appendChild(gg);
    const armSegs = gutsArm(gg);
    const skirt = gutsSkirt(gg, 6);
    gutsFace(gg, DOTS);
    gutsHelm(gg);
    // the drip
    const drips = Array.from({ length: 5 }, (_, i) =>
      ({ x: 270 + i * 24, ph: i * 29, q: el(svg, "line", { stroke: G_DRIP,
        "stroke-width": 1.4, opacity: .8 }) }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 64, 10, PH); call.setAttribute("text-anchor", "end");
    const CALLS = [
      { at: [322, 40], text: "HELM: THE FALCON JAR. THE PLINTH WANTS IT" },
      { at: [322, 146], text: "EYES: DECORATIVE. IT HUNTS BY EAR" },
      { at: [370, 190], text: "COLLAR: GUT, RECENTLY PROMOTED" },
      { at: [214, 260], text: "ARM: A HOSE WITH OPINIONS" },
    ];
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "SPAWN OF GUTS (SWAYING TOWARD EVERY SOUND)", T, 4, 1.3);
      gg.setAttribute("transform",
        `rotate(${Math.round(Math.sin(t * .09) * 3) * 1.4} 320 310)`);
      skirtTick(skirt, t, 0);
      drips.forEach(d => {
        const k = (t * 5 + d.ph) % 110;
        d.q.setAttribute("x1", d.x); d.q.setAttribute("x2", d.x);
        d.q.setAttribute("y1", 206 + k); d.q.setAttribute("y2", 212 + k);
        d.q.setAttribute("opacity", k > 100 ? 0 : .8);
      });
      const c = CALLS[Math.floor(T / 28) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 440,60 448,60`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "WHATEVER YOU JUST DID, IT HEARD.", T, 112, 1.6);
    });
  });

  // 27: THE DRIP -- the face, closer than anyone wants
  FIG._define("guts-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "gb-dots", PH, 1.2);
    const gg = document.createElementNS(NS, "g"); svg.appendChild(gg);
    gg.setAttribute("transform", "translate(-320 -110) scale(2)");
    const eyes = gutsFace(gg, DOTS);
    gutsHelm(gg);
    const ring = gg.querySelector("ellipse");                 // the collar, pulsing
    const drips = Array.from({ length: 7 }, (_, i) =>
      ({ x: 200 + i * 44, ph: i * 23, q: el(svg, "line", { stroke: G_DRIP,
        "stroke-width": 1.8 }),
        splat: el(svg, "polyline", { fill: "none", stroke: G_DIM,
          points: "0,0", opacity: 0 }) }));
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 150;
      doWipe(T);
      typeOn(hdr, "SPAWN OF GUTS (DETAIL. SORRY.)", T, 4, 1.4);
      eyes.forEach((e, i) => {                                // out-of-sequence blinks
        const open = ((t + i * 7) % 30) > 4;
        e.pupil.setAttribute("opacity", open ? 1 : 0);
        e.ball.setAttribute("fill", open ? BG : PH_DIM);
      });
      drips.forEach(d => {
        const k = (t * 6 + d.ph) % 130;
        d.q.setAttribute("x1", d.x); d.q.setAttribute("x2", d.x);
        d.q.setAttribute("y1", 270 + k * .5); d.q.setAttribute("y2", 280 + k * .5);
        d.q.setAttribute("opacity", k > 120 ? 0 : .85);
        const landed = k > 116;
        d.splat.setAttribute("points",
          `${d.x - 7},342 ${d.x - 2},338 ${d.x + 3},342 ${d.x + 8},339`);
        d.splat.setAttribute("opacity", landed ? .8 : 0);
      });
      typeOn(foot, "THE EYES ARE ORNAMENTAL. THE HUNGER IS NOT.", T, 100, 1.6);
    });
  });

  // 28: THE CLAIM -- it goes down, the jar survives
  FIG._define("guts-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const DOTS = stipple(svg, "gc-dots", PH, 1.2);
    for (let x = 60; x < 600; x += 16)
      el(svg, "line", { x1: x, y1: 314, x2: x + 7, y2: 314, stroke: PH_DIM });
    const gBody = document.createElementNS(NS, "g"); svg.appendChild(gBody);
    gutsArm(gBody);
    const skirt = gutsSkirt(gBody, 6);
    gutsFace(gBody, DOTS);
    const gHelm = document.createElementNS(NS, "g"); svg.appendChild(gHelm);
    gutsHelm(gHelm);
    const prize = label(svg, 452, 260, 10, FUNGUS);
    const foot = label(svg, 320, 348, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "SPAWN OF GUTS (THE CLAIM)", T, 4, 1.4);
      const down = Math.max(0, Math.min(1, (T - 60) / 20));   // it goes down
      gBody.setAttribute("transform",
        `translate(0 ${down * 80}) rotate(${down * 8} 320 310)`);
      gBody.setAttribute("opacity", 1 - down * .35);
      skirtTick(skirt, T < 60 ? t : 0, down * 26);
      // the helm topples forward, bounces once, settles upright
      let hx = 0, hy = 0, rot = 0;
      if (T >= 60) {
        const k = Math.min(1, (T - 60) / 26);
        rot = k * 92 - (T > 86 && T < 96 ? (96 - T) : 0) * 2; // the bounce
        hx = k * 120; hy = k * 190;
        if (T > 100) { rot = 0; hx = 128; hy = 196; }         // upright, waiting
      }
      gHelm.setAttribute("transform", `translate(${hx} ${hy}) rotate(${rot} 320 118)`);
      prize.textContent = T > 112 ? "[+5 -- THE FALCON JAR]" : "";
      typeOn(foot, "THE JAR IS OWED TO A PLINTH TWO FLOORS UP.", T, 130, 1.6);
    });
  });


  /* ---------------- 13-C: the Autarch, hollowed ---------------- */
  FIG._define("autarch-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "FALLEN AUTARCHY / BONE / CLAIMED";
    const ADOTS = stipple(svg, "dots-autarchc", PH, .9);
    const ODOTS = stipple(svg, "dots-orangec", FUNGUS, 1.2);
    const CX = 320, CY = 180;
    // the halo, carvings still
    el(svg, "circle", { cx: CX, cy: CY, r: 118, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.4 });
    Array.from({ length: 20 }, (_, i) => {
      const a = i * Math.PI / 10;
      el(svg, "polygon", { fill: PH, "fill-opacity": .35, stroke: PH,
        "stroke-width": 1, points:
        `${CX + Math.cos(a - .07) * 118},${CY + Math.sin(a - .07) * 118} ` +
        `${CX + Math.cos(a + .04) * (142 + (i % 2) * 18)},${CY + Math.sin(a + .04) * (142 + (i % 2) * 18)} ` +
        `${CX + Math.cos(a + .13) * 118},${CY + Math.sin(a + .13) * 118}` });
    });
    Array.from({ length: 8 }, (_, i) => {
      const a = i * Math.PI / 4 + .4;
      const pts = [70, 82, 94, 106, 116].map((r, k) => {
        const aa = a + (k % 2 ? .11 : -.07);
        return `${CX + Math.cos(aa) * r},${CY + Math.sin(aa) * r}`;
      });
      el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
        opacity: .55, points: pts.join(" ") });
    });
    // THE SKULL: the same stone, worn honest
    el(svg, "polygon", { points:
      "272,128 368,128 382,160 380,214 370,236 364,258 276,258 270,236 260,214 258,160",
      fill: ADOTS, stroke: PH, "stroke-width": 1.8 });
    [0, 1, 2].forEach(r =>
      el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
        Array.from({ length: 9 }, (_, k) =>
          `${272 + k * 12},${132 + r * 7 + (k % 2) * 3}`).join(" ") }));
    // the sockets, FULL of the orange
    const sockL = el(svg, "ellipse", { cx: 296, cy: 188, rx: 14, ry: 10,
      fill: ODOTS, stroke: PH, "stroke-width": 1.4 });
    const sockR = el(svg, "ellipse", { cx: 344, cy: 188, rx: 14, ry: 10,
      fill: ODOTS, stroke: PH, "stroke-width": 1.4 });
    const glowL = el(svg, "ellipse", { cx: 296, cy: 188, rx: 6, ry: 4,
      fill: FUNGUS, "fill-opacity": .5 });
    const glowR = el(svg, "ellipse", { cx: 344, cy: 188, rx: 6, ry: 4,
      fill: FUNGUS, "fill-opacity": .5 });
    // sprigs, testing the air out of each socket
    const sprigs = [[296, 188, -2.2], [300, 186, -.9], [344, 188, -.6], [340, 186, -2.6]]
      .map(() => el(svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.5 }));
    const SPRIG_AT = [[296, 190, -2.4], [302, 186, -.8], [344, 190, -.7], [338, 186, -2.5]];
    // the nasal aperture, and the cheek hollows
    el(svg, "path", { d: "M 320 204 L 312 230 Q 320 238 328 230 Z",
      fill: BG, stroke: PH, "stroke-width": 1.4 });
    el(svg, "path", { d: "M 276 214 Q 284 224 292 218", fill: "none", stroke: PH_DIM });
    el(svg, "path", { d: "M 348 218 Q 356 224 364 214", fill: "none", stroke: PH_DIM });
    // THE GRIN: carved teeth, one gone
    el(svg, "line", { x1: 294, y1: 240, x2: 346, y2: 240, stroke: PH, "stroke-width": 1.4 });
    el(svg, "line", { x1: 294, y1: 252, x2: 346, y2: 252, stroke: PH, "stroke-width": 1.4 });
    for (let x = 294; x <= 346; x += 6.5)
      el(svg, "line", { x1: x, y1: 240, x2: x, y2: 252, stroke: PH });
    el(svg, "rect", { x: 320.5, y: 240.5, width: 5.5, height: 11, fill: BG }); // the gap
    // the beard: curl-rows, filled, still
    for (let r = 0; r < 6; r++) for (let k = 0; k < 8 - (r > 3 ? 1 : 0); k++)
      el(svg, "circle", { cx: 286 + k * 10 + (r % 2) * 5, cy: 268 + r * 13,
        r: 4.4, fill: PH, "fill-opacity": .75, stroke: PH, "stroke-width": 1 });
    el(svg, "rect", { x: 282, y: 300, width: 78, height: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.2 });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "268,258 218,290 186,340 176,392" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "372,258 422,290 454,340 464,392" });
    // the ropes, as in 13-B
    const ROOTS = [
      [232, 268, -2.6], [408, 268, -.5], [258, 152, 3.4], [384, 150, -.2],
      [320, 344, 1.57], [206, 306, 2.9], [436, 306, .3], [320, 122, -1.57],
      [288, 338, 2.2], [352, 338, .9],
    ];
    const tendrils = ROOTS.map(() =>
      el(svg, "polygon", { fill: FUNGUS, "fill-opacity": .3,
        stroke: FUNGUS, "stroke-width": 1.4 }));
    const foot = label(svg, 320, 410, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "NASSAK AN-RAH (HOLLOWED)", T, 4, 1.4);
      const br = [.35, .45, .55, .65, .55, .45][Math.floor(t / 3) % 6]; // the sockets pulse
      glowL.setAttribute("fill-opacity", br);
      glowR.setAttribute("fill-opacity", br);
      sprigs.forEach((n, i) => {                                       // the sprigs test the air
        const [sx, sy, a0] = SPRIG_AT[i];
        const pts = [1, 2, 3].map(k => {
          const a = a0 + Math.sin(t * .3 + k + i * 2) * .35;
          const r = k * (5 + ((t + i * 7) % 8) * .6);
          return `${sx + Math.cos(a) * r},${sy + Math.sin(a) * r}`;
        });
        n.setAttribute("points", `${sx},${sy} ` + pts.join(" "));
      });
      tendrils.forEach((n, i) => {                                     // the ropes
        const [rx, ry, a0] = ROOTS[i];
        const w = Math.sin(t * .4 + i * 1.9);
        const c = [[rx, ry]];
        for (let k = 1; k <= 4; k++) {
          const a = a0 + Math.sin(t * .25 + k * 1.2 + i) * .3 + w * .04 * k;
          const r = k * (13 + ((t + i * 5) % 12));
          c.push([rx + Math.cos(a) * r, ry + Math.sin(a) * r * .8]);
        }
        const W = [6, 4.8, 3.4, 1.9, .7];
        const L = [], R = [];
        for (let k = 0; k < c.length; k++) {
          const [x0, y0] = c[Math.max(0, k - 1)];
          const [x1, y1] = c[Math.min(c.length - 1, k + 1)];
          const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len * W[k], ny = dx / len * W[k];
          L.push(`${c[k][0] + nx},${c[k][1] + ny}`);
          R.push(`${c[k][0] - nx},${c[k][1] - ny}`);
        }
        n.setAttribute("points", L.concat(R.reverse()).join(" "));
      });
      typeOn(foot, "THE STONE WEARS TO THE SKULL. THE SKULL WEARS ORANGE.", T, 130, 1.8);
    });
  });


  /* ---------------- 03-C: the canopic system, supine ---------------- */
  FIG._define("canopic-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "RITES / PROCEDURE / SUPINE";
    // THE PATIENT, lying flat: the standing drawing rotated onto the table,
    // narrowed slightly through the shoulders
    const gP = document.createElementNS(NS, "g");
    gP.setAttribute("transform",
      "rotate(90 320 150) translate(320 0) scale(.86 1) translate(-320 0)");
    svg.appendChild(gP);
    const inP = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); gP.appendChild(n); return n; };
    inP("polyline", { fill: "none", stroke: PH, "stroke-width": 1.8, points:
      "312,94 274,106 250,148 244,164 258,168 276,138 280,192 " +
      "284,220 292,268 284,274 302,274 306,224 320,224 334,224 " +
      "338,274 356,274 348,268 356,220 360,192 364,138 382,168 " +
      "396,164 390,148 366,106 328,94" });
    inP("circle", { cx: 320, cy: 72, r: 22, fill: "none", stroke: PH, "stroke-width": 1.8 });
    inP("circle", { cx: 320, cy: 78, r: 3.5, fill: PH_DIM });
    const ORGANS = {};
    ORGANS.BRAIN = inP("path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.4,
      d: "M 308 62 Q 312 54 320 56 Q 328 52 332 60 Q 336 66 330 68 " +
         "M 312 64 Q 316 60 318 66 M 324 60 Q 328 64 326 68" });
    ORGANS.EYES = inP("g", {});
    [[312, 76], [328, 76]].forEach(([x, y]) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", 3.4);
      c.setAttribute("fill", "none"); c.setAttribute("stroke", PH_DIM);
      c.setAttribute("stroke-width", 1.4); ORGANS.EYES.appendChild(c);
    });
    ORGANS.LUNGS = inP("path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.4,
      d: "M 314 112 Q 300 116 298 138 Q 298 150 308 150 Q 314 146 314 132 Z " +
         "M 326 112 Q 340 116 342 138 Q 342 150 332 150 Q 326 146 326 132 Z" });
    ORGANS.LIVER = inP("path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.4,
      d: "M 300 160 L 338 158 Q 344 166 336 172 L 306 174 Q 298 168 300 160 Z" });
    ORGANS.INTESTINES = inP("path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.5,
      d: "M 304 186 Q 320 180 336 186 Q 340 194 324 194 Q 306 192 306 200 " +
         "Q 322 206 336 200 Q 340 210 322 212 Q 306 212 308 218 Q 322 222 334 218" });
    // where each organ ENDS UP on screen (the patient transform, applied)
    const TX = (x, y) => [320 - (y - 150), 150 + (x - 320) * .86];
    const SEQ = [
      { key: "LUNGS", at: TX(320, 132), jar: 0, name: "LUNGS", head: "BABOON" },
      { key: "LIVER", at: TX(320, 166), jar: 1, name: "LIVER", head: "HUMAN" },
      { key: "EYES", at: TX(320, 76), jar: 2, name: "EYES", head: "MANTIS" },
      { key: "INTESTINES", at: TX(320, 200), jar: 3, name: "INTESTINES", head: "FALCON" },
      { key: "BRAIN", at: TX(320, 62), jar: 4, name: "BRAIN", head: "JACKAL" },
    ];
    const jars = SEQ.map((o, i) => {
      const jx = 70 + i * 125;
      el(svg, "polygon", { points: `${jx-22},345 ${jx+22},345 ${jx+16},295 ${jx-16},295`,
        fill: PH, "fill-opacity": .10, stroke: PH, "stroke-width": 1.5 });
      headGlyph(svg, o.head, jx);
      const cap = label(svg, jx, 372, 10, PH); cap.setAttribute("text-anchor", "middle");
      const who = label(svg, jx, 386, 9, PH_DIM); who.setAttribute("text-anchor", "middle");
      return { jx, cap, who, o };
    });
    const lead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const payload = el(svg, "circle", { r: 3.2, fill: PH_BRIGHT, opacity: 0 });
    const foot = label(svg, 320, 62, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 190;
      doWipe(T);
      typeOn(hdr, "THE CANOPIC SYSTEM (SUPINE)", T, 4, 1.4);
      const step = Math.floor((T - 20) / 28), f = ((T - 20) % 28) / 28;
      SEQ.forEach((o, i) => {
        const active = i === step && T >= 20;
        ORGANS[o.key].setAttribute("stroke", active ? PH_BRIGHT : PH_DIM);
        if (o.key === "EYES")
          [...ORGANS.EYES.children].forEach(c =>
            c.setAttribute("stroke", active ? PH_BRIGHT : PH_DIM));
        if (active) {
          const j = jars[i];
          lead.setAttribute("points", `${o.at[0]},${o.at[1]} ${j.jx},${o.at[1] + 40} ${j.jx},292`);
          payload.setAttribute("cx", o.at[0] + (j.jx - o.at[0]) * f);
          payload.setAttribute("cy", o.at[1] + (292 - o.at[1]) * f);
          payload.setAttribute("opacity", 1);
          if (f > .55) { typeOn(j.cap, o.name, T, 20 + i * 28 + 16, 1.6);
                         typeOn(j.who, o.head, T, 20 + i * 28 + 20, 1.6); }
        }
      });
      if (step > 4 || T < 20) { lead.setAttribute("points", ""); payload.setAttribute("opacity", 0); }
      typeOn(foot, "PLEASE REMOVE ORGANS BEFORE INTERMENT.", T, 160, 1.8);
    });
  });


  /* ---------------- 11-B: the burial sphere, coffin upright ---------------- */
  FIG._define("sphere-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "CHAMBER 6 / ZERO-G / TENANTED";
    const CDOTS = stipple(svg, "dots-sphereb", PH, .9);
    el(svg, "line", { x1: 296, y1: 44, x2: 296, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 344, y1: 44, x2: 344, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 290, y1: 96, x2: 350, y2: 96, stroke: PH_DIM });
    el(svg, "circle", { cx: 320, cy: 228, r: 132, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 2 });
    el(svg, "circle", { cx: 320, cy: 228, r: 122, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "5 4" });
    for (let a = 0; a < 24; a++) {
      const th = a * Math.PI / 12;
      el(svg, "line", { x1: 320 + Math.cos(th) * 114, y1: 228 + Math.sin(th) * 114,
        x2: 320 + Math.cos(th) * 108, y2: 228 + Math.sin(th) * 108, stroke: PH_DIM });
    }
    el(svg, "ellipse", { cx: 320, cy: 356, rx: 26, ry: 7, fill: BG,
      stroke: PH, "stroke-width": 1.4 });
    const six = label(svg, 424, 300, 64, PH_DIM);
    six.setAttribute("opacity", .3); six.textContent = "6";
    const strands = Array.from({ length: 3 }, () =>
      el(svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.5 }));
    // THE COFFIN, upright: a standing glass egg, seam running vertical
    const gCof = document.createElementNS(NS, "g"); svg.appendChild(gCof);
    const coffin = document.createElementNS(NS, "ellipse");
    for (const [k, v] of Object.entries({ cx: 320, cy: 232, rx: 30, ry: 52,
      fill: CDOTS, stroke: PH_BRIGHT, "stroke-width": 1.8 })) coffin.setAttribute(k, v);
    gCof.appendChild(coffin);
    el(svg, "line", { x1: 320, y1: 180, x2: 320, y2: 284, stroke: PH_DIM,
      "stroke-dasharray": "2 4" });                          // the seam, vertical
    const knot = document.createElementNS(NS, "circle");
    for (const [k, v] of Object.entries({ cx: 320, cy: 234, r: 13, fill: FUNGUS,
      "fill-opacity": .28, stroke: FUNGUS, "stroke-width": 1.4 })) knot.setAttribute(k, v);
    gCof.appendChild(knot);
    const tendrils = Array.from({ length: 9 }, (_, i) => {
      const under = i >= 5;
      const n = document.createElementNS(NS, "polyline");
      n.setAttribute("fill", "none"); n.setAttribute("stroke", FUNGUS);
      n.setAttribute("stroke-width", under ? 1.1 : 1.6);
      n.setAttribute("opacity", under ? .45 : 1);
      gCof.appendChild(n); return n;
    });
    const motes = Array.from({ length: 8 }, (_, i) =>
      ({ q: el(svg, "circle", { r: i % 3 ? 1 : 1.6, fill: PH_DIM }),
         R: 44 + (i * 29) % 68, ph: i * .8, sp: .04 + (i % 3) * .015 }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 62, 10, PH);
    const CALLS = [
      { at: [320, 96], text: "THROAT: THE FUNGUS COMES DOWN IT" },
      { at: [320, 180], text: "SEAM: VERTICAL, FINE AS A HAIR" },
      { at: [320, 234], text: "TENANT: COILED TALL, BREATHING SLOW" },
      { at: [204, 310], text: "PRAYERS: READ FROM EVERY DIRECTION AT ONCE" },
    ];
    label(svg, 24, 396, 10, PH_DIM).textContent = "THE CHURN";
    const breath = label(svg, 110, 396, 10, FUNGUS);
    const foot = label(svg, 420, 396, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "BURIAL SPHERE OF NASSAK AN-RAH", T, 4, 1.4);
      const br = [0, 1, 2, 3, 4, 4, 3, 2, 1, 0][Math.floor(t / 3) % 10];
      knot.setAttribute("r", 12 + br);
      coffin.setAttribute("stroke-width", 1.4 + br * .18);
      breath.textContent = "(" + "~".repeat(3 + br) + ")";
      tendrils.forEach((n, i) => {                           // coiling TALL
        const under = i >= 5;
        const a0 = i * (Math.PI * 2 / (under ? 4 : 5)) + t * (under ? -.06 : .09);
        const w = Math.sin(t * .5 + i * 1.7) * 5;
        const reach = under ? .8 : 1;
        const pts = [1, 2, 3, 4].map(k => {
          const r = (8 + k * (7 + br * .8)) * reach;
          const a = a0 + w * .02 * k + Math.sin(t * .3 + k * 1.3 + i) * .22;
          return `${320 + Math.cos(a) * r * .55},${234 + Math.sin(a) * r}`;
        });
        n.setAttribute("points", `320,234 ` + pts.join(" "));
      });
      strands.forEach((n, i) => {
        const sw = Math.sin(t * .22 + i * 2.1) * 5;
        n.setAttribute("points",
          `${306 + i * 14},46 ${306 + i * 14 + sw},96 ` +
          `${312 + i * 8 + sw},140 ${318 + i * 2},178`);     // meeting the crown
      });
      motes.forEach(m => {
        const a = t * m.sp + m.ph;
        m.q.setAttribute("cx", 320 + Math.cos(a) * m.R);
        m.q.setAttribute("cy", 228 + Math.sin(a) * m.R * .85);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 160,66 166,66`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "PRY IT, AND IT WILL MIND.", T, 120, 1.6);
    });
  });

  /* ---------------- 11-E: the burial sphere, shattered, full-cut ---------------- */
  FIG._define("sphere-e", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "CHAMBER 6 / ZERO-G / VACANT";
    const CDOTS = stipple(svg, "dots-spheree", PH, .9);
    el(svg, "line", { x1: 296, y1: 44, x2: 296, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 344, y1: 44, x2: 344, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 290, y1: 96, x2: 350, y2: 96, stroke: PH_DIM });
    el(svg, "circle", { cx: 320, cy: 228, r: 132, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 2 });
    el(svg, "circle", { cx: 320, cy: 228, r: 122, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "5 4" });
    for (let a = 0; a < 24; a++) {
      const th = a * Math.PI / 12;
      el(svg, "line", { x1: 320 + Math.cos(th) * 114, y1: 228 + Math.sin(th) * 114,
        x2: 320 + Math.cos(th) * 108, y2: 228 + Math.sin(th) * 108, stroke: PH_DIM });
    }
    el(svg, "ellipse", { cx: 320, cy: 356, rx: 26, ry: 7, fill: BG,
      stroke: PH, "stroke-width": 1.4 });
    const six = label(svg, 424, 300, 64, PH_DIM);
    six.setAttribute("opacity", .3); six.textContent = "6";
    // the ghost of the oval: where the pieces agree, once a cycle
    el(svg, "ellipse", { cx: 320, cy: 232, rx: 30, ry: 52, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "2 5", opacity: .5 });
    // FULL-CUT SHARDS: six closed pieces of the oval. Each is its arc of the
    // rim plus two jagged crack-edges; every crack is SHARED with the next
    // piece (both sampled from the same jag), so at zero drift the six seat
    // into the complete filled oval, cracks agreeing to the pixel.
    const IMPACT = [312, 220];                       // the pry landed off-heart
    const crackPts = (j) => {                        // impact -> rim, jagged
      const jj = j % 6;
      const bx = 320 + Math.cos(jj * Math.PI / 3) * 30,
            by = 232 + Math.sin(jj * Math.PI / 3) * 52;
      const dx = bx - IMPACT[0], dy = by - IMPACT[1], L = Math.hypot(dx, dy);
      const pts = [];
      for (let k = 1; k < 4; k++) {
        const f = k / 4, jog = Math.sin(jj * 2.7 + k * 3.1) * 4.5;
        pts.push([IMPACT[0] + dx * f - dy / L * jog,
                  IMPACT[1] + dy * f + dx / L * jog]);
      }
      return pts;
    };
    const SHARDS = Array.from({ length: 6 }, (_, i) => {
      const base = [IMPACT.slice()];
      base.push(...crackPts(i));                     // out along crack i
      const arc0 = base.length;
      for (let k = 0; k <= 6; k++) {                 // the rim, arc i..i+1
        const a = (i + k / 6) * Math.PI / 3;
        base.push([320 + Math.cos(a) * 30, 232 + Math.sin(a) * 52]);
      }
      const arc1 = base.length;
      base.push(...crackPts(i + 1).reverse());       // home along crack i+1
      const cxm = base.reduce((s, p) => s + p[0], 0) / base.length;
      const cym = base.reduce((s, p) => s + p[1], 0) / base.length;
      return {
        base, arc0, arc1, cxm, cym,
        mid: (i + .5) * Math.PI / 3,
        body: el(svg, "polygon", { fill: CDOTS, stroke: PH,
          "stroke-width": .9, "stroke-opacity": .7 }),
        rim: el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT,
          "stroke-width": 1.8 }),
      };
    });
    const motes = Array.from({ length: 8 }, (_, i) =>
      ({ q: el(svg, "circle", { r: i % 3 ? 1 : 1.6, fill: PH_DIM }),
         R: 44 + (i * 29) % 68, ph: i * .8, sp: .04 + (i % 3) * .015 }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 62, 10, PH);
    const CALLS = [
      { at: [352, 198], text: "SHARDS: SIX, FULL-CUT, KEEPING THEIR CURVE" },
      { at: [312, 220], text: "CRACKS: SIX, ALL TELLING THE SAME STORY" },
      { at: [204, 310], text: "PRAYERS: ONE OF THEM IS A MENDING" },
    ];
    label(svg, 24, 396, 10, PH_DIM).textContent = "THE DRIFT";
    const drift = label(svg, 104, 396, 10, PH_DIM);
    const foot = label(svg, 380, 396, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "BURIAL SPHERE OF NASSAK AN-RAH", T, 4, 1.4);
      // the envelope: seated whole through the wipe, apart by mid-cycle,
      // and home -- held home -- while the footer makes its claim.
      const ramp = (x) => x <= 0 ? 0 : x >= 1 ? 1 : (1 - Math.cos(Math.PI * x)) / 2;
      const e = ramp((T - 26) / 34) * (1 - ramp((T - 110) / 40));
      SHARDS.forEach((s, i) => {
        const d = e * (20 + 7 * Math.sin(t * .05 + i * 1.9));
        const spin = e * Math.sin(t * .03 + i * 2.4) * .5;
        const ox = Math.cos(s.mid) * d * .9, oy = Math.sin(s.mid) * d;
        const cs = Math.cos(spin), sn = Math.sin(spin);
        const put = s.base.map(([px, py]) => {
          const rx0 = px - s.cxm, ry0 = py - s.cym;
          return ((s.cxm + rx0 * cs - ry0 * sn + ox).toFixed(1) + "," +
                  (s.cym + rx0 * sn + ry0 * cs + oy).toFixed(1));
        });
        s.body.setAttribute("points", put.join(" "));
        s.rim.setAttribute("points", put.slice(s.arc0, s.arc1).join(" "));
      });
      drift.textContent = "(" + "~".repeat(1 + Math.round(e * 4)) + ")";
      motes.forEach(m => {
        const a = t * m.sp + m.ph;
        m.q.setAttribute("cx", 320 + Math.cos(a) * m.R);
        m.q.setAttribute("cy", 228 + Math.sin(a) * m.R * .85);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 160,66 166,66`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "THE SHARDS REMEMBER THEIR PLACES.", T, 120, 1.6);
    });
  });

  /* ---------------- 11-F: the burial sphere, shattered, tenanted ---------------- */
  FIG._define("sphere-f", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "CHAMBER 6 / ZERO-G / TENANTED";
    const CDOTS = stipple(svg, "dots-spheref", PH, .9);
    el(svg, "line", { x1: 296, y1: 44, x2: 296, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 344, y1: 44, x2: 344, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 290, y1: 96, x2: 350, y2: 96, stroke: PH_DIM });
    el(svg, "circle", { cx: 320, cy: 228, r: 132, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 2 });
    el(svg, "circle", { cx: 320, cy: 228, r: 122, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "5 4" });
    for (let a = 0; a < 24; a++) {
      const th = a * Math.PI / 12;
      el(svg, "line", { x1: 320 + Math.cos(th) * 114, y1: 228 + Math.sin(th) * 114,
        x2: 320 + Math.cos(th) * 108, y2: 228 + Math.sin(th) * 108, stroke: PH_DIM });
    }
    el(svg, "ellipse", { cx: 320, cy: 356, rx: 26, ry: 7, fill: BG,
      stroke: PH, "stroke-width": 1.4 });
    const six = label(svg, 424, 300, 64, PH_DIM);
    six.setAttribute("opacity", .3); six.textContent = "6";
    // the ghost of the oval: the house, as it stood
    el(svg, "ellipse", { cx: 320, cy: 232, rx: 30, ry: 52, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "2 5", opacity: .5 });
    // the throat still feeds it
    const strands = Array.from({ length: 3 }, () =>
      el(svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.5 }));
    // 11-E's full-cut shards, spinning outward -- and never coming home
    const IMPACT = [312, 220];
    const crackPts = (j) => {
      const jj = j % 6;
      const bx = 320 + Math.cos(jj * Math.PI / 3) * 30,
            by = 232 + Math.sin(jj * Math.PI / 3) * 52;
      const dx = bx - IMPACT[0], dy = by - IMPACT[1], L = Math.hypot(dx, dy);
      const pts = [];
      for (let k = 1; k < 4; k++) {
        const f = k / 4, jog = Math.sin(jj * 2.7 + k * 3.1) * 4.5;
        pts.push([IMPACT[0] + dx * f - dy / L * jog,
                  IMPACT[1] + dy * f + dx / L * jog]);
      }
      return pts;
    };
    const SHARDS = Array.from({ length: 6 }, (_, i) => {
      const base = [IMPACT.slice()];
      base.push(...crackPts(i));
      const arc0 = base.length;
      for (let k = 0; k <= 6; k++) {
        const a = (i + k / 6) * Math.PI / 3;
        base.push([320 + Math.cos(a) * 30, 232 + Math.sin(a) * 52]);
      }
      const arc1 = base.length;
      base.push(...crackPts(i + 1).reverse());
      const cxm = base.reduce((s, p) => s + p[0], 0) / base.length;
      const cym = base.reduce((s, p) => s + p[1], 0) / base.length;
      return {
        base, arc0, arc1, cxm, cym,
        mid: (i + .5) * Math.PI / 3,
        body: el(svg, "polygon", { fill: CDOTS, stroke: PH,
          "stroke-width": .9, "stroke-opacity": .7 }),
        rim: el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT,
          "stroke-width": 1.8 }),
      };
    });
    // THE TENANT, out: the coil at the heart of its broken house (from 11-B)
    const knot = el(svg, "circle", { cx: 320, cy: 234, r: 13, fill: FUNGUS,
      "fill-opacity": .28, stroke: FUNGUS, "stroke-width": 1.4 });
    const tendrils = Array.from({ length: 9 }, (_, i) => {
      const under = i >= 5;
      return el(svg, "polyline", { fill: "none", stroke: FUNGUS,
        "stroke-width": under ? 1.1 : 1.6, opacity: under ? .45 : 1 });
    });
    const motes = Array.from({ length: 8 }, (_, i) =>
      ({ q: el(svg, "circle", { r: i % 3 ? 1 : 1.6, fill: PH_DIM }),
         R: 44 + (i * 29) % 68, ph: i * .8, sp: .04 + (i % 3) * .015 }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 62, 10, PH);
    const CALLS = [
      { at: [320, 234], text: "TENANT: OUT" },
      { at: [352, 198], text: "SHARDS: SIX, SPINNING OUTWARD" },
      { at: [320, 96], text: "THROAT: THE FUNGUS STILL COMES DOWN IT" },
      { at: [204, 310], text: "PRAYERS: ONE OF THEM IS A WRATH" },
    ];
    label(svg, 24, 396, 10, PH_DIM).textContent = "THE CHURN";
    const breath = label(svg, 110, 396, 10, FUNGUS);
    const foot = label(svg, 550, 396, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "BURIAL SPHERE OF NASSAK AN-RAH", T, 4, 1.4);
      SHARDS.forEach((s, i) => {
        const d = 20 + 7 * Math.sin(t * .05 + i * 1.9);
        const spin = Math.sin(t * .03 + i * 2.4) * .5;
        const ox = Math.cos(s.mid) * d * .9, oy = Math.sin(s.mid) * d;
        const cs = Math.cos(spin), sn = Math.sin(spin);
        const put = s.base.map(([px, py]) => {
          const rx0 = px - s.cxm, ry0 = py - s.cym;
          return ((s.cxm + rx0 * cs - ry0 * sn + ox).toFixed(1) + "," +
                  (s.cym + rx0 * sn + ry0 * cs + oy).toFixed(1));
        });
        s.body.setAttribute("points", put.join(" "));
        s.rim.setAttribute("points", put.slice(s.arc0, s.arc1).join(" "));
      });
      const br = [0, 1, 2, 3, 4, 4, 3, 2, 1, 0][Math.floor(t / 3) % 10];
      knot.setAttribute("r", 12 + br);
      breath.textContent = "(" + "~".repeat(3 + br) + ")";
      tendrils.forEach((n, i) => {                           // coiling TALL
        const under = i >= 5;
        const a0 = i * (Math.PI * 2 / (under ? 4 : 5)) + t * (under ? -.06 : .09);
        const w = Math.sin(t * .5 + i * 1.7) * 5;
        const reach = under ? .8 : 1;
        const pts = [1, 2, 3, 4].map(k => {
          const r = (8 + k * (7 + br * .8)) * reach;
          const a = a0 + w * .02 * k + Math.sin(t * .3 + k * 1.3 + i) * .22;
          return `${320 + Math.cos(a) * r * .55},${234 + Math.sin(a) * r}`;
        });
        n.setAttribute("points", `320,234 ` + pts.join(" "));
      });
      strands.forEach((n, i) => {
        const sw = Math.sin(t * .22 + i * 2.1) * 5;
        n.setAttribute("points",
          `${306 + i * 14},46 ${306 + i * 14 + sw},96 ` +
          `${312 + i * 8 + sw},140 ${318 + i * 2},210`);     // reaching the tenant
      });
      motes.forEach(m => {
        const a = t * m.sp + m.ph;
        m.q.setAttribute("cx", 320 + Math.cos(a) * m.R);
        m.q.setAttribute("cy", 228 + Math.sin(a) * m.R * .85);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 160,66 166,66`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "IT MINDED.", T, 120, 1.6);
    });
  });

  /* ---------------- 11-D: the burial sphere, reforged ---------------- */
  FIG._define("sphere-d", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "CHAMBER 6 / ZERO-G / AT REST";
    const CDOTS = stipple(svg, "dots-sphered", PH, .9);
    el(svg, "line", { x1: 296, y1: 44, x2: 296, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 344, y1: 44, x2: 344, y2: 102, stroke: PH, "stroke-width": 1.6 });
    el(svg, "line", { x1: 290, y1: 96, x2: 350, y2: 96, stroke: PH_DIM });
    el(svg, "circle", { cx: 320, cy: 228, r: 132, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 2 });
    el(svg, "circle", { cx: 320, cy: 228, r: 122, fill: "none",
      stroke: PH_DIM, "stroke-dasharray": "5 4" });
    for (let a = 0; a < 24; a++) {
      const th = a * Math.PI / 12;
      el(svg, "line", { x1: 320 + Math.cos(th) * 114, y1: 228 + Math.sin(th) * 114,
        x2: 320 + Math.cos(th) * 108, y2: 228 + Math.sin(th) * 108, stroke: PH_DIM });
    }
    el(svg, "ellipse", { cx: 320, cy: 356, rx: 26, ry: 7, fill: BG,
      stroke: PH, "stroke-width": 1.4 });
    const six = label(svg, 424, 300, 64, PH_DIM);
    six.setAttribute("opacity", .3); six.textContent = "6";
    // THE COFFIN, reforged: the oval whole, no seam left to point at
    const ring = el(svg, "ellipse", { cx: 320, cy: 234, fill: "none",
      stroke: PH, "stroke-width": 1 });                       // each breath leaves it
    const coffin = el(svg, "ellipse", { cx: 320, cy: 232, rx: 30, ry: 52,
      fill: CDOTS, stroke: PH_BRIGHT, "stroke-width": 1.8 });
    const pulse = el(svg, "circle", { cx: 320, cy: 234, fill: PH,
      "fill-opacity": .22, stroke: PH, "stroke-width": 1.2 });
    const motes = Array.from({ length: 8 }, (_, i) =>
      ({ q: el(svg, "circle", { r: i % 3 ? 1 : 1.6, fill: PH_DIM }),
         R: 44 + (i * 29) % 68, ph: i * .8, sp: .04 + (i % 3) * .015 }));
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 16, 62, 10, PH);
    const CALLS = [
      { at: [320, 106], text: "FIELD: ANTI-ENTROPY, HOLDING" },
      { at: [320, 180], text: "SEAM: CLOSED. THE GLASS FORGAVE IT" },
      { at: [320, 234], text: "TENANT: ASLEEP, DREAMING SOMETHING KIND" },
      { at: [204, 310], text: "PRAYERS: ANSWERED" },
    ];
    label(svg, 24, 396, 10, PH_DIM).textContent = "THE KEEPING";
    const breath = label(svg, 122, 396, 10, PH);
    const foot = label(svg, 336, 396, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "BURIAL SPHERE OF NASSAK AN-RAH", T, 4, 1.4);
      const C = 60;                                 // sleep-slow: five seconds a breath
      const ph = (t % C) / C;
      const br = Math.round(Math.sin(ph * Math.PI) * 4);      // 0..4..0, quantized
      pulse.setAttribute("r", 9 + br);
      coffin.setAttribute("stroke-width", 1.6 + br * .1);
      ring.setAttribute("rx", 12 + ph * 14);                  // the exhale walks
      ring.setAttribute("ry", 12 + ph * 36);                  // out to the glass
      ring.setAttribute("opacity", Math.max(0, .5 - ph * .5).toFixed(2));
      breath.textContent = "(" + "~".repeat(2 + br) + ")";
      motes.forEach(m => {
        const a = t * m.sp + m.ph;
        m.q.setAttribute("cx", 320 + Math.cos(a) * m.R);
        m.q.setAttribute("cy", 228 + Math.sin(a) * m.R * .85);
      });
      const c = CALLS[Math.floor(T / 30) % CALLS.length];
      if (T > 14) {
        callLead.setAttribute("points", `${c.at[0]},${c.at[1]} 160,66 166,66`);
        call.textContent = c.text;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "FOUR THOUSAND YEARS INTO A GOOD NIGHT'S SLEEP.", T, 120, 1.6);
    });
  });


  /* ---------------- 05-C: one bat, portrait ---------------- */
  FIG._define("bats-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.8,
      points: "220,64 300,58 340,60 420,66" });               // the rock lip
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
      points: "308,60 306,74 312,70 316,74 314,60" });        // the gripping feet
    // the neighbors: more of the eleven hundred, folded and dimmer
    [[244, .62, .55], [398, .7, .6], [438, .5, .4]].forEach(([cx, sc, op]) => {
      const g = document.createElementNS(NS, "g");
      g.setAttribute("opacity", op); svg.appendChild(g);
      const put = (name, attrs) => { const n = document.createElementNS(NS, name);
        for (const k in attrs) n.setAttribute(k, attrs[k]); g.appendChild(n); return n; };
      put("polyline", { fill: "none", stroke: PH_DIM, "stroke-width": 1.2,
        points: `${cx - 2},62 ${cx - 4},70 ${cx + 4},70 ${cx + 2},62` });
      put("path", { d: `M ${cx - 2},70 Q ${cx - 18 * sc},${70 + 42 * sc} ` +
        `${cx - 10 * sc},${70 + 96 * sc} Q ${cx - 4 * sc},${70 + 112 * sc} ${cx},${70 + 116 * sc} L ${cx - 2},70`,
        fill: "none", stroke: PH, "stroke-width": 1.3 });
      put("path", { d: `M ${cx + 2},70 Q ${cx + 18 * sc},${70 + 42 * sc} ` +
        `${cx + 10 * sc},${70 + 96 * sc} Q ${cx + 4 * sc},${70 + 112 * sc} ${cx},${70 + 116 * sc} L ${cx + 2},70`,
        fill: "none", stroke: PH, "stroke-width": 1.3 });
      put("circle", { cx, cy: 70 + 124 * sc, r: 9 * sc, fill: "none",
        stroke: PH, "stroke-width": 1.2 });
      put("polygon", { points: `${cx - 6 * sc},${70 + 128 * sc} ${cx - 10 * sc},${70 + 146 * sc} ` +
        `${cx - 2 * sc},${70 + 132 * sc}`, fill: "none", stroke: PH_DIM });
      put("polygon", { points: `${cx + 6 * sc},${70 + 128 * sc} ${cx + 10 * sc},${70 + 146 * sc} ` +
        `${cx + 2 * sc},${70 + 132 * sc}`, fill: "none", stroke: PH_DIM });
    });
    const body = el(svg, "g", {});
    const inB = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); body.appendChild(n); return n; };
    // the folded wings: teardrops with the finger bones showing
    inB("path", { d: "M 310 74 Q 282 120 292 196 Q 300 224 310 226 L 310 74",
      fill: "none", stroke: PH, "stroke-width": 1.6 });
    inB("path", { d: "M 314 74 Q 342 120 332 196 Q 324 224 314 226 L 314 74",
      fill: "none", stroke: PH, "stroke-width": 1.6 });
    [[296, 100, 294, 180], [301, 92, 299, 196], [323, 92, 325, 196], [328, 100, 330, 180]]
      .forEach(([x1, y1, x2, y2]) =>
        inB("line", { x1, y1, x2, y2, stroke: PH_DIM }));      // the fingers
    // the head, upside down at the bottom: ears pointing DOWN
    inB("circle", { cx: 312, cy: 238, r: 14, fill: "none", stroke: PH, "stroke-width": 1.6 });
    const earA = inB("polygon", { fill: "none", stroke: PH, "stroke-width": 1.4 });
    const earB = inB("polygon", { fill: "none", stroke: PH, "stroke-width": 1.4 });
    inB("polyline", { fill: "none", stroke: PH_DIM, points: "306,244 312,248 318,244" });
    // every resident gets two glowing red eyes; they open on the last beats
    const RED = "#ff5252";
    const pair = (x1, y1, x2, y2, r) => {
      const g = document.createElementNS(NS, "g");
      g.setAttribute("opacity", 0); svg.appendChild(g);
      [[x1, y1], [x2, y2]].forEach(([x, y]) => {
        const halo = document.createElementNS(NS, "circle");
        halo.setAttribute("cx", x); halo.setAttribute("cy", y);
        halo.setAttribute("r", r * 2.2); halo.setAttribute("fill", RED);
        halo.setAttribute("fill-opacity", .3); g.appendChild(halo);
        const core = document.createElementNS(NS, "circle");
        core.setAttribute("cx", x); core.setAttribute("cy", y);
        core.setAttribute("r", r); core.setAttribute("fill", RED); g.appendChild(core);
      });
      return g;
    };
    const eyes = [                                            // left to right, star last
      pair(244 - 3.2, 70 + 121 * .62, 244 + 3.2, 70 + 121 * .62, 1.6),
      pair(398 - 3.6, 70 + 121 * .7, 398 + 3.6, 70 + 121 * .7, 1.8),
      pair(438 - 2.6, 70 + 121 * .5, 438 + 2.6, 70 + 121 * .5, 1.3),
      pair(306, 234, 318, 234, 2.4),
    ];
    label(svg, 24, 334, 10, PH_DIM).textContent = "LIGHT";
    const cells = Array.from({ length: 10 }, (_, i) =>
      el(svg, "rect", { x: 84 + i * 16, y: 324, width: 12, height: 11,
        fill: "#ffd76a", "fill-opacity": .08 }));
    const foot = label(svg, 430, 334, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 160;
      doWipe(T);
      typeOn(hdr, "RESIDENTS, HALL OF YOUTH (THOUSANDS)", T, 4, 1.4);
      const br = [0, 1, 2, 2, 1, 0][Math.floor(t / 4) % 6];   // the breath
      body.setAttribute("transform", `translate(0 ${br * .8})`);
      const tw = T > 118 ? 4 : 0;                             // the ears hear it
      earA.setAttribute("points", `302,246 ${294 - tw},272 306,254`);
      earB.setAttribute("points", `318,248 ${326 + tw},274 322,254`);
      const on = Math.min(10, Math.floor(T / 12));
      cells.forEach((r, i) => r.setAttribute("fill-opacity", i < on ? .8 : .08));
      // the last four beats of the gauge: eyes open, pair by pair
      eyes.forEach((g, i) => g.setAttribute("opacity", on >= 7 + i ? 1 : 0));
      foot.textContent = T > 118 ? "OPINION OF LIGHT: FORMING." : "";
    });
  });

  /* ---------------- 06-B: the burial cylinders, intact (factory) ----------------
     Re-stamped from cylCard (CCB): canon station order and the kit visible
     in every cylinder -- blade, mask, boots, igniter-and-bloom. */
  FIG._define("cylinders-b", "svg", function (svg) {
    cylCard(svg, "b", [],
      "THE BURIAL CYLINDERS (INTACT)",
      "AS THE TOMBWRIGHTS LEFT THEM. NOTHING HAS COME SCAVENGING. YET.");
  });

  /* ---------------- 17-C: the approach, old man crown, thin curls ---------------- */
  FIG._define("ext1c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    const XDOTS = stipple(svg, "dots-ext1c", PH, .8);
    el(svg, "line", { x1: 0, y1: 300, x2: 640, y2: 300, stroke: FUNGUS,
      "stroke-width": 1.4, opacity: .8 });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "20,296 70,282 120,294 150,288 190,297" });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "470,297 520,286 560,292 610,283 640,294" });
    el(svg, "rect", { x: 0, y: 301, width: 640, height: 99, fill: XDOTS, opacity: .35 });
    for (let i = 0; i < 14; i++)
      el(svg, "line", { x1: 30 + (i * 97) % 610, y1: 318 + (i * 37) % 70,
        x2: 36 + (i * 97) % 610, y2: 316 + (i * 37) % 70, stroke: PH_DIM });
    const cloud = el(svg, "polyline", { fill: "none", stroke: PH_DIM, opacity: .6,
      points: "0,0" });
    el(svg, "polygon", { fill: XDOTS, stroke: PH, "stroke-width": 1.8, points:
      "286,104 290,74 300,62 314,58 320,64 326,60 332,40 338,52 340,58 " +
      "344,62 344,76 352,78 354,66 362,68 368,80 " +
      "372,110 360,190 358,246 354,300 286,300 " +
      "282,250 288,214 278,196 284,188 276,180 286,172 282,162 288,140 " });
    el(svg, "path", { d: "M 322 66 Q 326 70 330 67", fill: "none", stroke: PH_DIM });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
      "358,150 350,158 354,168 348,176 356,184" });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, opacity: .7,
      points: "312,84 316,140 308,200 314,260" });
    el(svg, "circle", { cx: 320, cy: 252, r: 26, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    el(svg, "path", { d: "M 306 246 Q 311 250 316 246", fill: "none",
      stroke: PH, "stroke-width": 1.2 });
    el(svg, "path", { d: "M 324 246 Q 329 250 334 246", fill: "none",
      stroke: PH, "stroke-width": 1.2 });
    el(svg, "line", { x1: 320, y1: 252, x2: 318, y2: 258, stroke: PH_DIM });
    el(svg, "path", { d: "M 311 300 L 311 276 Q 320 264 329 276 L 329 300 Z",
      fill: BG, stroke: PH, "stroke-width": 1.5 });
    // the thin curls, rising from the mouth like handwriting
    const tendrils = Array.from({ length: 3 }, () =>
      el(svg, "polyline", { fill: "none", stroke: FUNGUS, "stroke-width": 1.8 }));
    const sBody = el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.4 });
    const sHead = el(svg, "circle", { r: 2.6, fill: PH_BRIGHT });
    const sLegs = el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.2 });
    const thought = label(svg, 0, 0, 9, PH_DIM);
    const foot = label(svg, 320, 392, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 220;
      doWipe(T);
      tendrils.forEach((n, i) => {
        const bx = 344 + i * 4, sway = Math.sin(t * .12 + i * 2) * 6;
        const pts = Array.from({ length: 7 }, (_, k) => {
          const a = -Math.PI / 2 + k * .5 * (i % 2 ? 1 : -1) + sway * .02 * k;
          const r = 8 + k * 5;
          return `${bx + Math.cos(a) * r * .8 + sway * k * .12},${68 - k * 7 + Math.sin(a) * r * .3}`;
        });
        n.setAttribute("points", `${bx},${72 + i * 2} ` + pts.join(" "));
      });
      const cx = ((t * .7) % 760) - 60;
      cloud.setAttribute("points",
        `${cx},110 ${cx + 24},102 ${cx + 52},106 ${cx + 78},100 ${cx + 96},110`);
      const wx = Math.min(214, 60 + Math.floor(T * 1.2));
      const standing = wx >= 214;
      const step = standing ? 0 : (t % 4 < 2 ? 3 : -3);
      const sy = 336;
      sHead.setAttribute("cx", wx + 106); sHead.setAttribute("cy", sy - 15);
      sBody.setAttribute("points", `${wx + 106},${sy - 12} ${wx + 106},${sy - 4}`);
      sLegs.setAttribute("points",
        `${wx + 103 + step * .4},${sy + 4} ${wx + 106},${sy - 4} ${wx + 109 - step * .4},${sy + 4}`);
      thought.setAttribute("x", wx + 114); thought.setAttribute("y", sy - 22);
      thought.textContent = standing && (T % 20) > 8 ? ". . ." : "";
      typeOn(foot, "HIS SENTENCE CONTINUES UNDERGROUND.", T, 168, 1.4);
    });
  });


  /* ---------------- 00: the road to Gnomon ---------------- */
  FIG._define("road", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const pace = label(svg, 624, 24, 10, PH_DIM); pace.setAttribute("text-anchor", "end");
    pace.textContent = "PACE: DESPERATE / RATIONS: SPOKEN FOR / WEATHER: CACKLEMAW";
    // the dunes
    el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
      "0,236 90,228 180,240 300,226 420,238 540,228 640,236" });
    el(svg, "line", { x1: 0, y1: 268, x2: 640, y2: 268, stroke: PH, "stroke-width": 1.4 });
    el(svg, "line", { x1: 0, y1: 269, x2: 640, y2: 269, stroke: FUNGUS, opacity: .4 });
    // THE WAGON, whole: hoops, bed, wheels, yoke, zoxen, driver
    const gW = document.createElementNS(NS, "g"); svg.appendChild(gW);
    const W = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); gW.appendChild(n); return n; };
    W("line", { x1: 96, y1: 240, x2: 214, y2: 240, stroke: PH, "stroke-width": 2 }); // the bed
    for (let i = 0; i < 4; i++)                                          // the ribs
      W("path", { d: `M ${106 + i * 26} 240 Q ${119 + i * 26} 198 ${132 + i * 26} 240`,
        fill: "none", stroke: PH, "stroke-width": 1.4 });
    W("polyline", { fill: "none", stroke: PH_DIM,
      points: "104,214 128,206 158,204 188,206 210,214" });              // the canvas line
    const wheels = [[122, 254], [196, 254]].map(([x, y]) => {
      W("circle", { cx: x, cy: y, r: 14, fill: "none", stroke: PH, "stroke-width": 1.6 });
      return { x, y, spokes: [0, 1, 2].map(() =>
        W("line", { stroke: PH_DIM, "stroke-width": 1.2 })) };
    });
    W("line", { x1: 214, y1: 244, x2: 252, y2: 250, stroke: PH, "stroke-width": 1.4 }); // yoke
    // the zoxen, plodding
    const zox = [[258, 238], [292, 240]].map(([x, y]) => ({
      x, y,
      body: W("ellipse", { cx: x + 12, cy: y, rx: 16, ry: 9, fill: "none",
        stroke: PH, "stroke-width": 1.5 }),
      head: W("polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
        points: `${x + 26},${y - 4} ${x + 36},${y} ${x + 34},${y + 6}` }),
      legs: W("polyline", { fill: "none", stroke: PH, "stroke-width": 1.4 }),
    }));
    const driver = W("g", {});
    const dv = (name, attrs) => { const n = document.createElementNS(NS, name);
      for (const k in attrs) n.setAttribute(k, attrs[k]); driver.appendChild(n); return n; };
    dv("circle", { cx: 208, cy: 222, r: 3.4, fill: PH_BRIGHT });
    dv("polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.3,
      points: "208,226 208,236 202,240" });
    // the roster
    const R = [
      { y: 80,  a: "MERCHANT ......... WITH THE WAGON", b: "MERCHANT ......... LOST (MOONSET)" },
      { y: 102, a: "ZOXEN x2 ......... PULLING",        b: "ZOXEN x2 ......... LOST" },
      { y: 124, a: "TEAMSTER ......... DRIVING",        b: "TEAMSTER ......... FLED SOUTH" },
      { y: 146, a: "YOU .............. NOT YET HERE",   b: "YOU .............. INCOMING" },
    ].map(r => ({ ...r, n: label(svg, 24, r.y, 10, PH) }));
    // the teamster, fleeing: a little walking figure, not an ambiguous dot
    const flee = el(svg, "g", { opacity: 0 });
    el(flee, "circle", { cx: 0, cy: -12, r: 3, fill: PH_BRIGHT });
    el(flee, "line", { x1: 0, y1: -9, x2: 0, y2: 2, stroke: PH_BRIGHT,
      "stroke-width": 1.4 });
    const fleeLegs = el(flee, "polyline", { fill: "none", stroke: PH_BRIGHT,
      "stroke-width": 1.3 });
    const foot = label(svg, 320, 384, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = Math.min(t, 259); // a title card: plays once, holds the tableau
      doWipe(T);
      typeOn(hdr, "ROAD TO GNOMON", T, 4, 1.4);
      const fallen = T >= 130;
      const wx = fallen ? 200 : Math.floor(T * 1.6);
      gW.setAttribute("transform",
        `translate(${wx} 0)` + (fallen ? " rotate(-11 200 254)" : ""));
      wheels.forEach(w => w.spokes.forEach((sp, i) => {
        const a = (fallen ? 0 : t * .5) + i * Math.PI / 3;
        sp.setAttribute("x1", w.x - Math.cos(a) * 12); sp.setAttribute("y1", w.y - Math.sin(a) * 12);
        sp.setAttribute("x2", w.x + Math.cos(a) * 12); sp.setAttribute("y2", w.y + Math.sin(a) * 12);
      }));
      zox.forEach((z, i) => {
        if (!fallen) {
          const st = ((t + i * 2) % 4 < 2) ? 4 : -4;
          z.legs.setAttribute("points",
            `${z.x + 2 + st},268 ${z.x + 4},248 ${z.x + 10},248 ${z.x + 10 - st},268 ` +
            `${z.x + 18 + st},268 ${z.x + 18},248 ${z.x + 24},248 ${z.x + 24 - st},268`);
          z.body.setAttribute("transform", ""); z.head.setAttribute("transform", "");
          z.head.setAttribute("opacity", 1);
        } else {                                    // arranged by the wind, as if asleep
          z.legs.setAttribute("points",
            `${z.x - 2},262 ${z.x + 8},264 ${z.x + 18},262 ${z.x + 28},264`);
          const down = `translate(0 14) rotate(8 ${z.x + 12} ${z.y})`;
          z.body.setAttribute("transform", down);
          z.head.setAttribute("transform", down);
          z.head.setAttribute("opacity", .4);
        }
      });
      // gone from the bench at moonset -- REMOVED, not just faded: some
      // renderers (Safari) leave stale paint behind attribute-only hides
      if (fallen && driver.isConnected) driver.remove();
      driver.setAttribute("opacity", fallen ? 0 : 1);
      if (fallen && T < 170) {                      // the teamster, fleeing south
        flee.setAttribute("opacity", 1);
        flee.setAttribute("transform",
          `translate(${420 + (T - 130) * 3} ${292 + (T - 130) * 2.4})`);
        const st = (t % 4 < 2) ? 4 : -4;
        fleeLegs.setAttribute("points", `${-st},10 0,2 ${st},10`);
      } else if (flee.isConnected && T >= 170) flee.remove();
      R.forEach((r, i) => {
        if (!fallen) typeOn(r.n, r.a, T, 16 + i * 14, 1.6);
        else { r.n.textContent = r.b; r.n.setAttribute("fill", i === 3 ? PH_BRIGHT : PH_DIM); }
      });
      typeOn(foot, "THE ROAD TO GNOMON IS WALKED ONLY BY THE DESPERATE. PROVEN AGAIN.",
        T, 176, 1.7);
    });
  });

  /* ---------------- 13-E: the Horror, ablaze, firelit ---------------- */
  FIG._define("autarch-e", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 420, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "FALLEN AUTARCHY / BONE / FIRELIT";
    const ADOTS = stipple(svg, "dots-autarche", PH, .9);
    const ODOTS = stipple(svg, "dots-orangee", FUNGUS, 1.2);
    const YELLOW = "#ffd76a", CHAR = [74, 42, 20];             // burnt umber, as rgb
    const ORANGE = [255, 154, 60];
    const mix = (a, b, k) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * k)).join(",")})`;
    const CX = 320, CY = 180;
    const ring = el(svg, "circle", { cx: CX, cy: CY, r: 118, fill: "none",
      stroke: PH_DIM, "stroke-width": 1.4 });
    const spikes = Array.from({ length: 20 }, (_, i) => {
      const a = i * Math.PI / 10;
      return el(svg, "polygon", { fill: PH, "fill-opacity": .35, stroke: PH,
        "stroke-width": 1, points:
        `${CX + Math.cos(a - .07) * 118},${CY + Math.sin(a - .07) * 118} ` +
        `${CX + Math.cos(a + .04) * (142 + (i % 2) * 18)},${CY + Math.sin(a + .04) * (142 + (i % 2) * 18)} ` +
        `${CX + Math.cos(a + .13) * 118},${CY + Math.sin(a + .13) * 118}` });
    });
    const curls = Array.from({ length: 8 }, (_, i) => {
      const a = i * Math.PI / 4 + .4;
      const pts = [70, 82, 94, 106, 116].map((r, k) => {
        const aa = a + (k % 2 ? .11 : -.07);
        return `${CX + Math.cos(aa) * r},${CY + Math.sin(aa) * r}`;
      });
      return el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.4,
        opacity: .55, points: pts.join(" ") });
    });
    const skull = el(svg, "polygon", { points:
      "272,128 368,128 382,160 380,214 370,236 364,258 276,258 270,236 260,214 258,160",
      fill: ADOTS, stroke: PH, "stroke-width": 1.8 });
    [0, 1, 2].forEach(r =>
      el(svg, "polyline", { fill: "none", stroke: PH_DIM, points:
        Array.from({ length: 9 }, (_, k) =>
          `${272 + k * 12},${132 + r * 7 + (k % 2) * 3}`).join(" ") }));
    el(svg, "ellipse", { cx: 296, cy: 188, rx: 14, ry: 10, fill: ODOTS,
      stroke: PH, "stroke-width": 1.4 });
    el(svg, "ellipse", { cx: 344, cy: 188, rx: 14, ry: 10, fill: ODOTS,
      stroke: PH, "stroke-width": 1.4 });
    const glowL = el(svg, "ellipse", { cx: 296, cy: 188, rx: 6, ry: 4,
      fill: YELLOW, "fill-opacity": .6 });
    const glowR = el(svg, "ellipse", { cx: 344, cy: 188, rx: 6, ry: 4,
      fill: YELLOW, "fill-opacity": .6 });
    el(svg, "path", { d: "M 320 204 L 312 230 Q 320 238 328 230 Z",
      fill: BG, stroke: PH, "stroke-width": 1.4 });
    el(svg, "line", { x1: 294, y1: 240, x2: 346, y2: 240, stroke: PH, "stroke-width": 1.4 });
    el(svg, "line", { x1: 294, y1: 252, x2: 346, y2: 252, stroke: PH, "stroke-width": 1.4 });
    for (let x = 294; x <= 346; x += 6.5)
      el(svg, "line", { x1: x, y1: 240, x2: x, y2: 252, stroke: PH });
    el(svg, "rect", { x: 320.5, y: 240.5, width: 5.5, height: 11, fill: BG });
    const beads = [];
    for (let r = 0; r < 6; r++) for (let k = 0; k < 8 - (r > 3 ? 1 : 0); k++)
      beads.push(el(svg, "circle", { cx: 286 + k * 10 + (r % 2) * 5, cy: 268 + r * 13,
        r: 4.4, fill: PH, "fill-opacity": .75, stroke: PH, "stroke-width": 1 }));
    el(svg, "rect", { x: 282, y: 300, width: 78, height: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.2 });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "268,258 218,290 186,340 176,392" });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "372,258 422,290 454,340 464,392" });
    // THE ROPES (charring) and THE FIRE (working the bust)
    const ROOTS = [
      [232, 268, -2.6], [408, 268, -.5], [258, 152, 3.4], [384, 150, -.2],
      [320, 344, 1.57], [206, 306, 2.9], [436, 306, .3], [320, 122, -1.57],
      [288, 338, 2.2], [352, 338, .9],
    ];
    const tendrils = ROOTS.map(() =>
      el(svg, "polygon", { "fill-opacity": .3, "stroke-width": 1.4 }));
    const FROOTS = [[250, 262], [300, 260], [352, 262], [396, 258], [270, 130],
      [366, 132], [230, 300], [412, 298], [320, 118]];
    const flames = FROOTS.map(() =>
      el(svg, "polygon", { stroke: "none" }));
    const embers = Array.from({ length: 22 }, (_, i) => {
      const x = 184 + i * 13;
      return { x, ph: i * 23, dir: (x < 320 ? -1 : 1) * (.35 + (i % 5) * .4),
        q: el(svg, "circle", { r: i % 3 ? 1.4 : 2.1,
          fill: i % 4 ? YELLOW : FUNGUS }) };
    });
    label(svg, 24, 410, 10, PH_DIM).textContent = "VIGOR";
    const cells = Array.from({ length: 5 }, (_, i) =>
      el(svg, "rect", { x: 76 + i * 18, y: 400, width: 14, height: 12,
        fill: FUNGUS, "fill-opacity": .8 }));
    const foot = label(svg, 400, 410, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 420, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "THE HORROR, ABLAZE", T, 4, 1.4);
      const burn = Math.max(0, Math.min(1, (T - 20) / 140));  // the charring
      tendrils.forEach((n, i) => {
        const k = Math.max(0, Math.min(1, burn * 1.4 - i * .06));
        const col = mix(ORANGE, CHAR, k);
        n.setAttribute("fill", col); n.setAttribute("stroke", col);
        const [rx, ry, a0] = ROOTS[i];
        const calm = 1 - k * .75;                             // burnt ropes slow
        const w = Math.sin(t * .4 * calm + i * 1.9);
        const c = [[rx, ry]];
        for (let q = 1; q <= 4; q++) {
          const a = a0 + Math.sin(t * .25 * calm + q * 1.2 + i) * .3 * calm
            + w * .04 * q + k * .25 * (ry > 230 ? 1 : .3);    // and they sag
          const r = q * (13 + ((t + i * 5) % 12) * calm);
          c.push([rx + Math.cos(a) * r, ry + Math.sin(a) * r * .8]);
        }
        const W2 = [6, 4.8, 3.4, 1.9, .7];
        const L = [], R2 = [];
        for (let q = 0; q < c.length; q++) {
          const [x0, y0] = c[Math.max(0, q - 1)];
          const [x1, y1] = c[Math.min(c.length - 1, q + 1)];
          const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
          L.push(`${c[q][0] - dy / len * W2[q]},${c[q][1] + dx / len * W2[q]}`);
          R2.push(`${c[q][0] + dy / len * W2[q]},${c[q][1] - dx / len * W2[q]}`);
        }
        n.setAttribute("points", L.concat(R2.reverse()).join(" "));
      });
      flames.forEach((f, i) => {                              // the fire, working
        const [fx, fy] = FROOTS[i];
        const h = 16 + ((t * 7 + i * 13) % 17) + burn * 10;
        const wob = Math.sin(t * .9 + i * 2.2) * 5;
        f.setAttribute("points",
          `${fx - 7},${fy} ${fx + wob * .4},${fy - h * .55} ${fx + wob},${fy - h} ` +
          `${fx + 4 + wob * .3},${fy - h * .5} ${fx + 8},${fy}`);
        f.setAttribute("fill", (t + i) % 3 ? FUNGUS : YELLOW);
        f.setAttribute("fill-opacity", .5 + ((t + i) % 2) * .3);
      });
      embers.forEach(e2 => {                                // sparks, thrown wide
        const k = (t * 3 + e2.ph) % 200;
        e2.q.setAttribute("cx", e2.x + e2.dir * k * .55 + Math.sin((t + e2.ph) * .35) * 9);
        e2.q.setAttribute("cy", 282 - k * 1.05);
        e2.q.setAttribute("opacity", k > 168 ? 0 : .5 + ((t + e2.ph) % 3) * .25);
      });
      const beat = Math.floor(t / 8);                         // slow firelight,
      const AMBER = "#e5b955";                                // not a strobe
      spikes.forEach((n, i) => {
        const lit = (beat + i) % 5 === 0;
        n.setAttribute("stroke", lit ? AMBER : PH);
        n.setAttribute("fill", lit ? AMBER : PH);
      });
      curls.forEach((n, i) =>
        n.setAttribute("stroke", (beat + i) % 4 === 0 ? AMBER : PH));
      beads.forEach((n, i) => {                               // and in the beard
        const lit = ((beat * 5 + i * 7) % 23) < 3;
        n.setAttribute("fill", lit ? AMBER : PH);
        n.setAttribute("stroke", lit ? AMBER : PH);
      });
      skull.setAttribute("stroke", beat % 5 === 0 ? AMBER : PH);
      ring.setAttribute("stroke", (beat + 2) % 5 === 0 ? AMBER : PH_DIM);
      glowL.setAttribute("fill-opacity", .4 + ((t % 4) / 4) * .4);
      glowR.setAttribute("fill-opacity", .4 + (((t + 2) % 4) / 4) * .4);
      const vig = 5 - Math.min(5, Math.floor(burn * 5.5));
      cells.forEach((r, i) => r.setAttribute("fill-opacity", i < vig ? .8 : .08));
      foot.textContent = vig === 0 ? "IT DOES NOT CLOSE AGAIN." : "";
      if (vig > 0) typeOn(foot, "ABLAZE, IT CANNOT MEND. KEEP CUTTING.", T, 40, 1.6);
    });
  });



  /* ---------------- 18: the seal answers the jars ---------------- */
  FIG._define("seal", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF THE CANOPIC JARS / THE SOLVE";
    const JDOTS = stipple(svg, "dots-seal", PH, .9);
    const CRIM = "#ff3b57", WHITE = "#eaf6ff";
    const arch = el(svg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.8,
      d: "M 246 316 L 246 170 Q 320 108 394 170 L 394 316" });
    // the crimson gate, barred until the hall is fully attended
    const bars = [268, 294, 320, 346, 372].map(x =>
      el(svg, "line", { x1: x, y1: 186, x2: x, y2: 316, stroke: CRIM,
        "stroke-width": 2.4, opacity: .85 }));
    const crossbar = el(svg, "line", { x1: 252, y1: 254, x2: 388, y2: 254,
      stroke: CRIM, "stroke-width": 2, opacity: .85 });
    const PLINTHS = [128, 224, 320, 416, 512];
    PLINTHS.forEach(cx => {
      el(svg, "polygon", { fill: JDOTS, stroke: PH, "stroke-width": 1.4,
        points: `${cx - 28},344 ${cx + 28},344 ${cx + 22},316 ${cx - 22},316` });
      el(svg, "line", { x1: cx - 24, y1: 316, x2: cx + 24, y2: 316,
        stroke: PH, "stroke-width": 1.6 });
    });
    // the jars of 03-C: tapered vessels, each stoppered with its head
    const jar = kind => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      el(g, "polygon", { points: "-22,345 22,345 16,295 -16,295",
        fill: PH, "fill-opacity": .10, stroke: PH, "stroke-width": 1.5 });
      headGlyph(g, kind, 0);
      return g;
    };
    [["BABOON", 0], ["HUMAN", 1], ["MANTIS", 4]].forEach(([kind, i]) =>
      jar(kind).setAttribute("transform", `translate(${PLINTHS[i]} -29)`));
    const m1 = jar("FALCON"), m2 = jar("JACKAL");
    const blinks = [2, 3].map(i => el(svg, "rect", { x: PLINTHS[i] - 26, y: 220,
      width: 52, height: 96, fill: "none", stroke: PH_DIM,
      "stroke-dasharray": "4 3" }));
    // the seal itself
    const sealRing = el(svg, "circle", { cx: 320, cy: 158, r: 50, fill: "none",
      stroke: CRIM, "stroke-width": 2 });
    const inner = el(svg, "circle", { cx: 320, cy: 158, r: 35, fill: "none",
      stroke: CRIM, "stroke-width": 1.2 });
    const runes = Array.from({ length: 8 }, () =>
      el(svg, "line", { stroke: CRIM, "stroke-width": 1.6 }));
    const motes = Array.from({ length: 14 }, () =>
      el(svg, "circle", { r: 2, fill: WHITE, opacity: 0 }));
    const att = label(svg, 24, 390, 10, PH_DIM);
    const foot = label(svg, 380, 390, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 400, 2, 10);
    const q6 = x => Math.round(x / 6) * 6;
    clock(t => {
      const T = t % 220;
      doWipe(T);
      typeOn(hdr, "THE SEAL ANSWERS THE JARS", T, 4, 1.4);
      const x1 = T < 60 ? -60 : q6(-60 + Math.min(1, (T - 60) / 40) * 380);
      const x2 = T < 80 ? 700 : q6(700 - Math.min(1, (T - 80) / 44) * 284);
      m1.setAttribute("transform", `translate(${x1} -29)`);
      m2.setAttribute("transform", `translate(${x2} -29)`);
      const in1 = x1 >= 314, in2 = x2 <= 422;
      blinks[0].setAttribute("opacity", !in1 && t % 6 < 3 ? .8 : 0);
      blinks[1].setAttribute("opacity", !in2 && t % 6 < 3 ? .8 : 0);
      att.textContent = `ATTENDANCE: ${3 + in1 + in2} OF 5`;
      // the gate raises once the last jar is home
      const raise = Math.max(0, Math.min(1, (T - 130) / 30));
      bars.forEach(n => {
        n.setAttribute("y2", 316 - Math.round(raise * 21) * 6);
        n.setAttribute("opacity", raise >= 1 ? 0 : .85);
      });
      crossbar.setAttribute("y1", 254 - Math.round(raise * 10) * 6);
      crossbar.setAttribute("y2", 254 - Math.round(raise * 10) * 6);
      crossbar.setAttribute("opacity", raise >= .55 ? 0 : .85);
      // crimson while short-handed; white when answered; then motes
      const col = T < 130 ? CRIM : T < 138 ? "#ff9aa8" : T < 146 ? "#ffd9de" : WHITE;
      const gone = T >= 150;
      [sealRing, inner].forEach(n => { n.setAttribute("stroke", col);
        n.setAttribute("opacity", gone ? 0 : 1); });
      const rot = T < 130 ? t * .12 : 15.6;
      runes.forEach((n, i) => {
        const a = i * Math.PI / 4 + rot;
        n.setAttribute("x1", 320 + Math.cos(a) * 37); n.setAttribute("y1", 158 + Math.sin(a) * 37);
        n.setAttribute("x2", 320 + Math.cos(a) * 48); n.setAttribute("y2", 158 + Math.sin(a) * 48);
        n.setAttribute("stroke", col); n.setAttribute("opacity", gone ? 0 : 1);
      });
      sealRing.setAttribute("stroke-width", T < 130 ? 1.5 + (t % 6) / 4 : 2);
      motes.forEach((n, i) => {
        if (!gone) { n.setAttribute("opacity", 0); return; }
        const a = i * Math.PI * 2 / 14, r = (T - 150) * 2.2;
        n.setAttribute("cx", 320 + Math.cos(a) * r);
        n.setAttribute("cy", 158 + Math.sin(a) * r - (T - 150) * .6);
        n.setAttribute("opacity", Math.max(0, 1 - r / 110));
      });
      arch.setAttribute("stroke", gone ? PH_BRIGHT : PH_DIM);
      typeOn(foot, "THE DOOR STOPS ARGUING.", T, 152, 1.6);
    });
  });

  /* ---------------- 18-B: the hall, short-handed ---------------- */
  FIG._define("seal-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF THE CANOPIC JARS / SHORT-HANDED";
    const JDOTS = stipple(svg, "dots-seal-b", PH, .9);
    const CRIM = "#ff3b57";
    const arch = el(svg, "path", { fill: "none", stroke: PH_DIM, "stroke-width": 1.8,
      d: "M 246 316 L 246 170 Q 320 108 394 170 L 394 316" });
    // the crimson gate, barred: in this state it stays barred
    [268, 294, 320, 346, 372].forEach(x =>
      el(svg, "line", { x1: x, y1: 186, x2: x, y2: 316, stroke: CRIM,
        "stroke-width": 2.4, opacity: .85 }));
    el(svg, "line", { x1: 252, y1: 254, x2: 388, y2: 254, stroke: CRIM,
      "stroke-width": 2, opacity: .85 });
    const PLINTHS = [128, 224, 320, 416, 512];
    PLINTHS.forEach(cx => {
      el(svg, "polygon", { fill: JDOTS, stroke: PH, "stroke-width": 1.4,
        points: `${cx - 28},344 ${cx + 28},344 ${cx + 22},316 ${cx - 22},316` });
      el(svg, "line", { x1: cx - 24, y1: 316, x2: cx + 24, y2: 316,
        stroke: PH, "stroke-width": 1.6 });
    });
    const jar = kind => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      el(g, "polygon", { points: "-22,345 22,345 16,295 -16,295",
        fill: PH, "fill-opacity": .10, stroke: PH, "stroke-width": 1.5 });
      headGlyph(g, kind, 0);
      return g;
    };
    [["BABOON", 0], ["HUMAN", 1], ["MANTIS", 4]].forEach(([kind, i]) =>
      jar(kind).setAttribute("transform", `translate(${PLINTHS[i]} -29)`));
    // the two wanting: dashed ghosts over plinths that burn crimson from within
    const blinks = [2, 3].map(i => el(svg, "rect", { x: PLINTHS[i] - 26, y: 220,
      width: 52, height: 96, fill: "none", stroke: PH_DIM,
      "stroke-dasharray": "4 3" }));
    const embers = [2, 3].map(i => el(svg, "circle", { cx: PLINTHS[i], cy: 330,
      r: 8, fill: CRIM, opacity: .3 }));
    // the seal, turning in place with the patience of a lock
    const sealRing = el(svg, "circle", { cx: 320, cy: 158, r: 50, fill: "none",
      stroke: CRIM, "stroke-width": 2 });
    el(svg, "circle", { cx: 320, cy: 158, r: 35, fill: "none",
      stroke: CRIM, "stroke-width": 1.2 });
    const runes = Array.from({ length: 8 }, () =>
      el(svg, "line", { stroke: CRIM, "stroke-width": 1.6 }));
    const att = label(svg, 24, 390, 10, PH_DIM);
    const foot = label(svg, 306, 390, 10, FUNGUS);
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 140;
      doWipe(T);
      typeOn(hdr, "THE HALL OF THE CANOPIC JARS", T, 4, 1.4);
      blinks.forEach(n => n.setAttribute("opacity", t % 6 < 3 ? .8 : 0));
      embers.forEach((n, k) => n.setAttribute("opacity",
        .22 + .14 * Math.sin((t + k * 3) * .5)));
      const rot = t * .06;
      runes.forEach((n, i) => {
        const a = i * Math.PI / 4 + rot;
        n.setAttribute("x1", 320 + Math.cos(a) * 37); n.setAttribute("y1", 158 + Math.sin(a) * 37);
        n.setAttribute("x2", 320 + Math.cos(a) * 48); n.setAttribute("y2", 158 + Math.sin(a) * 48);
      });
      sealRing.setAttribute("stroke-width", 1.5 + (t % 6) / 4);
      att.textContent = "ATTENDANCE: 3 OF 5";
      typeOn(foot, "TWO STAND EMPTY. THE STAIR IS BARRED.", T, 40, 1.6);
    });
  });

  /* ---- chimCard: the fungal chimney, on its side (20 / 20-F/G/H, CCB) ----
     The shaft rotated across the card: rock above and below, the prayers'
     glow at the far end, thick tendrils spanning the width -- orange and
     spored while the growth lives, charred brown and ash-quiet once burnt
     -- and the glass centipede at double scale through the middle of it,
     whenever the tenant is home. ---- */
  function chimCard(svg, bug, burnt, hdrText, clsText, footText) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = clsText;
    [[52, -1], [326, 1]].forEach(([wy, dir]) => {              // the rock, above and below
      const pts = [];
      for (let x = 0; x <= 640; x += 26)
        pts.push(`${x},${wy + ((x / 26) % 3 - 1) * 5 * dir}`);
      el(svg, "polyline", { points: pts.join(" "), fill: "none",
        stroke: PH_DIM, "stroke-width": 1.5 });
      for (let x = 40; x < 620; x += 74)
        el(svg, "line", { x1: x, y1: wy + 4 * dir, x2: x + 8, y2: wy + 16 * dir,
          stroke: PH_DIM, opacity: .5 });
    });
    el(svg, "ellipse", { cx: 652, cy: 190, rx: 40, ry: 150, fill: "#ffd76a",
      "fill-opacity": .06 });                                  // the prayers, that way
    el(svg, "ellipse", { cx: 648, cy: 190, rx: 26, ry: 100, fill: "#ffd76a",
      "fill-opacity": .07 });
    const motes = Array.from({ length: burnt ? 5 : 12 }, (_, i) =>
      ({ y: 68 + (i * 41) % 240, ph: i * 47,
         q: el(svg, "circle", { r: i % 3 ? 1.2 : 1.8,
           fill: burnt ? PH_DIM : FUNGUS, opacity: burnt ? .35 : .5 }) }));
    const TCOL = burnt ? ["#5d4227", "#6f4e2c", "#6f4e2c", "#5d4227"]
      : ["#b36b2a", FUNGUS, FUNGUS, "#b36b2a"];
    const NODE = burnt ? "#41301f" : "#b36b2a";
    const TEND = [[72, 12], [128, 15], [254, 13], [300, 10]].map(([ty, w], i) =>
      ({ ty, ph: i * 1.7, q: el(svg, "polyline", { fill: "none", stroke: TCOL[i],
        "stroke-width": w, "stroke-linecap": "round", opacity: .85 }) }));
    TEND.forEach(td => [120, 330, 540].forEach(nx =>
      el(svg, "circle", { cx: nx + td.ph * 12, cy: td.ty, r: 5, fill: NODE })));
    const GLASS = "#cfefff";
    const wave = x => 190 + Math.sin(x * .018) * 16;           // dead centre of the shaft
    const DASH = [[20, 28], [44, 52], [68, 76], [92, 100], [116, 124], [140, 148]];
    // it does not stop when it goes unseen (CCB): 4 px/frame in the light,
    // 5 in the dark -- every reappearance is ahead of the vanishing point.
    const seenIn = T => DASH.reduce((a, [s2, e2]) =>
      a + Math.max(0, Math.min(T, e2 + 3) - s2), 0);
    const pos = T => { const sf = seenIn(T); return -40 + sf * 4 + (T - sf) * 5; };
    let segs = [], legs = [], feelers = [], glints = [], cells = [];
    if (bug) {
      segs = Array.from({ length: 16 }, () => el(svg, "ellipse",
        { rx: 16, ry: 10, fill: "none", stroke: GLASS, "stroke-width": 1.5, opacity: 0 }));
      legs = Array.from({ length: 32 }, () => el(svg, "line",
        { stroke: "#9fd9f2", "stroke-width": 1.3, opacity: 0 }));
      feelers = [0, 1].map(() => el(svg, "line",
        { stroke: GLASS, "stroke-width": 1.4, opacity: 0 }));
      glints = ["#ff5a5a", "#ffd76a", "#7fff9e", GLASS, GLASS,
        "#9fd9f2", GLASS, "#ffd76a"].map(c =>
        el(svg, "circle", { r: 3, fill: c, opacity: 0 }));
      label(svg, 24, 350, 10, PH_DIM).textContent = "VISIBILITY";
      cells = Array.from({ length: 6 }, (_, i) =>
        el(svg, "rect", { x: 110 + i * 16, y: 340, width: 12, height: 11,
          fill: GLASS, "fill-opacity": .08 }));
    }
    const foot = label(svg, 630, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 168;
      doWipe(T);
      typeOn(hdr, hdrText, T, 4, 1.4);
      TEND.forEach(td => {
        const pts = [];
        for (let x = -10; x <= 650; x += 40)
          pts.push(`${x},${td.ty + Math.sin(x * .012 + td.ph + t * (burnt ? .015 : .04)) * (burnt ? 4 : 9)}`);
        td.q.setAttribute("points", pts.join(" "));            // burnt growth barely sways
      });
      motes.forEach(s => {                                     // drifting shaft-wise
        const k = (t * (burnt ? .4 : .8) + s.ph) % 700;
        s.q.setAttribute("cx", k - 30);
        s.q.setAttribute("cy", s.y + Math.sin((t + s.ph) * .1) * 6);
      });
      if (bug) {
        const hx = pos(T);
        const seen = DASH.some(([s2, e2]) => T >= s2 && T < e2 + 3);
        segs.forEach((n, i) => {                               // twice the animal (CCB)
          const x = hx - i * 26, y = wave(x);
          n.setAttribute("cx", x); n.setAttribute("cy", y);
          n.setAttribute("opacity", seen && x > -40 && x < 680 ? .9 - i * .02 : 0);
          [0, 1].forEach(k => {
            const L2 = legs[i * 2 + k];
            L2.setAttribute("x1", x - 6 + k * 12); L2.setAttribute("y1", y + 8);
            L2.setAttribute("x2", x - 12 + k * 24); L2.setAttribute("y2", y + 26);
            L2.setAttribute("opacity", seen && x > -40 && x < 680 ? .7 : 0);
          });
        });
        feelers.forEach((n, k) => {
          n.setAttribute("x1", hx + 12); n.setAttribute("y1", wave(hx) - 4);
          n.setAttribute("x2", hx + 40); n.setAttribute("y2", wave(hx) - 20 + k * 24);
          n.setAttribute("opacity", seen ? .9 : 0);
        });
        glints.forEach((n, j) => {                             // the sparkling wake
          const gi = (Math.floor(t / 2) * 7 + j * 5) % 22;     // 16 body + 6 wake
          const x = hx - gi * 26;
          n.setAttribute("cx", x + ((t + j) % 3) - 1);
          n.setAttribute("cy", wave(x) + ((t * j) % 5) - 2);
          n.setAttribute("opacity", !seen && (t + j * 2) % 5 < 2 && x > 0 && x < 640 ? .9 : 0);
        });
        const on = seen ? 6 : (t % 7 === 0 ? 1 : 0);
        cells.forEach((r, i) => r.setAttribute("fill-opacity", i < on ? .8 : .08));
      }
      typeOn(foot, footText, T, 20, 1.8);
    });
  }

  /* ---------------- 20: the glass centipede (in residence) ---------------- */
  FIG._define("centipede", "svg", function (svg) {
    chimCard(svg, true, false, "THE GLASS CENTIPEDE", "HAZARD / SILICA / QUICK",
      "FOUR FEET OF GLASS. FASTER THAN THE EYE WANTS TO ALLOW.");
  });

  /* ---------------- 20-F: the chimney, vacated ---------------- */
  FIG._define("chimney-f", "svg", function (svg) {
    chimCard(svg, false, false, "THE FUNGAL CHIMNEY", "THE CHIMNEY / TENANT: OUT",
      "SOMETHING LIVED HERE. IT FOLLOWED YOU OUT.");
  });

  /* ---------------- 20-G: the chimney, burnt and tenanted ---------------- */
  FIG._define("chimney-g", "svg", function (svg) {
    chimCard(svg, true, true, "THE FUNGAL CHIMNEY, BURNT",
      "THE CHIMNEY / CHARRED / TENANTED",
      "THE GROWTH BURNED. THE GLASS DID NOT.");
  });

  /* ---------------- 20-H: the chimney, burnt and bare ---------------- */
  FIG._define("chimney-h", "svg", function (svg) {
    chimCard(svg, false, true, "THE FUNGAL CHIMNEY, BURNT",
      "THE CHIMNEY / CHARRED / BARE",
      "BLACK, BARE, AND BREATHABLE.");
  });

  /* ---------------- 21: the epitaph ---------------- */
  FIG._define("epitaph", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "OREGON TRAIL / GRANITE / YOURS";
    const EDOTS = stipple(svg, "dots-epitaph", PH, .8);
    el(svg, "line", { x1: 60, y1: 330, x2: 580, y2: 330, stroke: PH, "stroke-width": 1.4 });
    [[150, 328], [446, 326], [488, 329]].forEach(([x, y]) =>
      el(svg, "circle", { cx: x, cy: y, r: 3, fill: "none", stroke: PH_DIM }));
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "430,330 426,318 430,322 432,314 434,322 438,318 436,330" });
    el(svg, "path", { d: "M 240 330 L 240 160 Q 320 96 400 160 L 400 330 Z",
      fill: EDOTS, stroke: PH, "stroke-width": 1.8 });
    el(svg, "path", { d: "M 252 330 L 252 166 Q 320 110 388 166 L 388 330",
      fill: "none", stroke: PH_DIM });
    const line = (y, size, color) => {
      const n = label(svg, 320, y, size, color);
      n.setAttribute("text-anchor", "middle"); return n;
    };
    const L1 = line(196, 10, PH), L2 = line(222, 12, PH_BRIGHT);
    const L3 = line(250, 8, PH), L4 = line(276, 8, PH_DIM);
    const score = label(svg, 320, 356, 10, PH); score.setAttribute("text-anchor", "middle");
    const press = label(svg, 320, 382, 10, PH_DIM); press.setAttribute("text-anchor", "middle");
    const foot = label(svg, 624, 356, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const bat = el(svg, "path", { fill: "none", stroke: PH, "stroke-width": 1.3 });
    // In the game the terminal fills this in at death (score, hints, the
    // wound that did it); standalone, the stone stays honest and carves
    // neither a fake score nor an invented cause.
    const CTX = (typeof window !== "undefined" && window.TombFigures
      && window.TombFigures.context) || {};
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "THE EPITAPH", T, 4, 1.4);
      L1.textContent = T > 20 ? "HERE LIES" : "";
      L2.textContent = T > 40 ? "A SCAVENGER" : "";
      L3.textContent = T > 60 && CTX.cause
        ? String(CTX.cause).toUpperCase().slice(0, 30) : "";
      L4.textContent = T > 80 ? "4,000 YRS + 6 DAYS" : "";
      if (CTX.score != null)
        typeOn(score, "SCORE: " + CTX.score + " OF " + CTX.max
          + " -- HINTS TAKEN: " + (CTX.hints || 0), T, 96, 1.8);
      press.textContent = T > 130 && t % 8 < 4 ? "PRESS ENTER TO TRY AGAIN" : "";
      typeOn(foot, "THE TOMB KEEPS YOU.", T, 140, 1.6);
      const a = t * .05;                                      // something leathery
      const bx = 320 + Math.cos(a) * 150, by = 84 + Math.sin(a * 2) * 14;
      const up = t % 4 < 2 ? -7 : 5;
      bat.setAttribute("d", `M ${bx - 11} ${by} Q ${bx - 5} ${by + up} ${bx} ${by} ` +
        `Q ${bx + 5} ${by + up} ${bx + 11} ${by}`);
    });
  });


  /* ---------------- 19-B: the ossified mystic, gifted ---------------- */
  FIG._define("mystic-b", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE SUMMIT / STONE / PSYCHIC";
    const BDOTS = stipple(svg, "dots-mysticb", PH, .85);
    el(svg, "line", { x1: 40, y1: 322, x2: 600, y2: 322, stroke: PH, "stroke-width": 1.4 });
    el(svg, "ellipse", { cx: 560, cy: 322, rx: 36, ry: 10, fill: BG,
      stroke: PH, "stroke-width": 1.5 });                     // the flue mouth
    [546, 560, 574].forEach(x =>
      el(svg, "line", { x1: x, y1: 328, x2: x, y2: 350, stroke: PH_DIM }));
    [[96, 322], [122, 322]].forEach(([x, y]) =>               // the standing stones
      el(svg, "polygon", { fill: BDOTS, stroke: PH, "stroke-width": 1.3,
        points: `${x - 9},${y} ${x + 9},${y} ${x + 6},${y - 34} ${x - 6},${y - 30}` }));
    // THE ROBE: a mound with one great eye
    el(svg, "path", { fill: BDOTS, stroke: PH, "stroke-width": 1.8,
      d: "M 152 322 Q 162 226 222 172 Q 248 148 276 162 Q 330 184 342 248 Q 350 296 358 322 Z" });
    el(svg, "path", { fill: "none", stroke: PH_DIM,
      d: "M 190 300 Q 214 268 208 236" });                    // a fold
    el(svg, "path", { fill: "none", stroke: PH_DIM,
      d: "M 300 306 Q 296 270 306 246" });
    const EX = 248, EY = 186;
    Array.from({ length: 7 }, (_, i) => {                     // the lash crown
      const a = -Math.PI * (.22 + i * .093);
      el(svg, "polygon", { fill: PH, stroke: PH, "stroke-width": 1, points:
        `${EX + Math.cos(a) * 24},${EY + Math.sin(a) * 24} ` +
        `${EX + Math.cos(a + .05) * (36 + (i % 2) * 7)},${EY + Math.sin(a + .05) * (36 + (i % 2) * 7)} ` +
        `${EX + Math.cos(a + .12) * 24},${EY + Math.sin(a + .12) * 24}` });
    });
    el(svg, "circle", { cx: EX, cy: EY, r: 21, fill: BG, stroke: PH, "stroke-width": 1.6 });
    const iris = el(svg, "circle", { cx: EX, cy: EY, r: 8.5, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    const pupil = el(svg, "circle", { cx: EX, cy: EY, r: 3.2, fill: PH_BRIGHT });
    Array.from({ length: 13 }, (_, i) => {                    // the fringe of threads
      const x = 206 + i * 7.4;
      el(svg, "line", { x1: x, y1: 218 + Math.sin(i * .9) * 4, x2: x,
        y2: 238 + (i % 3) * 7, stroke: PH, "stroke-width": 1.1, opacity: .8 });
    });
    el(svg, "line", { x1: 204, y1: 216, x2: 296, y2: 216, stroke: PH, "stroke-width": 1.4 });
    // the arm, the orb, the bowl
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "306,262 334,288 344,298" });
    const orb = el(svg, "circle", { cx: 352, cy: 296, r: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.4 });
    el(svg, "path", { d: "M 330 310 Q 352 322 376 310 L 372 320 Q 352 328 334 320 Z",
      fill: BDOTS, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polygon", { points: "398,320 404,306 410,320", fill: "none",
      stroke: PH_DIM });                                      // the bottle
    // THE GIFT: a jagged emanation, hung with geometry
    const ZAG = [[270, 158], [322, 122], [302, 92], [382, 102], [360, 58],
      [452, 82], [430, 38], [524, 68], [508, 30]];
    const bolt = el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT,
      "stroke-width": 2 });
    const bolt2 = el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      "stroke-width": 1.2 });
    const shapes = [];
    const shape = (cx, cy, k) => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      shapes.push({ g, cx, cy, k }); return g;
    };
    let g = shape(478, 44, 0);                                // a diamond
    el(g, "polygon", { points: "0,-13 9,0 0,13 -9,0", fill: BDOTS,
      stroke: PH, "stroke-width": 1.3 });
    g = shape(556, 96, 1);                                    // a frame in a frame
    el(g, "rect", { x: -14, y: -14, width: 28, height: 28, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    el(g, "rect", { x: -6, y: -6, width: 12, height: 12, fill: BDOTS,
      stroke: PH, "stroke-width": 1.2 });
    g = shape(606, 152, 2);                                   // a ring
    el(g, "circle", { cx: 0, cy: 0, r: 13, fill: "none", stroke: PH, "stroke-width": 1.4 });
    el(g, "circle", { cx: 0, cy: 0, r: 6, fill: "none", stroke: PH_DIM });
    g = shape(592, 52, 3);                                    // a cube
    el(g, "polygon", { points: "-10,-5 0,-11 10,-5 10,6 0,12 -10,6", fill: BDOTS,
      stroke: PH, "stroke-width": 1.3 });
    el(g, "polyline", { fill: "none", stroke: PH, points: "-10,-5 0,1 10,-5" });
    el(g, "line", { x1: 0, y1: 1, x2: 0, y2: 12, stroke: PH });
    g = shape(624, 210, 4);                                   // a splash
    el(g, "polygon", { fill: BDOTS, stroke: PH, "stroke-width": 1.2,
      points: "0,-10 8,-4 14,2 6,6 10,14 -2,8 -12,12 -8,2 -14,-4 -4,-4" });
    el(g, "circle", { cx: 18, cy: -8, r: 2, fill: PH });
    el(g, "circle", { cx: -16, cy: 16, r: 1.6, fill: PH });
    g = shape(438, 48, 5);                                    // a small diamond
    el(g, "polygon", { points: "0,-7 5,0 0,7 -5,0", fill: "none",
      stroke: PH, "stroke-width": 1.2 });
    // the fronds, still bound to the flue
    const FRONDS = [[242, 206, -1], [258, 208, 1], [250, 232, 0]];
    const HX = 556, HY = 316;
    const fpts = (f, t) => {
      const [x0, y0, ph] = FRONDS[f], pts = [];
      for (let q = 0; q <= 9; q++) {
        const u = q / 9;
        pts.push([x0 + (HX - x0) * u,
          y0 + (HY - y0) * u - Math.sin(u * Math.PI) * (30 + ph * 9)
          + Math.sin(t * .3 + u * 5 + ph) * 4 * u]);
      }
      return pts;
    };
    const fronds = FRONDS.map(() => el(svg, "polyline",
      { fill: "none", stroke: FUNGUS, "stroke-width": 2 }));
    const motes = Array.from({ length: 5 }, () =>
      el(svg, "circle", { r: 1.6, fill: FUNGUS }));
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 200;
      doWipe(T);
      typeOn(hdr, "THE OSSIFIED MYSTIC, GIFTED", T, 4, 1.4);
      const beat = Math.floor(t / 6);
      bolt.setAttribute("points", ZAG.map(([x, y], i) =>
        `${x + ((beat + i) % 3 - 1) * 4},${y + ((beat + i * 2) % 3 - 1) * 4}`).join(" "));
      bolt2.setAttribute("points", ZAG.slice(2, 7).map(([x, y], i) =>
        `${x + 16 + ((beat + i) % 3 - 1) * 5},${y + 40 + ((beat + i) % 3 - 1) * 5}`).join(" "));
      shapes.forEach(sh => {
        const bob = Math.round(Math.sin(t * .12 + sh.k * 1.3) * 2) * 2;
        const rot = (Math.floor(t / 8) * 15 * (sh.k % 2 ? -1 : 1)) % 360;
        sh.g.setAttribute("transform",
          `translate(${sh.cx} ${sh.cy + bob}) rotate(${sh.k < 4 ? rot : 0})`);
      });
      const look = [0, 2, 3, 1, -2, -3][Math.floor(t / 18) % 6];  // the eye considers
      iris.setAttribute("cx", EX + look); pupil.setAttribute("cx", EX + look * 1.4);
      orb.setAttribute("stroke-width", 1.2 + (Math.floor(t / 6) % 3) * .5);
      FRONDS.forEach((_, f) => fronds[f].setAttribute("points",
        fpts(f, t).map(p2 => p2.join(",")).join(" ")));
      motes.forEach((n, j) => {
        const pts = fpts(j % 3, t);
        const q = Math.floor(((t * 2 + j * 37) % 90) / 10);
        n.setAttribute("cx", pts[q][0]); n.setAttribute("cy", pts[q][1] - 4);
      });
      typeOn(foot, "THE GIFT DID NOT EXPIRE WITH HIM.", T, 40, 1.6);
    });
  });


  /* ---------------- 19-C: the ossified mystic, burned ---------------- */
  FIG._define("mystic-c", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE SUMMIT / FIRE / RELEASED";
    const CDOTS3 = stipple(svg, "dots-mysticc", PH, .85);
    const YEL = "#ffd76a", AMBER = "#e5b955";
    const CHARC = [74, 42, 20], ORANGE = [255, 154, 60];
    const mix = (a, b, k) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * k)).join(",")})`;
    const clamp = x => Math.max(0, Math.min(1, x));
    const ground = el(svg, "line", { x1: 40, y1: 322, x2: 600, y2: 322, stroke: PH, "stroke-width": 1.4 });
    el(svg, "ellipse", { cx: 560, cy: 322, rx: 36, ry: 10, fill: BG,
      stroke: PH, "stroke-width": 1.5 });                     // the flue mouth
    [546, 560, 574].forEach(x =>
      el(svg, "line", { x1: x, y1: 328, x2: x, y2: 350, stroke: PH_DIM }));
    const stones = [[96, 322], [122, 322]].map(([x, y]) =>
      el(svg, "polygon", { fill: CDOTS3, stroke: PH, "stroke-width": 1.3,
        points: `${x - 9},${y} ${x + 9},${y} ${x + 6},${y - 34} ${x - 6},${y - 30}` }));
    const robe = el(svg, "path", { fill: CDOTS3, stroke: PH, "stroke-width": 1.8,
      d: "M 152 322 Q 162 226 222 172 Q 248 148 276 162 Q 330 184 342 248 Q 350 296 358 322 Z" });
    el(svg, "path", { fill: "none", stroke: PH_DIM, d: "M 190 300 Q 214 268 208 236" });
    el(svg, "path", { fill: "none", stroke: PH_DIM, d: "M 300 306 Q 296 270 306 246" });
    const EX = 248, EY = 186;
    const lashes = Array.from({ length: 7 }, (_, i) => {
      const a = -Math.PI * (.22 + i * .093);
      return el(svg, "polygon", { fill: PH, stroke: PH, "stroke-width": 1, points:
        `${EX + Math.cos(a) * 24},${EY + Math.sin(a) * 24} ` +
        `${EX + Math.cos(a + .05) * (36 + (i % 2) * 7)},${EY + Math.sin(a + .05) * (36 + (i % 2) * 7)} ` +
        `${EX + Math.cos(a + .12) * 24},${EY + Math.sin(a + .12) * 24}` });
    });
    const eyeRing = el(svg, "circle", { cx: EX, cy: EY, r: 21, fill: BG, stroke: PH, "stroke-width": 1.6 });
    const iris = el(svg, "circle", { cx: EX, cy: EY, r: 8.5, fill: "none", stroke: PH, "stroke-width": 1.4 });
    const pupil = el(svg, "circle", { cx: EX, cy: EY, r: 3.2, fill: PH_BRIGHT });
    Array.from({ length: 13 }, (_, i) => {                    // the fringe of threads
      const x = 206 + i * 7.4;
      el(svg, "line", { x1: x, y1: 218 + Math.sin(i * .9) * 4, x2: x,
        y2: 238 + (i % 3) * 7, stroke: PH, "stroke-width": 1.1, opacity: .8 });
    });
    el(svg, "line", { x1: 204, y1: 216, x2: 296, y2: 216, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "306,262 334,288 344,298" });
    const orb = el(svg, "circle", { cx: 352, cy: 296, r: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.4 });
    el(svg, "path", { d: "M 330 310 Q 352 322 376 310 L 372 320 Q 352 328 334 320 Z",
      fill: CDOTS3, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polygon", { points: "398,320 404,306 410,320", fill: "none", stroke: PH_DIM });
    // the gift: the bolt and the hung geometry, as 19-B built them
    const ZAG = [[270, 158], [322, 122], [302, 92], [382, 102], [360, 58],
      [452, 82], [430, 38], [524, 68], [508, 30]];
    const bolt = el(svg, "polyline", { fill: "none", stroke: PH_BRIGHT, "stroke-width": 2 });
    const bolt2 = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-width": 1.2 });
    const shapes = [];
    const shape = (cx, cy, k) => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      shapes.push({ g, cx, cy, k }); return g;
    };
    let g = shape(478, 44, 0);                                // a diamond
    el(g, "polygon", { points: "0,-13 9,0 0,13 -9,0", fill: CDOTS3,
      stroke: PH, "stroke-width": 1.3 });
    g = shape(556, 96, 1);                                    // a frame in a frame
    el(g, "rect", { x: -14, y: -14, width: 28, height: 28, fill: "none",
      stroke: PH, "stroke-width": 1.4 });
    el(g, "rect", { x: -6, y: -6, width: 12, height: 12, fill: CDOTS3,
      stroke: PH, "stroke-width": 1.2 });
    g = shape(606, 152, 2);                                   // a ring
    el(g, "circle", { cx: 0, cy: 0, r: 13, fill: "none", stroke: PH, "stroke-width": 1.4 });
    el(g, "circle", { cx: 0, cy: 0, r: 6, fill: "none", stroke: PH_DIM });
    g = shape(592, 52, 3);                                    // a cube
    el(g, "polygon", { points: "-10,-5 0,-11 10,-5 10,6 0,12 -10,6", fill: CDOTS3,
      stroke: PH, "stroke-width": 1.3 });
    el(g, "polyline", { fill: "none", stroke: PH, points: "-10,-5 0,1 10,-5" });
    el(g, "line", { x1: 0, y1: 1, x2: 0, y2: 12, stroke: PH });
    g = shape(624, 210, 4);                                   // a splash
    el(g, "polygon", { fill: CDOTS3, stroke: PH, "stroke-width": 1.2,
      points: "0,-10 8,-4 14,2 6,6 10,14 -2,8 -12,12 -8,2 -14,-4 -4,-4" });
    el(g, "circle", { cx: 18, cy: -8, r: 2, fill: PH });
    el(g, "circle", { cx: -16, cy: 16, r: 1.6, fill: PH });
    g = shape(438, 48, 5);                                    // a small diamond
    el(g, "polygon", { points: "0,-7 5,0 0,7 -5,0", fill: "none",
      stroke: PH, "stroke-width": 1.2 });
    // the fronds and their sap-motes
    const FRONDS = [[242, 206, -1], [258, 208, 1], [250, 232, 0]];
    const HX = 556, HY = 316;
    const fpts = (f, tt, k) => {
      const [x0, y0, ph] = FRONDS[f], pts = [];
      const calm = 1 - k * .7;                                // burnt ropes slow
      for (let q = 0; q <= 9; q++) {
        const u = q / 9;
        pts.push([x0 + (HX - x0) * u,
          y0 + (HY - y0) * u
          - Math.sin(u * Math.PI) * (30 + ph * 9) * (1 - k * 1.25)  // and sag
          + Math.sin(tt * .3 * calm + u * 5 + ph) * 4 * u * calm]);
      }
      return pts;
    };
    const fronds = FRONDS.map(() => el(svg, "polyline",
      { fill: "none", stroke: FUNGUS, "stroke-width": 2 }));
    const motes = Array.from({ length: 5 }, () =>
      el(svg, "circle", { r: 1.6, fill: FUNGUS }));
    // the fire: 13-E's machinery, riding the scene itself -- five flames
    // stand ON the fronds (sampled from the same polylines, so they sag
    // and slow together), three ON the robe's arc, one ON the pupil (it
    // burns wherever the eye looks), and five keep the ground they held
    const FSTATIC = [[176, 318], [286, 300], [352, 316], [206, 262], [330, 258]];
    const FARC = [[174, 237], [249, 158], [333, 219]];
    const FRIDE = [[0, 3], [1, 5], [2, 7], [0, 6], [1, 8]];   // [frond, sample]
    const FSCALE = FSTATIC.map(() => 1).concat(FARC.map(() => .9),
      FRIDE.map(() => .85), [.65]);
    const flames = FSCALE.map(() => el(svg, "polygon", { stroke: "none" }));
    const embers = Array.from({ length: 26 }, (_, i) => {
      const x = 160 + i * 16;
      return { x, ph: i * 23, dir: (x < 300 ? -1 : 1) * (.3 + (i % 5) * .35),
        q: el(svg, "circle", { r: i % 3 ? 1.4 : 2.1, fill: i % 4 ? YEL : FUNGUS }) };
    });
    const smoke = Array.from({ length: 3 }, () =>
      el(svg, "polyline", { fill: "none", stroke: PH_DIM,
        "stroke-dasharray": "2 5", opacity: 0 }));
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 260;
      doWipe(T);
      typeOn(hdr, "THE OSSIFIED MYSTIC, BURNED", T, 4, 1.4);
      const burn = clamp((T - 30) / 115);                     // the charring
      const fire = clamp((T - 16) / 14) * (1 - clamp((T - 148) / 26));
      const leave = clamp((T - 152) / 34);                    // the recall
      const beat = Math.floor(t / 8);
      const lit = fire > .25;                                 // slow firelight,
      robe.setAttribute("stroke", lit && beat % 5 === 0 ? AMBER : PH);
      ground.setAttribute("stroke", lit && (beat + 2) % 5 === 0 ? AMBER : PH);
      stones.forEach((n, i) =>
        n.setAttribute("stroke", lit && (beat + i + 1) % 4 === 0 ? AMBER : PH));
      eyeRing.setAttribute("stroke", lit && (beat + 3) % 5 === 0 ? AMBER : PH);
      lashes.forEach((n, i) => {
        const hot = lit && (beat + i) % 5 === 0;
        n.setAttribute("stroke", hot ? AMBER : PH);
        n.setAttribute("fill", hot ? AMBER : PH);
      });
      const look = leave > 0 ? 0 : [0, 2, 3, 1, -2, -3][Math.floor(T / 18) % 6];
      const fks = FRONDS.map((_, f) => clamp(burn * 1.35 - f * .12));
      const fps2 = FRONDS.map((_, f) => fpts(f, T, fks[f]));
      fronds.forEach((n, f) => {                              // the fronds recant
        n.setAttribute("stroke", mix(ORANGE, CHARC, fks[f]));
        n.setAttribute("points", fps2[f].map(p => p.join(",")).join(" "));
      });
      const roots = FSTATIC.concat(FARC,
        FRIDE.map(([f, q]) => fps2[f][q]),                    // riding the ropes
        [[EX + look * 1.4, EY + 4]]);                         // and the pupil
      flames.forEach((fl, i) => {                             // the fire, working
        if (fire <= .02) { fl.setAttribute("opacity", 0); return; }
        const [fx, fy] = roots[i], s = FSCALE[i];
        const h = (14 + ((t * 7 + i * 13) % 15) + burn * 8) * fire * s;
        const wob = Math.sin(t * .9 + i * 2.2) * 5 * s;
        fl.setAttribute("points",
          `${fx - 6 * s},${fy} ${fx + wob * .4},${fy - h * .55} ${fx + wob},${fy - h} ` +
          `${fx + 4 * s + wob * .3},${fy - h * .5} ${fx + 7 * s},${fy}`);
        fl.setAttribute("fill", (t + i) % 3 ? FUNGUS : YEL);
        fl.setAttribute("opacity", (.5 + ((t + i) % 2) * .3) * fire);
      });
      // sparks outlive the flames: they climb with the leaving shapes,
      // and fade once the last of them is gone
      const spark = clamp((T - 16) / 14) * (1 - clamp((T - 190) / 22));
      embers.forEach(e2 => {
        const k = (t * 3 + e2.ph) % 190;
        e2.q.setAttribute("cx", e2.x + e2.dir * k * .5 + Math.sin((t + e2.ph) * .35) * 8);
        e2.q.setAttribute("cy", 300 - k);
        e2.q.setAttribute("opacity", k > 160 ? 0 : (.4 + ((t + e2.ph) % 3) * .25) * spark);
      });
      // the bolt lets go of the mystic and reels in, point by point
      const drop = Math.floor(leave * ZAG.length);
      const zz = ZAG.slice(drop);
      if (zz.length > 1 && leave < 1) {
        bolt.setAttribute("points", zz.map(([x, y], i) =>
          `${x + ((beat + i) % 3 - 1) * 4},${y + ((beat + i * 2) % 3 - 1) * 4}`).join(" "));
        bolt.setAttribute("opacity", (t % 3 ? 1 : .55) * (1 - leave * .5));
      } else bolt.setAttribute("opacity", 0);
      bolt2.setAttribute("points", ZAG.slice(2, 7).map(([x, y], i) =>
        `${x + 16 + ((beat + i) % 3 - 1) * 5},${y + 40 + ((beat + i) % 3 - 1) * 5}`).join(" "));
      bolt2.setAttribute("opacity", Math.max(0, .9 - leave * 2));
      shapes.forEach(sh => {                                  // released, skyward
        const li = clamp((T - (152 + sh.k * 4)) / 26);
        const bob = Math.round(Math.sin(t * .12 + sh.k * 1.3) * 2) * 2;
        const rot = (Math.floor(t / 8) * 15 * (sh.k % 2 ? -1 : 1)) % 360;
        const rise = li * li * 150;
        const dx = (sh.k % 2 ? 1 : -1) * li * 26;
        sh.g.setAttribute("transform",
          `translate(${sh.cx + dx} ${sh.cy + bob - rise}) rotate(${sh.k < 4 ? rot : 0})`);
        sh.g.setAttribute("opacity", 1 - li);
      });
      iris.setAttribute("cx", EX + look); pupil.setAttribute("cx", EX + look * 1.4);
      pupil.setAttribute("opacity", 1 - leave * .75);         // the eye dims last
      iris.setAttribute("opacity", 1 - leave * .5);
      orb.setAttribute("stroke-width", leave >= 1 ? 1.2 : 1.2 + (Math.floor(t / 6) % 3) * .5);
      motes.forEach((n, j) => {                               // the sap rides, then rises
        if (leave <= 0) {
          const pts = fps2[j % 3];
          const q = Math.floor(((T * 2 + j * 37) % 90) / 10);
          n.setAttribute("cx", pts[q][0]); n.setAttribute("cy", pts[q][1] - 4);
          n.setAttribute("opacity", 1);
        } else {
          const pts = fpts(j % 3, 152, 1);
          const q = Math.floor(((152 * 2 + j * 37) % 90) / 10);
          n.setAttribute("cx", pts[q][0] + (j % 2 ? 14 : -10) * leave);
          n.setAttribute("cy", pts[q][1] - 4 - leave * (46 + j * 15));
          n.setAttribute("opacity", 1 - leave);
        }
      });
      smoke.forEach((s, i) => {                               // what fire leaves
        const on = T > 170 && T < 244 ? .5 : 0;
        s.setAttribute("opacity", on);
        if (on) {
          const x0 = 210 + i * 52, up = (t * 2 + i * 17) % 40;
          s.setAttribute("points", Array.from({ length: 5 }, (_, q) =>
            `${x0 + Math.sin(t * .2 + q + i * 2) * 6},${306 - up - q * 12}`).join(" "));
        }
      });
      typeOn(foot, "THE GIFT EXPIRED AFTER ALL.", T, 196, 1.5);
    });
  });


  /* ---------------- 19-F: the ossified mystic, burned out ---------------- */
  FIG._define("mystic-f", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "THE SUMMIT / ASH / QUIET";
    const FDOTS2 = stipple(svg, "dots-mysticf", PH, .85);
    const CHARCOL = "rgb(74,42,20)";
    el(svg, "line", { x1: 40, y1: 322, x2: 600, y2: 322, stroke: PH, "stroke-width": 1.4 });
    el(svg, "ellipse", { cx: 560, cy: 322, rx: 36, ry: 10, fill: BG,
      stroke: PH, "stroke-width": 1.5 });                     // the flue mouth
    [546, 560, 574].forEach(x =>
      el(svg, "line", { x1: x, y1: 328, x2: x, y2: 350, stroke: PH_DIM }));
    [[96, 322], [122, 322]].forEach(([x, y]) =>               // the standing stones
      el(svg, "polygon", { fill: FDOTS2, stroke: PH, "stroke-width": 1.3,
        points: `${x - 9},${y} ${x + 9},${y} ${x + 6},${y - 34} ${x - 6},${y - 30}` }));
    el(svg, "path", { fill: FDOTS2, stroke: PH, "stroke-width": 1.8,
      d: "M 152 322 Q 162 226 222 172 Q 248 148 276 162 Q 330 184 342 248 Q 350 296 358 322 Z" });
    el(svg, "path", { fill: "none", stroke: PH_DIM, d: "M 190 300 Q 214 268 208 236" });
    el(svg, "path", { fill: "none", stroke: PH_DIM, d: "M 300 306 Q 296 270 306 246" });
    const EX = 248, EY = 186;
    Array.from({ length: 7 }, (_, i) => {                     // the lash crown
      const a = -Math.PI * (.22 + i * .093);
      el(svg, "polygon", { fill: PH, stroke: PH, "stroke-width": 1, points:
        `${EX + Math.cos(a) * 24},${EY + Math.sin(a) * 24} ` +
        `${EX + Math.cos(a + .05) * (36 + (i % 2) * 7)},${EY + Math.sin(a + .05) * (36 + (i % 2) * 7)} ` +
        `${EX + Math.cos(a + .12) * 24},${EY + Math.sin(a + .12) * 24}` });
    });
    el(svg, "circle", { cx: EX, cy: EY, r: 21, fill: BG, stroke: PH, "stroke-width": 1.6 });
    // the eye, fixed: nothing left to consider (CCB: it does not move)
    el(svg, "circle", { cx: EX, cy: EY, r: 8.5, fill: "none",
      stroke: PH, "stroke-width": 1.4, opacity: .7 });
    el(svg, "circle", { cx: EX, cy: EY, r: 3.2, fill: PH_BRIGHT, opacity: .55 });
    Array.from({ length: 13 }, (_, i) => {                    // the fringe of threads
      const x = 206 + i * 7.4;
      el(svg, "line", { x1: x, y1: 218 + Math.sin(i * .9) * 4, x2: x,
        y2: 238 + (i % 3) * 7, stroke: PH, "stroke-width": 1.1, opacity: .8 });
    });
    el(svg, "line", { x1: 204, y1: 216, x2: 296, y2: 216, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.5,
      points: "306,262 334,288 344,298" });
    el(svg, "circle", { cx: 352, cy: 296, r: 9, fill: "none",
      stroke: PH_BRIGHT, "stroke-width": 1.2 });              // the orb, gone dull
    el(svg, "path", { d: "M 330 310 Q 352 322 376 310 L 372 320 Q 352 328 334 320 Z",
      fill: FDOTS2, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polygon", { points: "398,320 404,306 410,320", fill: "none", stroke: PH_DIM });
    // the fronds, kept as charred rope (19-C's last frame)
    const FRONDS = [[242, 206, -1], [258, 208, 1], [250, 232, 0]];
    const HX = 556, HY = 316;
    const fpts = (f, tt) => {
      const [x0, y0, ph] = FRONDS[f], pts = [];
      for (let q = 0; q <= 9; q++) {                          // k = 1 throughout:
        const u = q / 9;                                      // sagged, slowed
        pts.push([x0 + (HX - x0) * u,
          y0 + (HY - y0) * u
          + Math.sin(u * Math.PI) * (30 + ph * 9) * .25
          + Math.sin(tt * .09 + u * 5 + ph) * 1.2 * u]);
      }
      return pts;
    };
    const fronds = FRONDS.map(() => el(svg, "polyline",
      { fill: "none", stroke: CHARCOL, "stroke-width": 2 }));
    const smoke = Array.from({ length: 3 }, () =>
      el(svg, "polyline", { fill: "none", stroke: PH_DIM,
        "stroke-dasharray": "2 5", opacity: .5 }));
    // a stray spark now and then, out of habit
    const strays = Array.from({ length: 3 }, (_, i) =>
      ({ ph: i * 67, x: 220 + i * 90,
         q: el(svg, "circle", { r: 1.4, fill: i % 2 ? "#ffd76a" : FUNGUS }) }));
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE OSSIFIED MYSTIC, BURNED OUT", T, 4, 1.4);
      fronds.forEach((n, f) => n.setAttribute("points",
        fpts(f, t).map(p => p.join(",")).join(" ")));
      smoke.forEach((s, i) => {
        const x0 = 210 + i * 52, up = (t * 2 + i * 17) % 40;
        s.setAttribute("points", Array.from({ length: 5 }, (_, q) =>
          `${x0 + Math.sin(t * .2 + q + i * 2) * 6},${306 - up - q * 12}`).join(" "));
      });
      strays.forEach(sp => {
        const k = (t * 2 + sp.ph) % 200;                      // long quiet gaps
        sp.q.setAttribute("cx", sp.x + Math.sin((t + sp.ph) * .3) * 7);
        sp.q.setAttribute("cy", 302 - k * 1.4);
        sp.q.setAttribute("opacity", k < 90 ? .35 + (k % 3) * .15 : 0);
      });
      typeOn(foot, "NOTHING LEFT TO GIVE.", T, 60, 1.4);
    });
  });


  /* ---------------- 17-D: the approach, elevations ---------------- */
  FIG._define("ext1e", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "AZURE STONE / SURVEY / BOTH DOORS";
    const EDOTS2 = stipple(svg, "dots-ext1e", PH, .85);
    el(svg, "line", { x1: 30, y1: 340, x2: 610, y2: 340, stroke: PH, "stroke-width": 1.4 });
    el(svg, "polyline", { fill: "none", stroke: PH_DIM,
      points: "30,336 120,330 210,337 430,331 520,338 610,333" });
    // THE SLAB, face-on
    const slab = el(svg, "polygon", { fill: EDOTS2, stroke: PH, "stroke-width": 1.8,
      points: "252,96 388,96 396,340 244,340" });
    // the old man at the summit, face to the sky -- constant on the elevations
    const crownG = el(svg, "g", {});
    el(crownG, "polyline", { fill: "none", stroke: PH, "stroke-width": 1.6,
      points: "292,96 298,78 306,72 312,74 316,64 326,62 330,68 336,66 342,74 348,96" });
    el(crownG, "circle", { cx: 322, cy: 70, r: 1.6, fill: PH_BRIGHT });
    const TENDRILS = [[318, 66, -1.9], [322, 64, -.6], [326, 66, .6], [330, 68, 1.7]];
    const tendrils = TENDRILS.map(() => el(crownG, "polyline",
      { fill: "none", stroke: FUNGUS, "stroke-width": 2 }));
    const drips = TENDRILS.map(() => el(crownG, "circle", { r: 1.7, fill: FUNGUS }));
    // each face's MOUTH is the way in: the doors stand on the ground itself
    const door = parent => {
      el(parent, "path", { d: "M 306 340 L 306 302 Q 320 288 334 302 L 334 340 Z",
        fill: BG, stroke: PH, "stroke-width": 1.6 });
      el(parent, "line", { x1: 306, y1: 340, x2: 334, y2: 340,
        stroke: PH_BRIGHT, "stroke-width": 1.5 });            // the threshold
    };
    // WEST: the Autarch young -- smooth, swaddled, unsettlingly tender
    const west = el(svg, "g", {});
    el(west, "ellipse", { cx: 320, cy: 244, rx: 52, ry: 62, fill: "none",
      stroke: PH, "stroke-width": 1.6 });
    el(west, "path", { d: "M 296 231 Q 304 225 312 231", fill: "none",
      stroke: PH, "stroke-width": 1.5 });                     // closed eyes
    el(west, "path", { d: "M 328 231 Q 336 225 344 231", fill: "none",
      stroke: PH, "stroke-width": 1.5 });
    el(west, "path", { d: "M 316 247 Q 320 253 324 247", fill: "none", stroke: PH_DIM });
    el(west, "path", { d: "M 286 275 Q 320 291 354 275", fill: "none",
      stroke: PH_DIM });                                      // the round cheekline
    [0, 1, 2].forEach(k => el(west, "path", { fill: "none", stroke: PH_DIM,
      d: `M ${268 - k * 4} ${199 + k * 26} Q 320 ${185 + k * 26} ${372 + k * 4} ${199 + k * 26}` }));
    door(west);
    // EAST: the helmed warrior -- a great helm, face-on
    const east = el(svg, "g", {});
    el(east, "path", { fill: "none", stroke: PH, "stroke-width": 1.8,
      d: "M 280 296 L 276 196 Q 276 150 320 146 Q 364 150 364 196 L 360 296 " +
         "Q 344 306 320 308 Q 296 306 280 296 Z" });          // dome to jaw
    el(east, "line", { x1: 320, y1: 146, x2: 320, y2: 212, stroke: PH,
      "stroke-width": 1.8 });                                  // the nasal ridge
    el(east, "polyline", { fill: "none", stroke: PH_DIM,
      points: "300,146 306,132 334,132 340,146" });            // low crest fin
    // the eye slit, split by the nasal: two dark windows
    el(east, "rect", { x: 286, y: 196, width: 28, height: 8, fill: BG,
      stroke: PH, "stroke-width": 1.5 });
    el(east, "rect", { x: 326, y: 196, width: 28, height: 8, fill: BG,
      stroke: PH, "stroke-width": 1.5 });
    for (let r = 0; r < 2; r++) for (let x = 294; x <= 346; x += 13)
      el(east, "circle", { cx: x, cy: 226 + r * 12, r: 1.6, fill: PH });  // breaths
    el(east, "line", { x1: 280, y1: 256, x2: 360, y2: 256, stroke: PH,
      "stroke-width": 1.4 });                                  // riveted band
    [290, 310, 330, 350].forEach(x =>
      el(east, "circle", { cx: x, cy: 262, r: 1.5, fill: PH_BRIGHT }));
    el(east, "line", { x1: 280, y1: 268, x2: 360, y2: 268, stroke: PH_DIM });
    door(east);
    // SUMMIT: the plan view -- he faces the sky, and you
    const plan = el(svg, "g", {});
    el(plan, "rect", { x: 254, y: 118, width: 132, height: 200, rx: 16,
      fill: "none", stroke: PH, "stroke-width": 1.6 });        // the slab footprint
    [[254, 118], [386, 118], [254, 318], [386, 318]].forEach(([x, y]) => {
      el(plan, "line", { x1: x - 8, y1: y, x2: x + 8, y2: y, stroke: PH_DIM });
      el(plan, "line", { x1: x, y1: y - 8, x2: x, y2: y + 8, stroke: PH_DIM });
    });
    el(plan, "ellipse", { cx: 320, cy: 218, rx: 50, ry: 64, fill: "none",
      stroke: PH, "stroke-width": 1.6 });                      // the upturned face
    el(plan, "path", { d: "M 288 186 Q 298 178 308 184", fill: "none", stroke: PH_DIM });
    el(plan, "path", { d: "M 332 184 Q 342 178 352 186", fill: "none", stroke: PH_DIM });
    const eyeL = el(plan, "circle", { cx: 299, cy: 196, r: 6.5, fill: "none",
      stroke: PH, "stroke-width": 1.5 });
    const eyeR = el(plan, "circle", { cx: 341, cy: 196, r: 6.5, fill: "none",
      stroke: PH, "stroke-width": 1.5 });
    el(plan, "circle", { cx: 299, cy: 196, r: 2.2, fill: PH_BRIGHT });
    el(plan, "circle", { cx: 341, cy: 196, r: 2.2, fill: PH_BRIGHT });
    el(plan, "polyline", { fill: "none", stroke: PH_DIM,
      points: "318,206 316,224 324,224" });                    // the nose, foreshortened
    el(plan, "path", { d: "M 284 226 Q 292 236 300 240", fill: "none", stroke: PH_DIM });
    el(plan, "path", { d: "M 356 226 Q 348 236 340 240", fill: "none", stroke: PH_DIM });
    el(plan, "circle", { cx: 320, cy: 254, r: 13, fill: BG, stroke: PH,
      "stroke-width": 1.8 });                                  // the mouth: a chimney
    el(plan, "circle", { cx: 320, cy: 254, r: 6, fill: "none", stroke: FUNGUS,
      "stroke-width": 1.4 });
    const PLANTENDRILS = Array.from({ length: 8 }, (_, i) => i * Math.PI / 4 + .35);
    const ptend = PLANTENDRILS.map(() => el(plan, "polyline",
      { fill: "none", stroke: FUNGUS, "stroke-width": 2 }));
    // the sweep: a bright edge redraws the sheet between views
    const cover = el(svg, "rect", { y: 96, height: 244, fill: BG, opacity: 0 });
    const edge = el(svg, "rect", { y: 96, width: 3, height: 244,
      fill: PH_BRIGHT, opacity: 0 });
    const compass = label(svg, 78, 230, 40, PH_DIM);
    const sheet = label(svg, 320, 372, 10, PH); sheet.setAttribute("text-anchor", "middle");
    const foot = label(svg, 320, 392, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    const CAPTIONS = [
      "WEST ELEVATION -- THE AUTARCH, YOUNG. HIS MOUTH IS A DOOR.",
      "EAST ELEVATION -- THE HELMED WARRIOR. HIS MOUTH IS A DOOR.",
      "SUMMIT -- THE OLD MAN GAZES SKYWARD. HIS MOUTH IS A CHIMNEY.",
    ];
    clock(t => {
      const T = t % 240;
      doWipe(Math.min(t, 239));
      typeOn(hdr, "THE APPROACH, ELEVATIONS", Math.min(t, 239), 4, 1.4);
      const phase = Math.floor(T / 80);
      west.setAttribute("opacity", phase === 0 ? 1 : 0);
      east.setAttribute("opacity", phase === 1 ? 1 : 0);
      plan.setAttribute("opacity", phase === 2 ? 1 : 0);
      crownG.setAttribute("opacity", phase === 2 ? 0 : 1);   // seen from above instead
      slab.setAttribute("opacity", phase === 2 ? 0 : 1);
      compass.textContent = ["W", "E", "UP"][phase];
      const k = Math.min(1, (T % 80) / 12);                   // the sweep, each sheet
      cover.setAttribute("x", 244 + k * 152);
      cover.setAttribute("width", Math.max(0, 152 * (1 - k)));
      cover.setAttribute("opacity", k >= 1 ? 0 : 1);
      edge.setAttribute("x", Math.min(244 + k * 152, 393));
      edge.setAttribute("opacity", k >= 1 ? 0 : 1);
      typeOn(sheet, CAPTIONS[phase], T % 80, 10, 2.4);
      tendrils.forEach((n, i) => {                            // the crown, weeping
        const [x0, y0, ph] = TENDRILS[i];
        const pts = [[x0, y0]];
        for (let q = 1; q <= 5; q++) {
          const sway = Math.sin(t * .22 + q * .9 + ph * 2) * 3 * q * .4;
          pts.push([x0 + ph * q * 7 + sway, y0 + q * 13 + (ph * ph) * q]);
        }
        n.setAttribute("points", pts.map(p2 => p2.join(",")).join(" "));
        const d = drips[i], dk = (t * 2 + i * 23) % 60;
        d.setAttribute("cx", pts[5][0]); d.setAttribute("cy", pts[5][1] + dk);
        d.setAttribute("opacity", dk > 46 ? 0 : .9);
      });
      ptend.forEach((n, i) => {                               // the chimney, radiating
        const a = PLANTENDRILS[i];
        const pts = [[320 + Math.cos(a) * 14, 254 + Math.sin(a) * 14]];
        for (let q = 1; q <= 4; q++) {
          const wob = Math.sin(t * .2 + q * 1.1 + i * 1.7) * 4;
          const r = 14 + q * 19;
          pts.push([320 + Math.cos(a + wob * .01 * q) * r * 1.15,
            254 + Math.sin(a + wob * .01 * q) * r * .95 + wob * .4]);
        }
        n.setAttribute("points", pts.map(p2 => p2.join(",")).join(" "));
      });
      const blink = (t % 90) > 86;                            // he blinks, rarely
      eyeL.setAttribute("ry", blink ? 1 : 6.5); eyeL.setAttribute("rx", 6.5);
      eyeR.setAttribute("ry", blink ? 1 : 6.5); eyeR.setAttribute("rx", 6.5);
      typeOn(foot, "THREE FACES, TWO DOORS, ONE CHIMNEY.", Math.min(t, 239), 100, 1.7);
    });
  });

})();
