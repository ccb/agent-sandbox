"""The one configured Penn world, shared by the bake and the live server (#297).

The Penn sim isn't just ``build_world`` over the ``the_upenn`` matrix -- it is
that *plus* three behavioral patches (centre-of-building routing, meeting
rendezvous clustering, perception-gated hearing) that make agents actually
converge and converse. Historically all of that lived inline in
``generate_penn_replay.py::main()``, so a live server rebuilding the world
without them would get a *subtly different Penn* -- agents that never meet,
conversations that never fire -- making live-vs-baked comparison meaningless.

:func:`build_penn_world` is the single factory both entry points import:

* ``generate_penn_replay.py`` -- the offline bake that writes
  ``maps/penn_replay.json`` for the load-once viewer;
* ``serve_penn.py`` -- the live server (#263) that steps the same world over
  ``backend.api``'s live loop (#349/#262).

Everything here is world *setup*; genuinely bake-only work (running
``simulate()`` to completion, the post-hoc conversation injector, writing the
JSON) stays in the generator, and live-only work (the on-the-fly injector, the
stepper) lives in the server.
"""

import os
from dataclasses import dataclass, field
from typing import Callable

import yaml

# Reuse the tested agent engine (not a fork). It's the installed top-level
# `backend` package now, so a plain import works -- no sys.path juggling.
from backend import path_finder
from backend.actions import (
    Activate,
    CheckOutBook,
    Deactivate,
    DrinkPenn,
    ReadPenn,
    Study,
    TalkTo,
    WaitPenn,
)
from backend.build_world import build_world, load_world_data, load_world_yaml
from backend.world_map import WorldMap
from text_adventure_games.actions.things import Craft
from text_adventure_games.crafting import Recipe
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))

WORLD_DATA = os.path.join(_SIM_DIR, "world_data_upenn.yaml")
# A one-persona boil-water DEMO world (#592): the same map + factory, a single
# Houston-homed resident running the full boil arc early so it doesn't cluster at
# the far-right of a long bundled bake. `generate_penn_replay.py --scenario boil`
# loads this instead of the full cast.
WORLD_DATA_BOIL = os.path.join(_SIM_DIR, "world_data_boil.yaml")
UPENN_DIR = os.path.join(_SIM_DIR, "the_upenn")

# The Penn-local verb set (#300): registered on top of Travel/Act via
# build_world(extra_actions=...). DrinkPenn overrides the engine's "drink"; Craft is
# the engine crafting action that drives the boil-water Recipe (see _boil_recipe) --
# boiling is now a declarative transform, not a bespoke action. Upstreaming these
# into the engine library is #464.
PENN_EXTRA_ACTIONS = [
    Activate,
    Deactivate,
    DrinkPenn,
    Craft,
    WaitPenn,
    TalkTo,
    Study,
    CheckOutBook,
    ReadPenn,
]

# The verb set a Penn brain may choose from (spec §3) -- the engine verbs the
# boil-water scenario wires in, on top of the base travel/perform. `make` is the
# crafting verb the brain uses to boil ("make boiled water"); `wait` is the
# universal honest-idle verb (#614) -- WaitPenn's pacing slots make a chosen
# wait settle, so offering it is no longer a recurring-token-spend trap.
# `talk_to` is the #614 agent-initiated conversation verb; its tool is curated
# per-decide in `cognition.action_tools_for`. `eat` (engine) and `study`
# (Penn-local, #615) are affordance-curated -- offered only where an EDIBLE
# meal / a `studyable` arena is in scope (#612). `check_out_book`
# (Penn-local) and `read` (engine) are the #616 Van Pelt book loop,
# curated to the shelf's arena / the borrower's pocket. Handed to
# attach_agents(extra_action_names=...) by every Penn entry point.
PENN_ACTION_VERBS = [
    "get",
    "drink",
    "activate",
    "deactivate",
    "make",
    "wait",
    "talk_to",
    "eat",
    "study",
    "check_out_book",
    "read",
]

SEC_PER_STEP = 10  # in-game seconds per step, for a wall-clock label
SIM_START = "2023-02-13 08:00:00"  # matches backend.sim_config default

