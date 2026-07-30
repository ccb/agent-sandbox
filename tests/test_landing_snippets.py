"""Pin the landing page's code snippets to the engine they quote.

The public landing page (godot-generative-agents/web) shows four code snippets.
Three quote real engine source; the fourth is an example verb a reader could
copy. Nothing else checks them -- a renamed method would leave the public page
confidently wrong -- so this module is that check.

The snippets are real files under web/src/components/home/snippets/, imported
into React with Vite's `?raw`. This test reads the same bytes, so there is no
second copy to drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.penn.penn_world import PENN_ACTION_VERBS, build_penn_world

from text_adventure_games import npc

REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPET_DIR = REPO_ROOT / "godot-generative-agents/web/src/components/home/snippets"

# snippet file -> (engine file it quotes, substrings that must still exist there)
QUOTED = {
    "gate.py": (
        "text_adventure_games/reactions.py",
        [
            "def __call__",
            "_preconditions_passed",
            "check_preconditions",
            "apply_effects",
        ],
    ),
    "drop.py": (
        "text_adventure_games/actions/things.py",
        ["class Drop", "was_matched", "is_worn", "carried_items", "discard_item"],
    ),
    "check_out_book.py": (
        "godot-generative-agents/backend/actions.py",
        [
            "class CheckOutBook",
            "REQUIRED_AFFORDANCES",
            "book_shelf",
            "ARGUMENTS_SCHEMA",
        ],
    ),
}


@pytest.fixture(scope="module")
def agent_at_the_book_stacks():
    """A Penn agent standing where the ``book_shelf`` affordance is.

    Module-scoped because building the Penn world is the slow part and the
    tests below only read from it. Locating the shelf by affordance rather than
    by name is deliberate: it is the same property the verb's declaration
    names, so renaming the room can't quietly break the lookup.
    """
    world = build_penn_world()
    game, _ = world.build_world_fn(world.world_map)
    shelf = next(
        loc
        for loc in game.locations.values()
        if any(i.get_property("book_shelf") for i in loc.items.values())
    )
    actor = game.characters["Diego Torres"]
    actor.location = shelf
    shelf.add_character(actor)
    return game, actor


@pytest.fixture(scope="module")
def offered_tools(agent_at_the_book_stacks):
    """The tools that agent is really offered, from the cast's own verb menu."""
    game, actor = agent_at_the_book_stacks
    return npc.tools_for(game.parser, actor=actor, names=PENN_ACTION_VERBS)


def test_every_snippet_file_exists():
    """A missing snippet must fail loudly here rather than skip."""
    expected = set(QUOTED) | {"nap.py", "check_out_book.tool.json"}
    assert {p.name for p in SNIPPET_DIR.iterdir() if p.is_file()} >= expected


@pytest.mark.parametrize("snippet,source,anchors", [
    (name, src, anchors) for name, (src, anchors) in QUOTED.items()
])
def test_quoted_snippet_anchors_still_exist(snippet, source, anchors):
    """Each quoted snippet names the engine file it came from; every anchor it
    relies on must still be there. This is what a rename trips."""
    engine_src = (REPO_ROOT / source).read_text()
    snippet_src = (SNIPPET_DIR / snippet).read_text()
    for anchor in anchors:
        assert anchor in engine_src, f"{anchor!r} gone from {source}"
        assert anchor in snippet_src, f"{anchor!r} missing from {snippet}"


def test_tool_schema_pane_matches_a_live_tools_for_call(offered_tools):
    """The JSON pane is what a Penn agent at the book stacks really receives.

    Regenerating it is the fix when this fails -- see the plan's Task 2 Step 2.
    """
    tool = next(t for t in offered_tools if t["name"] == "check_out_book")
    pane = (SNIPPET_DIR / "check_out_book.tool.json").read_text()
    assert json.dumps(tool, indent=2) + "\n" == pane


def test_the_library_menu_is_narrowed_by_affordance(offered_tools):
    """The section's prose claims 7 verbs at the book stacks out of the cast's
    11. Pin both numbers so the prose can't go stale."""
    assert len(PENN_ACTION_VERBS) == 11
    assert sorted(t["name"] for t in offered_tools) == [
        "check_out_book",
        "drink",
        "get",
        "make",
        "read",
        "talk_to",
        "wait",
    ]


def test_example_verb_compiles_against_the_real_base_class():
    """nap.py is a reader's copy-paste template, so it must actually work: it
    imports the real Action and every helper it calls must exist."""
    from text_adventure_games.actions.base import Action

    namespace: dict = {}
    src = (SNIPPET_DIR / "nap.py").read_text()
    exec(compile(src, "nap.py", "exec"), namespace)  # noqa: S102

    nap = namespace["Nap"]
    assert issubclass(nap, Action)
    assert nap.ACTION_NAME == "nap"
    assert nap.REQUIRED_AFFORDANCES == ("bench",)
    for helper in ("acting_character", "has_affordance_in_scope"):
        assert hasattr(nap, helper), f"Action lost {helper}()"
