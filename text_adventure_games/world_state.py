"""Typed, read-only snapshot of the whole world (issue #90).

A deterministic, JSON-able feed that a structured exporter or a future Godot
renderer (issues #9 / #10) can poll. The engine owns TOPOLOGY -- the room graph,
who is where, what is blocked -- while a renderer derives PIXELS client-side
(the engine has no x/y coordinates; space is named-exit adjacency).

This is the SNAPSHOT half of the export. The complementary per-message *change
feed* (a ``JSONRenderer`` over the ``reporting.py`` Channel/Message seam) is a
separate, deferred concern.

Deliberately OMITTED in v1 (privacy / non-serializable / out of scope):
  - private agent cognition: ``Character.knowledge`` / ``.heard`` (exporting
    them into a shared omniscient snapshot would leak one agent's mind);
  - runtime-only refs: behavior/agent/following/riding callables, and
    ``Game.triggers`` / ``recipes`` / pending prompt;
  - Block unlock conditions (arbitrary callables): an exit exports only a
    ``blocked`` boolean, never *why* (same limit as ``Game.from_primitive``);
  - per-viewer visibility filtering: v1 is omniscient.

Authored goals ARE included (already author-set state, in ``Character``). The
snapshot is pure: building it never mutates the game.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

SCHEMA_VERSION = "1.0"

# Well-known affordance flags worth surfacing as a list for a renderer/UI.
_AFFORDANCE_KEYS = (
    "drinkable",
    "edible",
    "flammable",
    "gettable",
    "wearable",
    "wieldable",
)

# How many of the newest events to include (the "recent events" tail).
_RECENT_EVENTS = 20


# --- value records (frozen, JSON-able, stably ordered) ---------------------


@dataclass(frozen=True)
class ExitState:
    direction: str
    to: str
    blocked: bool
    description: str = ""


@dataclass(frozen=True)
class ItemState:
    name: str
    description: str
    location: str | None
    owner: str | None
    container: str | None
    quantity: int
    affordances: tuple[str, ...]
    properties: dict
    contents: tuple["ItemState", ...]


@dataclass(frozen=True)
class GoalState:
    description: str
    type: str
    done: bool


@dataclass(frozen=True)
class CharacterState:
    name: str
    description: str
    persona: str
    location: str | None
    is_player: bool
    inventory: tuple[ItemState, ...]
    worn: tuple[ItemState, ...]
    wielded: tuple[ItemState, ...]
    goals: tuple[GoalState, ...]
    properties: dict


@dataclass(frozen=True)
class LocationState:
    name: str
    description: str
    visited: bool
    exits: tuple[ExitState, ...]
    items: tuple[ItemState, ...]
    characters: tuple[str, ...]
    properties: dict


@dataclass(frozen=True)
class ClockState:
    time: str
    period: str | None
    day: int
    hour: int
    minute: int


@dataclass(frozen=True)
class EventState:
    turn: int
    actor: str | None
    action: str
    summary: str
    payload: dict


@dataclass(frozen=True)
class WorldState:
    schema_version: str
    turn: int
    player: str
    clock: ClockState | None
    locations: tuple[LocationState, ...]
    characters: tuple[CharacterState, ...]
    events: tuple[EventState, ...]

    def to_jsonable(self) -> dict:
        """A plain nested dict/list structure ready for ``json.dumps``."""
        return asdict(self)


# --- helpers ---------------------------------------------------------------


def _name(thing):
    """Flatten a Thing-or-name reference to its name string (or None). The
    engine's own ``to_primitive`` flattens object back-pointers this way to stay
    acyclic; we do the same so the snapshot is a tree, never a cycle."""
    if thing is None:
        return None
    return getattr(thing, "name", thing)


def _jsonable(value):
    """Coerce a property value to something ``json.dumps`` can emit."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return getattr(value, "value", None) or str(value)