# How the Godot viewer (scripts/viewer.gd) plays a `chat` transcript back:
# ~DIALOGUE_LINE_STEPS replay steps per line, with the last line fading over
# DIALOGUE_FADE_STEPS. We mirror them here so the conversation injectors (the
# bake's post-hoc one and the live server's on-the-fly one) only fire a meeting
# when the participants stay together long enough for the whole exchange to play
# out on the map (otherwise the bubbles/link would linger after they part).
# Real #371 conversations get the same guarantee from the playback hold
# (cognition.CONVERSATION_LINE_PLAYBACK_STEPS, issue #673). Keep in sync with
# the constants of the same name in viewer.gd.
DIALOGUE_LINE_STEPS = 14
DIALOGUE_FADE_STEPS = 2


def _pin_building_meeting_points(world_map, offset=5.0):
    """Route agents heading into a building toward its *centre* (on the side they
    approach from), instead of the nearest tile of its huge lobby address.

    A building's interior is one big address (Houston Hall's "lobby" is ~2000 tiles
    spanning the whole footprint) and ``walk_path`` aims for the *nearest* such tile
    -- so two residents arriving from opposite sides settle at opposite edges, tens
    of tiles apart, even though the sim counts them co-located. A perception-gated
    conversation between them then renders as a long line across the building.

    Here we wrap ``walk_path`` so each agent walks to a tile a few (`offset`) tiles
    off the building's centre toward where it came from: residents converge near the
    middle -- close enough to read as together (a short conversation link) -- while
    still arriving from their own sides rather than stacking on one tile. The
    interior addressing is untouched (these are ordinary lobby tiles); if the target
    isn't reachable we fall back to the original nearest-tile routing, so no agent
    is ever stranded.
    """
    orig_walk_path = world_map.walk_path
    centres: dict = {}
    spot_cursor: dict = {}

    def centre_of(address):
        if address not in centres:
            tiles = [
                t for t in world_map.tiles_for(address) if not world_map.is_blocked(t)
            ]
            if tiles:
                cx = sum(t[0] for t in tiles) / len(tiles)
                cy = sum(t[1] for t in tiles) / len(tiles)
                centres[address] = (cx, cy, tiles)
            else:
                centres[address] = None
        return centres[address]

    def walk_path(from_tile, address, furniture=None):
        # Furniture first (#537): when the arena has seat spots, walk to one
        # of the k nearest to the approach-offset point -- consumed
        # round-robin per address so co-arrivals spread across furniture
        # instead of stacking -- and only fall through to the centroid pick
        # (below) when every candidate is unreachable. Bare arenas
        # (Williams, grounds) have no spots and keep today's behavior.
        # A furniture hint (#559) biases the pick to spots serving that piece
        # (a teacher -> blackboard); no match -> the full spot set, as before.
        spots = getattr(world_map, "furniture_spots", {}).get(address)
        info = centre_of(address)
        if spots and info:
            if furniture:
                types = getattr(world_map, "furniture_spot_type", {})
                matching = [t for t in spots if types.get(t) == furniture]
                if matching:
                    spots = matching
            cx, cy, _tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            near = sorted(spots, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            near = near[:4]
            n = spot_cursor.get(address, 0)
            spot_cursor[address] = n + 1
            for j in range(len(near)):
                target = near[(n + j) % len(near)]
                if tuple(from_tile) == target:
                    return []
                path = path_finder.path_finder(
                    world_map.collision, tuple(from_tile), target, 1
                )
                if path and len(path) > 1:
                    return [tuple(t) for t in path[1:]]
        if info:
            cx, cy, tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            # A point `offset` tiles from the centre toward the agent's approach...
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            # ...then the nearest actual lobby tile to it.
            target = min(tiles, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            if tuple(from_tile) != target:
                path = path_finder.path_finder(
                    world_map.collision, tuple(from_tile), target, 1
                )
                if path and len(path) > 1:
                    return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address)  # target unreachable -> nearest tile

    world_map.walk_path = walk_path
    return world_map


def _rendezvous_clusters(world_map, addresses, spacing=4):
    """For each meeting venue, a tight cluster of a few walkable tiles near its
    centre, all within a couple of `spacing` of each other.

    Routing every participant of a meeting onto one of these (below) makes them
    settle a handful of tiles apart -- comfortably inside the perception radius, so
    a conversation reads as people standing together with a short link, rather than
    at opposite ends of a big room (which the per-side centre routing can leave
    them). Tiles are taken from the venue's own arena, so they're always walkable
    and inside the room.
    """
    clusters: dict = {}
    for address in addresses:
        tiles = [t for t in world_map.tiles_for(address) if not world_map.is_blocked(t)]
        if not tiles:
            continue
        cx = sum(t[0] for t in tiles) / len(tiles)
        cy = sum(t[1] for t in tiles) / len(tiles)
        # The centre tile plus two neighbours offset by `spacing`, each snapped to
        # the nearest real arena tile; de-duplicated but order-preserving.
        wants = [(cx, cy), (cx + spacing, cy), (cx, cy + spacing)]
        cluster: list = []
        for wx, wy in wants:
            t = min(tiles, key=lambda p: (p[0] - wx) ** 2 + (p[1] - wy) ** 2)
            if t not in cluster:
                cluster.append(t)
        if cluster:
            clusters[address] = cluster
    return clusters


def _pin_meeting_rendezvous(world_map, venues):
    """Route each successive arrival at a meeting venue to a distinct tile in its
    rendezvous cluster (round-robin), so participants converge a few tiles apart.

    Wraps whatever ``walk_path`` is already installed (e.g. the centre routing
    above) and only intercepts the venue addresses; every other destination falls
    through unchanged. Any two cluster tiles are within perception range, so it
    doesn't matter which arrival gets which slot -- participants always end up close
    enough to converse. If the cluster tile is somehow unreachable we fall back to
    the underlying routing, so no agent is stranded.

    Note the round-robin ``counts`` live in this closure: the patched
    ``world_map`` is *stateful*, which is why :func:`build_penn_world` hands out
    a fresh one per call (a reused map would give later runs different
    rendezvous slots).
    """
    orig_walk_path = world_map.walk_path
    counts: dict = {address: 0 for address in venues}

    def walk_path(from_tile, address, furniture=None):
        cluster = venues.get(address)
        if cluster:
            target = tuple(cluster[counts[address] % len(cluster)])
            counts[address] += 1
            if tuple(from_tile) == target:
                return []  # already standing on the rendezvous tile
            path = path_finder.path_finder(
                world_map.collision, tuple(from_tile), target, 1
            )
            if path and len(path) > 1:
                return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address, furniture=furniture)

    world_map.walk_path = walk_path
    return world_map


