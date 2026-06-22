"""Render a slice of a Parsely PDF as compact markdown for a port prompt.

This is the porting front-end to the (alive, tested) ingest/structure half of
``codegen``: it scopes the book to one game, an explicit page range, or a
single room plus its exit neighbours, and renders it through the shared
:func:`pdf_structure.format_location`. The slice it returns is small enough to
paste into one authoring turn -- see ``docs/converting-parsely-games.md`` for
the slice-by-slice loop this feeds.

Unlike the spec->module emission half of ``codegen`` (deprecated -- Claude
generates better structured code directly), this view is meant to stay: it's
just a query over the parsed structure, not code generation.
"""

from __future__ import annotations

from pathlib import Path

from .pdf_ingest import ingest_pdf, game_page_ranges
from .pdf_structure import structure_pages, format_location, LocationBlock


def render_source(
    pdf_path: str | Path,
    *,
    game: str | None = None,
    pages: tuple[int, int] | None = None,
    room: str | None = None,
    include_exits: bool = True,
) -> str:
    """Render a slice of ``pdf_path`` as markdown.

    Pick exactly one primary selector:

    * ``game="Action Castle 4"`` -- the whole game, resolved via the PDF's TOC.
    * ``pages=(51, 58)`` -- an explicit inclusive 1-indexed page range.
    * ``room="Tower"`` (with ``game=`` to scope the search) -- that room plus
      the rooms its exits lead to. This is the natural "one slice" unit.

    ``include_exits`` (default ``True``) controls whether ``room=`` also pulls
    in the one-hop exit neighbours; set it ``False`` for just the named room.
    """
    blocks = _select_blocks(
        pdf_path, game=game, pages=pages, room=room, include_exits=include_exits
    )
    label = game or room or (f"pages {pages[0]}-{pages[1]}" if pages else "?")
    header = f"# Source: {label}\n"
    if not blocks:
        return header + "(no locations found in this selection)"
    return header + "\n\n".join(format_location(b) for b in blocks)


def _select_blocks(
    pdf_path: str | Path,
    *,
    game: str | None,
    pages: tuple[int, int] | None,
    room: str | None,
    include_exits: bool,
) -> list[LocationBlock]:
    # 1. Resolve the page window to ingest.
    if pages is not None:
        window = pages
    elif game is not None:
        ranges = game_page_ranges(pdf_path)
        if game not in ranges:
            raise ValueError(
                f"game {game!r} not found in PDF TOC; available: {sorted(ranges)}"
            )
        window = ranges[game]
    else:
        raise ValueError("pass exactly one of game=, pages=, or room= (with game=)")

    structured = structure_pages(ingest_pdf(pdf_path, window))
    blocks = [loc for sp in structured for loc in sp.locations]

    # 2. room= narrows to that block plus its one-hop exit neighbours.
    if room is not None:
        blocks = filter_to_room(blocks, room, include_exits=include_exits)

    return blocks


def filter_to_room(
    blocks: list[LocationBlock], room: str, *, include_exits: bool = True
) -> list[LocationBlock]:
    """Keep the named room and (optionally) its one-hop exit neighbours.

    Order is preserved. Raises ``ValueError`` if no block matches ``room``
    (case-insensitively).
    """
    target = next((b for b in blocks if _norm(b.name) == _norm(room)), None)
    if target is None:
        raise ValueError(f"room {room!r} not found; have: {[b.name for b in blocks]}")
    wanted = {_norm(target.name)}
    if include_exits:
        wanted |= {_norm(ex.target_name) for ex in target.exits}
    return [b for b in blocks if _norm(b.name) in wanted]


def _norm(s: str) -> str:
    return s.strip().casefold()
