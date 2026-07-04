"""Reactions: thing-owned, stimulus-triggered reflexes (gate -> effect).

A Reaction is to the world what an Action is to a command: a *gated effect*.
Where an Action is pulled by a player/agent command, a Reaction is pulled by
something happening in the world -- a noise it hears, a creature arriving, a
timer running out. Its precondition *is* the trigger; its effect *is* the
response.

Action and Reaction share :class:`GatedEffect` below -- the single place the
check-then-apply contract lives -- so the two read identically. Unlike an Action,
a Reaction has no parser-facing surface (no ``ACTION_NAME``/aliases, no command
matching) and is *persistent*: it is instantiated once, attached to a Thing via
:meth:`Game.add_reaction`, and re-evaluated in the post-round react phase for as
long as it lives. Like a Character's ``behavior``, reactions are runtime-only --
they hold live callables/state and are re-attached by ``build_game``, never
serialized.

See ``docs/design/reactions.md`` for the full design.
"""

from __future__ import annotations


class GatedEffect:
    """Shared check-then-apply runner for :class:`Action` and :class:`Reaction`.

    Calling the object runs its precondition gate and, only if it passes, applies
    its effects -- recording on ``_preconditions_passed`` whether the gate opened
    (read by the parser/NPC loop to tell "did nothing" from "did something").
    Subclasses override :meth:`check_preconditions` and :meth:`apply_effects`;
    this is the one place the gate->effect contract lives.
    """

    def check_preconditions(self) -> bool:
        """Return True when the effect should run. Override."""
        return False

    def apply_effects(self):
        """Change the state of the world. Override."""
        return None

    def __call__(self):
        self._preconditions_passed = False
        if self.check_preconditions():
            self._preconditions_passed = True
            return self.apply_effects()


class Reaction(GatedEffect):
    """A thing-owned reflex: a gated effect pulled by the world, not a command.

    Attach one with ``game.add_reaction(thing, reaction)``, which sets
    :attr:`owner` and :attr:`game` and registers the reaction to be evaluated each
    round in the react phase. :meth:`check_preconditions` inspects the world
    (typically through ``self.game`` and ``self.owner``) for the stimulus this
    reflex answers and stashes what it found on :attr:`cause` -- mirroring how an
    Action stashes a matched item; :meth:`apply_effects` then reacts, reading
    :attr:`cause`.

    By default a reaction fires at most once *ever* (``REPEATABLE = False``, the
    one-shot trigger semantics): a creature flees or wakes once, a countdown
    starts once. A standing reflex that should re-arm every round (e.g. "growl at
    any intruder") sets ``REPEATABLE = True``.
    """

    # Re-evaluate after firing? Default one-shot. The shipped library reactions
    # (flee / wake / countdown) all fire once; a re-arming reflex overrides this.
    REPEATABLE = False

    def __init__(self, game=None, owner=None):
        # Both are populated by Game.add_reaction at attach time; a reaction
        # constructed in build_game (before the game exists) leaves them None
        # until it is attached.
        self.game = game
        self.owner = owner
        # What check_preconditions detected this round, read by apply_effects.
        self.cause = None

    @property
    def name(self) -> str:
        """Stable label for the react-phase trigger and the event log."""
        owner = getattr(self.owner, "name", self.owner)
        return f"reaction:{type(self).__name__}:{owner}"


# ---------------------------------------------------------------------------
# Reusable reaction library (docs/design/reactions.md §6)
#
# Two ready shapes cover the existing threats; a game subclasses Reaction (or one
# of these) for anything bespoke, exactly as it subclasses Action.
# ---------------------------------------------------------------------------


def _relocate_and_log(game, thing, dest):
    """Move a Thing (Item or Character) into *dest* and log a movement event.

    Reactions move their owner directly (not through a command), but the move
    must still be *seen*: logging it the way the parser logs a Go means
    perception renders the arrival/departure and other reactions can key on it
    (``entered_this_round``) -- the chain that lets the poacher's countdown start
    the instant the doe is driven into his clearing. The flight itself is silent
    (``heard_radius`` 0); the noise that *caused* it was its own event."""
    src = getattr(thing, "location", None)
    name = getattr(thing, "name", None)
    is_character = hasattr(thing, "take_turn")
    direction = None
    if src is not None:
        if name in getattr(src, "characters", {}):
            src.remove_character(thing)
            is_character = True
        elif name in getattr(src, "items", {}):
            src.remove_item(thing)
            is_character = False
        direction = next((d for d, r in src.connections.items() if r is dest), None)
    if is_character:
        dest.add_character(thing)
    else:
        dest.add_item(thing)
    game.log_event(
        name,
        "go",
        f"{name} flees to {dest.name}",
        payload={
            "location": getattr(src, "name", None),
            "dest": dest.name,
            "dir": direction,
            "heard_radius": 0,
        },
    )


