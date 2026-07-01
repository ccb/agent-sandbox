"""Engine enums for the well-known string-keyed APIs.

Every enum in this module inherits from ``(str, Enum)``, so each member *is* a
string. ``Property.IS_LOCKED == "is_locked"`` is true, ``f"{Direction.NORTH}"``
formats as ``"north"``, and a dict keyed by ``"north"`` still resolves a lookup
made with ``Direction.NORTH``. That means existing call sites that pass the
literal string keep working; the enum just adds autocomplete, a single source
of truth, and a way to ``grep`` for every consumer at once.

Open vs closed sets:
    Direction / LlmProvider / Period / ReActLabel / Role are CLOSED sets — every
    value the engine cares about appears here.

    Property / ActionName / EventKind are OPEN — the engine ships well-known
    members, but games are free to invent new ones (a wizard quest may set
    ``flying``; a custom action may declare ``ACTION_NAME = "cast"``). For
    those, set the property/action name with a plain string.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """``str`` + ``Enum`` mixin.

    We use the explicit ``(str, Enum)`` mixin rather than ``enum.StrEnum``
    so the behavior is identical on every supported Python version:
    ``str(member)`` and f-strings render the value (``"north"``), and
    members compare equal to plain strings and work as dict keys.
    """

    def __str__(self) -> str:  # so f-strings render the value, not "Direction.NORTH"
        return self.value


# ----------------------------------------------------------------------
# Property keys
# ----------------------------------------------------------------------


class Property(_StrEnum):
    """Well-known keys for ``Thing.properties``.

    Acts as the single source of truth for the properties the engine itself
    reads. Games define their own properties freely — pass any string to
    ``set_property``/``get_property`` and it just works.
    """

    # Character state
    IS_DEAD = "is_dead"
    IS_UNCONSCIOUS = "is_unconscious"
    IS_INVULNERABLE = "is_invulerable"  # legacy misspelling kept for compat
    IS_HUNGRY = "is_hungry"
    IS_THIRSTY = "is_thirsty"
    IS_DRUNK = "is_drunk"
    CHARACTER_TYPE = "character_type"
    EMOTIONAL_STATE = "emotional_state"

    # Affordances -- yes/no capabilities of an item. Read by action
    # preconditions ("is this drinkable?") and surfaced to agents as an
    # affordance list. Games may add their own affordances by passing a
    # plain string to set_property.
    GETTABLE = "gettable"
    EDIBLE = "edible"
    DRINKABLE = "drinkable"
    FLAMMABLE = "flammable"
    WEARABLE = "wearable"
    WIELDABLE = "wieldable"
    READABLE = "is_readable"  # has writing the READ action can show

    # Other item flags (state or descriptors, not affordances)
    IS_WEAPON = "is_weapon"
    IS_FRAGILE = "is_fragile"
    IS_ALCOHOL = "is_alcohol"
    IS_POISONOUS = "is_poisonous"
    IS_LIT = "is_lit"
    # Concealed until found: a hidden item is not described, in scope, or
    # gettable until a SEARCH of its location/holder reveals it (clears this).
    IS_HIDDEN = "is_hidden"
    TASTE = "taste"
    SCENT = "scent"
    READ_TEXT = "read_text"  # the words shown by READ (a string, not a flag)

    # Location / world flags
    IS_LOCKED = "is_locked"
    IS_DARK = "is_dark"
    GAME_OVER = "game_over"

    # Quest-y flags used by the bundled Action Castle game. Listed here so
    # auto-complete surfaces them; games are free to ignore them.
    HAS_FISH = "has_fish"
    HAS_ROSE = "has_rose"
    IS_REIGNING = "is_reigning"
    IS_CROWNED = "is_crowned"
    IS_ROYAL = "is_royal"
    IS_MARRIED = "is_married"
    IS_BANISHED = "is_banished"


# ----------------------------------------------------------------------
# Movement directions
# ----------------------------------------------------------------------


class Direction(_StrEnum):
    """Canonical movement directions used by ``Location.connections``."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    UP = "up"
    DOWN = "down"
    IN = "in"
    OUT = "out"
    INSIDE = "inside"
    OUTSIDE = "outside"


# Each cardinal direction has a single opposite; this map is consulted by
# Location.add_connection so a one-way add wires both sides automatically.
OPPOSITES: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.IN: Direction.OUT,
    Direction.OUT: Direction.IN,
    Direction.INSIDE: Direction.OUTSIDE,
    Direction.OUTSIDE: Direction.INSIDE,
}


