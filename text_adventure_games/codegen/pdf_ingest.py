"""PDF -> color-tagged structured page representation.

Pure-Python, no LLM. Reads a PDF with PyMuPDF (``pymupdf``) and returns one
``ColorTaggedPage`` per page in the requested range, plus a helper to read
the table of contents into clean ``{game_name: (start, end)}`` ranges.

The output is what the extraction stage prompts the LLM with -- by tagging
every span as ``flavor`` (black, read-aloud) or ``rule`` (cyan, parser
logic) we preserve the load-bearing color distinction in the Parsely book
without sending the LLM page images.

Underlined nouns -- Parsely's convention for items -- are detected by
searching ``page.get_drawings()`` for short horizontal-line primitives near
text baselines. Color rendering in the PDF uses two near-identical cyans
(``#00aeef`` and ``#00b3f0``) which are normalized to a single ``"rule"``
channel here so downstream code never has to choose.

This module imports ``pymupdf`` lazily so the rest of the engine works
without it; the codegen package only requires it for PDF-driven extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Color thresholds (24-bit RGB packed integers from PyMuPDF span.color).
_FLAVOR_BLACK = 0x231F20
_RULE_CYANS = {0x00AEEF, 0x00B3F0}

# Underline detection tuned against Action Castle pages 15-28:
# 2pt < width < 60pt and slope ~ 0.
_UNDERLINE_MIN_WIDTH = 2.0
_UNDERLINE_MAX_WIDTH = 60.0
_UNDERLINE_SLOPE_MAX = 0.5
# How close the underline's y must be to a span's baseline (in points).
_UNDERLINE_BASELINE_TOL = 2.5


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class ColorTaggedSpan:
    """One PDF text span, tagged by role.

    ``color`` is one of ``"flavor"`` (black body text), ``"rule"`` (the
    cyan parser-rule text), or ``"other"`` (titles, page numbers, decorative
    text). The extraction stage typically ignores ``"other"``.
    """

    text: str
    color: str  # "flavor" | "rule" | "other"
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    underlined_words: list[str] = field(default_factory=list)


@dataclass
class ColorTaggedPage:
    page_number: int  # 1-indexed (matches the PDF's own pagination)
    spans: list[ColorTaggedSpan] = field(default_factory=list)
    item_nouns: list[str] = field(default_factory=list)
    title_guess: str | None = None

    def flavor_text(self) -> str:
        return " ".join(s.text for s in self.spans if s.color == "flavor")

    def rule_text(self) -> str:
        return " ".join(s.text for s in self.spans if s.color == "rule")


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def ingest_pdf(
    pdf_path: str | Path, page_range: tuple[int, int]
) -> list[ColorTaggedPage]:
    """Parse the given inclusive 1-indexed ``page_range`` (e.g. ``(15, 28)``).

    Returns one ``ColorTaggedPage`` per page. Spans are emitted in reading
    order. Underlined nouns are attached to the span they overlap with and
    also collected into ``ColorTaggedPage.item_nouns`` (deduplicated, order
    of first appearance) -- this is the per-page candidate item list the
    extractor uses.
    """
    import pymupdf  # type: ignore

    start, end = page_range
    doc = pymupdf.open(str(pdf_path))
    try:
        pages: list[ColorTaggedPage] = []
        for pno in range(start - 1, min(end, doc.page_count)):
            page = doc[pno]
            pages.append(_ingest_one_page(page, pno + 1))
        return pages
    finally:
        doc.close()


def game_page_ranges(pdf_path: str | Path) -> dict[str, tuple[int, int]]:
    """Read the PDF's table of contents into ``{game_name: (start, end)}``.

    Top-level entries (TOC depth 1) are treated as games. Each entry's range
    runs from its start page up to the page before the next top-level
    entry (or the end of the document for the last entry). Non-game TOC
    entries that you want to exclude (e.g. ``Hello``, ``Readme``, ``Index``)
    are still returned -- the caller can filter by name.
    """
    import pymupdf  # type: ignore

    doc = pymupdf.open(str(pdf_path))
    try:
        toc = [e for e in doc.get_toc() if e[0] == 1]
        if not toc:
            return {}
        result: dict[str, tuple[int, int]] = {}
        for i, entry in enumerate(toc):
            _, title, start = entry
            end = toc[i + 1][2] - 1 if i + 1 < len(toc) else doc.page_count
            result[title.strip()] = (start, end)
        return result
    finally:
        doc.close()


# ----------------------------------------------------------------------
# Per-page parsing
# ----------------------------------------------------------------------


def _ingest_one_page(page, page_number: int) -> ColorTaggedPage:
    underlines = _underline_strokes(page)
    out = ColorTaggedPage(page_number=page_number)
    raw = page.get_text("dict")
    biggest = (0.0, "")  # (font size, text) for title_guess
    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # type 0 == text
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                color_int = span.get("color", 0)
                color = _classify_color(color_int)
                bbox = tuple(span.get("bbox", (0, 0, 0, 0)))
                font = span.get("font", "")
                size = float(span.get("size", 0))
                underlined = _underlined_words_for(text, bbox, underlines)
                out.spans.append(
                    ColorTaggedSpan(
                        text=text,
                        color=color,
                        bbox=bbox,
                        font=font,
                        size=size,
                        underlined_words=underlined,
                    )
                )
                # Track the biggest font near the top of the page as the
                # title candidate. The first half of the page typically
                # contains the location heading.
                if (
                    bbox[1] < page.rect.height / 2
                    and size > biggest[0]
                    and color != "other"
                ):
                    biggest = (size, text)
    # Deduplicate item_nouns preserving first-appearance order.
    seen: set[str] = set()
    for s in out.spans:
        for w in s.underlined_words:
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                out.item_nouns.append(w)
    if biggest[1]:
        out.title_guess = biggest[1]
    return out


def _classify_color(color_int: int) -> str:
    if color_int == _FLAVOR_BLACK:
        return "flavor"
    if color_int in _RULE_CYANS:
        return "rule"
    return "other"


def _underline_strokes(page) -> list[tuple[float, float, float]]:
    """Return ``[(y, x_start, x_end), ...]`` for short horizontal underlines.

    Filters ``page.get_drawings()`` for short ``"l"`` (line) primitives with
    near-zero slope. The width window rejects long horizontal rules (page
    dividers) and stray decorative strokes.
    """
    strokes: list[tuple[float, float, float]] = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            if not item or item[0] != "l":
                continue
            p1, p2 = item[1], item[2]
            dy = abs(p1.y - p2.y)
            dx = abs(p1.x - p2.x)
            if dy > _UNDERLINE_SLOPE_MAX:
                continue
            if not (_UNDERLINE_MIN_WIDTH < dx < _UNDERLINE_MAX_WIDTH):
                continue
            y = (p1.y + p2.y) / 2
            x_start = min(p1.x, p2.x)
            x_end = max(p1.x, p2.x)
            strokes.append((y, x_start, x_end))
    return strokes


def _underlined_words_for(
    text: str,
    span_bbox: tuple[float, float, float, float],
    underlines: list[tuple[float, float, float]],
) -> list[str]:
    """Return the words (or short phrases) within ``text`` that an underline
    sits beneath.

    PyMuPDF spans don't expose per-word x-positions, so we estimate them
    by linearly interpolating character offsets across the span's x-range
    (assumes near-monospaced character widths -- close enough for the
    short underlines Parsely uses, which the width window already caps at
    60pt). For each underline whose baseline matches this span's baseline,
    we collect the contiguous words whose midpoints fall inside the
    underline's x-range; consecutive underlined words become one phrase
    ("vending machine" rather than ["vending", "machine"]).

    The old behavior -- crediting the entire span text whenever any
    underline touched it -- was lossy: a flavor sentence like "A can of
    soda drops out of the machine" with an underline under "soda" alone
    was attributed as "A can of soda drops" because the whole span won.
    """
    if not underlines:
        return []
    x0, y0, x1, y1 = span_bbox
    span_baseline = y1  # bottom edge -- close enough to baseline for our use
    span_x_lo = min(x0, x1)
    span_x_hi = max(x0, x1)
    span_width = max(span_x_hi - span_x_lo, 0.001)

    matching: list[tuple[float, float]] = []
    for uy, ux_start, ux_end in underlines:
        if abs(uy - span_baseline) > _UNDERLINE_BASELINE_TOL:
            continue
        # x-range overlap with the span.
        if ux_end < span_x_lo or ux_start > span_x_hi:
            continue
        matching.append((ux_start, ux_end))
    if not matching:
        return []

    # Map each word to an estimated x-range via character-count interpolation.
    words = text.split()
    if not words:
        return []
    # Total characters including single-space separators between words.
    total_chars = sum(len(w) for w in words) + max(len(words) - 1, 0)
    if total_chars <= 0:
        return []
    char_pos = 0
    word_ranges: list[tuple[str, float, float]] = []
    for w in words:
        w_start = span_x_lo + (char_pos / total_chars) * span_width
        char_pos += len(w)
        w_end = span_x_lo + (char_pos / total_chars) * span_width
        char_pos += 1  # one space separator
        word_ranges.append((w, w_start, w_end))

    def _normalize(phrase: str) -> str:
        return phrase.strip().strip(".,;:!?“”\"'")

    found: list[str] = []
    for ux_start, ux_end in matching:
        phrase_words: list[str] = []
        for word, w_start, w_end in word_ranges:
            midpoint = (w_start + w_end) / 2
            in_range = ux_start <= midpoint <= ux_end
            if in_range:
                phrase_words.append(word)
            else:
                if phrase_words:
                    phrase = _normalize(" ".join(phrase_words))
                    if phrase and phrase.lower() not in (f.lower() for f in found):
                        found.append(phrase)
                    phrase_words = []
        if phrase_words:
            phrase = _normalize(" ".join(phrase_words))
            if phrase and phrase.lower() not in (f.lower() for f in found):
                found.append(phrase)
    return found
