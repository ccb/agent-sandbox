"""Codegen pipeline: PDF -> GameSpec JSON -> Python build_game() module.

Top-level layout::

    codegen.pdf_ingest      PyMuPDF page parser (color- and underline-aware).
    codegen.extract         LLM-driven GameSpec extractor (mock fallback).
    codegen.spec            GameSpec dataclasses, JSON I/O, validation.
    codegen.emit            GameSpec -> Python source string.
    codegen.templates       Per-template emitters for actions and blocks.
    codegen.prompts         LLM prompt strings used by extract.
    codegen.cli             ``python -m text_adventure_games.codegen`` entry.

The package is intentionally optional: the base engine does not import it, and
PyMuPDF stays an optional dependency. Generated game modules import only from
``text_adventure_games`` (no runtime dependency on codegen).
"""

from .spec import (
    GameSpec,
    load_spec,
    dump_spec,
    validate,
    lint,
    legal_command_hints,
)
from .emit import emit_module, emit_module_to_file, emit_walkthrough_module

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
    "GameSpec",
    "load_spec",
    "dump_spec",
    "validate",
    "lint",
    "legal_command_hints",
    "emit_module",
    "emit_module_to_file",
    "emit_walkthrough_module",
    "ingest_pdf",
    "game_page_ranges",
    "ColorTaggedPage",
    "ColorTaggedSpan",
]
