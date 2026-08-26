"""Persona relationships reach agent memory on the Penn path (issue #779).

A persona file may author ``relationships:`` edges (``{a, b, kind, closeness,
description}``). They were validated (``penn_world.relationships_meta``) and
projected into ``meta.relationships`` for the viewer's social-graph pop-up
(#450) -- and delivered to nobody. ``cognition.attach_agents`` seeded social
structure only from ``relationships_csv``, the upstream Smallville bootstrap
(#79), which no Penn entry point passes; so ``seed_relationships(memory, [])``
was a no-op for every Penn agent and the #760 live runs produced *zero*
memories derived from a seeded edge. Authored rivals spent their conversation
as each other's campaign cheerleaders.

The wiring under test: ``build_penn_world`` hands each persona spec the edges
it is an endpoint of (``relationship_edges``), and ``attach_agents`` seeds one
memory per edge through the existing :func:`seed.seed_relationships`.

Why naming the other person matters -- and why these assertions check for it:
``conversation._dialogue_observation`` retrieves a speaker's memories with
``query=listener.name``, so a statement naming the partner is what puts the
prior in the dialogue prompt that needs it. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_relationship_seeding_779.py -v
"""

import sys
from pathlib import Path

import pytest

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import seed  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from penn_world import build_penn_world  # noqa: E402

# Omar owns the `rivals` edge to Bethany (personas/omar.yaml, closeness 2) -- the
# pair whose live run headlined #779.
RIVALS = ["omar", "bethany"]


def _seeded(char):
    """The relationship memories one character holds (the `seed`/`relationship` tag)."""
    return [r for r in char.agent.memory.records if "relationship" in (r.tags or set())]


def _attach(cast=None):
    pw = build_penn_world(cast=cast)
    _game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas)
    return chars


@pytest.fixture(scope="module")
def rivals():
    return _attach(RIVALS)


# ------------------------------------------------------ both ends know


def test_both_ends_of_an_edge_hold_it(rivals):
    # The YAML authors this edge ONCE, under Omar (`a:`). Before #779 neither
    # agent held it; a one-sided fix would leave Bethany none the wiser.
    for name, other in (
        ("Omar Haddad", "Bethany Cole"),
        ("Bethany Cole", "Omar Haddad"),
    ):
        records = _seeded(rivals[name])
        assert len(records) == 1, f"{name} should hold exactly one seeded edge"
        rec = records[0]
        assert other in rec.text  # the retrieval hook: conversation queries by name
        assert "rivals" in rec.text  # the kind, so an ally-vs-rival prior exists
        assert rec.created_turn == 0  # a prior, not something learned in the run
        assert rec.importance == seed.RELATIONSHIP_IMPORTANCE
        assert rec.tags >= {"seed", "relationship"}


def test_the_seeded_text_is_pinned(rivals):
    # Pins relationship_memory.prompty's exact render against a real persona
    # file: the label form, both optional clauses present, single spaces, no
    # stray colon. (Raw-vs-HTML-escaped output is guarded separately below --
    # this authored text happens to contain nothing autoescaping would touch.)
    assert _seeded(rivals["Omar Haddad"])[0].text == (
        "I know Bethany Cole: rivals. We know each other a little. "
        "Omar and Bethany are the two front-runners for student body president "
        "-- civil in public, fiercely competitive about every endorsement."
    )


def test_seeded_importance_is_locked_against_rescoring(rivals):
    # #794: attach_agents seeds this as a plain OBSERVATION, which
    # score_new_memories (#583) would otherwise re-score -- turning the
    # authored 3.0 (a deliberately-background social prior, see
    # seed.RELATIONSHIP_IMPORTANCE) into a model-guessed 6-8.
    from backend.cognition import _IMPORTANCE_LOCKED

    for name in ("Omar Haddad", "Bethany Cole"):
        rec = _seeded(rivals[name])[0]
        assert rec.metadata.get(_IMPORTANCE_LOCKED) is True


def test_closeness_reaches_the_agent_in_words(rivals):
    # #779's second half: closeness 2 predicted nothing live because it never
    # left the manifest. It is not a number in the text -- it is a sentence,
    # which is what a model can act on.
    text = _seeded(rivals["Bethany Cole"])[0].text
    assert seed.CLOSENESS_PHRASE[2] in text
    assert "closeness" not in text.lower()


# ------------------------------------------- a persona with no edge


def test_default_cast_seeds_only_the_authored_edge():
    # diego -- tanaka is the default cast's one edge; Sofia knows nobody on
    # purpose (the pop-up's demo story is a first-year's graph growing).
    chars = _attach()
    assert len(_seeded(chars["Diego Torres"])) == 1
    assert len(_seeded(chars["Professor Tanaka"])) == 1
    assert _seeded(chars["Sofia Ramirez"]) == []
    assert "lecture regular" in _seeded(chars["Diego Torres"])[0].text


# ------------------------------------------- seed.relationship_statements


def test_statements_skip_edges_about_other_people():
    edges = [
        {"a": "Ana", "b": "Bo", "kind": "friends", "closeness": 4, "description": "d"},
        {"a": "Cy", "b": "Di", "kind": "rivals", "closeness": 1, "description": "d"},
    ]
    assert len(seed.relationship_statements("Ana", edges)) == 1
    assert seed.relationship_statements("Nobody", edges) == []


def test_a_bare_edge_renders_cleanly():
    # relationships_meta defaults kind/description to "", and closeness outside
    # 1..5 contributes no sentence -- no stray colons or double spaces.
    bare = [{"a": "Ana", "b": "Bo", "kind": "", "closeness": 0, "description": ""}]
    assert seed.relationship_statements("Ana", bare) == ["I know Bo."]


def test_punctuation_reaches_memory_raw():
    # The escaping guard prompt_templates/README.md points at for this template:
    # Jinja autoescaping is off, so `&` and `'` must arrive as themselves. The
    # library's compound kinds ("TA & student", "reporter & source") and
    # possessive descriptions would otherwise reach the model as &amp; / &#39;.
    edge = [
        {
            "a": "Ana",
            "b": "Bo",
            "kind": "TA & student",
            "closeness": 3,
            "description": "Bo is Ana's advisee.",
        }
    ]
    assert seed.relationship_statements("Ana", edge) == [
        "I know Bo: TA & student. We know each other fairly well. Bo is Ana's advisee."
    ]