def _gate_conversations_by_perception(built):
    """Make the Penn agents converse only with whoever they can *perceive*.

    The engine already perceives by tile distance (``TiledGame`` overrides
    ``perceivable_locations`` for sight, vision_r=8), but its *hearing* seam
    (``audience_for``) is still room-based by default -- so two residents would
    only talk when in the exact same arena, even when standing far apart on the
    map. We keep that fix in the Godot sim (not the shared engine): override the
    Penn game's ``audience_for`` to reuse its own ``perceivable_locations``, so an
    agent's conversation partners are exactly the residents within its perception
    radius. ``simulate``'s conversation loop reads ``audience_for`` (via
    ``can_converse`` / ``find_conversation_pairs``), so this gates dialogue by
    proximity with no engine change.

    ``build_world`` returns ``(game, characters)``; we patch the game and pass it
    straight through.
    """
    game, characters = built

    def audience_for(speaker, message, target=None):
        # Two gates (issue #662): perceivable_locations picks the *rooms* in
        # earshot, can_perceive then drops same-room residents who are actually
        # out of range -- the outdoor hub is one room spanning the whole campus,
        # so room membership alone would let agents converse across the map.
        # Deliberately observer-only: the gate reads the SPEAKER's vision_r, so
        # if per-agent vision ever diverges, A can address a B who can't
        # perceive A back (shouting at someone with narrow sight is fine).
        audience = []
        for loc in game.perceivable_locations(speaker):
            audience.extend(
                c
                for c in loc.characters.values()
                if c is not speaker and game.can_perceive(speaker, c)
            )
        return audience

    game.audience_for = audience_for
    return game, characters


