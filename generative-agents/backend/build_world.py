"""Build the Smallville world as a ``text_adventure_games`` game.

This is the "uses our library" half of the port: Smallville's places become
engine ``Location``s, the cast become ``Character``s carrying first-person
persona text (lifted from the upstream ``scratch.json`` profiles), and the two
custom actions (:mod:`actions`) are registered so agents can ``travel`` and
``perform`` through the normal precondition gate.

The world is fully data-driven: every persona is one entry in :data:`PERSONAS`
and every place one entry in :data:`_LOCATIONS`, both defined in
``world_data.yaml``. We model the whole upstream ``the_ville_n25`` cast -- all
25 residents -- each waking at home and heading to where they spend their day
(the cafe owner to her cafe, students to the college, the bartender to the pub,
and so on). Adding a 26th resident is just another YAML entry; adding a new
place is one more location.
"""

from pathlib import Path

import yaml
from text_adventure_games.things.characters import Character
from text_adventure_games.things.locations import Location

from .actions import Act, Travel
from .tiled_game import TiledGame

_WORLD_DATA_PATH = Path(__file__).with_name("world_data.yaml")


def _load_world_data() -> tuple[list[dict], list[dict]]:
    with _WORLD_DATA_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["personas"], data["locations"]


# The cast and locations live in world_data.yaml. Each persona entry has:
#   name        display name (also picks the sprite: "John Lin" -> John_Lin.png)
#   home        the location they wake in (must be a name in _LOCATIONS)
#   persona     the first-person identity the agent reasons as (innate traits +
#               background, condensed from the upstream scratch.json profile)
#   emoji       the default pronunciatio bubble shown above the sprite
#   start_tile  the [x, y] tile they spawn on -- matches the base sim's
#               environment/0.json so the frontend places them exactly as upstream
#
# A persona's *day* is given one of two ways:
#   schedule    an ordered list of stops the agent works through over the run.
#               Each stop is {place, activity, emoji?, steps?}: travel to <place>,
#               then <activity> there for <steps> steps before moving on (omit
#               <steps> to stay for the rest of the day -- the natural choice for
#               the last stop). emoji defaults to the persona's. This is what makes
#               memory evolve: every stop adds new travel/perform memories and
#               lets co-located residents perceive each other.
#   destination/activity
#               a single place + activity (the upstream-style one-stop day). The
#               inactive 25-resident roster uses this; _normalize_personas turns it
#               into a one-stop schedule so the step loop has a single code path.
#
# Each location entry has name, description, address (Smallville tile address or
# null for the hub), and optionally hub: true for the town center.
_ALL_PERSONAS, _LOCATIONS = _load_world_data()

# The valid place names a plan may target. A generated planner (issue #83,
# :class:`backend.planner.LLMPlanner`) validates its stops against this so a
# hallucinated location is dropped before it reaches the parser.
LOCATION_NAMES = frozenset(loc["name"] for loc in _LOCATIONS)


def _normalize_personas(personas: list[dict]) -> list[dict]:
    """Give every persona a uniform ``schedule`` list (mutates in place).

    A persona authored with a ``schedule:`` keeps it (each stop filled out with a
    default emoji and an explicit ``steps`` of ``None`` when omitted); its legacy
    ``destination``/``activity`` are mirrored from the first stop so code and tests
    that read those fields still work. A persona authored with only
    ``destination``/``activity`` gets a synthesized one-stop schedule that stays
    put for the whole run -- the original single-activity behavior.
    """
    for spec in personas:
        if spec.get("schedule"):
            spec["schedule"] = [
                {
                    "place": stop["place"],
                    "activity": stop["activity"],
                    "emoji": stop.get("emoji", spec["emoji"]),
                    "steps": stop.get("steps"),  # None => stay for the rest of the day
                }
                for stop in spec["schedule"]
            ]
            spec["destination"] = spec["schedule"][0]["place"]
            spec["activity"] = spec["schedule"][0]["activity"]
        else:
            spec["schedule"] = [
                {
                    "place": spec["destination"],
                    "activity": spec["activity"],
                    "emoji": spec["emoji"],
                    "steps": None,
                }
            ]
    return personas


_normalize_personas(_ALL_PERSONAS)

# Active cast size. The full 25-resident roster still loads from world_data.yaml
# (nothing is deleted) -- we just run a smaller subset so the demo's per-agent
# memory/reasoning panels stay readable. Set this to len(_ALL_PERSONAS) to run
# the whole town again. The first 5 are a deliberate mix: Isabella + Maria share
# Hobbs Cafe and Klaus + Ayesha share Oak Hill College, so co-located agents
# perceive and remember each other, while Wolfgang heads to the park alone.
MAX_ACTIVE_PERSONAS = 5
PERSONAS = _ALL_PERSONAS[:MAX_ACTIVE_PERSONAS]


def build_world(world_map=None):
    """Construct the Smallville game.

    Returns ``(game, characters)`` where ``characters`` maps persona name ->
    :class:`Character`. Agents are *not* attached here (see
    :mod:`smallville_agents`); the caller wires those onto each character.

    Pass a :class:`~backend.world_map.WorldMap` to make "who/what is nearby"
    tile-distance based (issue #82): the game is a :class:`TiledGame`, so an
    agent with ``vision_r > 0`` perceives residents/objects in arenas within that
    many tiles. With no ``world_map`` (the default) perception falls back to the
    current room, so callers that don't need proximity are unaffected.
    """
    locations: dict[str, Location] = {}
    hub = None
    for spec in _LOCATIONS:
        loc = Location(spec["name"], spec["description"])
        # Plain attribute (not a bool property): the Smallville address this
        # engine location resolves to on the tile map.
        loc.tile_address = spec["address"]
        locations[spec["name"]] = loc
        if spec.get("hub"):
            hub = spec["name"]

    # Catch a typo in a persona's home or any scheduled place early, with a clear
    # message, rather than failing deep inside the parser at simulate() time.
    for spec in PERSONAS:
        if spec["home"] not in locations:
            raise ValueError(
                f"{spec['name']}'s home '{spec['home']}' is not a known location"
            )
        for stop in spec["schedule"]:
            if stop["place"] not in locations:
                raise ValueError(
                    f"{spec['name']}'s scheduled place '{stop['place']}' "
                    "is not a known location"
                )

    # Wire every location to the hub so Game.__init__ discovers them all (it
    # walks the connection graph from start_at). Non-canonical direction labels
    # ("to hobbs cafe") don't auto-create a reverse exit, which is fine: agents
    # travel by name via the Travel action, not by compass direction.
    hub_loc = locations[hub]
    for name, loc in locations.items():
        if name != hub:
            hub_loc.add_connection(f"to {name.lower()}", loc)

    # A silent observer stands in as the engine's required "player". It never
    # acts; every persona is an NPC driven by its agent.
    observer = Character(
        "Observer", "A silent observer of the town.", "I quietly watch Smallville."
    )

    characters: dict[str, Character] = {}
    for spec in PERSONAS:
        char = Character(spec["name"], spec["name"], spec["persona"])
        characters[spec["name"]] = char

    game = TiledGame(
        hub_loc,
        observer,
        characters=list(characters.values()),
        custom_actions=[Travel, Act],
        turn_mode="simultaneous",
        world_map=world_map,
    )

    # Place each persona in their home location (Game only auto-places the player).
    for spec in PERSONAS:
        locations[spec["home"]].add_character(characters[spec["name"]])

    return game, characters
