"""#762: growing the Penn persona library -- a full-library validation sweep.

#731 gave the Penn world a persona library (`backend/penn/personas/`) and
#762 grows it: more roles (staff, librarian, athlete, visitor, postdoc,
admin) and more schedule shapes (early-riser vs night-owl, one-building days
vs campus criss-crossing), all parked outside the default cast so the baked
replay stays byte-identical (#640, pinned by test_replay_contract).

The loader is fail-loud (#757) -- one broken persona file in a cast breaks
the whole world -- so this suite sweeps EVERY library file, present and
future, against the authoring contract in personas/README.md:

* the file carries the full persona field set and builds into the real world;
* every schedule stop names a real location, and the whole cast's start
  tiles are walkable campus-walk tiles (not inside a building, not a wall);
* activity text survives the mock brain's ``perform <activity>`` re-parse
  (the parser routes on keywords, so a verb-shaped activity can hijack the
  command -- the historical "...late into the day" -> EAT freeze);
* relationships/meetings live in their first-named persona's file, reference
  real personas and venues, and dialogue speakers are participants.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_persona_library_762.py -v
"""

import os
import re

import pytest
import yaml

from backend.build_world import library_personas, load_world_yaml
from backend.penn.penn_world import WORLD_DATA, build_penn_world

DEFAULT_CAST = ["diego", "tanaka", "sofia"]

# The engine's canonical Direction names: a place name containing one of these
# as a bare word turns "travel to <place>" into a movement command ("West
# Wing" reads as "go west" -- see the world YAML's heads-up comment).
_COMPASS_WORDS = (
    "north",
    "south",
    "east",
    "west",
    "up",
    "down",
    "in",
    "out",
    "inside",
    "outside",
)

# Verb substrings the personas/README.md contract bans from activity text.
# The parser's EAT check was historically substring-based ("ate " matched
# inside "...late into the day" and froze Diego), and the perform re-parse
# below is the behavioral guard; this list keeps the authored wording
# convention greppable and the failure message obvious.
_BANNED_ACTIVITY_SUBSTRINGS = ("ate ", "eat ", "get ", "take ", "drink")


# --------------------------------------------------------------------------- #
# Module-scoped world state: one composed library, one built game, shared by
# every test below (building the Penn world loads the tile matrix -- do it once).


@pytest.fixture(scope="module")
def library_ids():
    return [entry["id"] for entry in library_personas(WORLD_DATA)]


@pytest.fixture(scope="module")
def library_specs():
    """id -> the RAW persona yaml (library_personas drops relationships/meetings)."""
    personas_dir = os.path.join(os.path.dirname(WORLD_DATA), "personas")
    specs = {}
    for fname in sorted(os.listdir(personas_dir)):
        if fname.endswith(".yaml"):
            with open(os.path.join(personas_dir, fname), encoding="utf-8") as f:
                specs[fname[:-5]] = yaml.safe_load(f)
    return specs


@pytest.fixture(scope="module")
def location_names():
    return {loc["name"] for loc in load_world_yaml(WORLD_DATA)["locations"]}


@pytest.fixture(scope="module")
def full_world(library_ids):
    """The Penn world built with EVERY library persona cast at once.

    Building is itself half the validation: unknown homes/places, unresolved
    tile addresses (#642), and bad relationship edges (unknown names,
    self-edges, duplicate pairs, closeness outside 1..5) all raise here.
    """
    return build_penn_world(cast=library_ids)


@pytest.fixture(scope="module")
def full_game(full_world):
    game, _characters = full_world.build_world_fn(full_world.world_map)
    return game


# --------------------------------------------------------------------------- #
# The default cast is untouched: #762 personas are parked, the bake's bytes
# can't move (test_replay_contract::test_bake_is_byte_identical pins the file
# itself; this pins the composition the bake reads).


def test_default_cast_is_still_the_three_person_mvp():
    data = load_world_yaml(WORLD_DATA)
    assert data["cast"] == DEFAULT_CAST
    assert [p["name"] for p in data["personas"]] == [
        "Diego Torres",
        "Professor Tanaka",
        "Sofia Ramirez",
    ]


def test_growth_personas_are_all_parked(library_ids):
    by_id = {e["id"]: e for e in library_personas(WORLD_DATA)}
    for pid in library_ids:
        assert by_id[pid]["in_default_cast"] == (pid in DEFAULT_CAST), pid


# --------------------------------------------------------------------------- #
# Every library file loads, carries the full field set, and builds.


def test_full_library_cast_builds(full_world, library_ids):
    assert len(library_ids) >= 15  # 7 from #731 + the #762 growth batch
    assert [p["name"] for p in full_world.personas] == [
        p["name"] for p in load_world_yaml(WORLD_DATA, cast=library_ids)["personas"]
    ]
    assert len(full_world.personas) == len(library_ids)


def test_every_persona_carries_the_full_field_set(library_specs):
    for pid, spec in library_specs.items():
        for field in ("name", "home", "persona", "emoji", "start_tile", "schedule"):
            assert spec.get(field), f"personas/{pid}.yaml is missing '{field}'"
        x, y = spec["start_tile"]  # exactly [x, y]
        assert isinstance(x, int) and isinstance(y, int), pid
        for stop in spec["schedule"]:
            assert stop.get("place"), f"{pid}: schedule stop without a place"
            assert stop.get("activity"), f"{pid}: schedule stop without an activity"


