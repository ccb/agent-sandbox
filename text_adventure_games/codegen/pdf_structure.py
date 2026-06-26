"""Structured intermediate over ``pdf_ingest.ColorTaggedPage``.

The raw ingest emits one span per text run in reading order, tagged ``flavor``
/ ``rule`` / ``other``. That's what the LLM used to consume directly -- and it
worked, except the model kept dropping rules whenever they sat across a column
break or a page break, and it had no clean way to tell "EXAMINE WIZARD:" apart
from a description sentence that happened to be cyan.

This module rebuilds the layout structure that's visible to a human reader:

  * A **LocationBlock** for each room heading on the page (font ``Uni0553``,
    size >= 16). The room owns every span whose y-coordinate falls between its
    heading and the next heading.
  * An **Interaction** for each cyan verb header ("EXAMINE LAMP:", "USE
    FISHING POLE:") plus the adjacent black response and any continuation
    rule bullets that follow.
  * An **ExitRow** for each "DIRECTION page N TARGET" line that follows the
    "X exits are:" opener at the bottom of a location block.
  * **floating_spans** for anything we couldn't bucket. The downstream prompt
    still shows these so the heuristic never silently drops content.

Heuristics are intentionally conservative: when in doubt, fall through to
``floating_spans`` rather than mis-classify. Driven by a real failing
example beats speculative coverage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_ingest import ColorTaggedPage, ColorTaggedSpan

# ---- Font / size signatures (calibrated against Parsely_r31_final.pdf) ----
_ROOM_HEADING_FONT = "Uni0553"
_ROOM_HEADING_MIN_SIZE = 16.0  # excludes 60pt drop-caps
_SECTION_HEADER_FONT = "Realtime-Black"
_SECTION_HEADER_MIN_SIZE = 14.0
_SECTION_HEADER_MAX_SIZE = 17.5
_VERB_HEADER_FONT = "Realtime-Bold"
_BODY_FONT_PREFIX = "Decour"  # Decour-Regular, Decour-RegularItalic, etc.
_MENU_SIDEBAR_FONT = "SHPinscher-Regular"
_PAGE_NUMBER_FONT = "Realtime-Black"

# Bullet markers Parsely uses on rule continuation lines and exit rows.
_BULLET_RE = re.compile(r"^[>\s]+")
# Verb-header pattern: ALL CAPS (with /, ', digits, spaces) ending in a colon.
_VERB_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9 /’'.’ -]*:")
# Exit-table opener: "ROOM NAME exits are:".
_EXIT_TABLE_OPENER_RE = re.compile(r"^[A-Z][A-Z 0-9'’ -]+ exits are:?\s*$")
# Epilogue / section sub-header: "1. VICTORY!", "2. THE HITCHHIKER", etc.
_SECTION_NUMBER_RE = re.compile(r"^\d+\.\s+\S")


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class Interaction:
    """One cyan verb header plus the adjacent black response and rules.

    ``verb_header`` is the raw text including the trailing colon (e.g.
    ``"EXAMINE LAMP:"``). ``response`` is the immediately following black
    flavor text. ``rules`` are the bulleted continuation lines (still cyan)
    that document preconditions / side effects beyond the response.
    """

    verb_header: str
    response: str = ""
    rules: list[str] = field(default_factory=list)
    underlined_nouns: list[str] = field(default_factory=list)
    y: float = 0.0


@dataclass
class ExitRow:
    """One row of a ROOM exits table.

    ``direction`` is the player-typed verb (``"north"``, ``"out"``,
    ``"enter cavern"``). ``target_page`` is the page number printed in the
    table (handy for cross-referencing); ``target_name`` is the room name.
    """

    direction: str
    target_name: str
    target_page: int | None = None
    raw: str = ""


@dataclass
class LocationBlock:
    """A single location on the page.

    Holds the room heading, the leading description paragraphs, the
    interactions in document order, and the exits table.
    """

    name: str
    page_number: int
    description: str = ""
    interactions: list[Interaction] = field(default_factory=list)
    exits: list[ExitRow] = field(default_factory=list)
    designer_notes: list[str] = field(default_factory=list)
    underlined_nouns: list[str] = field(default_factory=list)
    y_start: float = 0.0


@dataclass
class StructuredPage:
    """Structured view of one PDF page.

    ``locations`` are the room blocks anchored by ``Uni0553`` headings.
    ``floating_spans`` capture everything we couldn't bucket -- the
    extractor still surfaces these so nothing the LLM might need silently
    disappears.
    """

    page_number: int
    locations: list[LocationBlock] = field(default_factory=list)
    floating_spans: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def structure_pages(pages: list[ColorTaggedPage]) -> list[StructuredPage]:
    return [_structure_one_page(p) for p in pages]


def format_location(loc: LocationBlock) -> str:
    """Render one ``LocationBlock`` as compact, LLM-friendly text.

    The block starts at column 0 with ``location: '<name>'`` and nests its
    description, interactions (verb header + response + rule bullets), and
    exit table (each with its cross-reference page) underneath. This is the
    shared rendering used by both :func:`extract._format_pages` (the codegen
    prompt) and :func:`source_view.render_source` (the porting view), so the
    two can't drift.
    """
    lines = [f"location: {loc.name!r}"]
    if loc.description:
        lines.append(f"  description: {loc.description!r}")
    if loc.underlined_nouns:
        lines.append(f"  underlined_nouns: {loc.underlined_nouns!r}")
    for note in loc.designer_notes:
        lines.append(f"  designer_note: {note!r}")
    if loc.interactions:
        lines.append("  interactions:")
        for ix in loc.interactions:
            lines.append(f"    - verb: {ix.verb_header!r}")
            if ix.response:
                lines.append(f"      response: {ix.response!r}")
            for rule in ix.rules:
                lines.append(f"      rule: {rule!r}")
            if ix.underlined_nouns:
                lines.append(f"      underlined_nouns: {ix.underlined_nouns!r}")
    if loc.exits:
        lines.append("  exits:")
        for ex in loc.exits:
            page = f" (page {ex.target_page})" if ex.target_page is not None else ""
            lines.append(
                f"    - direction: {ex.direction!r} -> target: {ex.target_name!r}{page}"
            )
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _structure_one_page(page: ColorTaggedPage) -> StructuredPage:
    result = StructuredPage(page_number=page.page_number)

    game_spans = [s for s in page.spans if _is_game_content(s)]

    headings = [s for s in game_spans if _is_room_heading(s)]
    headings.sort(key=lambda s: s.bbox[1])

    if not headings:
        for s in game_spans:
            result.floating_spans.append(_render_floating(s))
        return result

    # Bucket non-heading spans by which heading they fall under, using
    # y-coordinate. Single-column layout (the dominant Parsely format)
    # means a span belongs to the most recent heading above it.
    boundaries = [h.bbox[1] for h in headings] + [float("inf")]
    buckets: list[list[ColorTaggedSpan]] = [[] for _ in headings]
    for s in game_spans:
        if s in headings:
            continue
        y = s.bbox[1]
        for i in range(len(headings)):
            if boundaries[i] <= y < boundaries[i + 1]:
                buckets[i].append(s)
                break
        else:
            # Above the first heading (e.g. column-spanning prologue text).
            result.floating_spans.append(_render_floating(s))

    for heading, bucket_spans in zip(headings, buckets):
        block = _build_location_block(heading, bucket_spans, page.page_number)
        result.locations.append(block)

    return result


def _build_location_block(
    heading: ColorTaggedSpan,
    spans: list[ColorTaggedSpan],
    page_number: int,
) -> LocationBlock:
    block = LocationBlock(
        name=_normalize_heading_text(heading.text),
        page_number=page_number,
        y_start=heading.bbox[1],
    )

    # Sort by y for predictable processing inside the bucket. PyMuPDF
    # already groups by block, but the bucket may have inherited two
    # different blocks (description block + exits block) in mixed order.
    spans = sorted(spans, key=lambda s: (round(s.bbox[1], 1), s.bbox[0]))

    # Pass 1: split spans into pre-table content vs exit-table content.
    table_start = _find_exit_table_start(spans)
    pre_table = spans[:table_start] if table_start is not None else spans
    table_spans = spans[table_start:] if table_start is not None else []

    # Pass 2: classify pre-table spans into description / interactions.
    _classify_pre_table(block, pre_table)

    # Pass 3: parse exit table.
    if table_spans:
        _parse_exit_table(block, table_spans)

    # Roll up underlined nouns from everywhere -- handy for the prompt.
    seen: set[str] = set()
    for src in [block.description, *(i.response for i in block.interactions)]:
        for w in _underlined_in(src, spans):
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                block.underlined_nouns.append(w)
    return block


def _classify_pre_table(block: LocationBlock, spans: list[ColorTaggedSpan]) -> None:
    """Walk the bucket and pair cyan verb headers with the next black response.

    Description = leading flavor spans before the first verb header.
    Interaction = verb-header span + the following flavor span(s) on/near
    the same baseline + any continuation rule bullets that follow.
    """
    chunks = _group_into_paragraphs(spans)

    desc_parts: list[str] = []
    current: Interaction | None = None

    for chunk in chunks:
        text = _join_text([c.text for c in chunk])
        if not text:
            continue
        head = chunk[0]
        if _is_verb_header(head):
            # Take only the verb-header span as the header; the rest of the
            # chunk (flavor wrap on the same baseline) is part of the
            # response. The header span's own y is the anchor.
            current = Interaction(verb_header=head.text.strip(), y=head.bbox[1])
            block.interactions.append(current)
            tail_text = _join_text([c.text for c in chunk[1:]])
            tail_nouns: list[str] = []
            for c in chunk[1:]:
                tail_nouns.extend(c.underlined_words)
            if tail_text:
                current.response = tail_text
            for w in tail_nouns:
                if w.lower() not in (n.lower() for n in current.underlined_nouns):
                    current.underlined_nouns.append(w)
            continue
        if head.color == "rule":
            stripped = _strip_bullets(text)
            if not stripped:
                continue
            if current is not None:
                current.rules.append(stripped)
            else:
                block.designer_notes.append(stripped)
            continue
        if head.color == "flavor":
            if current is None:
                desc_parts.append(text)
            else:
                current.response = _join_text([current.response, text])
                for c in chunk:
                    for w in c.underlined_words:
                        if w.lower() not in (
                            n.lower() for n in current.underlined_nouns
                        ):
                            current.underlined_nouns.append(w)

    block.description = _join_text(desc_parts)


def _group_into_paragraphs(
    spans: list[ColorTaggedSpan],
) -> list[list[ColorTaggedSpan]]:
    """Group spans into paragraph chunks of the same color and adjacent y.

    Two same-color spans whose y-baselines differ by <= 16pt and which sit
    in document order are merged. A color change or a y gap > 16pt starts a
    new chunk. This collapses multi-line cyan rule paragraphs (line-wrap)
    into a single chunk, and pairs each verb-header rule with the wrapped
    flavor response that follows on the same baseline.
    """
    chunks: list[list[ColorTaggedSpan]] = []
    current: list[ColorTaggedSpan] = []
    for s in spans:
        if not s.text.strip():
            continue
        if not current:
            current.append(s)
            continue
        prev = current[-1]
        same_color = prev.color == s.color
        # A verb header always starts a new chunk so its rules / response
        # don't get folded into the previous paragraph.
        if _is_verb_header(s):
            chunks.append(current)
            current = [s]
            continue
        # Same-baseline continuations (response wrap, inline bold) can be
        # different color but always belong on the same chunk.
        same_baseline = abs(s.bbox[1] - prev.bbox[1]) < 2.0
        close_y = abs(s.bbox[1] - prev.bbox[1]) <= 16.0
        if (same_color and close_y) or (same_baseline and not _is_verb_header(prev)):
            current.append(s)
        else:
            chunks.append(current)
            current = [s]
    if current:
        chunks.append(current)
    return chunks


def _find_exit_table_start(spans: list[ColorTaggedSpan]) -> int | None:
    for idx, s in enumerate(spans):
        if s.color != "rule":
            continue
        if _EXIT_TABLE_OPENER_RE.match(s.text.strip()):
            return idx
    return None


def _parse_exit_table(block: LocationBlock, table_spans: list[ColorTaggedSpan]) -> None:
    # Sort by y first so column reorder doesn't matter.
    ordered = sorted(table_spans, key=lambda s: (round(s.bbox[1], 1), s.bbox[0]))
    # Drop bullet-only spans that occasionally appear as separate runs.
    rows: list[str] = []
    for s in ordered:
        t = s.text.strip()
        if not t:
            continue
        if _EXIT_TABLE_OPENER_RE.match(t):
            continue  # skip the "X exits are:" opener
        if len(t) <= 1:
            continue  # stray bullet/Wingdings character
        rows.append(t)
    for raw in rows:
        parsed = _parse_exit_row(raw)
        if parsed is not None:
            block.exits.append(parsed)


def _parse_exit_row(raw: str) -> ExitRow | None:
    text = _strip_bullets(raw)
    if not text:
        return None
    tokens = text.split()
    if not tokens:
        return None
    digit_idx = next(
        (i for i, t in enumerate(tokens) if t.isdigit()),
        None,
    )
    if digit_idx is None:
        return None
    page = int(tokens[digit_idx])
    direction_tokens = tokens[:digit_idx]
    # Drop trailing literal 'page' before the digit (e.g. "NORTH page 19 ...").
    if direction_tokens and direction_tokens[-1].lower() == "page":
        direction_tokens = direction_tokens[:-1]
    target_tokens = tokens[digit_idx + 1 :]
    if not direction_tokens or not target_tokens:
        return None
    direction = " ".join(t.lower() for t in direction_tokens)
    target = " ".join(target_tokens)
    return ExitRow(
        direction=direction,
        target_name=_normalize_heading_text(target),
        target_page=page,
        raw=raw,
    )


# ---- Per-span classifiers ----------------------------------------------


def _is_game_content(span: ColorTaggedSpan) -> bool:
    """Drop spans that are page furniture (numbers, banners, sidebars)."""
    text = span.text.strip()
    if not text:
        return False
    # Page number digits.
    if span.font == _PAGE_NUMBER_FONT and text.isdigit():
        return False
    # Top banner (game title at very top of page).
    if span.bbox[1] < 20 and span.size <= 12:
        return False
    # MENU sidebar.
    if span.font == _MENU_SIDEBAR_FONT and span.size >= 16:
        return False
    # Rating tags on cover pages (FANTASY / BEGINNER / EVERYONE etc.).
    if span.size <= 9 and span.font.startswith("Realtime-Regular"):
        return False
    # Wingdings glyphs that escape as single characters.
    if span.font.startswith("Wingdings") and len(text) <= 2:
        return False
    if span.font == "PrintChar21" and len(text) <= 2:
        return False
    # Drop-cap big letters (used for prose chapters, not headings).
    if span.size >= 40 and len(text) <= 2:
        return False
    return True


def _is_room_heading(span: ColorTaggedSpan) -> bool:
    if span.font != _ROOM_HEADING_FONT:
        return False
    if span.size < _ROOM_HEADING_MIN_SIZE or span.size > 25:
        return False
    text = span.text.strip()
    if len(text) < 2:
        return False
    # The map index pages title is "ACTION CASTLE MAP" -- include those;
    # the LLM won't try to model the map page as a room because it has no
    # interactions or exits.
    return True


def _is_verb_header(span: ColorTaggedSpan) -> bool:
    if span.color != "rule":
        return False
    if not span.font.startswith(_VERB_HEADER_FONT):
        return False
    text = _strip_bullets(span.text)
    if not text:
        return False
    if not text.endswith(":"):
        return False
    return bool(_VERB_HEADER_RE.match(text))


# ---- Text utilities ----------------------------------------------------


def _strip_bullets(text: str) -> str:
    return _BULLET_RE.sub("", text).strip()


def _normalize_heading_text(text: str) -> str:
    # Squash repeated whitespace and the U+2009 thin space the Parsely
    # banners like to use.
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def _join_text(parts: list[str]) -> str:
    """Join wrapped text pieces, collapsing whitespace and stripping NBSP."""
    text = " ".join(p for p in parts if p)
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def _render_floating(span: ColorTaggedSpan) -> str:
    tag = span.color.upper()
    snippet = span.text.strip()
    extra = ""
    if span.underlined_words:
        extra = f"   (underlined: {span.underlined_words!r})"
    return f"[{tag}] {snippet}{extra}"


def _underlined_in(
    text: str, spans: list[ColorTaggedSpan]
) -> list[str]:  # noqa: ARG001 (text is current API stub; rolls up from spans)
    nouns: list[str] = []
    for s in spans:
        for w in s.underlined_words:
            nouns.append(w)
    return nouns