@dataclass
class PennWorld:
    """Everything the configured Penn sim is made of, ready to run.

    ``world_map`` carries the routing patches (and their round-robin state --
    see :func:`_pin_meeting_rendezvous`), ``build_world_fn`` bakes in the
    perception gating, ``meetings`` is the authored dialogue script both
    conversation injectors consume, ``llm`` is the world's declared LLM
    settings (the YAML ``llm:`` block; only ``serve_penn --brain llm`` acts
    on it), and ``relationships`` is the validated t=0 seed social graph the
    viewer's social-graph pop-up draws (#252)."""

    world_map: WorldMap
    personas: list
    locations: list
    meetings: list
    build_world_fn: Callable
    llm: dict | None = None
    relationships: list = field(default_factory=list)


def make_boil_sink() -> Item:
    """The boil-water sink prop (#300). A plain on/off device."""
    sink = Item("sink", "a utility sink", "An old utility sink. The tap runs cloudy.")
    sink.set_property(Property.GETTABLE, False)
    sink.set_property("is_device", True)
    return sink


def make_boil_stove() -> Item:
    """The boil-water stove prop (#300). The heat source the boil Recipe requires
    as a tool (present, not consumed)."""
    stove = Item(
        "stove", "a small electric stove", "A single coil burner, dusty but working."
    )
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    return stove


def make_murky_pot() -> Item:
    """The pot of unboiled water (#300) -- the boil Recipe's consumed input.

    ``requires_boiling`` + ``is_boiled: False`` so DrinkPenn sickens on it;
    ``portions`` so drinking it raw keeps the vessel (until boiling consumes it).
    The single source of this item so the tiny-world tests can't drift from the
    furnished Houston Hall (finding 12)."""
    pot = Item(
        "pot of murky water",
        "a pot of murky water",
        "A dented steel pot of cloudy, untreated tap water.",
    )
    pot.set_property(Property.DRINKABLE, True)
    pot.set_property("requires_boiling", True)
    pot.set_property("is_boiled", False)
    pot.set_property("portions", 3)
    # Aliases (#635): the full name is long and a model naturally says "water" /
    # "murky water" / "the pot". Safe because Drink matches *carried* items only
    # and the arc never carries both pots at once (make consumes this one), so
    # the "water"/"pot" it shares with the boiled pot can't collide in practice.
    for alias in ("water", "murky water", "pot", "murky pot"):
        pot.add_alias(alias)
    return pot


def make_boiled_pot() -> Item:
    """What the boil Recipe PRODUCES (#300): a real, distinctly-named vessel of safe
    water. ``is_boiled`` is what DrinkPenn's recovery gate keys on, and the name is
    what its narration reads -- so drinking this correctly says "boiled water", and
    the transform is a visible object swap, not a hidden flag on the murky pot."""
    pot = Item(
        "pot of boiled water",
        "a pot of boiled water",
        "A steel pot of water, boiled clear and now safe to drink.",
    )
    pot.set_property(Property.DRINKABLE, True)
    pot.set_property("is_boiled", True)
    pot.set_property("portions", 3)
    # Aliases (#635): see make_murky_pot -- the recovery drink must be nameable
    # as "boiled water" / "water" / "the pot", not only the full string.
    for alias in ("water", "boiled water", "pot", "boiled pot"):
        pot.add_alias(alias)
    return pot


def _boil_recipe() -> Recipe:
    """Boiling as an engine crafting Recipe (#300, superseding the bespoke
    BoilWater): consume the held ``pot of murky water``, require a ``stove`` present
    (a tool, not consumed), and PRODUCE a ``pot of boiled water``. Driven by the
    engine ``Craft`` action via ``make boiled water`` -- a declarative, discoverable,
    learnable transform an LLM can reason over (the #595/#301 payoff), not a one-off
    action. The output factory logs the ``boiled`` event the viewer's timeline marks,
    so the on-screen arc reads unchanged."""

    def _produce(game) -> Item:
        pot = make_boiled_pot()
        game.log_event(
            None,
            "boiled",
            summary="the pot is boiled clear on the stove",
            payload={"item": pot.name},
        )
        return pot

    return Recipe(
        inputs=["pot of murky water"],
        tools=["stove"],
        output=_produce,
        name="boiled water",
        result_text=(
            "You set the pot on the stove and boil it until the water runs clear."
        ),
    )