# ----------------------------------------------------------------------
# Built-in action names
# ----------------------------------------------------------------------


class ActionName(_StrEnum):
    """Names of the engine's built-in actions.

    The parser keys actions by this string. Custom games can register actions
    with arbitrary string names — these are just the ones the engine ships.
    """

    # Movement / meta
    GO = "go"
    DESCRIBE = "describe"
    WAIT = "wait"
    QUIT = "quit"
    HELP = "help"
    SEQUENCE = "sequence"

    # Object handling
    GET = "get"
    DROP = "drop"
    BREAK = "break"
    INVENTORY = "inventory"
    EXAMINE = "examine"
    READ = "read"
    SEARCH = "search"
    GIVE = "give"
    UNLOCK_DOOR = "unlock door"
    # Holders: put things in containers / on surfaces, and open/close containers
    PUT = "put"
    OPEN = "open"
    CLOSE = "close"

    # Combat / social
    ATTACK = "attack"
    SAY = "say"
    TALK = "talk"
    FOLLOW = "follow"
    UNFOLLOW = "stop following"

    # Consumables
    EAT = "eat"
    DRINK = "drink"
    LIGHT = "light"
    DOUSE = "douse"

    # Crafting: combine ingredients (optionally at a station/with a tool) into
    # a new item (see crafting.py). Games opt in by registering recipes.
    CRAFT = "craft"

    # Vehicles/mounts (see actions/vehicles.py): board and ride a horse, a
    # motorcycle, a boat; some exits require being mounted.
    MOUNT = "mount"
    DISMOUNT = "dismount"

    # Equipment
    WEAR = "wear"
    TAKE_OFF = "take off"
    WIELD = "wield"
    UNWIELD = "unwield"

    # Bundled-game actions (Action Castle quest items)
    CATCH_FISH = "catch fish"
    PICK_ROSE = "pick rose"
    SMELL_ROSE = "smell rose"


# ----------------------------------------------------------------------
# LLM providers
# ----------------------------------------------------------------------


class LlmProvider(_StrEnum):
    """Identifies an LLM backend. Used by ``LlmConfig.provider`` and the
    ``LLM_PROVIDER`` environment variable."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class EmbeddingProvider(_StrEnum):
    """Identifies an embedding backend. Used by ``EmbeddingConfig.provider`` and
    the ``EMBEDDING_PROVIDER`` environment variable.

    ``local`` runs a small static model offline (model2vec, the default);
    ``sentence-transformers`` runs a local transformer model; ``openai`` calls
    the hosted OpenAI embeddings API; ``mock`` is the deterministic,
    dependency-free stand-in the test suite uses. Other backends (e.g. Voyage,
    raw Hugging Face ``transformers``) can join later behind the same
    ``EmbeddingClient`` seam."""

    LOCAL = "local"
    MOCK = "mock"
    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence-transformers"


# ----------------------------------------------------------------------
# Day periods
# ----------------------------------------------------------------------


class Period(_StrEnum):
    """Named coarse periods of the in-game day (see ``clock.GameClock``)."""

    DAWN = "dawn"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    DUSK = "dusk"
    NIGHT = "night"


# ----------------------------------------------------------------------
# ReAct prompt labels
# ----------------------------------------------------------------------


class ReActLabel(_StrEnum):
    """The line-prefix labels in the ReAct prompt/reply format.

    Stored with the trailing colon so they double as both prompt template
    fragments ("Reasoning: ...") and parser tokens. ``THOUGHT`` is accepted as
    a synonym for ``REASONING`` when parsing replies. ``DURATION`` is the
    optional line on which a model estimates how many in-game minutes an action
    takes (consumed by the per-turn NPC time budget).
    """

    REASONING = "Reasoning:"
    ACTION = "Action:"
    THOUGHT = "Thought:"
    DURATION = "Duration:"


# ----------------------------------------------------------------------
# Chat-completion roles
# ----------------------------------------------------------------------


class Role(_StrEnum):
    """The OpenAI/Anthropic chat-completion role keys used in command_history
    entries and prompt messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ----------------------------------------------------------------------
# GameEvent kinds
# ----------------------------------------------------------------------


class EventKind(_StrEnum):
    """Engine-generated values for ``GameEvent.action``.

    Most events carry an action *name* (the parser logs the action's keyword
    on success). ``TRIGGER`` is written by the trigger system; ``SOUND`` is an
    ambient noise emitted by a thing rather than by a command (Game.emit_sound) --
    both are engine-internal kinds rather than player/NPC commands.
    """

    TRIGGER = "trigger"
    SOUND = "sound"
