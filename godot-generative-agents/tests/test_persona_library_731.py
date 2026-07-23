"""#731: cast-by-reference persona library.

A world YAML may either carry its cast inline (a ``personas:`` list, like the
boil demo) or name it by reference: ``cast: [ids...]``, each id resolving to
``personas/<id>.yaml`` next to the world file. Composition also assembles the
``relationships`` and ``meetings`` blocks from the persona files, dropping any
entry that references a persona outside the cast (an edge needs both ends, a
meeting needs all its participants).
"""

import pytest
import yaml

from backend.build_world import load_world_data, load_world_yaml


def _write_yaml(path, data):
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def library_world(tmp_path):
    """A tiny cast-by-reference world: cast [ana, bo]; cy parked in the library.

    ana's file anchors one edge to Bo (both in cast -> kept) and one meeting
    with Cy (not in cast -> dropped).
    """
    world = tmp_path / "world.yaml"
    _write_yaml(
        world,
        {
            "cast": ["ana", "bo"],
            "locations": [
                {"name": "Hub", "description": "the hub", "address": None, "hub": True}
            ],
            "llm": {"provider": "anthropic", "model": "claude-haiku-4-5"},
        },
    )
    lib = tmp_path / "personas"
    lib.mkdir()
    _write_yaml(
        lib / "ana.yaml",
        {
            "name": "Ana",
            "home": "Hub",
            "persona": "I am Ana.",
            "emoji": "🅰️",
            "start_tile": [1, 1],
            "destination": "Hub",
            "activity": "idling",
            "relationships": [
                {
                    "a": "Ana",
                    "b": "Bo",
                    "kind": "friends",
                    "closeness": 3,
                    "description": "Ana and Bo are friends.",
                },
            ],
            "meetings": [
                {
                    "label": "Ana meets Cy",
                    "at": "Hub",
                    "participants": ["Ana", "Cy"],
                    "dialogue": [["Ana", "Hi Cy."]],
                },
            ],
        },
    )
    _write_yaml(
        lib / "bo.yaml",
        {
            "name": "Bo",
            "home": "Hub",
            "persona": "I am Bo.",
            "emoji": "🅱️",
            "start_tile": [2, 2],
            "destination": "Hub",
            "activity": "idling",
        },
    )
    _write_yaml(
        lib / "cy.yaml",
        {
            "name": "Cy",
            "home": "Hub",
            "persona": "I am Cy.",
            "emoji": "🌀",
            "start_tile": [3, 3],
            "destination": "Hub",
            "activity": "idling",
        },
    )
    return world


def test_inline_personas_world_passes_through(tmp_path):
    """A world with inline personas: (the boil-demo shape) is returned verbatim."""
    world = tmp_path / "inline.yaml"
    _write_yaml(
        world,
        {
            "personas": [
                {
                    "name": "Solo",
                    "home": "Hub",
                    "persona": "I am Solo.",
                    "emoji": "🙂",
                    "start_tile": [0, 0],
                    "destination": "Hub",
                    "activity": "idling",
                }
            ],
            "locations": [{"name": "Hub", "description": "d", "address": None}],
        },
    )
    data = load_world_yaml(world)
    assert [p["name"] for p in data["personas"]] == ["Solo"]
    assert "cast" not in data


def test_cast_composes_personas_in_cast_order(library_world):
    data = load_world_yaml(library_world)
    assert [p["name"] for p in data["personas"]] == ["Ana", "Bo"]
    # The persona dicts carry persona fields only -- the edge/meeting blocks
    # are lifted to the world's top level, not left on the persona.
    for p in data["personas"]:
        assert "relationships" not in p
        assert "meetings" not in p


def test_edge_kept_when_both_ends_in_cast(library_world):
    data = load_world_yaml(library_world)
    assert [(r["a"], r["b"]) for r in data["relationships"]] == [("Ana", "Bo")]


def test_meeting_dropped_when_a_participant_is_missing(library_world):
    # Ana's meeting names Cy, who is not in the default [ana, bo] cast.
    assert load_world_yaml(library_world)["meetings"] == []


def test_meeting_kept_when_all_participants_in_cast(library_world):
    data = load_world_yaml(library_world, cast=["ana", "bo", "cy"])
    assert [m["label"] for m in data["meetings"]] == ["Ana meets Cy"]


def test_edge_dropped_when_one_end_leaves_cast(library_world):
    assert load_world_yaml(library_world, cast=["ana"])["relationships"] == []


def test_cast_override_beats_the_file(library_world):
    data = load_world_yaml(library_world, cast=["bo"])
    assert [p["name"] for p in data["personas"]] == ["Bo"]


def test_unknown_persona_id_raises(library_world):
    with pytest.raises(ValueError, match="zed"):
        load_world_yaml(library_world, cast=["zed"])


def test_duplicate_persona_id_raises(library_world):
    with pytest.raises(ValueError, match="duplicate"):
        load_world_yaml(library_world, cast=["ana", "ana"])


def test_load_world_data_resolves_cast_and_normalizes(library_world):
    personas, locations = load_world_data(library_world)
    assert [p["name"] for p in personas] == ["Ana", "Bo"]
    # _normalize_personas ran: every persona has a uniform schedule list.
    assert all(p["schedule"] for p in personas)
    assert locations[0]["name"] == "Hub"


# --------------------------------------------------------------------------- #
# Acceptance against the REAL Penn library (#731): default cast unchanged,
# all 7 loadable, sub-casts filter their edges/meetings.

from backend.penn.penn_world import WORLD_DATA, build_penn_world

FULL_CAST = ["diego", "tanaka", "sofia", "maya", "ellis", "priya", "marcus"]


def test_default_cast_is_the_three_person_mvp():
    data = load_world_yaml(WORLD_DATA)
    assert [p["name"] for p in data["personas"]] == [
        "Diego Torres",
        "Professor Tanaka",
        "Sofia Ramirez",
    ]
    assert [m["label"] for m in data["meetings"]] == [
        "Diego shows Sofia around the gallery (Kamin Gallery)",
        "Before the guest lecture at Irvine (Irvine Auditorium)",
    ]
    assert [(r["a"], r["b"]) for r in data["relationships"]] == [
        ("Diego Torres", "Professor Tanaka")
    ]


def test_full_seven_cast_loads_all_seven():
    data = load_world_yaml(WORLD_DATA, cast=FULL_CAST)
    assert len(data["personas"]) == 7
    assert len(data["meetings"]) == 4
    assert len(data["relationships"]) == 3


def test_full_seven_cast_builds():
    world = build_penn_world(cast=FULL_CAST)
    assert len(world.personas) == 7
    # relationships_meta validated all 3 edges against the 7-person cast.
    assert len(world.relationships) == 3


def test_sub_cast_drops_orphaned_edges_and_meetings():
    # Maya without Priya: her study-buddies edge and cram meeting both go.
    world = build_penn_world(cast=["maya"])
    assert [p["name"] for p in world.personas] == ["Maya Chen"]
    assert world.relationships == []
    assert world.meetings == []
