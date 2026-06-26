"""Tests for ``codegen.pdf_structure.structure_pages``.

Synthesizes :class:`ColorTaggedSpan` lists directly -- no PDF dependency --
so the heuristics can be exercised without PyMuPDF and without depending on
the gitignored Parsely book.
"""

from __future__ import annotations

from text_adventure_games.codegen.pdf_ingest import ColorTaggedPage, ColorTaggedSpan
from text_adventure_games.codegen.pdf_structure import structure_pages


def _span(
    text: str,
    color: str,
    y: float,
    *,
    x: float = 50.0,
    font: str = "Decour-Regular",
    size: float = 12.0,
    underlined: list[str] | None = None,
) -> ColorTaggedSpan:
    return ColorTaggedSpan(
        text=text,
        color=color,
        bbox=(x, y, x + 200, y + 14),
        font=font,
        size=size,
        underlined_words=list(underlined or []),
    )


def _heading(text: str, y: float) -> ColorTaggedSpan:
    return _span(text, color="other", y=y, font="Uni0553", size=18.5)


def _verb(text: str, y: float) -> ColorTaggedSpan:
    return _span(text, color="rule", y=y, font="Realtime-Bold")


def _rule(text: str, y: float) -> ColorTaggedSpan:
    return _span(text, color="rule", y=y, font="Realtime-Bold")


def _flavor(text: str, y: float, **kw) -> ColorTaggedSpan:
    return _span(text, color="flavor", y=y, font="Decour-Regular", **kw)


def _page(spans: list[ColorTaggedSpan], number: int = 1) -> ColorTaggedPage:
    return ColorTaggedPage(page_number=number, spans=spans)


def test_simple_location_with_one_interaction_and_one_exit():
    page = _page(
        [
            _heading("COTTAGE", y=32),
            _flavor("You are in a small cottage.", y=80, underlined=["pole"]),
            _verb("EXAMINE LAMP:", y=120),
            _flavor("You see an old lamp.", y=120, x=160),
            _rule("COTTAGE exits are:", y=300),
            _rule("> OUT page 2 GARDEN PATH", y=316),
        ]
    )
    [sp] = structure_pages([page])
    assert len(sp.locations) == 1
    loc = sp.locations[0]
    assert loc.name == "COTTAGE"
    assert "small cottage" in loc.description
    assert [ix.verb_header for ix in loc.interactions] == ["EXAMINE LAMP:"]
    assert loc.interactions[0].response == "You see an old lamp."
    assert [(e.direction, e.target_name, e.target_page) for e in loc.exits] == [
        ("out", "GARDEN PATH", 2)
    ]


def test_multi_word_direction_in_exit_table():
    page = _page(
        [
            _heading("CAVERN ENTRANCE", y=32),
            _flavor("You are at a mossy outcrop.", y=80),
            _rule("CAVERN ENTRANCE exits are:", y=300),
            _rule("> NORTH page 51 DARK FOREST", y=316),
            _rule("ENTER CAVERN 54 DARK CAVERN", y=332),
        ]
    )
    [sp] = structure_pages([page])
    [loc] = sp.locations
    assert [(e.direction, e.target_name, e.target_page) for e in loc.exits] == [
        ("north", "DARK FOREST", 51),
        ("enter cavern", "DARK CAVERN", 54),
    ]


def test_two_locations_on_the_same_page():
    page = _page(
        [
            _heading("COTTAGE", y=32),
            _flavor("You are in a small cottage.", y=80),
            _rule("COTTAGE exits are:", y=200),
            _rule("> OUT page 1 GARDEN PATH", y=216),
            _heading("GARDEN PATH", y=300),
            _flavor("You are on a garden path.", y=340),
            _rule("GARDEN PATH exits are:", y=500),
            _rule("> NORTH page 2 WINDING PATH", y=516),
        ]
    )
    [sp] = structure_pages([page])
    assert [loc.name for loc in sp.locations] == ["COTTAGE", "GARDEN PATH"]
    assert sp.locations[1].exits[0].target_name == "WINDING PATH"


