"""PDF ingest + structured-view helpers for hand-porting Parsely games.

Top-level layout::

    codegen.pdf_ingest      PyMuPDF page parser (color- and underline-aware).
    codegen.pdf_structure   Group ingested spans into per-location blocks.
    codegen.source_view     render_source: a scoped PDF slice as compact markdown.
    codegen.source          ``python -m text_adventure_games.codegen.source`` CLI.

This is the *ingest* half of what used to be a full PDF -> GameSpec -> Python
pipeline. The spec-extraction and module-emission half has been removed: in
practice a good prompt with Claude Code working directly against the PDF
produces a better port than the template-driven emitter did. What remains is
the genuinely useful part -- a structured, color-tagged view of a Parsely PDF
to read slice by slice while hand-porting. See ``docs/converting-parsely-games.md``.

The package is intentionally optional: the base engine does not import it, and
PyMuPDF stays an optional dependency.
"""

from .pdf_structure import format_location
from .source_view import render_source

# Note: pdf_ingest is imported lazily where used so PyMuPDF stays an
# optional dependency. Tests in ``tests/test_codegen_pdf_ingest.py`` use
# pytest.importorskip("pymupdf") to skip cleanly when it's missing.
try:
    from .pdf_ingest import (  # noqa: F401
        ColorTaggedPage,
        ColorTaggedSpan,
        ingest_pdf,
        game_page_ranges,
    )
except ImportError:  # PyMuPDF not installed
    pass

__all__ = [
    "format_location",
    "render_source",
    "ingest_pdf",
    "game_page_ranges",
    "ColorTaggedPage",
    "ColorTaggedSpan",
]
