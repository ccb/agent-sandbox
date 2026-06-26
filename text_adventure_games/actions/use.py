"""The ``USE X ON Y`` pattern -- a reusable two-object action (feature outline).

Every Parsely game leans on a two-object interaction: ``USE WAND ON OOZE``,
``HIT MAN WITH KETTLE``, ``THROW JAVELIN AT DEMON``, ``SHOW ID TO GUARD``,
``POUR SODA ON GOAT``. They all share one shape:

    actor holds X  +  Y is here  +  (optional extra condition)
        -> mutate the world  +  narrate

Until now each one was a hand-written ``Action`` subclass (see the bespoke
``UseHatchet`` / ``ShootSpider`` / ``GiveBowToElf`` classes in the Action
Castle ports). That is a lot of identical ``__init__`` / ``check_preconditions``
boilerplate for what is really just "which item, which target, what changes."

``use_item_on(...)`` factors that boilerplate out. You describe the interaction
declaratively and get back a ready-to-register ``Action`` subclass::

    from text_adventure_games.actions import use_item_on

    UseWandOnOoze = use_item_on(
        "use wand on ooze",
        item="wand",
        target="ooze",
        effect=lambda a: a.target.set_property("is_frozen", True),
        success="A beam of frost engulfs the ooze. It freezes solid.",
        consume=False,
    )

    game = MyGame(start, player, custom_actions=[UseWandOnOoze])

The returned class is a normal ``Action`` -- it routes through the parser's
precondition gate like everything else, so a wrong move ("you aren't holding
the wand", "there's no ooze here") fails with a readable reason that the ReAct
loop can feed back on retry.

The verb need not be "use": pass ``verb=`` / ``preposition=`` to spell the
sibling grammars (``hit ... with ...``, ``throw ... at ...``, ``show ... to
...``). The canonical ``ACTION_NAME`` is built from those, and you can add
``aliases=`` for alternate phrasings the keyword parser should also accept.
"""

from __future__ import annotations

from typing import Callable

from . import base


class UseItemOn(base.Action):
    """Base class for a configured ``use X on Y`` action.

    Not registered or used directly -- :func:`use_item_on` subclasses it with
    the per-interaction configuration filled in as class attributes. The
    machinery here (matching X among the actor's held items, matching Y among
    the things present, running the precondition gate, applying effects) is the
    part every two-object interaction shares.
    """

    # -- configuration, filled in by the factory --------------------------
    _ITEM_NOUN: str = ""  # X: the item the actor must be holding
    _TARGET_NOUN: str = ""  # Y: the item or character acted upon
    _EFFECT: Callable | None = None  # effect(action) -> None; world mutation
    _SUCCESS: str | None = None  # narration emitted on success
    _CONSUME: bool = False  # remove X from the actor after a successful use
    _AWARD: tuple | None = None  # (key, points[, text]) passed to game.award
    _REQUIRES: Callable | None = None  # requires(action) -> error str | None
    _ITEM_MISSING: str | None = None  # override "you aren't holding ..." message
    _TARGET_MISSING: str | None = None  # override "there's no ... here" message

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to use something")
        # X must be in hand, worn, wielded, or stowed in a carried container.
        held = {
            **self.character.carried_items(),
            **self.character.worn,
            **self.character.wielded,
        }
        self.item = self.parser.match_item(self._ITEM_NOUN, held, hint=self._ITEM_NOUN)
        # Y is whatever is present: an item in the room/inventory, else a
        # character standing in the room. We try item first, then character,
        # so ``self.target`` is the single thing the effect acts on.
        scope = self.parser.get_items_in_scope(self.character)
        target_item = self.parser.match_item(
            self._TARGET_NOUN, scope, hint=self._TARGET_NOUN
        )
        self.target = target_item or self.character_in_room(
            self._TARGET_NOUN, self.character
        )

    def claimed_resource(self):
        """The target is the contended resource in a simultaneous round (#42):
        two actors using something on the same target compete for it."""
        return self.target

    def check_preconditions(self) -> bool:
        if not self.was_matched(
            self.item,
            self._ITEM_MISSING or f"You aren't holding the {self._ITEM_NOUN}.",
        ):
            return False
        if not self.was_matched(
            self.target,
            self._TARGET_MISSING or f"There's no {self._TARGET_NOUN} here.",
        ):
            return False
        # Optional game-specific gate (target state, party membership, ...).
        # It returns an error string to block the action, or None to allow it.
        if self._REQUIRES is not None:
            problem = self._REQUIRES(self)
            if problem:
                self.parser.fail(problem)
                return False
        return True

    def apply_effects(self):
        # 1) the world mutation (set a property, relocate, reveal an item ...).
        if self._EFFECT is not None:
            self._EFFECT(self)
        # 2) X may be a single-use item (a thrown javelin, a poured soda).
        if self._CONSUME:
            self.character.discard_item(self.item)
        # 3) scoring, if this interaction awards points. ``Game.award`` is a
        #    base engine method (idempotent + narrates when given text), so a
        #    non-scoring game just leaves max_score at 0 and still shows the text.
        if self._AWARD is not None:
            self.game.award(*self._AWARD)
        # 4) narration. An effect callback may emit its own variable line; pass
        #    ``success=`` for the simple fixed-text case. Fall back to a plain
        #    default so an action never completes silently.
        if self._SUCCESS:
            self.parser.ok(self._SUCCESS)
        elif self._EFFECT is None and self._AWARD is None:
            self.parser.ok(
                f"{self.character.name.capitalize()} uses the "
                f"{self.item.name} on the {self.target.name}."
            )