def _furnish_boil_water(game) -> None:
    """Stock Houston Hall with the boil-water props (#300).

    A pot of unboiled water (``requires_boiling`` + ``is_boiled: False``, with
    ``portions``), plus a sink and a stove device. The full arc: drink the murky
    water and DrinkPenn makes you sick; ``make boiled water`` (the boil Recipe)
    consumes the murky pot and produces a ``pot of boiled water``; drinking that
    boiled pot cures the sickness. (Whether an agent *chooses* to boil before
    drinking is the experiment; the self-coded variant is #301.)"""
    hall = game.locations.get("Houston Hall")
    if hall is None:
        return
    hall.add_item(make_boil_sink())
    hall.add_item(make_boil_stove())
    hall.add_item(make_murky_pot())


def make_meal(name: str, description: str, examine: str) -> Item:
    """A Houston Hall meal (#615): EDIBLE and gettable (the Item default), so
    the natural loop is get -> eat -- the same possession gate as the drink
    pattern. Discrete items ARE the portions: the engine's Eat consumes the
    whole item (it has no Drink-style portions), so one meal = one portion."""
    meal = Item(name, description, examine)
    meal.set_property(Property.EDIBLE, True)
    return meal


def _furnish_meals(game) -> None:
    """Stock Houston Hall with EDIBLE meals (#615). An EDIBLE thing in scope is
    exactly what makes the engine's `eat` (declared `(Property.EDIBLE,)` in
    #612) offered -- so agents can eat here and only here. Meals live in the
    building-level "Houston Hall" location, next to the boil props, for the
    same reason those do (see the world-YAML comment): schedule stops that act
    on them must target "Houston Hall" itself. Gated on the authored `dining`
    arena tag (#613): a world that doesn't tag the hall -- the isolated boil
    scenario (#299/#301), whose one resident lives in Houston Hall and must
    keep a decision surface of only the drink/boil arc -- gets no meals, so
    `eat` is never offered there."""
    hall = game.locations.get("Houston Hall")
    if hall is None or not hall.get_property("dining"):
        return
    for name, description, examine in (
        (
            "sandwich",
            "a wrapped sandwich",
            "A turkey club off the Houston Hall food-court counter.",
        ),
        (
            "bowl of soup",
            "a bowl of lentil soup",
            "Steaming lentil soup from the Houston Hall food court.",
        ),
        (
            "apple",
            "a red apple",
            "A crisp apple from the fruit basket by the register.",
        ),
    ):
        hall.add_item(make_meal(name, description, examine))


def make_library_shelf() -> Item:
    """The Van Pelt circulating shelf (#616). ``book_shelf`` is the affordance
    CheckOutBook declares, so the verb is offered exactly where the shelf
    stands -- the Book Stacks arena -- and nowhere else."""
    shelf = Item(
        "book shelf",
        "a tall shelf of circulating books",
        "Open shelving, rows of spines with call numbers taped to them.",
    )
    shelf.set_property(Property.GETTABLE, False)
    shelf.set_property("book_shelf", True)
    return shelf


def make_campus_history_book() -> Item:
    """A checkout-able Van Pelt book (#616): ``library_book`` is what the
    CheckOutBook gate accepts, READABLE makes the engine's Read offerable,
    and READ_TEXT is the content the read memory quotes. Not GETTABLE, so
    checkout is the only way into a pocket."""
    book = Item(
        "campus history book",
        "a clothbound campus history",
        "A clothbound history of the university, corners soft with use.",
    )
    book.set_property(Property.GETTABLE, False)
    book.set_property("library_book", True)
    book.set_property(Property.READABLE, True)
    book.set_property(
        Property.READ_TEXT,
        "College Hall opened in 1873; its green serpentine stone is so soft "
        "the university repairs it block by block.",
    )
    return book


def make_star_atlas() -> Item:
    """The second Van Pelt book (#616), so two borrowers can each hold one --
    and the contention gate has a real 'that one is taken' case to explain."""
    book = Item(
        "star atlas",
        "a fold-out star atlas",
        "A tall atlas of the northern sky, plates worn at the folds.",
    )
    book.set_property(Property.GETTABLE, False)
    book.set_property("library_book", True)
    book.set_property(Property.READABLE, True)
    book.set_property(
        Property.READ_TEXT,
        "A chart of the winter sky; someone has circled Cassiopeia in pencil.",
    )
    return book


