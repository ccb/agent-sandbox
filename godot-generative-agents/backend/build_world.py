"""Build a ``text_adventure_games`` game from world data (personas + places).

This is the "uses our library" half of the generative-agents port: a world's
places become engine ``Location``s, its cast become ``Character``s carrying
first-person persona text, and the two custom actions (:mod:`actions`) let
agents ``travel`` and ``perform`` through the normal precondition gate.

The builder is world-agnostic -- it takes a ``(personas, locations)`` pair and
constructs the game. The project's primary world is the **UPenn campus**, loaded
and patched by :mod:`penn.penn_world` (it reads ``world_data_upenn.yaml`` via
:func:`load_world_data` and hands the normalized pair to :func:`build_world`).
Any world authored in the same YAML shape builds the same way.
"""

import yaml
from text_adventure_games.things.characters import Character
from text_adventure_games.things.locations import Location

from .actions import Act, Travel
from .parser import PennParser
from .tiled_game import TiledGame

# The cast and locations come from a world YAML (e.g. ``penn/world_data_upenn.yaml``).
# Each persona entry has:
#   name        display name (also picks the sprite: "John Lin" -> John_Lin.png)
#   home        the location they wake in (must be a name in the locations list)
#   persona     the first-person identity the agent reasons as (innate traits +
#               background)
#   emoji       the default pronunciatio bubble shown above the sprite
#   start_tile  the [x, y] tile they spawn on -- so the frontend places them exactly
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
#               a single place + activity (a one-stop day). _normalize_personas
#               turns it into a one-stop schedule so the step loop has one path.
#
# Each location entry has name, description, address (the tile-map address or null
# for the hub), and optionally hub: true for the world's center.


def load_world_data(path) -> tuple[list[dict], list[dict]]:
    """Load + normalize a world YAML into ``(personas, locations)``.

    Every persona is given a uniform ``schedule`` (see :func:`_normalize_personas`)
    so downstream code has a single path. ``path`` points at a YAML with
    ``personas:`` and ``locations:`` lists -- e.g. the UPenn campus
    (``world_data_upenn.yaml``). The result is what :func:`build_world` expects.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _normalize_personas(data["personas"]), data["locations"]


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
                    # Authored one-shot commands the mock brain replays at this
                    # stop, one per decision, before settling into `perform`
                    # (#300 -- e.g. "get ..." then "drink ..." at Houston Hall).
                    "commands": list(stop.get("commands") or []),
                    # Optional furniture the agent should occupy at this stop
                    # (#559 -- e.g. "blackboard" for a teacher). None => the
                    # router's default nearest-spot pick.
                    "furniture": stop.get("furniture"),
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
                    "commands": [],
                    "furniture": None,
                }
            ]
    return personas


def build_world(
    world_map=None,
    personas: list[dict] | None = None,
    locations_data: list[dict] | None = None,
    extra_actions: list | None = None,
):
    """Construct a generative-agents game from a world's personas + locations.

    Returns ``(game, characters)`` where ``characters`` maps persona name ->
    :class:`Character`. Agents are *not* attached here (see :mod:`backend.cognition`);
    the caller wires those onto each character.

    ``personas`` and ``locations_data`` are required -- pass the normalized pair
    from :func:`load_world_data` (the UPenn campus, or any world in the same
    shape). ``personas`` must already carry a ``schedule`` (load_world_data does
    this), or building fails on the schedule checks below.

    Pass a :class:`~backend.world_map.WorldMap` to make "who/what is nearby"
    tile-distance based (issue #82): the game is a :class:`TiledGame`, so an
    agent with ``vision_r > 0`` perceives residents/objects in arenas within that
    many tiles. With no ``world_map`` perception falls back to the current room,
    so callers that don't need proximity are unaffected.

    ``extra_actions`` appends world-specific Action classes to the registry (the
    UPenn boil-water verbs, #300); an entry whose action_name matches a built-in
    (e.g. "drink") overrides it for this game.
    """
    if personas is None or locations_data is None:
        raise ValueError(
            "build_world requires personas and locations_data -- load them with "
            "load_world_data(path) (e.g. penn/world_data_upenn.yaml)."
        )

    locations: dict[str, Location] = {}
    hub = None
    for spec in locations_data:
        loc = Location(spec["name"], spec["description"])
        # Plain attribute (not a bool property): the tile-map address this engine
        # location resolves to.
        loc.tile_address = spec["address"]
        locations[spec["name"]] = loc
        if spec.get("hub"):
            hub = spec["name"]

    # Catch a typo in a persona's home or any scheduled place early, with a clear
    # message, rather than failing deep inside the parser at simulate() time.
    for spec in personas:
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
        "Observer", "A silent observer of the world.", "I quietly watch the world."
    )

    characters: dict[str, Character] = {}
    for spec in personas:
        char = Character(spec["name"], spec["name"], spec["persona"])
        characters[spec["name"]] = char

    game = TiledGame(
        hub_loc,
        observer,
        characters=list(characters.values()),
        custom_actions=[Travel, Act, *(extra_actions or [])],
        turn_mode="simultaneous",
        world_map=world_map,
    )

    # Wire up the custom parser that fixes the "ate " substring collision with
    # "activate"/"deactivate" (see parser.py); delegates everything else to
    # the engine parser unchanged.
    game.set_parser(PennParser(game))

    # Place each persona in their home location (Game only auto-places the player).
    for spec in personas:
        locations[spec["home"]].add_character(characters[spec["name"]])

    return game, characters