class Startle(Reaction):
    """Base for reflexes pulled by *any sound the owner perceives* this round.

    The precondition is dead simple -- "is there a sound where I'm standing?"
    (:meth:`Game.sounds_audible_at`, excluding the owner's own noise). What's a
    sound is the *source's* business (an action's ``AUDIBLE_RADIUS`` or
    ``emit_sound``), so there's no per-scene loud/safe/earshot list here; hearing
    *is* earshot. Subclasses (:class:`FleesAtNoise`, :class:`WakesAtNoise`) say
    what to do, and may add their own gate (e.g. "only while asleep") via
    :meth:`ready`."""

    def ready(self) -> bool:
        """Extra owner-state gate beyond "a sound was heard" (default: always)."""
        return True

    def check_preconditions(self) -> bool:
        loc = getattr(self.owner, "location", None)
        if loc is None or not self.ready():
            return False
        # Dead, unconscious, or pacified things don't answer sounds.
        if (
            self.owner.get_property("is_dead")
            or self.owner.get_property("is_unconscious")
            or self.owner.get_property("dosed")
        ):
            return False
        sounds = self.game.sounds_audible_at(
            loc, exclude=getattr(self.owner, "name", None)
        )
        if not sounds:
            return False
        self.cause = sounds[0]  # the sound that set off the reflex
        return True


class FleesAtNoise(Startle):
    """The owner bolts to another room at the first noise it hears (once).

    ``to`` is the destination Location (or its name). Use it for skittish prey:
    ``game.add_reaction(deer, FleesAtNoise(to=deep_woods))``."""

    def __init__(self, to):
        super().__init__()
        self._to = to

    def _destination(self):
        to = self._to
        return to if hasattr(to, "connections") else self.game.locations.get(to)

    def apply_effects(self):
        dest = self._destination()
        if dest is None:
            return
        _relocate_and_log(self.game, self.owner, dest)
        self.game.parser.ok(self.narration(dest))

    def narration(self, dest) -> str:
        """How the flight reads. Built from the cause so no per-creature wiring is
        needed; override for bespoke flavor."""
        name = getattr(self.owner, "name", "creature")
        flee = f"the {name} bolts off into {dest.name}"
        cue = (self.cause or {}).get("description")
        if cue:
            return f"{cue[:1].upper()}{cue[1:]}, and {flee}."
        return f"{flee[:1].upper()}{flee[1:]}."


class WakesAtNoise(Startle):
    """A sleeping creature wakes at the first noise it hears.

    Gated on the owner's ``asleep`` property (override ``ASLEEP_PROPERTY`` to
    match a game's flag). The default effect just clears the flag and narrates;
    subclass :meth:`wake` for a bespoke response -- e.g. the dragon rears up and
    challenges the intruder."""

    ASLEEP_PROPERTY = "asleep"

    def ready(self) -> bool:
        return bool(self.owner.get_property(self.ASLEEP_PROPERTY))

    def apply_effects(self):
        self.owner.set_property(self.ASLEEP_PROPERTY, False)
        self.wake()

    def wake(self):
        """React to being woken. Override for a bespoke awakening."""
        name = getattr(self.owner, "name", "it")
        self.game.parser.ok(f"The noise wakes {name}.")


class DrawnToSound(Startle):
    """The moth-to-flame inverse of :class:`FleesAtNoise`: the owner moves one hop
    *toward* the loudest sound it hears each round, until it reaches the source.

    For pursuers, lured beasts, sirens -- anything that homes on noise. Re-arms
    every round (``REPEATABLE = True``), so sustained noise keeps drawing it in;
    silence lets it stop. The AC4-style doe flees noise; this is its opposite, and
    the Tomb's Spawn use it (lured to the singing fungal head)."""

    REPEATABLE = True
    REACH = 12  # hops to search for a path back to the source; spans any real map

    def apply_effects(self):
        origin = (self.cause or {}).get("origin")
        loc = getattr(self.owner, "location", None)
        if not origin or loc is None or origin == loc.name:
            return  # no source, or already standing on it
        # audible_rooms(origin, r)[my_room] is the exit in my room toward origin --
        # the first step on the shortest path back to the noise.
        step = self.game.audible_rooms(origin, self.REACH).get(loc.name)
        dest = loc.connections.get(step) if step else None
        if dest is not None:
            _relocate_and_log(self.game, self.owner, dest)
            self.game.parser.ok(self.narration(dest))

    def narration(self, dest) -> str:
        name = getattr(self.owner, "name", "it")
        cue = (self.cause or {}).get("description", "a sound")
        return f"Drawn by {cue}, the {name} moves off toward {dest.name}."


class Countdown(Reaction):
    """A clock: a stimulus starts it, and ``DELAY`` turns later a consequence
    lands unless it was averted.

    Fires **once** when :meth:`stimulus` first becomes true, narrates
    :meth:`warning`, and schedules :meth:`consequence` for ``DELAY`` turns out.
    Before it lands, the scheduled resolution checks :meth:`cancelled` -- so a
    player action that sets the right flag calls it off. Subclass to fill in the
    four hooks (the poacher: doe-arrival stimulus, ``poacher_dealt`` cancel, a
    warning, and the lethal shot)."""

    DELAY = 2

    def stimulus(self) -> bool:
        """What starts the clock. Must override."""
        raise NotImplementedError

    def cancelled(self) -> bool:
        """Has the consequence been averted before it lands? (default: no)."""
        return False

    def warning(self) -> str:
        """Narration when the countdown starts (default: silent)."""
        return ""

    def consequence(self, game):
        """What happens when the timer elapses uncancelled. Must override to act."""

    def check_preconditions(self) -> bool:
        return self.stimulus()

    def apply_effects(self):
        message = self.warning()
        if message:
            self.game.parser.ok(message)
        self.game.schedule_event(
            self.game.turn + self.DELAY, self._resolve, name=f"{self.name}:resolve"
        )

    def _resolve(self, game):
        if not self.cancelled():
            self.consequence(game)