def _furnish_van_pelt(game) -> None:
    """Stock the Van Pelt Book Stacks with the #616 book-loop props: the
    circulating shelf (the check_out_book affordance anchor) plus two
    checkout-able, readable books. Same pattern as _furnish_boil_water."""
    stacks = game.locations.get("Van Pelt — Book Stacks")
    if stacks is None:
        return
    stacks.add_item(make_library_shelf())
    stacks.add_item(make_campus_history_book())
    stacks.add_item(make_star_atlas())


def build_penn_world(
    world_data=WORLD_DATA,
    upenn_dir=UPENN_DIR,
    *,
    withhold_boil: bool = False,
    cast: list[str] | None = None,
) -> PennWorld:
    """Load + patch the Penn world, exactly as the replay bake configures it.

    Every call returns a *fresh* world (fresh ``WorldMap``, fresh patch state),
    because the routing patches are stateful -- a live server's ``reset()``
    must call this again rather than reuse the old map.

    Pass ``withhold_boil=True`` to build the world WITHOUT registering the boil
    Recipe (#624): restores the #300 capability gap ("no agent can boil water
    yet") on demand, instrumented, for the boil-wish-articulation experiment
    (``experiments/boil_wish_articulation.py``). Houston Hall is still furnished
    with the murky pot / sink / stove -- an agent can see and reach for them --
    only the Recipe (and so the ``make``/Craft route to it) is missing, and
    ``game.recipes`` stays empty. A YAML flag was considered and rejected: the
    Penn world loader (``load_world_data``) silently drops unknown keys, so a
    flag added to a world YAML would need the loader taught to read it too --
    an explicit builder parameter is the direct, unambiguous wiring. Every
    other call site (the bake, the live server, #595's experiment) passes the
    default ``False`` and is unaffected.

    ``cast`` (#731) overrides the world YAML's ``cast:`` persona-reference
    list -- build the same world with a sub-cast (or with parked personas
    un-parked) without editing YAML. ``None`` (every existing call site)
    means the YAML's own cast; worlds with inline ``personas:`` (the boil
    demo) ignore it.
    """
    # One composed read (#731): personas/relationships/meetings resolved from
    # the cast (or passed through verbatim for inline-personas worlds), then
    # the same file normalized into the (personas, locations) build pair.
    data = load_world_yaml(world_data, cast)
    personas, locations = load_world_data(world_data, cast)
    meetings = data.get("meetings") or []

    world_map = _pin_building_meeting_points(WorldMap(upenn_dir))
    # Route each meeting's participants to a tight rendezvous cluster inside its
    # venue, so they settle close enough to converse (the centre routing alone can
    # leave them just out of perception range -- see _rendezvous_clusters).
    addr_of = {loc["name"]: loc.get("address") for loc in locations}
    venue_addrs = {
        addr_of[m["at"]]
        for m in meetings
        if m.get("at") in addr_of and addr_of[m["at"]]
    }
    world_map = _pin_meeting_rendezvous(
        world_map, _rendezvous_clusters(world_map, venue_addrs)
    )

    def _build(wm):
        game, characters = build_world(
            wm, personas, locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        _furnish_meals(game)
        _furnish_van_pelt(game)
        if not withhold_boil:
            game.add_recipe(_boil_recipe())  # boiling = Craft over this Recipe (#300)
        return _gate_conversations_by_perception((game, characters))

    return PennWorld(
        world_map=world_map,
        personas=personas,
        locations=locations,
        meetings=meetings,
        build_world_fn=_build,
        llm=data.get("llm") or None,
        # Validated once here, so an authoring typo fails the bake / the live
        # server's boot loudly instead of drawing a wrong graph.
        relationships=relationships_meta(personas, data.get("relationships") or []),
    )


def relationships_meta(personas, relationships):
    """The world YAML's ``relationships`` block -> the ``meta.relationships`` list.

    A sibling of :func:`persona_meta_entry`: the single projection the bake
    (``generate_penn_replay``) and the live server (``serve_penn.meta``) share,
    so the viewer's social-graph pop-up (#252) sees the same seed edges whether
    it's watching a baked file or a live run.

    Validates against the *active* cast and normalizes for determinism: names
    are sorted within each edge, edges are sorted by ``(a, b)``, and the output
    carries exactly ``{a, b, kind, closeness, description}``. Raises
    ``ValueError`` on an unknown name (cast composition already drops edges
    that leave the cast, #731, so a raise here means an inline-authored world
    names someone who doesn't exist), a self-edge, a duplicate pair, or a
    ``closeness`` outside 1..5 -- authoring mistakes should fail the build,
    not render a misleading graph.
    """
    cast = {p["name"] for p in personas}
    edges = []
    seen_pairs = set()
    for rel in relationships:
        a, b = str(rel.get("a", "")), str(rel.get("b", ""))
        for name in (a, b):
            if name not in cast:
                raise ValueError(
                    f"relationships: {name!r} is not an active persona "
                    f"(cast: {sorted(cast)})"
                )
        if a == b:
            raise ValueError(f"relationships: self-edge on {a!r}")
        pair = tuple(sorted((a, b)))
        if pair in seen_pairs:
            raise ValueError(
                f"relationships: duplicate edge {pair[0]!r} -- {pair[1]!r}"
            )
        seen_pairs.add(pair)
        closeness = int(rel.get("closeness", 1))
        if not 1 <= closeness <= 5:
            raise ValueError(
                f"relationships: closeness {closeness} for {pair[0]!r} -- {pair[1]!r} "
                "must be 1..5"
            )
        edges.append(
            {
                "a": pair[0],
                "b": pair[1],
                "kind": str(rel.get("kind", "")),
                "closeness": closeness,
                "description": str(rel.get("description", "")),
            }
        )
    return sorted(edges, key=lambda e: (e["a"], e["b"]))


def persona_meta_entry(spec):
    """One persona's static detail for the replay/live ``meta.personas`` block.

    The sibling of :func:`replay_frame_entry` -- the single projection the bake
    (``generate_penn_replay``) and the live server (``serve_penn.meta``) share, so
    the persona-inspector "State Details" modal (viewer.gd, issue #408) gets the
    same identity + schedule whether it's watching a baked file or a live run.

    ``name``/``emoji`` drive the sprite + sidebar (they always existed here);
    ``persona``/``home``/``schedule`` are the extra fields the inspector reads.
    Everything is pulled from the *normalized* persona spec (see
    ``build_world._normalize_personas``), so ``schedule`` is always a list of
    ``{place, activity, emoji, steps}`` stops (``steps=None`` => stays put for the
    rest of the day). ``vision_r`` is deliberately NOT here: Penn personas don't
    override it, so it stays a single top-level ``meta`` global.
    """
    return {
        "name": spec["name"],
        "emoji": spec["emoji"],
        "persona": spec.get("persona", ""),
        "home": spec.get("home", ""),
        "schedule": [
            {
                "place": s["place"],
                "activity": s["activity"],
                "emoji": s.get("emoji", spec["emoji"]),
                "steps": s.get("steps"),
            }
            for s in spec.get("schedule", [])
        ],
    }


def replay_frame_entry(raw):
    """One persona's raw ``simulate()``/``step()`` frame -> the replay schema.

    The one mapping the bake, the live server, and the equivalence tests share,
    so the wire contract can't drift between them. KEY ORDER IS PINNED --
    x, y, act, e, reasoning, chat, memories, trace -- because the bake's
    ``json.dump`` serializes insertion order and #297's acceptance is a
    byte-identical replay file.

    The Godot canvas reads only x/y/act/e; reasoning/chat/memories/trace are
    the agent-card cognition extras (issue #163). The mock leaves reasoning a
    stub and chat None; a real-LLM run fills them in. `memories` is the small
    set retrieval surfaced for *this* decision (the card's "Memories
    retrieved" shorthand) -- a subset of the run's full memory stream; it
    populates even under the mock since retrieval still runs (the mock only
    ignores it when deciding). `trace` is the per-decision cognition trace
    (issue #359, Task 5) -- the brain's consults plus the terminal action,
    as compact digests; [] when this frame carried no decision."""
    return {
        "x": int(raw["movement"][0]),
        "y": int(raw["movement"][1]),
        "act": raw["description"],
        "e": raw["pronunciatio"],
        "reasoning": raw.get("reasoning"),
        "chat": raw.get("chat"),
        "memories": raw.get("memories"),
        "trace": raw.get("trace") or [],
    }
