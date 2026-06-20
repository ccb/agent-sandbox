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
#   destination where they head for the day (must be a name in _LOCATIONS)
#   activity    what they do once they arrive (the on-screen action label)
#   emoji       the pronunciatio bubble shown above the sprite while performing
#   start_tile  the [x, y] tile they spawn on -- matches the base sim's
#               environment/0.json so the frontend places them exactly as upstream
#
# Each location entry has name, description, address (Smallville tile address or
# null for the hub), and optionally hub: true for the town center.
PERSONAS, _LOCATIONS = _load_world_data()


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

    # Catch a typo in a persona's home/destination early, with a clear message,
    # rather than failing deep inside the parser at simulate() time.
    for spec in PERSONAS:
        for key in ("home", "destination"):
            if spec[key] not in locations:
                raise ValueError(
                    f"{spec['name']}'s {key} '{spec[key]}' is not a known location"
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