def test_paired_gated_interactions_with_same_verb():
    page = _page(
        [
            _heading("CAVERN ENTRANCE", y=32),
            _flavor("Description.", y=80),
            _verb("ENTER CAVERN:", y=120),
            _flavor("It's too dark to see!", y=120, x=160),
            _rule("A player must LIGHT LANTERN first.", y=140),
            _verb("ENTER CAVERN:", y=180),
            _flavor("You crawl inside the dark cavern.", y=180, x=160),
            _rule("CAVERN ENTRANCE exits are:", y=300),
            _rule("ENTER CAVERN 2 DARK CAVERN", y=316),
        ]
    )
    [sp] = structure_pages([page])
    [loc] = sp.locations
    assert [ix.verb_header for ix in loc.interactions] == [
        "ENTER CAVERN:",
        "ENTER CAVERN:",
    ]
    assert loc.interactions[0].response == "It's too dark to see!"
    assert "LIGHT LANTERN" in loc.interactions[0].rules[0]
    assert "crawl inside" in loc.interactions[1].response


def test_post_interaction_flavor_attaches_to_current_interaction():
    """Flavor narrative after an interaction's rules belongs to that
    interaction (tree-top description after CLIMB TREE/UP), not a designer
    note."""
    page = _page(
        [
            _heading("WINDING PATH", y=32),
            _flavor("You walk along a path.", y=80),
            _verb("CLIMB TREE/UP:", y=120),
            _flavor("You climb up the tree.", y=120, x=160),
            _rule("While in the tree, examine the branch.", y=140),
            _flavor("You are at the top of a tall tree.", y=180),
            _verb("CLIMB TREE/DOWN:", y=220),
            _flavor("You climb down.", y=220, x=160),
            _rule("WINDING PATH exits are:", y=300),
            _rule("> SOUTH page 1 GARDEN PATH", y=316),
        ]
    )
    [sp] = structure_pages([page])
    [loc] = sp.locations
    up, down = loc.interactions
    assert "top of a tall tree" in up.response
    assert down.response == "You climb down."
    assert loc.designer_notes == []


def test_rule_paragraphs_before_first_interaction_become_designer_notes():
    page = _page(
        [
            _heading("COTTAGE", y=32),
            _flavor("You are in a small cottage.", y=80),
            _rule("Every new game starts in the Cottage.", y=110),
            _rule("The player starts with a lamp.", y=125),
            _verb("EXAMINE LAMP:", y=160),
            _flavor("An old lamp.", y=160, x=160),
            _rule("COTTAGE exits are:", y=300),
            _rule("> OUT page 2 GARDEN PATH", y=316),
        ]
    )
    [sp] = structure_pages([page])
    [loc] = sp.locations
    assert len(loc.designer_notes) == 1
    assert "starts in the Cottage" in loc.designer_notes[0]
    assert "lamp" in loc.designer_notes[0]


def test_page_furniture_is_skipped():
    """Page numbers, top banners, MENU sidebar, and rating tags shouldn't
    appear as floating spans or interfere with location bucketing."""
    page = _page(
        [
            _span("15", color="other", y=33, x=395, font="Realtime-Black", size=18.1),
            _span("ACTIONCASTLE", color="flavor", y=1, x=295, font="Realtime-Regular"),
            _span(
                "MENU",
                color="other",
                y=97,
                x=12,
                font="SHPinscher-Regular",
                size=17.0,
            ),
            _heading("COTTAGE", y=32),
            _flavor("You are in a small cottage.", y=80),
            _rule("COTTAGE exits are:", y=300),
            _rule("> OUT page 2 GARDEN PATH", y=316),
        ]
    )
    [sp] = structure_pages([page])
    # No floating spans should have leaked from page furniture.
    assert sp.floating_spans == []
    [loc] = sp.locations
    assert loc.name == "COTTAGE"


def test_underlined_nouns_aggregate_to_location():
    page = _page(
        [
            _heading("BRICK HUT", y=32),
            _flavor(
                "There is a hammer here.",
                y=80,
                underlined=["hammer"],
            ),
            _verb("EXAMINE TORCH:", y=120),
            _flavor("It glows.", y=120, x=160, underlined=["torch"]),
        ]
    )
    [sp] = structure_pages([page])
    [loc] = sp.locations
    assert "hammer" in loc.underlined_nouns
    assert any("torch" in n.lower() for n in loc.interactions[0].underlined_nouns)
