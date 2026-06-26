"""CLI: print a slice of a Parsely PDF as markdown for a port prompt.

    python -m text_adventure_games.codegen.source \\
        --pdf parsely_pdfs/Parsely_r31_final.pdf --game "Action Castle 4"
    python -m text_adventure_games.codegen.source --pdf <pdf> --pages 51-58
    python -m text_adventure_games.codegen.source --pdf <pdf> \\
        --game "Action Castle 4" --room "Tower"

See ``docs/converting-parsely-games.md`` for the slice-by-slice loop this feeds.
"""

from __future__ import annotations

import argparse
import sys

from .source_view import render_source


def _parse_page_range(s: str) -> tuple[int, int]:
    if "-" not in s:
        raise argparse.ArgumentTypeError("--pages must be START-END (e.g. 51-58)")
    a, b = s.split("-", 1)
    return int(a), int(b)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m text_adventure_games.codegen.source",
        description="Render a slice of a Parsely PDF as markdown.",
    )
    ap.add_argument("--pdf", required=True, help="path to the Parsely PDF")
    ap.add_argument("--game", help="game name from the PDF's table of contents")
    ap.add_argument("--pages", type=_parse_page_range, help="page range START-END")
    ap.add_argument(
        "--room", help="render this room plus its exit neighbours (needs --game)"
    )
    ap.add_argument(
        "--no-exits",
        action="store_true",
        help="with --room, render only the named room (skip its exit neighbours)",
    )
    args = ap.parse_args(argv)

    if args.room and not args.game:
        ap.error("--room needs --game to scope the search")
    if not args.game and not args.pages:
        ap.error("pass --game or --pages")

    try:
        out = render_source(
            args.pdf,
            game=args.game,
            pages=args.pages,
            room=args.room,
            include_exits=not args.no_exits,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