def test_schedule_places_resolve_to_real_locations(library_specs, location_names):
    for pid, spec in library_specs.items():
        assert spec["home"] in location_names, pid
        for stop in spec["schedule"]:
            assert stop["place"] in location_names, (
                f"personas/{pid}.yaml: scheduled place {stop['place']!r} "
                "is not in world_data_upenn.yaml"
            )


def test_start_tiles_are_walkable_campus_tiles(library_specs, full_world):
    """Spawn tiles must be walkable, distinct, and on the campus walks.

    Every library persona homes at the outdoor hub, so a start tile inside a
    building's arena would contradict its engine location (and a blocked tile
    strands the pathfinder at step 0).
    """
    wm = full_world.world_map
    addressed = set()
    for tiles in wm.address_tiles.values():
        addressed |= tiles
    seen = {}
    for pid, spec in library_specs.items():
        tile = tuple(spec["start_tile"])
        assert not wm.is_blocked(tile), f"{pid}: start_tile {tile} is a wall"
        assert tile not in addressed, f"{pid}: start_tile {tile} is inside a building"
        assert tile not in seen, f"{pid}: start_tile {tile} collides with {seen[tile]}"
        seen[tile] = pid


# --------------------------------------------------------------------------- #
# Activity wording: the mock brain replays each stop as ``perform <activity>``
# through the real parser, so the activity must re-parse as PERFORM -- not be
# hijacked by a verb keyword hiding in the text (#535/#536).


def test_every_activity_reparses_as_perform(library_specs, full_game):
    for pid, spec in library_specs.items():
        for stop in spec["schedule"]:
            intent = full_game.parser.determine_intent(f"perform {stop['activity']}")
            assert intent == "perform", (
                f"personas/{pid}.yaml: activity {stop['activity']!r} re-parses "
                f"as {intent!r}, not 'perform' -- reword it (see README.md)"
            )


def test_every_authored_command_parses(library_specs, full_game):
    # A stop's one-shot `commands:` (#300) are raw engine commands; each must
    # resolve to SOME intent or the agent burns its turn on a parse failure.
    for pid, spec in library_specs.items():
        for stop in spec["schedule"]:
            for command in stop.get("commands") or []:
                intent = full_game.parser.determine_intent(command)
                assert intent, f"{pid}: authored command {command!r} parses to nothing"


def test_activities_avoid_the_banned_verb_substrings(library_specs):
    for pid, spec in library_specs.items():
        for stop in spec["schedule"]:
            lowered = stop["activity"].lower()
            for banned in _BANNED_ACTIVITY_SUBSTRINGS:
                assert banned not in lowered, (
                    f"personas/{pid}.yaml: activity {stop['activity']!r} "
                    f"contains banned substring {banned!r} (see README.md)"
                )


def test_place_names_avoid_bare_compass_words(location_names):
    # "travel to <place>" is movement-verb-led, so a compass word on a word
    # boundary anywhere in the place name routes to GO ("West Wing" -> "go
    # west"). The world's own location list is the single source of places.
    for name in location_names:
        for word in _COMPASS_WORDS:
            assert not re.search(rf"\b{word}\b", name.lower()), (
                f"location {name!r} contains bare compass word {word!r} -- "
                "the parser would read 'travel to' it as a movement command"
            )


# --------------------------------------------------------------------------- #
# Relationships/meetings: ownership and reference rules from personas/README.md.


def test_relationships_live_with_their_first_named_persona(library_specs):
    known = {spec["name"] for spec in library_specs.values()}
    for pid, spec in library_specs.items():
        for edge in spec.get("relationships") or []:
            assert edge["a"] == spec["name"], (
                f"personas/{pid}.yaml: edge {edge['a']!r} -- {edge['b']!r} "
                "must live in its first-named persona's file"
            )
            assert edge["b"] in known, f"{pid}: unknown persona {edge['b']!r}"
            assert edge["a"] != edge["b"], f"{pid}: self-edge"
            assert 1 <= int(edge["closeness"]) <= 5, f"{pid}: closeness out of range"
            assert edge.get("kind") and edge.get("description"), pid


def test_meetings_are_owned_venued_and_spoken_by_participants(
    library_specs, location_names
):
    known = {spec["name"] for spec in library_specs.values()}
    for pid, spec in library_specs.items():
        for meeting in spec.get("meetings") or []:
            participants = meeting["participants"]
            assert participants[0] == spec["name"], (
                f"personas/{pid}.yaml: meeting {meeting.get('label')!r} must "
                "live in its first-named participant's file"
            )
            assert len(participants) >= 2, f"{pid}: meeting needs 2+ participants"
            for name in participants:
                assert name in known, f"{pid}: unknown participant {name!r}"
            assert meeting["at"] in location_names, (
                f"personas/{pid}.yaml: meeting venue {meeting['at']!r} is not "
                "a world location -- the injector would silently skip it"
            )
            assert meeting.get("dialogue"), f"{pid}: meeting without dialogue"
            for speaker, text in meeting["dialogue"]:
                assert speaker in participants, (
                    f"personas/{pid}.yaml: dialogue speaker {speaker!r} is not "
                    f"a participant of {meeting.get('label')!r}"
                )
                assert text, f"{pid}: empty dialogue line"