def _properties(thing, exclude=()):
    """Truthy properties only, sorted, string-keyed, JSON-safe.

    Filters the raw ``defaultdict(bool)`` to keys that are actually set (truthy),
    so the export carries meaningful flags only -- no False noise, no internals,
    and stable ordering regardless of insertion order. Read-only: ``.items()``
    and ``get_property`` never write."""
    out = {}
    for key, value in thing.properties.items():
        key = str(key)
        if value and key not in exclude:
            out[key] = _jsonable(value)
    return dict(sorted(out.items()))


def _item_state(item) -> ItemState:
    return ItemState(
        name=item.name,
        description=item.description,
        location=_name(getattr(item, "location", None)),
        owner=_name(getattr(item, "owner", None)),
        container=_name(getattr(item, "container", None)),
        quantity=getattr(item, "quantity", 1),
        affordances=tuple(k for k in _AFFORDANCE_KEYS if item.get_property(k)),
        properties=_properties(item, exclude=_AFFORDANCE_KEYS),
        contents=_items(getattr(item, "contents", {})),
    )


def _items(by_name) -> tuple[ItemState, ...]:
    """Item states for a name->Item dict, sorted by name for determinism."""
    return tuple(_item_state(v) for _, v in sorted(by_name.items()))


def _goal_state(goal) -> GoalState:
    return GoalState(
        description=goal.description,
        type=getattr(goal.type, "value", str(goal.type)),
        done=goal.done,
    )


def _character_state(character, player) -> CharacterState:
    return CharacterState(
        name=character.name,
        description=character.description,
        persona=getattr(character, "persona", ""),
        location=_name(getattr(character, "location", None)),
        is_player=character is player,
        inventory=_items(character.inventory),
        worn=_items(character.worn),
        wielded=_items(character.wielded),
        goals=tuple(_goal_state(g) for g in getattr(character, "goals", [])),
        properties=_properties(character),
    )


def _location_state(location) -> LocationState:
    exits = tuple(
        ExitState(
            direction=direction,
            to=destination.name,
            blocked=location.is_blocked(direction),
            description=location.travel_descriptions.get(direction, ""),
        )
        for direction, destination in sorted(location.connections.items())
    )
    return LocationState(
        name=location.name,
        description=location.description,
        visited=getattr(location, "has_been_visited", False),
        exits=exits,
        items=_items(location.items),
        characters=tuple(sorted(location.characters.keys())),
        properties=_properties(location),
    )


def _clock_state(game) -> ClockState | None:
    clock = getattr(game, "clock", None)
    if clock is None:
        return None
    turn = getattr(game, "turn", 0)
    day, hour, minute = clock.time_at(turn)
    return ClockState(
        time=clock.format_time(turn),
        period=clock.period_at(turn),
        day=day,
        hour=hour,
        minute=minute,
    )


def _event_state(event) -> EventState:
    return EventState(
        turn=event.turn,
        actor=_name(event.actor),
        action=str(getattr(event.action, "value", event.action)),
        summary=getattr(event, "summary", ""),
        payload=dict(getattr(event, "payload", {}) or {}),
    )


# --- the builder -----------------------------------------------------------


def world_state(game) -> WorldState:
    """Build a typed, deterministic, read-only snapshot of *game*'s world.

    Reads only public Game attributes (locations, characters, player, turn,
    clock, events) and public Thing accessors; never mutates the game. Every
    collection is sorted by name/direction so two equivalent worlds serialize
    identically."""
    player = game.player
    locations = tuple(_location_state(loc) for _, loc in sorted(game.locations.items()))
    characters = tuple(
        _character_state(ch, player) for _, ch in sorted(game.characters.items())
    )
    events = tuple(
        _event_state(e) for e in getattr(game, "events", [])[-_RECENT_EVENTS:]
    )
    return WorldState(
        schema_version=SCHEMA_VERSION,
        turn=getattr(game, "turn", 0),
        player=player.name,
        clock=_clock_state(game),
        locations=locations,
        characters=characters,
        events=events,
    )