def use_item_on(
    name: str,
    *,
    item: str,
    target: str,
    effect: Callable | None = None,
    success: str | None = None,
    consume: bool = False,
    award: tuple | None = None,
    requires: Callable | None = None,
    aliases: list[str] | None = None,
    verb: str = "use",
    preposition: str = "on",
    description: str | None = None,
    duration: int | None = None,
    item_missing: str | None = None,
    target_missing: str | None = None,
) -> type[UseItemOn]:
    """Build a ``UseItemOn`` subclass for one two-object interaction.

    The only required pieces are *item* (X, which the actor must be holding)
    and *target* (Y, which must be present) -- everything else customizes the
    gate, the effect, and the narration.

    Args:
        name: The action's canonical ``ACTION_NAME`` and the command players
            type, e.g. ``"use wand on ooze"``. Multi-word, so the parser routes
            it ahead of the generic single verbs.
        item: The noun for X. Matched against the actor's held items (hand,
            worn, wielded, or a carried container).
        target: The noun for Y. Matched against items in the room/inventory,
            then against characters standing in the room.
        effect: ``effect(action) -> None`` -- the world mutation. The action
            instance exposes ``.game``, ``.parser``, ``.character`` (the actor),
            ``.item`` (X) and ``.target`` (Y). Omit for a pure-narration verb.
        success: Fixed narration emitted on success. Use this for the common
            case; let *effect* call ``action.parser.ok(...)`` itself when the
            line varies.
        consume: Remove X from the actor after a successful use (a thrown
            javelin, a poured drink).
        award: ``(key, points)`` or ``(key, points, text)`` forwarded to
            ``game.award`` for scoring; the 3-arg form narrates the award.
        requires: ``requires(action) -> str | None`` -- an extra precondition.
            Return an error message to block the action (shown to the player
            and fed back to a ReAct agent), or ``None`` to allow it. Use for
            target-state gates ("the spider is still watching", "the door is
            already open").
        aliases: Extra command phrasings the keyword parser should also accept
            (e.g. ``["zap ooze", "use the wand on the ooze"]``).
        verb, preposition: Spell sibling grammars -- ``verb="hit",
            preposition="with"`` reads ``HIT ... WITH ...``. Only used to build
            a sensible default ``ACTION_DESCRIPTION``; *name* still drives
            routing.
        description: Override the generated ``ACTION_DESCRIPTION``.
        duration: In-game minutes the action costs (issue #24), if any.
        item_missing, target_missing: Override the default "not holding X" /
            "no Y here" failure messages.

    Returns:
        A ``UseItemOn`` subclass ready to pass in a game's ``custom_actions``.
    """
    if description is None:
        description = f"{verb.capitalize()} the {item} {preposition} the {target}"

    # A readable class name for tracebacks: "use wand on ooze" -> UseWandOnOoze.
    class_name = "".join(w.capitalize() for w in name.split())

    return type(
        class_name,
        (UseItemOn,),
        {
            "ACTION_NAME": name,
            "ACTION_DESCRIPTION": description,
            "ACTION_ALIASES": list(aliases or []),
            "DURATION": duration,
            "_ITEM_NOUN": item,
            "_TARGET_NOUN": target,
            "_EFFECT": staticmethod(effect) if effect is not None else None,
            "_SUCCESS": success,
            "_CONSUME": consume,
            "_AWARD": award,
            "_REQUIRES": staticmethod(requires) if requires is not None else None,
            "_ITEM_MISSING": item_missing,
            "_TARGET_MISSING": target_missing,
        },
    )
