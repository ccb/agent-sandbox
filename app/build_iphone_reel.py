#!/usr/bin/env python3
"""Assemble app/dist/animations-iphone/index.html -- the phone-legible reel.

Parallel to the /animations/ reel, but showing every ``KEY-m`` twin from
figures.js at a phone column width (the iPhone versions of the cards). The page
is self-contained: figures.js is inlined, so it never touches the live game.
Adding a ``-m`` card to app/prototypes/retro-animations.html and rebuilding
grows this page automatically.

    uv run python app/build_iphone_reel.py      # -> app/dist/animations-iphone/
    ./app/deploy_iphone_reel.sh                 # push just that dir to gh-pages
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REEL = os.path.join(HERE, "prototypes", "retro-animations.html")
FIGJS = os.path.join(HERE, "figures.js")
TEMPLATE = os.path.join(HERE, "animations-iphone.html")
OUTDIR = os.path.join(HERE, "dist", "animations-iphone")


def _m_cards(html):
    """[(key, title)] for every ``-m`` card, in reel order.

    Each card sits under a ``<div class="slate"><h2>TITLE</h2>`` and renders
    into a ``<svg id="KEY">`` or ``<canvas id="KEY">``; we walk both markers in
    document order and pair each screen with the nearest preceding slate title,
    then keep the ``-m`` ids.
    """
    cards, last_title = [], None
    for m in re.finditer(r'<h2>(.*?)</h2>|<(?:svg|canvas) id="([^"]+)"', html, re.S):
        if m.group(1) is not None:
            last_title = re.sub(r"\s+", " ", m.group(1).replace("&mdash;", "—")).strip()
        elif m.group(2).endswith("-m"):
            cards.append((m.group(2), last_title))
    return cards


def build():
    # figures.js regenerates from the reel every build (single source of truth)
    sys.path.insert(0, HERE)
    import gen_figures

    gen_figures.generate()

    html = open(REEL, encoding="utf-8").read()
    fig = open(FIGJS, encoding="utf-8").read()
    tpl = open(TEMPLATE, encoding="utf-8").read()
    cards = _m_cards(html)

    assert "</script>" not in fig, "figures.js has a script-closing tag; escape needed"
    page = tpl.replace("/*__FIGURES_JS__*/", fig).replace(
        "/*__CARDS__*/", json.dumps(cards)
    )
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    return cards


if __name__ == "__main__":
    cards = build()
    print(f"animations-iphone: {len(cards)} phone card(s) -> {OUTDIR}")
    for key, title in cards:
        print(f"  {key:14s} {title}")
