"""Tests for ``codegen.source_view`` and the shared ``format_location``.

Builds :class:`LocationBlock` values directly -- no PDF dependency and no
PyMuPDF -- so the slice-selection and rendering logic is exercised without the
gitignored Parsely book. (The ingest path itself is covered by
``tests/test_codegen_pdf_ingest.py`` / ``test_codegen_pdf_structure.py``.)
"""

from __future__ import annotations

import pytest

from text_adventure_games.codegen.pdf_structure import (
    ExitRow,
    Interaction,
    LocationBlock,
    format_location,
)
from text_adventure_games.codegen.source_view import filter_to_room


def _tower() -> LocationBlock:
    return LocationBlock(
        name="Tower",
        page_number=51,
        description="A cramped stone tower. A window looks out over the moat.",
        interactions=[
            Interaction(
                verb_header="CUT HAIR:",
                response="You saw at your braid with the dagger.",
                rules=["Requires the dagger.", "Yields a length of rope."],
                underlined_nouns=["dagger", "rope"],
            )
        ],
        exits=[
            ExitRow("down", "Guardroom", target_page=52),
            ExitRow("climb out window", "Drawbridge", target_page=53),
        ],
        underlined_nouns=["window"],
    )


def _world() -> list[LocationBlock]:
    return [
        _tower(),
        LocationBlock(name="Guardroom", page_number=52, description="A guard dozes."),
        LocationBlock(name="Drawbridge", page_number=53, description="Lowered."),
        LocationBlock(name="Gardens", page_number=54, description="Untended roses."),
    ]


def test_format_location_renders_all_parts():
    out = format_location(_tower())
    assert out.startswith("location: 'Tower'")
    assert "  description: 'A cramped stone tower." in out
    assert "  underlined_nouns: ['window']" in out
    assert "    - verb: 'CUT HAIR:'" in out
    assert "      response: 'You saw at your braid with the dagger.'" in out
    assert "      rule: 'Yields a length of rope.'" in out
    assert "      underlined_nouns: ['dagger', 'rope']" in out
    # Exit cross-reference page is preserved for topology checks.
    assert "    - direction: 'down' -> target: 'Guardroom' (page 52)" in out


def test_format_location_omits_empty_sections():
    bare = LocationBlock(name="Void", page_number=9)
    assert format_location(bare) == "location: 'Void'"


def test_filter_to_room_pulls_in_exit_neighbours():
    kept = filter_to_room(_world(), "Tower")
    names = [b.name for b in kept]
    assert names == ["Tower", "Guardroom", "Drawbridge"]  # order preserved
    assert "Gardens" not in names  # not an exit neighbour


def test_filter_to_room_without_exits_is_just_the_room():
    kept = filter_to_room(_world(), "Tower", include_exits=False)
    assert [b.name for b in kept] == ["Tower"]


def test_filter_to_room_is_case_insensitive():
    assert filter_to_room(_world(), "tOwEr", include_exits=False)[0].name == "Tower"


def test_filter_to_room_unknown_room_raises():
    with pytest.raises(ValueError, match="Dungeon"):
        filter_to_room(_world(), "Dungeon")
