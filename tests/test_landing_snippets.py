"""Pin the landing page's code snippets to the engine they quote.

The public landing page (godot-generative-agents/web) quotes real engine source
in its code snippets, and godot-generative-agents/README.md quotes the example
verb template (#880). Nothing else checks them -- a renamed method would leave
the public page confidently wrong -- so this module is that check.

The snippets are real files under web/src/components/home/snippets/, imported
into React with Vite's `?raw`. This test reads the same bytes, so there is no
second copy to drift.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

from backend.penn.penn_world import PENN_ACTION_VERBS, build_penn_world

from text_adventure_games import npc

REPO_ROOT = Path(__file__).resolve().parents[1]
SNIPPET_DIR = REPO_ROOT / "godot-generative-agents/web/src/components/home/snippets"

# snippet file -> (engine file, header of the block it quotes, anchors)
QUOTED = {
    "gate.py": (
        "text_adventure_games/reactions.py",
        "class GatedEffect:",
        [
            "def __call__",
            "_preconditions_passed",
            "check_preconditions",
            "apply_effects",
        ],
    ),
    "check_out_book.py": (
        "godot-generative-agents/backend/actions.py",
        "class CheckOutBook(base.Action):",
        [
            "class CheckOutBook",
            "REQUIRED_AFFORDANCES",
            "book_shelf",
            "ARGUMENTS_SCHEMA",
        ],
    ),
    "check_out_book_gate.py": (
        "godot-generative-agents/backend/actions.py",
        "class CheckOutBook(base.Action):",
        [
            "checked_out_by",
            "already checked out by",
            "add_to_inventory",
            "library_book",
        ],
    ),
}


def _enclosing_block(source: str, header: str) -> str:
    """The source of the top-level block introduced by *header*.

    Anchors are checked against this slice rather than the whole file: these are
    multi-class modules, and a sibling class using the same helper name would
    otherwise keep a stale snippet's pin green.
    """
    start = source.index(header)
    rest = source[start + len(header) :]
    dedent = re.search(r"^\S", rest, re.M)  # next line starting in column 0
    return header + (rest[: dedent.start()] if dedent else rest)


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
    expected = set(QUOTED) | {"my_verb.py", "check_out_book.tool.json"}
    assert {p.name for p in SNIPPET_DIR.iterdir() if p.is_file()} >= expected


@pytest.mark.parametrize(
    "snippet,source,header,anchors",
    [(name, src, header, anchors) for name, (src, header, anchors) in QUOTED.items()],
)
def test_quoted_snippet_anchors_still_exist(snippet, source, header, anchors):
    """Each quoted snippet names the engine file and block it came from; every
    anchor it relies on must still be there -- in that block, not just
    somewhere in the file. This is what a rename OR a rewrite trips."""
    engine_src = (REPO_ROOT / source).read_text()
    block = _enclosing_block(engine_src, header)
    snippet_src = (SNIPPET_DIR / snippet).read_text()
    for anchor in anchors:
        assert anchor in block, f"{anchor!r} gone from {header} in {source}"
        assert anchor in snippet_src, f"{anchor!r} missing from {snippet}"


@pytest.mark.parametrize(
    "snippet,source,header",
    [(name, src, header) for name, (src, header, _) in QUOTED.items()],
)
def test_every_quoted_line_is_real_engine_source(snippet, source, header):
    """No line of a quoted snippet may be invented.

    The anchors above are identifiers, so they cannot see a rewritten string
    literal. That gap shipped once: drop.py's ``parser.fail`` message and its
    success message had both been reworded down to one-liners while every
    anchor stayed green, so the public page showed code the engine does not
    contain. This checks whole lines instead -- each one must appear, stripped,
    in the block being quoted. Trimming lines out is still allowed (that is
    what "abridged" in the caption means); rewriting one is not.
    """
    block = _enclosing_block((REPO_ROOT / source).read_text(), header)
    real = {line.strip() for line in block.splitlines() if line.strip()}
    missing = [
        line.strip()
        for line in (SNIPPET_DIR / snippet).read_text().splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and line.strip() not in real
    ]
    assert not missing, f"{snippet} lines absent from {header} in {source}: {missing}"


def test_gate_snippet_is_verbatim_engine_source():
    """gate.py is pinned by equality rather than by anchors or a line count.

    The prose calls the gate "five lines", and neither weaker check guards
    that: adding a hook or a ``try`` inside ``__call__`` would leave every
    anchor green, and the *snippet* would still be five lines, while the page's
    central claim quietly stopped matching the engine. Equality subsumes both.

    ``__call__`` is the last member of ``GatedEffect``, so the inner
    ``_enclosing_block`` call runs off the end of the class -- which is why the
    trailing blank lines are normalized away. A method added after it would be
    over-included and fail here loudly, which is the safe direction.
    """
    engine_src = (REPO_ROOT / "text_adventure_games/reactions.py").read_text()
    gated = _enclosing_block(engine_src, "class GatedEffect:")
    call = _enclosing_block(gated, "    def __call__(self):")
    assert (
        textwrap.dedent(call).rstrip() + "\n" == (SNIPPET_DIR / "gate.py").read_text()
    )


def test_tool_schema_pane_matches_a_live_tools_for_call(offered_tools):
    """The JSON pane is what a Penn agent at the book stacks really receives.

    Regenerating it is the fix when this fails -- see the plan's Task 2 Step 2.
    """
    tool = next(t for t in offered_tools if t["name"] == "check_out_book")
    pane = (SNIPPET_DIR / "check_out_book.tool.json").read_text()
    assert json.dumps(tool, indent=2) + "\n" == pane


def test_the_library_menu_is_narrowed_by_affordance(offered_tools):
    """The section's prose claims 7 of the cast's 11 Penn verbs survive the
    affordance check at the book stacks. Pin both numbers so it can't go stale.

    SCOPE: this pins the affordance-curation demonstration -- ``tools_for``
    restricted to ``PENN_ACTION_VERBS`` -- and NOT the live sim's wiring. A
    running sim goes through ``cognition.attach_agents`` ->
    ``action_tools_for``, which prepends ``travel`` and ``perform`` (13
    ``action_names``) and drops ``talk_to`` when nobody is co-located, offering
    8 tools here rather than 7. The prose is worded to claim only what this call
    measures; do not read these numbers as the agent's complete live menu.
    """
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
    """my_verb.py is a reader's fill-in-the-blank template, so it must still
    actually work: it imports the real Action and every helper it calls must
    exist. It is not runnable against any shipped world -- no ``my_affordance``
    exists anywhere -- and that is fine: the point is that the shape compiles
    against the real base class, not that the placeholder affordance resolves."""
    from text_adventure_games.actions.base import Action

    namespace: dict = {}
    src = (SNIPPET_DIR / "my_verb.py").read_text()
    exec(compile(src, "my_verb.py", "exec"), namespace)  # noqa: S102

    my_verb = namespace["MyVerb"]
    assert issubclass(my_verb, Action)
    assert my_verb.ACTION_NAME == "my_verb"
    assert my_verb.REQUIRED_AFFORDANCES == ("my_affordance",)
    for helper in ("acting_character", "has_affordance_in_scope"):
        assert hasattr(my_verb, helper), f"Action lost {helper}()"


def test_readme_verb_guide_matches_the_template():
    """The "Adding your own verb" guide (#880) quotes my_verb.py in
    godot-generative-agents/README.md. The snippet file is the copy the test
    above proves compiles against the real base class, so the README block must
    be byte-identical to it -- otherwise readers copy code nothing validates."""
    readme = (REPO_ROOT / "godot-generative-agents/README.md").read_text()
    fenced = re.findall(r"```python\n(.*?)```", readme, re.S)
    template = (SNIPPET_DIR / "my_verb.py").read_text()
    assert template in fenced, "README's MyVerb block drifted from my_verb.py"
