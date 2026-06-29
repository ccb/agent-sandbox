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
