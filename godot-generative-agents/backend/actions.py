"""Custom engine actions for the generative-agents port.

The world is a map you travel across, not a compass maze, and agents spend most
of their time *doing an activity* in place. Two small ``Action`` subclasses model
that, each going through the engine's precondition gate like any built-in action:

* :class:`Travel` -- move to a named location anywhere in town (the spatial,
  tile-by-tile walk is handled afterwards by the exporter via the pathfinder).
* :class:`Act` -- perform an activity at the current location, recorded on the
  character so the exporter can render it as the on-screen action label.
"""

from text_adventure_games.actions import base, consume, investigate
from text_adventure_games.enums import Property
from text_adventure_games.things.characters import MAX_ENERGY


class Travel(base.Action):
    """Move the acting character to a named location (matched from the command).

    e.g. ``"travel to Hobbs Cafe"``. The logical move happens here; turning it
    into a believable on-screen walk is the exporter's job (it reads the new
    location's tile address and asks the pathfinder for a route)."""

    ACTION_NAME = "travel"
    ACTION_DESCRIPTION = "Travel to a named location in town"
    # Typed tool slot (issues #356/#485): a tool-calling brain fills a
    # ``destination`` field instead of writing free text, and the ``connector``
    # reassembles its pick as ``"travel to <destination>"`` -- the same phrasing
    # the schedule mock emits, so :meth:`_match_destination` parses both
    # identically. The slot stays ``type: string`` because the engine's scope
    # kinds (item / character / direction) don't cover "any named location in
    # town"; :func:`cognition.action_tools_for` narrows it to an enum of the
    # world's real location names at decision time.
    ARGUMENTS_SCHEMA = {
        "destination": {
            "type": "string",
            "description": "the exact name of the location to travel to",
            "connector": "to",
            "required": True,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="traveler")
        self.destination = self._match_destination(command)

    def _match_destination(self, command: str):
        """Longest location name appearing in the command (case-insensitive)."""
        cmd = command.lower()
        best = None
        for name, loc in self.game.locations.items():
            if name.lower() in cmd and (best is None or len(name) > len(best.name)):
                best = loc
        return best

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is traveling."):
            return False
        if not self.was_matched(
            self.destination, "I don't know how to get to that place."
        ):
            return False
        return True

    def apply_effects(self):
        from_loc = self.character.location
        if from_loc is not None and self.character.name in from_loc.characters:
            from_loc.remove_character(self.character)
        self.destination.add_character(self.character)
        return self.parser.ok(
            f"{self.character.name} sets off for {self.destination.name}."
        )


class Act(base.Action):
    """Perform an activity in place, e.g. ``"perform tending the cafe counter"``.

    The activity text (everything after the verb) is stored on the character as
    the ``activity`` property; the exporter renders it as the action label."""

    ACTION_NAME = "perform"
    ACTION_DESCRIPTION = "Perform an activity at the current location"
    # Typed tool slot (issues #356/#485). The activity is genuinely free text --
    # it becomes the on-screen action label verbatim -- so the slot carries a
    # description rather than an enum, and reassembles as
    # ``"perform <activity>"``.
    ARGUMENTS_SCHEMA = {
        "activity": {
            "type": "string",
            "description": "the activity to do here, as a short present-tense "
            "phrase, e.g. 'reading in the stacks'",
            "required": True,
        },
        # Brain-authoritative pacing (#581). Optional meta-slots: how long to
        # stay, and the emoji to show while doing it. They are NOT part of the
        # routed command -- cognition.decide_with_action_tools pops them off the
        # tool call before reassembly, so they never reach the parser. The mock
        # never fills them, so the offline replay is byte-identical.
        "duration_minutes": {
            "type": "number",
            "description": "how many in-game minutes to spend on this activity "
            "before deciding again (optional; omit to use the planned duration)",
            "required": False,
        },
        "emoji": {
            "type": "string",
            "description": "a single emoji shown on the map while doing this "
            "(optional; omit to use the planned/persona default)",
            "required": False,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="actor")
        parts = command.split(" ", 1)
        self.activity = parts[1].strip() if len(parts) > 1 else ""

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is acting."):
            return False
        if self.character.location is None:
            self.parser.fail("There is nowhere to do that.")
            return False
        if not self.activity:
            self.parser.fail("There is no activity to perform.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("activity", self.activity)
        return self.parser.ok(f"{self.character.name} is {self.activity}.")


class WaitPenn(base.Wait):
    """The engine's Wait, offered to Penn brains with the #581 pacing slots
    (issue #614): a chosen wait *settles* like ``perform`` -- one decision, one
    tick of execution, then no re-decide until the duration elapses -- which is
    what retires the original objection to offering Wait (a per-decide Wait
    tool invites sitting idle and is recurring token spend). Registered under
    the same "wait" action name so it overrides the built-in for this game
    only (the DrinkPenn precedent). The step loop needs no change: its settle
    trigger is already "perform, OR any action that carried a model duration"
    (run_simulation.step), so a wait carrying ``duration_minutes`` settles and
    a schedule-spacer wait (no stash) stays a one-tick no-op -- byte-identical.
    """

    # duration_minutes is REQUIRED, unlike perform's optional slot: perform
    # falls back to the authored stop's steps, but a bare wait has nothing to
    # fall back to and would just re-decide every tick -- the exact spend the
    # settle design exists to kill. (A brain that omits it anyway degrades to
    # that one-tick wait: harmless, just not settled.)
    ARGUMENTS_SCHEMA = {
        "duration_minutes": {
            "type": "number",
            "description": "how many in-game minutes to wait before deciding " "again",
            "required": True,
        },
        "emoji": {
            "type": "string",
            "description": "a single emoji shown on the map while waiting "
            "(optional)",
            "required": False,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, command, actor=actor)
        self.character = self.acting_character(command, hint="waiter")

    def apply_effects(self):
        # Stamp "waiting" so the settle branch's card/desc reads honest idle
        # instead of the previous stop's stale activity -- but ONLY when this
        # wait actually settles (a real brain stashed a duration this decide;
        # observe_and_decide resets the stash every tick). The mock's schedule
        # spacers never stash, take the super() path verbatim, and the bake
        # stays byte-identical.
        agent = getattr(self.character, "agent", None)
        if getattr(agent, "last_duration_minutes", None) is not None:
            self.character.set_property("activity", "waiting")
        return super().apply_effects()


class DrinkPenn(consume.Drink):
    """The engine's Drink, plus the Penn boil-water twist (#300): drinking a
    liquid that ``requires_boiling`` and is not ``is_boiled`` sets ``is_sick``
    on the drinker and logs a ``sickness`` GameEvent -- the measurable
    motivation signal the self-coding experiment (#299) needs. The pair is
    deliberate: properties default to False, so gating on ``is_boiled`` alone
    would sicken every future drinkable; ``requires_boiling`` scopes the rule
    to raw water, and a (self-coded, #301) boil action clears it by setting
    ``is_boiled``. Registered with the same "drink" action name, so it
    overrides the built-in for this game only. Drinking specifically *boiled*
    water (``is_boiled``) while ``is_sick`` clears the sickness and logs a
    ``recovery`` event, so a full drink -> sicken -> boil -> drink -> recover arc
    is watchable. The cure is gated on ``is_boiled`` (not "any safe drink") on
    purpose: the #301 comparison asks whether an agent *learned to boil*, which
    a cure that any beverage could trigger would erase (upstreaming the generic
    slice is #464)."""

    def apply_effects(self):
        super().apply_effects()
        # If the drink just killed the drinker (the engine's Drink sets is_dead
        # on a poisonous item), the #300 health twist is moot: don't sicken or
        # "recover" a corpse -- a recovery on a dead agent would log the event
        # and a feel-better memory for someone who just died.
        if self.character.get_property("is_dead"):
            return
        if self.item.get_property("requires_boiling") and not self.item.get_property(
            "is_boiled"
        ):
            # Authoritative outcome (#595): this drink was raw water -- the
            # agent did NOT boil first. The harness reads this counter
            # directly instead of parsing the event log.
            self.character.set_property(
                "drank_unboiled",
                (self.character.get_property("drank_unboiled") or 0) + 1,
            )
            self.character.set_property("is_sick", True)
            # Wording for the engine's is_sick self-line (#634): describe_for
            # emits this while sick, replacing the Penn-local append cognition
            # used to add (#594) -- one line, Penn's vivid phrasing.
            self.character.set_property(
                "sick_self_description",
                "You feel violently ill -- your stomach is cramping.",
            )
            # One-shot marker: this drink is what just sickened the character,
            # as opposed to an already-sick character drinking something clean.
            # Consumed (and cleared) by cognition.remember_outcome so
            # the high-importance memory attaches to the actual transition.
            self.character.set_property("just_sickened", True)
            self.parser.ok(
                f"{self.character.name} clutches their stomach -- "
                "that water was foul."
            )
            self.game.log_event(
                self.character.name,
                "sickness",
                summary=(f"{self.character.name} got sick drinking {self.item.name}"),
                payload={
                    "item": self.item.name,
                    "location": getattr(self.character.location, "name", None),
                },
            )
        else:
            # Authoritative outcome (#595): any other successful, non-fatal
            # drink is safe -- boiled water, or water that never required
            # boiling -- hence "safe", not "boiled": this counter also stamps
            # outside the boil world, where safe drinks needn't involve a
            # stove. The harness reads it directly instead of parsing the
            # event log.
            self.character.set_property(
                "drank_safe",
                (self.character.get_property("drank_safe") or 0) + 1,
            )
            if self.character.get_property("is_sick") and self.item.get_property(
                "is_boiled"
            ):
                # The recovery half of the arc: drinking the *boiled* water
                # cures a sick drinker. Gated on is_boiled (not merely "not
                # raw") so an unrelated safe beverage can't stand in for
                # boiling -- that's the behavior the #301 "did it learn to
                # boil?" comparison rests on. Only fires on the sick->well
                # transition, so a healthy drinker logs nothing.
                self.character.set_property("is_sick", False)
                # One-shot marker mirroring just_sickened: cognition.remember_outcome
                # keys off it to write the "feel better" memory to the agent's card.
                self.character.set_property("just_recovered", True)
                self.parser.ok(
                    f"{self.character.name} drinks deep -- the clean "
                    "water settles their stomach, and the sickness passes."
                )
                self.game.log_event(
                    self.character.name,
                    "recovery",
                    summary=(
                        f"{self.character.name} recovered after drinking {self.item.name}"
                    ),
                    payload={
                        "item": self.item.name,
                        "location": getattr(self.character.location, "name", None),
                    },
                )


class EatPenn(consume.Eat):
    """The engine's Eat, plus the Penn energy payoff (#931): restores
    ``Property.ENERGY`` from the eaten item's ``energy_value``, capped at
    ``MAX_ENERGY``. This is the scaffold slice of the port from Action
    Castle's ``Eat`` (``text_adventure_games/adventures/action_castle.py``),
    which also gates re-eating behind a 16-in-game-hour cooldown
    (``ate_food``/``ate_at``) -- that cooldown is deliberately NOT ported yet
    (#931's open design question: a boolean-flag pair vs. a single
    ``NOT_HUNGRY_TIME`` timestamp), so this slice only wires the energy
    restore, the same way #300's ``DrinkPenn`` started with sickness before
    the drive/cooldown machinery existed. Registered with the same "eat"
    action name, so it overrides the built-in for this game only.

    Guarded like ``DrinkPenn``: if the item was poisonous and the engine's
    Eat just killed the character, don't also restore energy on a corpse."""

    def apply_effects(self):
        super().apply_effects()
        if self.character.get_property("is_dead"):
            return
        energy_value = self.item.get_property("energy_value") or 0
        current_energy = self.character.get_property(Property.ENERGY) or 0
        self.character.set_property(
            Property.ENERGY, min(MAX_ENERGY, current_energy + energy_value)
        )


class Activate(base.Action):
    """Switch on a fixed device -- a stove, a sink (#300). Devices are room
    fixtures (in scope, not necessarily held), marked with ``is_device``; the
    only effect is the ``is_on`` flag. Deliberately no downstream process: the
    stove heats nothing until the self-coding experiment (#299) writes one.
    Distinct verb from the engine's Light ("turn on" alias) -- no flame here."""

    ACTION_NAME = "activate"
    ACTION_DESCRIPTION = "Switch on a device (a stove, a sink)"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch on."
        ):
            return False
        if not self.item.get_property("is_device"):
            self.parser.fail(f"The {self.item.name} isn't something you can switch on.")
            return False
        if self.item.get_property("is_on"):
            self.parser.fail(f"The {self.item.name} is already on.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_on", True)
        return self.parser.ok(f"The {self.item.name} hums to life.")


class Deactivate(base.Action):
    """Switch off a device -- the inverse of :class:`Activate`."""

    ACTION_NAME = "deactivate"
    ACTION_DESCRIPTION = "Switch off a device (a stove, a sink)"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch off."
        ):
            return False
        if not self.item.get_property("is_device"):
            self.parser.fail(
                f"The {self.item.name} isn't something you can switch off."
            )
            return False
        if not self.item.get_property("is_on"):
            self.parser.fail(f"The {self.item.name} is already off.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_on", False)
        return self.parser.ok(f"The {self.item.name} winds down and goes quiet.")


class TalkTo(base.Action):
    """Agent-initiated conversation (issue #614): ``talk_to <person> [about
    <topic>]``.

    Conversation today only fires engine-side when two settled residents happen
    to be co-located (cognition.maybe_converse); this verb lets a brain CHOOSE
    "go find Marcus and ask him about the demo". The engine's Talk was checked
    for reuse and voices canned ``talk_text`` lines, not the LLM dialogue loop,
    so this is a new Penn-local verb (the DrinkPenn precedent).

    apply_effects does not run dialogue itself: it leaves a one-shot
    ``talk_request`` (+ optional ``talk_topic``) marker on the actor, which
    ``maybe_converse`` consumes THIS SAME TICK to open a #371
    ActiveConversation -- so bubbles/feed/#582 consequences all ride the
    existing machinery. The topic threads into the opener via the intent
    memory maybe_converse writes when the conversation actually opens (the
    dialogue seam's opener retrieval queries the partner's name and surfaces
    it) -- no new dialogue machinery, and a dropped request records nothing.

    Gate = the same fact curation reads (action_tools_for drops/enum-fills the
    tool from co-located living characters): target matched in the actor's room
    + alive + has an ``agent`` -- the same fact the engine's
    ``conversation.can_converse`` requires of both sides, which is what excludes
    build_world's silent "Observer" player (the engine's required player,
    never scripted with an agent) from ever being a talk target. "Conversations
    enabled" needs no explicit precondition: the verb is only reachable from a
    real tool-calling brain, and without one the marker is simply never
    consumed.
    """

    ACTION_NAME = "talk_to"
    ACTION_DESCRIPTION = "Start a conversation with someone at your location"
    ARGUMENTS_SCHEMA = {
        "person": {
            "type": "string",
            "description": "the name of the person to talk to (someone here)",
            "required": True,
        },
        "topic": {
            "type": "string",
            "description": "what to bring up, as a short phrase (optional)",
            "connector": "about",
            "required": False,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="talker")
        # Match the person against the pre-topic head only, so a topic that
        # happens to contain a resident's name can't hijack the match -- and
        # with the verb token dropped, since character_in_room scans by
        # substring and a resident named e.g. "Al" would match inside the
        # literal "talk_to".
        head, _, tail = command.partition(" about ")
        _, _, head = head.partition(" ")
        self.target = self.character_in_room(head, self.character)
        self.topic = tail.strip()

    def check_preconditions(self) -> bool:
        if self.target is None:
            self.parser.fail("There is no one by that name here to talk to.")
            return False
        if self.target.get_property("is_dead"):
            self.parser.fail(f"{self.target.name} is in no state to talk.")
            return False
        if getattr(self.target, "agent", None) is None:
            self.parser.fail(f"{self.target.name} is not up for a conversation.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("talk_request", self.target.name)
        if self.topic:
            self.character.set_property("talk_topic", self.topic)
        return self.parser.ok(
            f"{self.character.name} strikes up a conversation with "
            f"{self.target.name}."
        )


DEFAULT_STUDY_MINUTES = 30


class Study(base.Action):
    """Study in place (#615) -- the first arena-tier affordance verb (#617).

    Offered (and place-gated, via #612's shared declaration) only where
    something in scope carries the ``studyable`` arena tag #613 authored on
    the Van Pelt reading rooms. Effects mirror ``perform`` (an activity label
    the exporter renders) plus the visible state that distinguishes a study
    from a free-text perform: ``studied_minutes`` accumulates on the
    character. The ARGUMENTS_SCHEMA opts into the #581 pacing slots, so a
    live brain settles here for its chosen duration."""

    ACTION_NAME = "study"
    ACTION_DESCRIPTION = "Study here (only somewhere with a study space)"
    REQUIRED_AFFORDANCES = ("studyable",)
    ARGUMENTS_SCHEMA = {
        "topic": {
            "type": "string",
            "description": "what to study, as a short phrase, e.g. "
            "'thermodynamics problem sets' (optional)",
            "required": False,
        },
        # Brain-authoritative pacing (#581), same contract as `perform`:
        # popped off the tool call before reassembly, never reach the parser.
        "duration_minutes": {
            "type": "number",
            "description": "how many in-game minutes to spend studying "
            "before deciding again (optional; omit to use the planned duration)",
            "required": False,
        },
        "emoji": {
            "type": "string",
            "description": "a single emoji shown on the map while studying "
            "(optional; omit to use the planned/persona default)",
            "required": False,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="studier")
        parts = command.split(" ", 1)
        self.topic = parts[1].strip() if len(parts) > 1 else ""

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is studying."):
            return False
        # The #612 place-check: same fact the toolset builder read to offer
        # this verb, so offered <=> this passes (the #617 invariant).
        if not self.has_affordance_in_scope(
            self.character,
            error_message="There is nothing to study here -- find a study space.",
        ):
            return False
        return True

    def apply_effects(self):
        activity = f"studying {self.topic}" if self.topic else "studying"
        self.character.set_property("activity", activity)
        # The brain's duration pick for THIS decision -- validated by
        # cognition._take_pacing_args when stashed and clamped by the step
        # loop to the run's cog.duration_*_minutes before the command routed,
        # so this ledger matches the settled wall-time -- or a flat default
        # when absent (the mock path, or a brain that gave none). The floor
        # guards paths that route a command without the step loop.
        minutes = getattr(
            getattr(self.character, "agent", None), "last_duration_minutes", None
        )
        if minutes is None:
            minutes = DEFAULT_STUDY_MINUTES
        minutes = max(1, int(round(minutes)))
        prev = self.character.get_property("studied_minutes")
        self.character.set_property(
            "studied_minutes", (int(prev) if prev else 0) + minutes
        )
        # One-shot marker (the just_sickened pattern): the delta this study
        # added, consumed by cognition.remember_outcome for the memory line.
        self.character.set_property("just_studied_minutes", minutes)
        return self.parser.ok(f"{self.character.name} is {activity}.")


class CheckOutBook(base.Action):
    """Check a library book out from the shelf (#616) -- Penn's first
    object-tier verb: the book moves shelf -> inventory and records who has
    it, which is what unlocks the engine's ``read`` (the book travels in the
    borrower's pocket, so READABLE stays in their scope).

    The affordance is the SHELF, not the book: ``book_shelf`` rides on the
    ungettable shelf Item, so the verb is offered exactly in the shelf's
    arena (#612 offered <=> place-check) -- including after every book is
    borrowed, where the gate then explains who has what. Books are not
    GETTABLE, so checkout is the only path into a pocket and
    ``checked_out_by`` can never be bypassed by a plain ``get``. There is
    deliberately no return verb (YAGNI until agents hoard)."""

    ACTION_NAME = "check_out_book"
    ACTION_DESCRIPTION = "Check out a library book from the shelf"
    REQUIRED_AFFORDANCES = ("book_shelf",)
    ARGUMENTS_SCHEMA = {
        "book": {
            "type": "item",
            "description": "the exact name of the book to check out",
            "required": True,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="borrower")
        self.book = self._match_book(command)

    def _match_book(self, command: str):
        """The named book: in the actor's own scope, or -- so the gate can say
        WHO has it instead of "I don't see it" -- checked out by someone here
        (the simultaneous-round contention case, issue #42: both decided
        against the same turn-start shelf, the loser re-checks after the book
        already moved into the winner's inventory)."""
        if self.character is None:
            return None
        items_in_scope = self.parser.get_items_in_scope(self.character)
        loc = self.character.location
        # Every library book the command could mean, as ONE pool: books in the
        # actor's own scope (shelf or pocket) plus books checked out by someone
        # standing here. One pool means the longest-name tie-break resolves the
        # exact title even when a shorter-named cousin is still shelved, and a
        # borrowed book always reaches the "checked out by X" gate instead of
        # being shadowed by whatever else shares a word with it.
        books = {
            name: item
            for other in (loc.characters.values() if loc is not None else ())
            if other is not self.character
            for name, item in other.inventory.items()
            if item.get_property("library_book")
        }
        books.update(
            (name, item)
            for name, item in items_in_scope.items()
            if item.get_property("library_book")
        )
        book = self.parser.match_item(command, books, hint=None)
        if book is not None:
            return book
        # No library book named: match any in-scope item so the gate can say
        # "The X isn't a library book" instead of "I don't see it".
        return self.parser.match_item(command, items_in_scope, hint=None)

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is checking out a book."):
            return False
        if not self.has_affordance_in_scope(
            self.character,
            "There is no library shelf to check a book out from here.",
        ):
            return False
        if self.book is not None:
            holder = self.book.get_property("checked_out_by")
            if holder:
                message = (
                    f"You already have {self.book.name} checked out."
                    if holder == self.character.name
                    else f"The {self.book.name} is already checked out by {holder}."
                )
                self.parser.fail(message)
                return False
        if not self.was_matched(self.book, "I don't see that book on the shelf."):
            return False
        if not self.book.get_property("library_book"):
            self.parser.fail(f"The {self.book.name} isn't a library book.")
            return False
        return True

    def apply_effects(self):
        # add_to_inventory removes the book from the shelf's location itself.
        self.character.add_to_inventory(self.book)
        self.book.set_property("checked_out_by", self.character.name)
        return self.parser.ok(
            f"{self.character.name} checks out {self.book.name} from the shelf."
        )


class ReadPenn(investigate.Read):
    """The engine's Read with the Penn tool-schema enrichments (#616): a typed
    item slot (scope-enum'd like every engine item slot) and the #581
    duration/emoji pacing meta-slots, so a live brain can settle in with a
    book instead of skimming it in one tick. Registered under the same "read"
    name, overriding the built-in for this game only (the DrinkPenn
    precedent). Gate, narration, and the READABLE affordance declaration are
    all inherited unchanged."""

    ARGUMENTS_SCHEMA = {
        "item": {
            "type": "item",
            "description": "the exact name of the thing to read",
            "required": True,
        },
        # Brain-authoritative pacing (#581), same contract as Act: popped off
        # the tool call before command reassembly, never seen by the parser.
        "duration_minutes": {
            "type": "number",
            "description": "how many in-game minutes to spend reading "
            "before deciding again (optional; omit to use the planned duration)",
            "required": False,
        },
        "emoji": {
            "type": "string",
            "description": "a single emoji shown on the map while reading "
            "(optional; omit to use the planned/persona default)",
            "required": False,
        },
    }
