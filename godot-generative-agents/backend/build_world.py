"""Build a ``text_adventure_games`` game from world data (personas + places).

This is the "uses our library" half of the generative-agents port: a world's
places become engine ``Location``s, its cast become ``Character``s carrying
first-person persona text, and the two custom actions (:mod:`actions`) let
agents ``travel`` and ``perform`` through the normal precondition gate.

The builder is world-agnostic -- it takes a ``(personas, locations)`` pair and
constructs the game. The project's primary world is the **UPenn campus**, loaded
and patched by :mod:`penn.penn_world` (it reads ``world_data_upenn.yaml`` via
:func:`load_world_yaml` and hands the normalized pair to :func:`build_world`).
Any world authored in the same YAML shape builds the same way.
"""

import difflib
import os

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


def load_world_yaml(path, cast: list[str] | None = None) -> dict:
    """Read a world YAML into a dict, resolving a cast-by-reference world (#731).

    A world either carries its cast inline (a ``personas:`` list -- e.g. the
    boil demo, ``world_data_boil.yaml``) or names it by reference: a
    ``cast: [diego, tanaka, sofia]`` list of persona ids, each resolved to
    ``personas/<id>.yaml`` next to the world file. A persona file holds the
    persona's own fields plus optional ``relationships:`` / ``meetings:``
    blocks (see ``penn/personas/README.md``); composition lifts those into the
    world's top-level blocks, dropping any entry that references a persona
    outside the cast -- an edge needs both ends present, a meeting needs all
    its participants. Dropping only applies to personas that exist in the
    library but sit outside the cast (parked); a name that matches *no*
    library persona is an authoring typo and raises ValueError, keeping the
    old inline-YAML fail-loud contract.

    ``cast`` overrides the file's list, so the pre-run config seam (#730) can
    pick a sub-cast without editing YAML. A ``cast`` passed against a world
    with no persona library, or an empty cast, fails loudly (ValueError)
    rather than being ignored.

    The composed dict's ``cast`` field records the effective ids that resolved
    to persona files. Duplicate display names (two files sharing a ``name``) or
    malformed persona files (empty or missing ``name`` field) raise ValueError.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    ids = cast if cast is not None else data.get("cast")
    if ids is None:
        return data
    if not ids:
        raise ValueError(f"cast: empty cast for {path}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"cast: duplicate persona ids in {ids}")
    library = os.path.join(os.path.dirname(os.path.abspath(path)), "personas")
    # Load the WHOLE library, not just the cast: edge/meeting endpoints are
    # validated against every library name so a typo'd name fails the build
    # instead of being silently filtered out with the parked personas.
    catalog: dict[str, dict] = {}
    if os.path.isdir(library):
        for fname in sorted(os.listdir(library)):
            if fname.endswith(".yaml"):
                with open(os.path.join(library, fname), encoding="utf-8") as f:
                    catalog[fname[:-5]] = yaml.safe_load(f)
    entries = []
    for pid in ids:
        if pid not in catalog:
            raise ValueError(
                f"cast: no persona file for {pid!r} "
                f"(expected {os.path.join(library, pid + '.yaml')})"
            )
        spec = catalog[pid]
        if not isinstance(spec, dict) or not spec.get("name"):
            raise ValueError(
                f"personas/{pid}.yaml is empty or not a persona mapping "
                "(it needs at least a 'name' field)"
            )
        entries.append(spec)
    names = {entry["name"] for entry in entries}
    if len(names) != len(entries):
        seen: dict = {}
        for entry in entries:
            seen[entry["name"]] = seen.get(entry["name"], 0) + 1
        dupes = sorted(n for n, c in seen.items() if c > 1)
        raise ValueError(
            f"cast: duplicate display name(s) {dupes} -- two persona files "
            "share a `name`, and build_world would silently collapse them "
            "into one character"
        )
    known = {
        spec["name"]
        for spec in catalog.values()
        if isinstance(spec, dict) and spec.get("name")
    }
    data["personas"] = [
        {k: v for k, v in entry.items() if k not in ("relationships", "meetings")}
        for entry in entries
    ]
    data["cast"] = list(ids)
    relationships, meetings = [], []
    for pid, entry in zip(ids, entries):
        for edge in entry.get("relationships") or []:
            ends = [edge.get("a"), edge.get("b")]
            for name in ends:
                if name not in known:
                    raise ValueError(
                        f"personas/{pid}.yaml: relationship references "
                        f"unknown persona {name!r}"
                    )
            if all(name in names for name in ends):
                relationships.append(edge)
        for meeting in entry.get("meetings") or []:
            participants = meeting.get("participants") or []
            for name in participants:
                if name not in known:
                    raise ValueError(
                        f"personas/{pid}.yaml: meeting references "
                        f"unknown persona {name!r}"
                    )
            if set(participants) <= names:
                meetings.append(meeting)
    data["relationships"] = relationships
    data["meetings"] = meetings
    return data


def library_personas(path) -> list[dict]:
    """Enumerate the persona library adjacent to world YAML *path* (#732).

    The catalog the pre-run config surface (GET /config) serves: one entry
    per ``personas/<id>.yaml`` next to the world file, sorted by id --
    ``{"id", "name", "blurb", "in_default_cast"}``. ``blurb`` is the
    persona's first-person ``persona`` text verbatim (frontends truncate);
    ``in_default_cast`` reflects the world file's own ``cast:`` list. A
    world with no adjacent library (or inline personas only) enumerates to
    ``[]``. Tolerant of malformed library files -- this is a read surface;
    a broken PARKED persona must not break browsing (putting it in a cast
    still fails the build loudly, see load_world_yaml).
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    default_cast = set(data.get("cast") or [])
    library = os.path.join(os.path.dirname(os.path.abspath(path)), "personas")
    entries = []
    if os.path.isdir(library):
        for fname in sorted(os.listdir(library)):
            if not fname.endswith(".yaml"):
                continue
            with open(os.path.join(library, fname), encoding="utf-8") as f:
                spec = yaml.safe_load(f)
            if not isinstance(spec, dict) or not spec.get("name"):
                continue
            pid = fname[:-5]
            entries.append(
                {
                    "id": pid,
                    "name": str(spec["name"]),
                    "blurb": str(spec.get("persona", "")),
                    "in_default_cast": pid in default_cast,
                }
            )
    return entries


def load_world_data(
    path, cast: list[str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Load + normalize a world YAML into ``(personas, locations)``.

    Every persona is given a uniform ``schedule`` (see :func:`_normalize_personas`)
    so downstream code has a single path. ``path`` points at a YAML with
    ``locations:`` and either an inline ``personas:`` list or a ``cast:``
    persona-reference list (resolved by :func:`load_world_yaml`, #731). The
    result is what :func:`build_world` expects.
    """
    data = load_world_yaml(path, cast)
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
        # Affordance tags (#613): a Location IS a Thing, so an arena tag is a
        # plain bool property -- the same fact npc.tools_for curation and the
        # verb's place-precondition read (#612). An absent `properties:` key
        # means no tags, so every existing world stays unchanged.
        for tag in spec.get("properties", ()):
            loc.set_property(tag, True)
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

    # Catch a typo in a Location's tile_address early (issue #642): an address
    # that resolves to no tiles builds cleanly, then walk_path returns [] and the
    # agent is stuck re-issuing `travel` forever -- no error, just a frozen
    # sprite burning live spend. Only checkable with a matrix in hand: a world
    # built without a world_map perceives by room and never paths on
    # tile_address, so it is unaffected. A falsy address (None/"") is an
    # intentional label-only location -- the hub carries `address: null`
    # (world_data_upenn.yaml) and a home can be "only ever a label"
    # (WorldMap.tile_gap) -- so only a *non-empty* address that resolves to
    # nothing is the typo we guard against.
    # ponytail: checks the address has *some* tiles, not that any are unblocked;
    # a fully-walled address is a map-authoring bug outside this typo's scope.
    if world_map is not None:
        known = getattr(world_map, "address_tiles", {})
        for loc in locations.values():
            if loc.tile_address and not world_map.tiles_for(loc.tile_address):
                near = difflib.get_close_matches(loc.tile_address, known, n=1)
                hint = f" Did you mean '{near[0]}'?" if near else ""
                raise ValueError(
                    f"Location '{loc.name}' has tile_address "
                    f"'{loc.tile_address}', which resolves to no tiles in the "
                    f"map.{hint}"
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

    # Place each persona in their home location (Game only auto-places the player)
    # and stamp its spawn tile: characters carry their live map position so
    # TiledGame.can_perceive can judge real distance inside one big Location
    # (issue #662). run_simulation.step keeps the stamp fresh as they walk.
    for spec in personas:
        char = characters[spec["name"]]
        locations[spec["home"]].add_character(char)
        if spec.get("start_tile"):
            char.tile = tuple(spec["start_tile"])

    return game, characters
