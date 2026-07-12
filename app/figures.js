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
  const META = {"autarch": ["svg", 640, 420], "autarch-c": ["svg", 640, 420], "autarch-e": ["svg", 640, 420], "bats": ["canvas", 640, 300], "bats-c": ["svg", 640, 360], "blade": ["canvas", 640, 360], "canopic-c": ["svg", 640, 400], "centipede": ["svg", 640, 360], "core": ["svg", 640, 360], "cylinders": ["svg", 640, 400], "cylinders-b": ["svg", 640, 400], "dagger": ["svg", 640, 360], "epitaph": ["svg", 640, 400], "ext1c": ["svg", 640, 400], "ext1e": ["svg", 640, 400], "fungus": ["svg", 640, 360], "glowstone": ["canvas", 640, 300], "guts-a": ["svg", 640, 360], "guts-b": ["svg", 640, 360], "guts-c": ["svg", 640, 360], "hound": ["svg", 640, 360], "jackal": ["svg", 640, 360], "jar-baboon": ["svg", 640, 300], "jar-falcon": ["svg", 640, 300], "jar-human": ["svg", 640, 300], "jar-jackal": ["svg", 640, 300], "jar-mantis": ["svg", 640, 300], "mystic-b": ["svg", 640, 400], "road": ["svg", 640, 400], "seal": ["svg", 640, 400], "seal-b": ["svg", 640, 400], "shard": ["svg", 640, 360], "silas": ["svg", 640, 400], "spawn-a": ["svg", 640, 360], "spawn-b": ["svg", 640, 360], "spawn-c": ["svg", 640, 360], "sphere-b": ["svg", 640, 420], "tesseract": ["canvas", 640, 360], "ulfire": ["svg", 640, 360]};
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

  /* ---------------- 01: tesseract ---------------- */
  FIG._define("tesseract", "canvas", function (cv) {
    const ctx = cv.getContext("2d");
    const verts = [], edges = [];
    for (let i = 0; i < 16; i++) verts.push([1,2,4,8].map(b => (i & b) ? 1 : -1));
    for (let i = 0; i < 16; i++) for (const b of [1,2,4,8]) if (!(i & b)) edges.push([i, i | b]);
    clock(t => {
      const a = (t % 96) * Math.PI / 48, b = (t % 144) * Math.PI / 72;
      ctx.fillStyle = BG; ctx.fillRect(0, 0, cv.width, cv.height);
      const inner = [], outer = [], pts = verts.map(v => {
        let [x, y, z, w] = v;
        [x, w] = rot(x, w, a); [y, z] = rot(y, z, b); [z, w] = rot(z, w, a * .5);
        const s4 = 1.6 / (2.6 - w);           // 4D -> 3D
        x *= s4; y *= s4; z *= s4;
        const s3 = 300 / (4 - z * 1.2);       // 3D -> 2D
        return { p: [320 + x * s3, 180 + y * s3], w };
      });
      edges.forEach(([i, j]) => ((pts[i].w + pts[j].w) < 0 ? inner : outer).push([i, j]));
      drawEdges(ctx, pts.map(q => q.p), inner, PH_DIM, 4);
      drawEdges(ctx, pts.map(q => q.p), outer, PH, 9);
      // the METIS garnish: impossible debris, each shape awake for a moment
      const DEBRIS = [
        (x, y) => { ctx.strokeRect(x - 6, y - 6, 12, 12); },
        (x, y) => { ctx.beginPath(); ctx.moveTo(x, y - 8); ctx.lineTo(x + 7, y);
                    ctx.lineTo(x, y + 8); ctx.lineTo(x - 7, y); ctx.closePath(); ctx.stroke(); },
        (x, y) => { ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.stroke();
                    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.stroke(); },
        (x, y) => { ctx.beginPath(); ctx.moveTo(x - 8, y + 4); ctx.lineTo(x - 2, y - 6);
                    ctx.lineTo(x + 3, y + 2); ctx.lineTo(x + 9, y - 5); ctx.stroke(); },
      ];
      ctx.strokeStyle = PH_DIM; ctx.lineWidth = 1.2; ctx.shadowColor = PH; ctx.shadowBlur = 5;
      DEBRIS.forEach((draw, i) => {
        if (Math.floor(t / 7 + i * 2.5) % 4) return;   // each wakes in turn
        const th = t * .05 + i * Math.PI / 2;
        draw(320 + Math.cos(th) * 190, 180 + Math.sin(th) * 105);
      });
      ctx.shadowBlur = 0; ctx.fillStyle = PH_DIM; ctx.font = "11px ui-monospace, monospace";
      ctx.fillText("INTERIOR: ADVISORY", 18, 340);
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

  /* ---------------- 06: the burial cylinders ---------------- */
  FIG._define("cylinders", "svg", function (svg) {
    const AMBER = "#ffd06a", VIRIDIAN = "#4ee0a8";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF WARRIORS / GUARD ISSUE / GEL-KEPT";
    const CYLS = [
      { cx: 105, hue: AMBER,    name: "AMBER",    note: "AMBER: A RESPIRATOR, STILL SEALED" },
      { cx: 245, hue: VIRIDIAN, name: "VIRIDIAN", note: "VIRIDIAN: MAGNETIC BOOTS, GUARD ISSUE" },
      { cx: 385, hue: FUNGUS,   name: "ORANGE",   note: "ORANGE: A PLASMA-IGNITER -- AND A BLOOM" },
      { cx: 525, hue: PH_DIM,   name: "BURST",    note: "BURST: KIT OUTLASTS ITS OWNERS", burst: true },
    ];
    const groups = CYLS.map((c, i) => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      const put = (n, a) => { const q = document.createElementNS(NS, n);
        for (const k in a) q.setAttribute(k, a[k]); g.appendChild(q); return q; };
      const gel = stipple(svg, "gel" + i, c.hue, 1);
      if (!c.burst) {
        put("rect", { x: c.cx - 32, y: 130, width: 64, height: 186, fill: gel });
        put("line", { x1: c.cx - 34, y1: 122, x2: c.cx - 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
        put("line", { x1: c.cx + 34, y1: 122, x2: c.cx + 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 122, rx: 34, ry: 9, fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 318, rx: 34, ry: 9, fill: "none", stroke: PH });
        // the tenant, at an attention no order will relieve
        put("circle", { cx: c.cx, cy: 165, r: 7, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
        put("polyline", { points: `${c.cx-11},178 ${c.cx+11},178 ${c.cx+8},240 ${c.cx+6},296 ` +
          `${c.cx-6},296 ${c.cx-8},240 ${c.cx-11},178`, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
        put("line", { x1: c.cx - 9, y1: 196, x2: c.cx + 7, y2: 212, stroke: PH_DIM });
        put("line", { x1: c.cx + 9, y1: 196, x2: c.cx - 7, y2: 212, stroke: PH_DIM });
        if (c.name === "ORANGE") // the bloom, veining like pressed flowers
          [[-22, 300, -14, 250, -20, 214], [0, 306, 4, 262, -2, 226], [20, 300, 14, 246, 22, 208]]
            .forEach(v => put("polyline", { points:
              `${c.cx+v[0]},${v[1]} ${c.cx+v[2]},${v[3]} ${c.cx+v[4]},${v[5]}`,
              fill: "none", stroke: FUNGUS, "stroke-width": 1 }));
      } else {
        // the burst one: a jagged stump, shards, the spill, the slumped dead
        put("polyline", { points: `${c.cx-34},318 ${c.cx-34},236 ${c.cx-22},252 ${c.cx-12},230 ` +
          `${c.cx},248 ${c.cx+12},226 ${c.cx+22},250 ${c.cx+34},232 ${c.cx+34},318`,
          fill: "none", stroke: PH, "stroke-width": 1.5 });
        put("ellipse", { cx: c.cx, cy: 318, rx: 34, ry: 9, fill: "none", stroke: PH });
        put("ellipse", { cx: c.cx, cy: 336, rx: 52, ry: 8, fill: gel, stroke: "none" });
        [[-48, 300, -40, 290], [44, 306, 52, 296], [40, 316, 50, 314]].forEach(v =>
          put("line", { x1: c.cx + v[0], y1: v[1], x2: c.cx + v[2], y2: v[3], stroke: PH_BRIGHT }));
        put("polyline", { points: `${c.cx-20},306 ${c.cx-6},296 ${c.cx+10},304 ${c.cx+20},298`,
          fill: "none", stroke: PH_DIM, "stroke-width": 1.6 }); // the slump
      }
      const cap = label(svg, c.cx, 362, 10, c.hue); cap.setAttribute("text-anchor", "middle");
      cap.textContent = c.name;
      return { g, c };
    });
    // bubbles, on the step clock (the gel is alive enough to breathe)
    const bubbles = [];
    groups.forEach(({ c }, i) => {
      if (c.burst) return;
      for (let b = 0; b < 3; b++) {
        const q = el(svg, "circle", { cx: c.cx + (b - 1) * 12, cy: 300, r: 2, fill: "none",
          stroke: c.hue, opacity: .8 });
        bubbles.push({ q, phase: i * 31 + b * 57 });
      }
    });
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE BURIAL CYLINDERS", T, 4, 1.4);
      groups.forEach(({ g }, i) => g.setAttribute("opacity", T > 10 + i * 7 ? 1 : 0));
      bubbles.forEach(b => b.q.setAttribute("cy", 300 - ((t * 3 + b.phase) % 156)));
      const k = Math.floor(T / 26) % CYLS.length;
      if (T > 40) {
        const c = CYLS[k];
        callLead.setAttribute("points", `${c.cx},116 ${c.cx},58 448,58`);
        call.textContent = c.note;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "BREAK AMBER FIRST. WEAR WHAT YOU FIND.", T, 120, 1.6);
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
    const verdict = label(svg, 330, 334, 10, FUNGUS);
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
      typeOn(verdict, "FOUR THOUSAND YEARS, HOLDING. DO NOT LIGHT THE GEL.", T, 90, 1.6);
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

  /* ---------------- 06-B: the burial cylinders, intact ---------------- */
  FIG._define("cylinders-b", "svg", function (svg) {
    const AMBER = "#ffd06a", VIRIDIAN = "#4ee0a8", CERULEAN = "#7fc4ff";
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 400, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HALL OF WARRIORS / AS INTERRED / SEALED";
    const CYLS = [
      { cx: 105, hue: AMBER,    name: "AMBER",    note: "AMBER: A RESPIRATOR, STILL SEALED" },
      { cx: 245, hue: VIRIDIAN, name: "VIRIDIAN", note: "VIRIDIAN: MAGNETIC BOOTS, GUARD ISSUE" },
      { cx: 385, hue: FUNGUS,   name: "ORANGE",   note: "ORANGE: A PLASMA-IGNITER -- AND A BLOOM" },
      { cx: 525, hue: CERULEAN, name: "CERULEAN", note: "CERULEAN: THE PRISMATIC BLADE, SHEATHED" },
    ];
    const groups = CYLS.map((c, i) => {
      const g = document.createElementNS(NS, "g"); svg.appendChild(g);
      const put = (n, a) => { const q = document.createElementNS(NS, n);
        for (const k in a) q.setAttribute(k, a[k]); g.appendChild(q); return q; };
      const gel = stipple(svg, "gelb" + i, c.hue, 1);
      put("rect", { x: c.cx - 32, y: 130, width: 64, height: 186, fill: gel });
      put("line", { x1: c.cx - 34, y1: 122, x2: c.cx - 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
      put("line", { x1: c.cx + 34, y1: 122, x2: c.cx + 34, y2: 318, stroke: PH, "stroke-width": 1.5 });
      put("ellipse", { cx: c.cx, cy: 122, rx: 34, ry: 9, fill: "none", stroke: PH_BRIGHT, "stroke-width": 1.5 });
      put("ellipse", { cx: c.cx, cy: 318, rx: 34, ry: 9, fill: "none", stroke: PH });
      put("circle", { cx: c.cx, cy: 165, r: 7, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
      put("polyline", { points: `${c.cx-11},178 ${c.cx+11},178 ${c.cx+8},240 ${c.cx+6},296 ` +
        `${c.cx-6},296 ${c.cx-8},240 ${c.cx-11},178`, fill: "none", stroke: PH_DIM, "stroke-width": 1.4 });
      put("line", { x1: c.cx - 9, y1: 196, x2: c.cx + 7, y2: 212, stroke: PH_DIM });
      put("line", { x1: c.cx + 9, y1: 196, x2: c.cx - 7, y2: 212, stroke: PH_DIM });
      if (c.name === "ORANGE") // the bloom, veining like pressed flowers
        [[-22, 300, -14, 250, -20, 214], [0, 306, 4, 262, -2, 226], [20, 300, 14, 246, 22, 208]]
          .forEach(v => put("polyline", { points:
            `${c.cx+v[0]},${v[1]} ${c.cx+v[2]},${v[3]} ${c.cx+v[4]},${v[5]}`,
            fill: "none", stroke: FUNGUS, "stroke-width": 1 }));
      const cap = label(svg, c.cx, 362, 10, c.hue); cap.setAttribute("text-anchor", "middle");
      cap.textContent = c.name;
      return { g, c };
    });
    const bubbles = [];
    groups.forEach(({ c }, i) => {
      for (let b = 0; b < 3; b++) {
        const q = el(svg, "circle", { cx: c.cx + (b - 1) * 12, cy: 300, r: 2, fill: "none",
          stroke: c.hue, opacity: .8 });
        bubbles.push({ q, phase: i * 31 + b * 57 });
      }
    });
    const callLead = el(svg, "polyline", { fill: "none", stroke: PH_DIM, "stroke-dasharray": "3 3" });
    const call = label(svg, 624, 62, 10, PH); call.setAttribute("text-anchor", "end");
    const foot = label(svg, 320, 390, 10, FUNGUS); foot.setAttribute("text-anchor", "middle");
    const doWipe = wipe(svg, 640, 400, 2, 10);
    clock(t => {
      const T = t % 170;
      doWipe(T);
      typeOn(hdr, "THE BURIAL CYLINDERS (INTACT)", T, 4, 1.4);
      groups.forEach(({ g }, i) => g.setAttribute("opacity", T > 10 + i * 7 ? 1 : 0));
      bubbles.forEach(b => b.q.setAttribute("cy", 300 - ((t * 3 + b.phase) % 156)));
      const k = Math.floor(T / 26) % CYLS.length;
      if (T > 40) {
        const c = CYLS[k];
        callLead.setAttribute("points", `${c.cx},116 ${c.cx},58 448,58`);
        call.textContent = c.note;
      } else { call.textContent = ""; callLead.setAttribute("points", ""); }
      typeOn(foot, "AS THE TOMBWRIGHTS LEFT THEM. NOTHING HAS COME SCAVENGING. YET.", T, 120, 1.6);
    });
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

  /* ---------------- 20: the glass centipede ---------------- */
  FIG._define("centipede", "svg", function (svg) {
    el(svg, "rect", { x: 0, y: 0, width: 640, height: 360, fill: BG });
    el(svg, "line", { x1: 16, y1: 34, x2: 624, y2: 34, stroke: PH_DIM });
    const hdr = label(svg, 16, 24, 13, PH_BRIGHT);
    const cls = label(svg, 624, 24, 10, PH_DIM); cls.setAttribute("text-anchor", "end");
    cls.textContent = "HAZARD / SILICA / QUICK";
    el(svg, "line", { x1: 0, y1: 316, x2: 640, y2: 316, stroke: PH, "stroke-width": 1.4 });
    for (let x = 30; x < 640; x += 74)                        // rubble on the floor
      el(svg, "polyline", { fill: "none", stroke: PH_DIM,
        points: `${x},316 ${x + 6},308 ${x + 13},316` });
    const GLASS = "#cfefff";
    const wave = x => 286 + Math.sin(x * .018) * 16;
    const DASH = [[20, 28], [44, 52], [68, 76], [92, 100], [116, 124], [140, 148]];
    // it does not stop when it goes unseen (CCB): 4 px/frame in the light,
    // 5 in the dark -- it gains ground while your eye loses it, so every
    // reappearance is ahead of the vanishing point.
    const seenIn = T => DASH.reduce((a, [s2, e2]) =>
      a + Math.max(0, Math.min(T, e2 + 3) - s2), 0);
    const pos = T => { const sf = seenIn(T); return -40 + sf * 4 + (T - sf) * 5; };
    const segs = Array.from({ length: 16 }, () => el(svg, "ellipse",
      { rx: 8, ry: 5, fill: "none", stroke: GLASS, "stroke-width": 1.3, opacity: 0 }));
    const legs = Array.from({ length: 32 }, () => el(svg, "line",
      { stroke: "#9fd9f2", "stroke-width": 1, opacity: 0 }));
    const feelers = [0, 1].map(() => el(svg, "line",
      { stroke: GLASS, "stroke-width": 1.2, opacity: 0 }));
    const glints = ["#ff5a5a", "#ffd76a", "#7fff9e", GLASS, GLASS,
      "#9fd9f2", GLASS, "#ffd76a"].map(c =>
      el(svg, "circle", { r: 2, fill: c, opacity: 0 }));
    label(svg, 24, 350, 10, PH_DIM).textContent = "VISIBILITY";
    const cells = Array.from({ length: 6 }, (_, i) =>
      el(svg, "rect", { x: 110 + i * 16, y: 340, width: 12, height: 11,
        fill: GLASS, "fill-opacity": .08 }));
    const foot = label(svg, 630, 350, 10, FUNGUS); foot.setAttribute("text-anchor", "end");
    const doWipe = wipe(svg, 640, 360, 2, 10);
    clock(t => {
      const T = t % 168;
      doWipe(T);
      typeOn(hdr, "THE GLASS CENTIPEDE", T, 4, 1.4);
      const hx = pos(T);
      const seen = DASH.some(([s2, e2]) => T >= s2 && T < e2 + 3);
      segs.forEach((n, i) => {
        const x = hx - i * 13, y = wave(x);
        n.setAttribute("cx", x); n.setAttribute("cy", y);
        n.setAttribute("opacity", seen && x > -20 && x < 660 ? .9 - i * .02 : 0);
        [0, 1].forEach(k => {
          const L2 = legs[i * 2 + k];
          L2.setAttribute("x1", x - 3 + k * 6); L2.setAttribute("y1", y + 4);
          L2.setAttribute("x2", x - 6 + k * 12); L2.setAttribute("y2", y + 13);
          L2.setAttribute("opacity", seen && x > -20 && x < 660 ? .7 : 0);
        });
      });
      feelers.forEach((n, k) => {
        n.setAttribute("x1", hx + 6); n.setAttribute("y1", wave(hx) - 2);
        n.setAttribute("x2", hx + 20); n.setAttribute("y2", wave(hx) - 10 + k * 12);
        n.setAttribute("opacity", seen ? .9 : 0);
      });
      glints.forEach((n, j) => {                              // the sparkling wake
        const gi = (Math.floor(t / 2) * 7 + j * 5) % 22;      // 16 body + 6 wake
        const x = hx - gi * 13;
        n.setAttribute("cx", x + ((t + j) % 3) - 1); n.setAttribute("cy", wave(x) + ((t * j) % 5) - 2);
        n.setAttribute("opacity", !seen && (t + j * 2) % 5 < 2 && x > 0 && x < 640 ? .9 : 0);
      });
      const on = seen ? 6 : (t % 7 === 0 ? 1 : 0);
      cells.forEach((r, i) => r.setAttribute("fill-opacity", i < on ? .8 : .08));
      typeOn(foot, "FOUR FEET OF GLASS. FASTER THAN THE EYE WANTS TO ALLOW.", T, 20, 1.8);
    });
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
