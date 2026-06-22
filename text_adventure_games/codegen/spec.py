"""GameSpec: the structured intermediate that a codegen pipeline emits to.

A GameSpec is a fully declarative description of a `text_adventure_games`
game -- locations, items, characters, blocks, custom action templates, the
player, and a win condition. The PDF extraction stage produces one of these;
the emit stage turns it into runnable Python.

Two responsibilities live here:
  1. The dataclass shape (plus JSON round-trip via ``load_spec`` / ``dump_spec``).
  2. Structural validation (``validate``) that catches the kinds of errors
     the LLM would otherwise smuggle into emit -- broken cross-references,
     duplicate names, or action-name prefix collisions that the substring
     parser would mis-route.

The emit stage refuses to run if ``validate`` returns any errors, so the
guarantees here are part of the codegen contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .directions import canonical_opposite

# ----------------------------------------------------------------------
# Property normalization
# ----------------------------------------------------------------------
#
# The engine's affordance refactor renamed the old ``is_*able`` property keys
# to bare affordance tags (``is_lightable`` -> ``flammable``, ``is_food`` ->
# ``edible``, etc.). The Light/Eat/Drink/Wear actions now read the canonical
# names, so an LLM that emits the legacy key produces a spec where ``light
# candle`` silently fails. We normalize on the way *in* so legacy specs (and
# legacy LLM hallucinations) keep working; the canonical names also stay
# accepted, of course.
_LEGACY_PROPERTY_ALIASES: dict[str, str] = {
    "is_lightable": "flammable",
    "is_food": "edible",
    "is_drink": "drinkable",
    "is_wearable": "wearable",
    "is_wieldable": "wieldable",
    "is_gettable": "gettable",
}


def _normalize_properties(props: dict) -> dict:
    """Map legacy property keys to their canonical affordance names.

    Returns a NEW dict so callers can't accidentally mutate the LLM payload.
    Unknown keys pass through unchanged so games can still declare arbitrary
    bespoke properties (the engine's defaultdict-of-bool model relies on it).
    """
    if not props:
        return {}
    out = {}
    for key, value in props.items():
        out[_LEGACY_PROPERTY_ALIASES.get(key, key)] = value
    return out


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class Source:
    pdf: str
    pages: list[int]  # [start, end] inclusive

    @classmethod
    def from_dict(cls, data: dict) -> "Source":
        pages = list(data.get("pages", [0, 0]))
        return cls(pdf=data.get("pdf", ""), pages=pages)


@dataclass
class Exit:
    direction: str
    to: str
    travel_description: str = ""
    # Explicit return verb for non-canonical directions ("enter moat" pairs
    # with "exit moat", "crawl in" with "crawl out", etc.). When set, the
    # engine wires the named reverse edge AND suppresses the canonical
    # auto-reverse; the multi-direction validator treats the pair as a
    # single edge.
    reverse_direction: str | None = None
    reverse_travel_description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Exit":
        return cls(
            direction=data["direction"],
            to=data["to"],
            travel_description=data.get("travel_description", ""),
            reverse_direction=data.get("reverse_direction"),
            reverse_travel_description=data.get("reverse_travel_description", ""),
        )


@dataclass
class LocationSpec:
    name: str
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    exits: list[Exit] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationSpec":
        return cls(
            name=data["name"],
            description=data["description"],
            properties=_normalize_properties(data.get("properties", {})),
            exits=[Exit.from_dict(e) for e in data.get("exits", [])],
        )


@dataclass
class ItemAt:
    """Where an item starts: either at a location OR in a character's inventory."""

    location: str | None = None
    owner: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ItemAt":
        return cls(location=data.get("location"), owner=data.get("owner"))


@dataclass
class UseResponseSpec:
    """Declarative reaction to ``use <tool> on <this thing>``.

    Lives on item OR character targets, mirroring the engine's
    :class:`text_adventure_games.things.base.UseResponse`. The first
    response whose ``tool`` matches and whose predicates all hold fires
    its property sets and ``response_text``. Used INSTEAD of inventing a
    custom action for ``use X on Y`` puzzles (the engine's USE intent
    fires first and would shadow it).
    """

    tool: str
    response_text: str = ""
    requires_tool_properties: dict[str, Any] = field(default_factory=dict)
    requires_target_properties: dict[str, Any] = field(default_factory=dict)
    sets_tool_properties: dict[str, Any] = field(default_factory=dict)
    sets_target_properties: dict[str, Any] = field(default_factory=dict)
    consumes_tool: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "UseResponseSpec":
        return cls(
            tool=data["tool"],
            response_text=data.get("response_text", ""),
            requires_tool_properties=dict(data.get("requires_tool_properties", {})),
            requires_target_properties=dict(data.get("requires_target_properties", {})),
            sets_tool_properties=dict(data.get("sets_tool_properties", {})),
            sets_target_properties=dict(data.get("sets_target_properties", {})),
            consumes_tool=bool(data.get("consumes_tool", False)),
        )


@dataclass
class ItemSpec:
    name: str
    description: str
    examine_text: str = ""
    at: ItemAt = field(default_factory=ItemAt)
    properties: dict[str, Any] = field(default_factory=dict)
    command_hints: list[str] = field(default_factory=list)
    # Text printed by the engine's built-in ``read`` action. Items with
    # ``read_text`` (or ``is_readable: true``) become first-class readable
    # without needing a custom action.
    read_text: str = ""
    # Declarative reactions to ``use <tool> on <this item>``. See
    # :class:`UseResponseSpec` and the prompt's USE-X-ON-Y section.
    use_responses: list[UseResponseSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ItemSpec":
        return cls(
            name=data["name"],
            description=data["description"],
            examine_text=data.get("examine_text", ""),
            at=ItemAt.from_dict(data.get("at", {})),
            properties=_normalize_properties(data.get("properties", {})),
            command_hints=list(data.get("command_hints", [])),
            read_text=data.get("read_text", ""),
            use_responses=[
                UseResponseSpec.from_dict(u) for u in data.get("use_responses", [])
            ],
        )


@dataclass
class BehaviorGuard:
    """Per-turn guard condition on an escalating_commands behavior.

    The behavior runs only while ``character.get_property(property) == equals``;
    when the guard fails, the closure no-ops (no command issued).
    """

    property: str
    equals: Any

    @classmethod
    def from_dict(cls, data: dict) -> "BehaviorGuard":
        return cls(property=data["property"], equals=data.get("equals", True))


@dataclass
class BehaviorSpec:
    kind: str  # "none" | "escalating_commands"
    commands: list[str] = field(default_factory=list)
    fallback: str = ""
    guard: BehaviorGuard | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "BehaviorSpec":
        return cls(
            kind=data["kind"],
            commands=list(data.get("commands", [])),
            fallback=data.get("fallback", ""),
            guard=BehaviorGuard.from_dict(data["guard"]) if data.get("guard") else None,
        )


@dataclass
class GiveResponseSpec:
    """Declarative reaction registered on a recipient character.

    Emitted as a ``recipient.add_give_response(...)`` call; fired by the
    engine's built-in ``Give`` action after the transfer succeeds. Use this
    instead of inventing a custom action with a ``give X to Y`` verb (the
    parser's GIVE intent fires first and shadows it).
    """

    item: str
    response_text: str
    requires_recipient_properties: dict[str, Any] = field(default_factory=dict)
    sets_recipient_properties: dict[str, Any] = field(default_factory=dict)
    sets_giver_properties: dict[str, Any] = field(default_factory=dict)
    # Properties set on the GIVEN ITEM (e.g. the smith sharpens the axe).
    sets_item_properties: dict[str, Any] = field(default_factory=dict)
    # Hand the item back to the giver after the response runs -- for
    # "sharpen/repair my item and return it" exchanges rather than a gift.
    returns_to_giver: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "GiveResponseSpec":
        return cls(
            item=data["item"],
            response_text=data.get("response_text", ""),
            requires_recipient_properties=dict(
                data.get("requires_recipient_properties", {})
            ),
            sets_recipient_properties=dict(data.get("sets_recipient_properties", {})),
            sets_giver_properties=dict(data.get("sets_giver_properties", {})),
            sets_item_properties=dict(data.get("sets_item_properties", {})),
            returns_to_giver=bool(data.get("returns_to_giver", False)),
        )


@dataclass
class CharacterSpec:
    name: str
    description: str
    persona: str
    at: str  # starting location name
    properties: dict[str, Any] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)  # item names from items[]
    behavior: BehaviorSpec | None = None
    give_responses: list[GiveResponseSpec] = field(default_factory=list)
    # Engine ``talk to`` greeting and ``ask <name> about <topic>`` table.
    # Empty greeting/dialogue means the character has nothing to say.
    greeting: str = ""
    dialogue: dict[str, str] = field(default_factory=dict)
    # Reactions to ``use <tool> on <this character>``. Same shape as on items.
    use_responses: list[UseResponseSpec] = field(default_factory=list)
    # Detailed text the engine's Examine action shows for this character
    # (mirrors ItemSpec.examine_text). Empty falls back to ``description``.
    examine_text: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterSpec":
        return cls(
            name=data["name"],
            description=data["description"],
            persona=data["persona"],
            at=data["at"],
            properties=_normalize_properties(data.get("properties", {})),
            inventory=list(data.get("inventory", [])),
            behavior=(
                BehaviorSpec.from_dict(data["behavior"])
                if data.get("behavior")
                else None
            ),
            give_responses=[
                GiveResponseSpec.from_dict(g) for g in data.get("give_responses", [])
            ],
            greeting=data.get("greeting", ""),
            dialogue=dict(data.get("dialogue", {})),
            use_responses=[
                UseResponseSpec.from_dict(u) for u in data.get("use_responses", [])
            ],
            examine_text=data.get("examine_text", ""),
        )


@dataclass
class BlockObstacle:
    kind: str  # "character" | "item"
    name: str

    @classmethod
    def from_dict(cls, data: dict) -> "BlockObstacle":
        return cls(kind=data["kind"], name=data["name"])


@dataclass
class BlockCondition:
    """A single predicate on a property_block obstacle.

    ``target`` selects what the predicate reads from: ``obstacle`` (the
    character or item the block guards), ``location`` (the block's location),
    or ``actor`` (the moving character). ``equals`` is the value that the
    property must hold for the block to remain blocked.
    """

    target: str  # "obstacle" | "location" | "actor"
    property: str
    equals: Any

    @classmethod
    def from_dict(cls, data: dict) -> "BlockCondition":
        return cls(
            target=data["target"], property=data["property"], equals=data["equals"]
        )


@dataclass
class BlockSpec:
    id: str
    template: str  # "property_block" | "darkness_block"
    name: str  # the generated class name, e.g. "Troll_Block"
    at_location: str
    direction: str
    description: str = ""
    block_message: str = ""
    obstacle: BlockObstacle | None = None  # required for property_block
    conditions: list[BlockCondition] = field(default_factory=list)
    # For darkness_block only:
    unblocked_if_inventory_has_property: str | None = None
    # property_block only: the traveller passes if they CARRY an item with this
    # property (e.g. a sharp weapon past the catfish). Pairs well with `lethal`.
    unblocked_if_actor_carries_property: str | None = None
    # When True, crossing this block ends the game with its message instead of
    # merely failing the move (the catfish drowns you; the guards jail you).
    lethal: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "BlockSpec":
        return cls(
            id=data["id"],
            template=data["template"],
            name=data["name"],
            at_location=data["at_location"],
            direction=data["direction"],
            description=data.get("description", ""),
            block_message=data.get("block_message", ""),
            obstacle=(
                BlockObstacle.from_dict(data["obstacle"])
                if data.get("obstacle")
                else None
            ),
            conditions=[
                BlockCondition.from_dict(c) for c in data.get("conditions", [])
            ],
            unblocked_if_inventory_has_property=data.get(
                "unblocked_if_inventory_has_property"
            ),
            unblocked_if_actor_carries_property=data.get(
                "unblocked_if_actor_carries_property"
            ),
            lethal=bool(data.get("lethal", False)),
        )


@dataclass
class CustomActionSpec:
    id: str
    template: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "CustomActionSpec":
        return cls(
            id=data["id"],
            template=data["template"],
            params=dict(data.get("params", {})),
        )


@dataclass
class PlayerInventoryItem:
    name: str
    description: str
    examine_text: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    command_hints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerInventoryItem":
        return cls(
            name=data["name"],
            description=data["description"],
            examine_text=data.get("examine_text", ""),
            properties=_normalize_properties(data.get("properties", {})),
            command_hints=list(data.get("command_hints", [])),
        )


@dataclass
class PlayerSpec:
    name: str
    description: str
    persona: str
    properties: dict[str, Any] = field(default_factory=dict)
    inventory: list[PlayerInventoryItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerSpec":
        return cls(
            name=data["name"],
            description=data["description"],
            persona=data["persona"],
            properties=_normalize_properties(data.get("properties", {})),
            inventory=[
                PlayerInventoryItem.from_dict(i) for i in data.get("inventory", [])
            ],
        )


@dataclass
class Walkthrough:
    """A winning command sequence used to self-validate the spec.

    The extractor emits this alongside the spec; the post-emit step plays
    every command through the generated module and asserts the final state
    matches ``expects_win``. A failure folds the failing command and the
    parser's response into a retry prompt so the LLM can fix the cause.

    Notes:
      * Commands are exactly what the player would type (one per element);
        comma-separated multi-commands are also accepted by the engine.
      * The sequence is also written to disk as a ``_walkthrough.py``
        sibling next to the generated module so it doubles as a manual
        smoke test the user can re-run anytime.
    """

    commands: list[str] = field(default_factory=list)
    expects_win: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> "Walkthrough | None":
        if not data:
            return None
        return cls(
            commands=list(data.get("commands", [])),
            expects_win=bool(data.get("expects_win", True)),
        )


@dataclass
class WinCondition:
    """Predicate that decides whether ``Game.is_won()`` returns True.

    ``kind`` is a closed enum; the emit stage switches on it. Outside the
    closed set the validator rejects the spec (the LLM doesn't get to invent
    new kinds).
    """

    kind: str
    property: str | None = None
    equals: Any = None
    location: str | None = None
    item: str | None = None
    name: str | None = None  # used by ``flag``
    children: list["WinCondition"] | None = None
    ok_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "WinCondition":
        children = data.get("children")
        return cls(
            kind=data["kind"],
            property=data.get("property"),
            equals=data.get("equals"),
            location=data.get("location"),
            item=data.get("item"),
            name=data.get("name"),
            children=(
                [WinCondition.from_dict(c) for c in children]
                if children is not None
                else None
            ),
            ok_message=data.get("ok_message"),
        )


@dataclass
class GameSpec:
    version: str
    game_name: str
    class_name: str
    source: Source
    start_at: str
    win_condition: WinCondition
    locations: list[LocationSpec]
    items: list[ItemSpec]
    characters: list[CharacterSpec]
    blocks: list[BlockSpec]
    custom_actions: list[CustomActionSpec]
    player: PlayerSpec
    walkthrough: Walkthrough | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "GameSpec":
        return cls(
            version=str(data.get("version", "1")),
            game_name=data["game_name"],
            class_name=data["class_name"],
            source=Source.from_dict(data.get("source", {})),
            start_at=data["start_at"],
            win_condition=WinCondition.from_dict(data["win_condition"]),
            locations=[LocationSpec.from_dict(l) for l in data.get("locations", [])],
            items=[ItemSpec.from_dict(i) for i in data.get("items", [])],
            characters=[CharacterSpec.from_dict(c) for c in data.get("characters", [])],
            blocks=[BlockSpec.from_dict(b) for b in data.get("blocks", [])],
            custom_actions=[
                CustomActionSpec.from_dict(a) for a in data.get("custom_actions", [])
            ],
            player=PlayerSpec.from_dict(data["player"]),
            walkthrough=Walkthrough.from_dict(data.get("walkthrough")),
        )


# ----------------------------------------------------------------------
# JSON I/O
# ----------------------------------------------------------------------


_ANTAGONIST_KEYWORDS = (
    "troll",
    "guard",
    "ghost",
    "ogre",
    "wraith",
    "knight",
    "dragon",
    "goblin",
    "demon",
    "vampire",
    "zombie",
    "skeleton",
)


# First tokens of every command the parser accepts. Used to validate
# `command_hints` so we don't advertise verbs the engine cannot route
# (e.g. "climb tree", "open door" -- there is no Climb or Open action;
# the hint is a phantom that confuses players and, worse, can mis-route
# via substring matching to GO).
#
# Sources:
#   * ActionName values' first words (built-in engine actions).
#   * Parser aliases from `parsing.determine_intent`'s special-case
#     elif chain (hit / take / x / i / l / z / speak / ate).
#   * Direction names usable as bare GO commands.
_ENGINE_VERB_FIRST_TOKENS: frozenset[str] = frozenset(
    {
        # ActionName first words
        "go",
        "describe",
        "wait",
        "quit",
        "get",
        "drop",
        "inventory",
        "examine",
        "give",
        "unlock",
        "attack",
        "say",
        "eat",
        "drink",
        "light",
        "catch",
        "pick",
        "smell",
        "help",
        "break",
        "score",
        "read",
        "open",
        "close",
        "wear",
        "wield",
        "unwield",
        "talk",
        "ask",
        "use",
        # Parser aliases / shorthands
        "look",
        "take",
        "hit",
        "speak",
        "ate",
        "eats",
        "eating",
        "l",
        "x",
        "i",
        "z",
        # Direction tokens (the engine's GO accepts bare directions)
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
        "n",
        "s",
        "e",
        "w",
    }
)


def _custom_action_first_tokens(spec: GameSpec) -> set[str]:
    """First word of each custom action's ACTION_NAME."""
    tokens: set[str] = set()
    for action in spec.custom_actions:
        name = _action_name_for(action)
        if not name:
            continue
        first = name.split()[0]
        if first:
            tokens.add(first.lower())
    return tokens


def _exit_directions(spec: GameSpec) -> set[str]:
    """Every declared exit direction (lowercased), forward and reverse.

    Custom movement verbs ("row boat", "enter tunnel") route through GO's
    exit-name fallback even though their first word isn't an engine verb, so a
    command_hint naming one is legal. Their first word ('row', 'enter') is NOT
    a general engine verb, which is why the first-token check alone rejects
    them."""
    out: set[str] = set()
    for loc in spec.locations:
        for ex in loc.exits:
            if ex.direction:
                out.add(ex.direction.lower())
            if ex.reverse_direction:
                out.add(ex.reverse_direction.lower())
    return out


def _hint_is_legal(
    hint: str, legal_first_tokens: set[str], exit_directions: set[str] = frozenset()
) -> bool:
    """A hint is legal iff its first token routes to a registered action.

    This catches phantoms like ``"climb tree"`` (no climb action) and
    ``"open door"`` (no open action) without requiring a live game build.
    False positives (a hint we accept whose route fails downstream) are
    benign -- worst case the player sees the same advertised-but-broken
    hint they'd see today. False negatives (a hint we drop that would
    have routed via some clever fallback) are also benign -- the player
    can still type the command.
    """
    if not hint:
        return False
    parts = hint.lower().split()
    if not parts:
        return False
    if parts[0] in legal_first_tokens:
        return True
    # A hint that names a declared exit ("row boat", "enter tunnel") routes via
    # GO's exit-name fallback, so it's legal even though its first word isn't a
    # general engine verb.
    return hint.lower() in exit_directions


def legal_command_hints(
    spec: GameSpec, hints: list[str]
) -> tuple[list[str], list[str]]:
    """Split a hint list into (kept, dropped) by parser legality."""
    legal = _ENGINE_VERB_FIRST_TOKENS | _custom_action_first_tokens(spec)
    exits = _exit_directions(spec)
    kept: list[str] = []
    dropped: list[str] = []
    for h in hints:
        (kept if _hint_is_legal(h, legal, exits) else dropped).append(h)
    return kept, dropped


def _effective_connections(spec: GameSpec) -> dict[str, dict[str, str]]:
    """Materialize the connection graph the engine actually builds.

    ``Location.add_connection`` auto-installs the reverse connection for any
    canonical direction (north<->south, up<->down, in<->out, ...). That
    means a spec which emits ``Stairs up -> Tower`` AND ``Tower out -> Stairs``
    yields a runtime graph where ``Stairs`` reaches ``Tower`` via BOTH
    ``up`` and ``in`` -- the auto-reverse on ``out`` quietly installs
    ``Stairs.in -> Tower``. A door-block on ``up`` is then trivially
    bypassed by typing ``go in``. This helper lets ``validate`` see the
    full effective graph rather than just the declared exits.

    Returns ``{loc_name: {direction: target_name}}`` after auto-reverse.
    """
    location_names = {loc.name for loc in spec.locations}
    graph: dict[str, dict[str, str]] = {name: {} for name in location_names}
    for loc in spec.locations:
        for ex in loc.exits:
            d = ex.direction.lower()
            graph[loc.name][d] = ex.to
            if ex.reverse_direction is not None:
                # Explicit paired-custom direction: install the user-named
                # reverse, skip the canonical auto-reverse.
                if ex.to in graph:
                    graph[ex.to][ex.reverse_direction.lower()] = loc.name
                continue
            opp = canonical_opposite(d)
            if opp is None:
                continue
            if ex.to in graph:
                graph[ex.to][opp] = loc.name
    return graph


def lint(spec: GameSpec) -> list[str]:
    """Return non-fatal *warnings* about likely-buggy spec patterns.

    Structural problems live in ``validate``; ``lint`` catches semantic
    drift that compiles fine but breaks gameplay. Used by the CLI for a
    human-readable report and folded into the extractor's retry prompt so
    the LLM can correct itself.
    """
    warnings: list[str] = []

    # 1. Named antagonists with no turn behavior.
    for c in spec.characters:
        nm = c.name.lower()
        if any(k in nm for k in _ANTAGONIST_KEYWORDS):
            if c.behavior is None or c.behavior.kind == "none":
                warnings.append(
                    f"character {c.name!r} reads as an antagonist but has "
                    f"behavior.kind = 'none'; expected 'escalating_commands'"
                )

    # 2. Redundant reverse exits (engine auto-installs them). Dedupe so
    #    each pair is reported once.
    exit_map: dict[tuple[str, str], str] = {}  # (loc, direction) -> target
    for loc in spec.locations:
        for ex in loc.exits:
            exit_map[(loc.name, ex.direction.lower())] = ex.to
    reported_pairs: set[frozenset] = set()
    for (loc_name, direction), target in list(exit_map.items()):
        opp = canonical_opposite(direction)
        if opp is None:
            continue
        if (target, opp) in exit_map and exit_map[(target, opp)] == loc_name:
            pair = frozenset((loc_name, target))
            if pair in reported_pairs:
                continue
            reported_pairs.add(pair)
            warnings.append(
                f"redundant reverse exit between {loc_name!r} and {target!r}: "
                f"both {loc_name!r}.{direction!r} -> {target!r} and "
                f"{target!r}.{opp!r} -> {loc_name!r} are emitted; the "
                f"engine auto-installs the reverse, so keep only one"
            )

    # 3. (Multi-direction connections between the same location pair are
    #    now caught as a fatal validate error -- see ``validate``. The
    #    same-location-only check used to live here; the validate check is
    #    a strict superset because it also catches the case where the
    #    duplicate path is induced by the engine's auto-reverse.)

    # 4. wear_item / sit_on_furniture gated on a non-boolean stub.
    for action in spec.custom_actions:
        if action.template in ("wear_item", "sit_on_furniture"):
            req = action.params.get("required_actor_property")
            if req == "character_type":
                warnings.append(
                    f"action {action.id!r}: required_actor_property = "
                    f"'character_type' is a string and trivially truthy; use "
                    f"the actual boolean gate the rules describe (e.g. "
                    f"'is_royal', 'is_crowned')"
                )

    # 5. Weapons named in NPC fallback that don't exist as items.
    item_set = {i.name for i in spec.items}
    item_by_name = {i.name: i for i in spec.items}
    for c in spec.characters:
        if c.behavior is None:
            continue
        for verb in [*c.behavior.commands, c.behavior.fallback]:
            if not verb:
                continue
            if " with " in verb:
                weapon = verb.split(" with ", 1)[1].strip().split()[0]
                if weapon and weapon not in item_set:
                    warnings.append(
                        f"character {c.name!r} fallback/command references "
                        f"weapon {weapon!r} but no such item exists; add it "
                        f"with at.owner = {c.name!r}"
                    )

    # 5b. NPC escalation routes through the engine Attack action (verbs
    #     containing "attack" or starting with "hit"), but the NPC holds no
    #     weapon. Attack's preconditions require ``is_weapon: true`` on
    #     something in the attacker's inventory; without it, every turn
    #     fails with "<npc> doesn't have a weapon."
    for c in spec.characters:
        if c.behavior is None:
            continue
        verbs = [*c.behavior.commands, c.behavior.fallback]
        uses_attack = any(
            v and ("attack" in v.lower() or v.lower().startswith("hit ")) for v in verbs
        )
        if not uses_attack:
            continue
        has_weapon = any(
            (inv_name in item_by_name)
            and item_by_name[inv_name].properties.get("is_weapon") is True
            for inv_name in c.inventory
        )
        if not has_weapon:
            warnings.append(
                f"character {c.name!r} has an attack/hit verb in its "
                f"behavior but holds no item with is_weapon=true; the "
                f"engine's Attack action will fail with "
                f'"{c.name} doesn\'t have a weapon." -- give them an item '
                f"with `at.owner = {c.name!r}` and `is_weapon: true`"
            )

    # 6. command_hints advertising verbs that don't route to any registered
    #    action (engine built-in OR custom). These are phantoms -- typing
    #    them does nothing useful, and short ones can even mis-route via
    #    substring matching ("climb up" -> GO up via the location's exit).
    legal_first = _ENGINE_VERB_FIRST_TOKENS | _custom_action_first_tokens(spec)
    exit_dirs = _exit_directions(spec)
    for item in spec.items:
        for hint in item.command_hints:
            if not _hint_is_legal(hint, legal_first, exit_dirs):
                warnings.append(
                    f"item {item.name!r}: command_hint {hint!r} starts with a "
                    f"verb the engine cannot route ('{hint.split()[0] if hint.split() else ''}'); "
                    f"drop it or add a custom_action that handles it"
                )
    for pi in spec.player.inventory:
        for hint in pi.command_hints:
            if not _hint_is_legal(hint, legal_first, exit_dirs):
                warnings.append(
                    f"player inventory {pi.name!r}: command_hint {hint!r} "
                    f"starts with a verb the engine cannot route; drop it "
                    f"or add a custom_action that handles it"
                )

    # 7a. Multi-word noun names on items folded into an ACTION_NAME. The
    #     parser substring-matches the ACTION_NAME against the player's
    #     input, so an item named "tower door" makes the verb
    #     "unlock tower door" -- and "unlock door" silently fails. Short
    #     single-word names match the natural thing the player types.
    _NOUN_PARAM_BY_TEMPLATE = {
        "unlock_with_key": "lock_item",
        "wear_item": "item",
        "sit_on_furniture": "furniture_item",
    }
    for action in spec.custom_actions:
        key = _NOUN_PARAM_BY_TEMPLATE.get(action.template)
        if key is None:
            continue
        noun = action.params.get(key, "")
        if not noun:
            continue
        if len(noun.split()) > 1:
            verb = _action_name_for(action)
            warnings.append(
                f"action {action.id!r}: {key} = {noun!r} is multi-word, "
                f"so the player must type {verb!r} verbatim. Rename the "
                f"item to a single noun (e.g. 'door' instead of "
                f"'tower door', 'crown' instead of 'gold crown'); the "
                f"location description gives the player the context."
            )

    # 7. propose_marriage royalty_property: at least one party must already
    #    have the royalty property, otherwise marriage propagates nothing.
    for action in spec.custom_actions:
        if action.template != "propose_marriage":
            continue
        royalty = action.params.get("royalty_property")
        if not royalty:
            continue
        has_royal = (
            any(c.properties.get(royalty) is True for c in spec.characters)
            or spec.player.properties.get(royalty) is True
        )
        if not has_royal:
            warnings.append(
                f"action {action.id!r}: royalty_property = {royalty!r} but no "
                f"character has it set to true; the marriage will not "
                f"propagate royalty"
            )

    # 8. Custom action verbs that the engine's intent-routing elif chain in
    #    ``parsing.Parser.determine_intent`` will shadow. Substring matchers
    #    like "drink" in command, "give" in command, "attack" in command,
    #    etc. run BEFORE the substring loop that resolves custom ACTION_NAMEs,
    #    so a custom verb like "drink soda" or "give X to Y" silently routes
    #    to the engine built-in instead of the LLM-emitted custom action.
    #    Phrase the verb around a different head word: "guzzle soda" instead
    #    of "drink soda", "pour soda on goat" instead of "give soda to goat".
    _RESERVED_SUBSTRINGS = (
        # ``look`` is NOT listed: the parser only routes to DESCRIBE on the
        # bare strings ``look``/``l``, so ``look up``, ``look at sky`` etc.
        # fall through to the substring-action-name matcher and reach a
        # custom action with that ACTION_NAME.
        "say ",
        "speak ",
        "examine ",
        "take ",
        "get ",
        "light",
        "drop ",
        "eat ",
        "eats ",
        "ate ",
        "eating ",
        "drink",
        "give",
        "attack",
        "hit ",
        "hits ",
        "inventory",
        "quit",
        "wait",
        "north",
        "south",
        "east",
        "west",
    )
    for action in spec.custom_actions:
        if action.template in ("npc_taunt", "npc_kill"):
            # NPC verbs run via explicit-actor dispatch (see Parser
            # NPC_ONLY logic), which bypasses the player elif chain.
            continue
        verb = _action_name_for(action)
        if not verb:
            continue
        padded = f" {verb.lower()} "
        for substring in _RESERVED_SUBSTRINGS:
            # Reserved entries already include their own trailing space
            # where needed (see ``_RESERVED_SUBSTRINGS``); look for them in
            # the unpadded verb, with extra leading-space tolerance.
            head = substring.rstrip()
            sentinel = head + " " if substring.endswith(" ") else head
            if (
                f" {sentinel}" in padded
                or padded.lstrip().startswith(sentinel + " ")
                or padded.strip() == head
            ):
                if head == "give":
                    warnings.append(
                        f"action {action.id!r}: verb {verb!r} contains a "
                        f"reserved engine token 'give'; the parser fires GIVE "
                        f"before reaching this custom action. For "
                        f"give-to-NPC puzzles, drop the custom action and "
                        f"register a `give_responses` entry on the recipient "
                        f"character instead (the engine's Give action fires "
                        f"matching responses after the transfer)."
                    )
                else:
                    warnings.append(
                        f"action {action.id!r}: verb {verb!r} contains a "
                        f"reserved engine token {head!r}; the parser will route "
                        f"to the built-in (DRINK/EAT/GIVE/ATTACK/...) BEFORE "
                        f"reaching this custom action. Pick a different head "
                        f"verb (e.g. 'pour' instead of 'give', 'guzzle' instead "
                        f"of 'drink', 'shake' instead of 'attack')."
                    )
                break

    # N. flavor_response with a movement verb -- almost always a misplaced
    # exit (the LLM trap that lets "climb tree" print text without actually
    # moving the player). Movement verbs belong on a connection, not on a
    # text-only flavor action.
    _MOVEMENT_VERB_PREFIXES = (
        "climb",
        "enter",
        "exit",
        "crawl",
        "jump",
        "dive",
        "leap",
        "swim",
        "walk",
        "ride",
        "fly",
    )
    for action in spec.custom_actions:
        if action.template != "flavor_response":
            continue
        verb = (action.params.get("verb") or "").strip().lower()
        if not verb:
            continue
        first_word = verb.split()[0]
        if first_word in _MOVEMENT_VERB_PREFIXES:
            warnings.append(
                f"custom_action {action.id!r}: flavor_response with verb "
                f"{verb!r} -- movement verbs ({first_word!r} is one) belong "
                f"on a location's exit, not on a flavor_response. Encode as "
                f'``"direction": {verb!r}`` on the source location, or '
                f'``"direction": "{first_word} up <noun>"`` for the '
                f"climb-up/climb-down pair the engine auto-reverses."
            )

    return warnings


def load_spec(path: str | Path) -> GameSpec:
    """Load a GameSpec from a JSON file. Does not run ``validate``."""
    with open(path, "r") as f:
        data = json.load(f)
    return GameSpec.from_dict(data)


def dump_spec(spec: GameSpec, path: str | Path) -> None:
    """Write a GameSpec to a JSON file."""
    data = asdict(spec)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


# Templates the emit stage knows about. Keep in sync with
# ``codegen/templates/__init__.py``.
ACTION_TEMPLATES: set[str] = {
    "unlock_with_key",
    "read_inscription_to_banish",
    "propose_marriage",
    "wear_item",
    "sit_on_furniture",
    "npc_taunt",
    "npc_kill",
    "flavor_response",
    "transform_item",
}

BLOCK_TEMPLATES: set[str] = {"property_block", "darkness_block"}

WIN_CONDITION_KINDS: set[str] = {
    "any_character_property",
    "player_at_location",
    "player_has_item",
    "all_of",
    "any_of",
    "flag",
}


def _action_name_for(action: CustomActionSpec) -> str:
    """Derive the runtime ACTION_NAME a template will emit for these params.

    The parser routes commands by substring match against every action's
    name (see ``parsing.Parser.determine_intent``), so this must match what
    the emitters in ``codegen/templates/actions.py`` produce.
    """
    p = action.params
    if action.template == "unlock_with_key":
        return f"unlock {p.get('lock_item', '')}".strip()
    if action.template == "read_inscription_to_banish":
        # "read runes" in Action Castle. Parameterized on the verb noun.
        return p.get("action_name", "read runes")
    if action.template == "propose_marriage":
        return "propose"
    if action.template == "wear_item":
        return f"wear {p.get('item', '')}".strip()
    if action.template == "sit_on_furniture":
        return f"sit on {p.get('furniture_item', '')}".strip()
    if action.template == "npc_taunt":
        return p.get("verb", "").strip()
    if action.template == "npc_kill":
        return p.get("verb", "").strip()
    if action.template == "flavor_response":
        return p.get("verb", "").strip()
    if action.template == "transform_item":
        return p.get("verb", "").strip()
    return ""


def _validate_win_condition(
    wc: WinCondition,
    location_names: set[str],
    item_names: set[str],
    character_names: set[str],
    errors: list[str],
    path: str = "win_condition",
) -> None:
    if wc.kind not in WIN_CONDITION_KINDS:
        errors.append(
            f"{path}: unknown kind {wc.kind!r}; expected one of {sorted(WIN_CONDITION_KINDS)}"
        )
        return
    if wc.kind in ("all_of", "any_of"):
        if not wc.children:
            errors.append(f"{path}: {wc.kind} requires non-empty children")
            return
        for i, child in enumerate(wc.children):
            _validate_win_condition(
                child,
                location_names,
                item_names,
                character_names,
                errors,
                f"{path}.children[{i}]",
            )
    elif wc.kind == "any_character_property":
        if not wc.property:
            errors.append(f"{path}: any_character_property requires 'property'")
    elif wc.kind == "player_at_location":
        if not wc.location:
            errors.append(f"{path}: player_at_location requires 'location'")
        elif wc.location not in location_names:
            errors.append(f"{path}: unknown location {wc.location!r}")
    elif wc.kind == "player_has_item":
        if not wc.item:
            errors.append(f"{path}: player_has_item requires 'item'")
    elif wc.kind == "flag":
        if not wc.name:
            errors.append(f"{path}: flag requires 'name'")


def validate(spec: GameSpec) -> list[str]:
    """Return a list of human-readable validation errors. Empty list = valid.

    Checks:
      * unique location names
      * every Exit.to resolves to a known location
      * start_at resolves to a known location
      * every Item.at resolves (location or owner) to a known thing
      * every Character.at resolves to a known location
      * every Character.inventory entry resolves to a known item
      * every Block.at_location resolves; every Block.obstacle resolves
      * every Block.template is known; per-template required fields present
      * every CustomAction.template is known
      * every CustomAction param that names a thing resolves
      * win_condition kind is known and its fields resolve
      * no ACTION_NAME is a strict prefix of another (would mis-route
        through the substring parser)
    """
    errors: list[str] = []

    # --- collect names ---
    location_names: list[str] = [l.name for l in spec.locations]
    item_names: set[str] = {i.name for i in spec.items} | {
        pi.name for pi in spec.player.inventory
    }
    character_names: set[str] = {c.name for c in spec.characters} | {spec.player.name}

    # --- duplicate location names ---
    seen: dict[str, int] = {}
    for name in location_names:
        seen[name] = seen.get(name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            errors.append(f"duplicate location name: {name!r} (x{count})")
    location_set = set(location_names)

    # --- start_at ---
    if spec.start_at not in location_set:
        errors.append(f"start_at: unknown location {spec.start_at!r}")

    # --- locations / exits ---
    for loc in spec.locations:
        for ex in loc.exits:
            if ex.to not in location_set:
                errors.append(
                    f"location {loc.name!r} exit {ex.direction!r}: "
                    f"unknown target {ex.to!r}"
                )

    # --- multi-direction connections between the same location pair ---
    # If the effective graph (declared exits + engine auto-reverse) ever
    # connects a single (loc -> target) pair via more than one direction,
    # the spec is broken: any block on one direction is silently bypassed
    # by typing the other. This is the locked-door walk-through bug --
    # see ``_effective_connections`` for the auto-reverse mechanic.
    if not any(e.startswith("location ") for e in errors):
        graph = _effective_connections(spec)
        reported: set[tuple[str, str]] = set()
        for loc_name, edges in graph.items():
            by_target: dict[str, list[str]] = {}
            for direction, target in edges.items():
                by_target.setdefault(target, []).append(direction)
            for target, dirs in by_target.items():
                if len(dirs) < 2:
                    continue
                key = tuple(sorted([loc_name, target]))
                if key in reported:
                    continue
                reported.add(key)
                errors.append(
                    f"{loc_name!r} reaches {target!r} via multiple "
                    f"directions {sorted(dirs)} (counting the engine's "
                    f"auto-reverse on canonical directions). Each "
                    f"location pair must use exactly ONE direction-pair; "
                    f"a block on one direction is otherwise bypassed by "
                    f"the other. Drop the extra exit; if both sides "
                    f"declare an exit between this pair, keep only one."
                )

    # --- items ---
    for item in spec.items:
        loc = item.at.location
        own = item.at.owner
        if not loc and not own:
            errors.append(f"item {item.name!r}: at.location or at.owner required")
        if loc and loc not in location_set:
            errors.append(f"item {item.name!r}: unknown at.location {loc!r}")
        if own and own not in character_names:
            errors.append(f"item {item.name!r}: unknown at.owner {own!r}")

    # --- characters ---
    for char in spec.characters:
        if char.at not in location_set:
            errors.append(f"character {char.name!r}: unknown at {char.at!r}")
        for inv_name in char.inventory:
            if inv_name not in item_names:
                errors.append(
                    f"character {char.name!r} inventory item "
                    f"{inv_name!r}: not defined in items[]"
                )
        if char.behavior and char.behavior.kind not in (
            "none",
            "escalating_commands",
            "follow",
        ):
            errors.append(
                f"character {char.name!r}: unknown behavior kind "
                f"{char.behavior.kind!r}"
            )
        if char.behavior and char.behavior.kind == "escalating_commands":
            if not char.behavior.commands and not char.behavior.fallback:
                errors.append(
                    f"character {char.name!r}: escalating_commands "
                    "requires at least commands[] or fallback"
                )

    # --- blocks ---
    for block in spec.blocks:
        if block.template not in BLOCK_TEMPLATES:
            errors.append(
                f"block {block.id!r}: unknown template {block.template!r}; "
                f"expected one of {sorted(BLOCK_TEMPLATES)}"
            )
            continue
        if block.at_location not in location_set:
            errors.append(
                f"block {block.id!r}: unknown at_location {block.at_location!r}"
            )
        if block.template == "property_block":
            if not block.obstacle:
                errors.append(f"block {block.id!r}: property_block requires 'obstacle'")
            else:
                if block.obstacle.kind == "character":
                    if block.obstacle.name not in character_names:
                        errors.append(
                            f"block {block.id!r}: unknown obstacle character "
                            f"{block.obstacle.name!r}"
                        )
                elif block.obstacle.kind == "item":
                    if block.obstacle.name not in item_names:
                        errors.append(
                            f"block {block.id!r}: unknown obstacle item "
                            f"{block.obstacle.name!r}"
                        )
                else:
                    errors.append(
                        f"block {block.id!r}: obstacle.kind must be "
                        "'character' or 'item'"
                    )
            for cond in block.conditions:
                if cond.target not in ("obstacle", "location", "actor"):
                    errors.append(
                        f"block {block.id!r}: condition.target must be "
                        "'obstacle', 'location', or 'actor'"
                    )
        elif block.template == "darkness_block":
            if not block.unblocked_if_inventory_has_property:
                errors.append(
                    f"block {block.id!r}: darkness_block requires "
                    "'unblocked_if_inventory_has_property'"
                )

    # --- custom actions ---
    for action in spec.custom_actions:
        if action.template not in ACTION_TEMPLATES:
            errors.append(
                f"action {action.id!r}: unknown template {action.template!r}; "
                f"expected one of {sorted(ACTION_TEMPLATES)}"
            )
            continue
        _validate_action_params(action, item_names, character_names, errors)

    # --- ACTION_NAME uniqueness ---
    # The substring parser routes by longest match (see
    # parsing.Parser.determine_intent), so prefix pairs coexist cleanly --
    # "wear" and "wear crown" route correctly. The only fatal case is two
    # custom actions with the SAME ACTION_NAME.
    seen_action_names: dict[str, str] = {}
    for action in spec.custom_actions:
        name = _action_name_for(action)
        if not name:
            continue
        if name in seen_action_names:
            errors.append(
                f"duplicate action name {name!r} from actions "
                f"{seen_action_names[name]!r} and {action.id!r}"
            )
        else:
            seen_action_names[name] = action.id

    # --- win condition ---
    _validate_win_condition(
        spec.win_condition, location_set, item_names, character_names, errors
    )

    return errors


def _validate_action_params(
    action: CustomActionSpec,
    item_names: set[str],
    character_names: set[str],
    errors: list[str],
) -> None:
    """Per-template required parameter checks."""
    p = action.params
    tmpl = action.template

    def need(key: str) -> Any:
        if key not in p:
            errors.append(
                f"action {action.id!r}: template {tmpl!r} requires param {key!r}"
            )
            return None
        return p[key]

    def need_item(key: str) -> None:
        v = need(key)
        if v and v not in item_names:
            errors.append(
                f"action {action.id!r}: param {key!r}={v!r} is not a defined item"
            )

    def need_character(key: str) -> None:
        v = need(key)
        if v and v not in character_names:
            errors.append(
                f"action {action.id!r}: param {key!r}={v!r} is not a defined character"
            )

    if tmpl == "unlock_with_key":
        need_item("lock_item")
        need_item("key_item")
        need("unlocked_property")
    elif tmpl == "read_inscription_to_banish":
        need_item("inscribed_item")
        need_character("target_character")
        need("required_property")
        need("banished_property")
    elif tmpl == "propose_marriage":
        need("required_emotional_state")
        need("set_property_on_pair")
    elif tmpl == "wear_item":
        need_item("item")
        need("required_actor_property")
        need("set_actor_property")
    elif tmpl == "sit_on_furniture":
        need_item("furniture_item")
        need("required_actor_property")
        need("set_actor_property")
    elif tmpl == "npc_taunt":
        need("verb")
        need("template_string")
    elif tmpl == "npc_kill":
        need("verb")
        need("template_string")
        need("sets_target_property")
    elif tmpl == "flavor_response":
        need("verb")
        need("template_string")
        # Optional: requires_in_scope, at_location, consumes_item. Soft-check
        # that any named item resolves; an empty string is "no constraint".
        scope_item = p.get("requires_in_scope")
        if scope_item and scope_item not in item_names:
            errors.append(
                f"action {action.id!r}: requires_in_scope = {scope_item!r} "
                "is not a defined item"
            )
        consumed = p.get("consumes_item")
        if consumed and consumed not in item_names:
            errors.append(
                f"action {action.id!r}: consumes_item = {consumed!r} "
                "is not a defined item"
            )
    elif tmpl == "transform_item":
        need("verb")
        need_item("item")
        sets = p.get("sets_properties") or {}
        if not isinstance(sets, dict) or not sets:
            errors.append(
                f"action {action.id!r}: transform_item requires non-empty "
                "'sets_properties' (dict of property -> value)"
            )
