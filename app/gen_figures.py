#!/usr/bin/env python3
"""Generate app/figures.js from the prototype reel (design: retro-animations M1).

The reel -- app/prototypes/retro-animations.html -- is the single source of
truth for every illustration card: a shareable page of self-running blocks,
each targeting its own element by id. This script mechanically re-plumbs those
blocks into a registry the game terminal can draw from on demand:

    <block>  { const svg = document.getElementById("KEY"); ... }
    becomes  FIG._define("KEY", "svg", function (svg) { ... });

plus a small runtime (``window.TombFigures``) that owns element creation, a
shared 12 fps step clock with per-instance counters, pattern-id uniquifying
(two live renders of one card must not share <pattern> ids), and a freeze
policy so a long transcript doesn't accumulate dozens of ticking cards.

Run it directly, or let app/build_dist.py run it at build time. A test
(tests/test_figures.py) regenerates and compares, so the committed figures.js
can never drift from the reel.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REEL = os.path.join(HERE, "prototypes", "retro-animations.html")
OUT = os.path.join(HERE, "figures.js")

SVG_OPEN = re.compile(r'  \{\n    const svg = document\.getElementById\("([^"]+)"\);')
CV_OPEN = re.compile(
    r'  \{\n    const cv = document\.getElementById\("([^"]+)"\), '
    r"ctx = cv\.getContext\(\"2d\"\);"
)


def _match_brace(text, open_pos):
    """Index just past the ``}`` matching the ``{`` at *open_pos*, skipping
    string/template literals and comments (template ``${...}`` nests)."""
    i, n = open_pos, len(text)
    depth = 0
    # stack of contexts: "{" (code brace) or "`" (template literal)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.index("\n", i)
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i = text.index("*/", i) + 2
            continue
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
                    j = _match_brace(text, j + 1)
                    continue
                j += 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces")


def _meta_from_html(html):
    """id -> (kind, w, h) for every .screen element in the reel."""
    meta = {}
    for m in re.finditer(r'<svg id="([^"]+)" viewBox="0 0 (\d+) (\d+)"', html):
        meta[m.group(1)] = ("svg", int(m.group(2)), int(m.group(3)))
    for m in re.finditer(r'<canvas id="([^"]+)" width="(\d+)" height="(\d+)"', html):
        meta[m.group(1)] = ("canvas", int(m.group(2)), int(m.group(3)))
    return meta


def _transform_blocks(body):
    """Rewrite every self-running card block into a FIG._define registration."""
    keys = []
    out, i = [], 0
    while True:
        m_svg = SVG_OPEN.search(body, i)
        m_cv = CV_OPEN.search(body, i)
        m = min((x for x in (m_svg, m_cv) if x), key=lambda x: x.start(), default=None)
        if m is None:
            out.append(body[i:])
            break
        key = m.group(1)
        keys.append(key)
        out.append(body[i : m.start()])
        brace = body.index("{", m.start())
        end = _match_brace(body, brace)  # just past the block's closing }
        inner_from = m.end()
        inner = body[inner_from : end - 1]  # drop the closing }
        if m is m_cv:
            out.append(
                f'  FIG._define("{key}", "canvas", function (cv) {{\n'
                f'    const ctx = cv.getContext("2d");{inner}}});'
            )
        else:
            out.append(f'  FIG._define("{key}", "svg", function (svg) {{{inner}}});')
        i = end
    return "".join(out), keys


def _transform_jar_calls(body):
    """jarCard("key", ...) call sites become deferred defines."""
    keys = []
    for key in re.findall(r'\n  jarCard\("([^"]+)",', body):
        keys.append(key)
        call = f'\n  jarCard("{key}",'
        start = body.index(call)
        paren = body.index("(", start + 3)
        end = _match_paren(body, paren)  # index of the matching )
        # past the ) there is a ; -- keep the original call intact inside a thunk
        assert body[end + 1] == ";", "jarCard call must end with ;"
        original = body[start + 1 : end + 2]  # "  jarCard(...);"
        wrapped = (
            f'  FIG._define("{key}", "svg", function (svg) {{\n'
            f'  {original.replace("jarCard(", "jarCard(svg, ", 1)}\n'
            f"  }});"
        )
        body = body[: start + 1] + wrapped + body[end + 2 :]
    return body, keys


def _match_paren(text, open_pos):
    """Index of the ``)`` matching the ``(`` at *open_pos* (same skipping)."""
    i, n = open_pos, len(text)
    depth = 0
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.index("\n", i)
            continue
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
                    j = _match_brace(text, j + 1)
                    continue
                j += 1
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced parens")


RUNTIME = """\
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
  const META = __META__;
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
"""


def generate():
    html = open(REEL, encoding="utf-8").read()
    meta = _meta_from_html(html)

    a = html.index('<script>\n(() => {\n  "use strict";')
    body_start = html.index('"use strict";', a) + len('"use strict";')
    body_end = html.rindex("})();\n</script>")
    body = html[body_start:body_end]

    # The reel's free-running clock becomes the runtime's registering clock.
    old_clock = (
        "  const timers = [];\n"
        "  function clock(fn) { fn(0); if (reduced) return; let t = 0;\n"
        "    timers.push(setInterval(() => fn(++t), 1000 / FPS)); }"
    )
    assert old_clock in body, "reel clock changed; update gen_figures.py"
    body = body.replace(old_clock, "  function clock(fn) { FIG._clock(fn); }", 1)

    # reduced-motion: route through the runtime's flag.
    old_reduced = (
        '  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;'
    )
    assert old_reduced in body
    body = body.replace(old_reduced, "  const reduced = FIG.reducedMotion;", 1)

    # Pattern ids must be unique per rendered instance, not per card.
    old_stipple = "  function stipple(svg, id, color, r) {"
    assert old_stipple in body
    body = body.replace(
        old_stipple,
        '  function stipple(svg, id, color, r) {\n    id = id + "-f" + (++FIG._uid);',
        1,
    )

    # jarCard: takes the svg it draws into; the reel's lookup line goes.
    old_jar = (
        "  function jarCard(id, title, drawHead, drawInside, CALLS, footText, tick) {\n"
        "    const svg = document.getElementById(id);"
    )
    assert old_jar in body, "jarCard signature changed; update gen_figures.py"
    body = body.replace(
        old_jar,
        "  function jarCard(svg, id, title, drawHead, drawInside, CALLS, "
        "footText, tick) {",
        1,
    )

    body, jar_keys = _transform_jar_calls(body)
    body, block_keys = _transform_blocks(body)

    keys = set(jar_keys) | set(block_keys)
    assert keys == set(meta), (
        f"cards and screens disagree: only-in-js={sorted(keys - set(meta))} "
        f"only-in-html={sorted(set(meta) - keys)}"
    )
    assert "getElementById" not in body, "an element lookup survived the transform"

    meta_js = (
        "{"
        + ", ".join(
            f'"{k}": ["{v[0]}", {v[1]}, {v[2]}]' for k, v in sorted(meta.items())
        )
        + "}"
    )
    js = RUNTIME.replace("__META__", meta_js) + body + "})();\n"
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(js)
    return sorted(keys)


if __name__ == "__main__":
    keys = generate()
    print(f"figures.js: {len(keys)} cards -> {OUT}")
    print(" ".join(keys))
    sys.exit(0)
