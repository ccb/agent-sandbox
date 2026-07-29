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


def _tile_address_parent(location):
    """The ``world:sector`` portion of a location's tile address, or ``None``.

    Penn's named rooms use arena-level addresses below a shared building
    sector.  The addressless campus hub intentionally has no parent: callers
    treat it as matching every place, mirroring the run analyzer's
    ``same_place_total`` classification.
    """
    address = getattr(location, "tile_address", None)
    if not address:
        return None
    return ":".join(str(address).split(":")[:2])


def travel_destination_allowed(game, character, destination) -> bool:
    """Whether ``character`` may travel to ``destination`` right now.

    A scheduled character may deviate to a genuinely different building, but
    cannot bounce among the lobby, rooms, and addressless campus hub that all
    represent its current place.  Within that same-place group, the plan's own
    stops -- the current scheduled stop and the *next* one -- are the only
    legal destinations, each until arrival.  Characters without an attached
    schedule retain the engine's unrestricted travel behavior.

    The next stop earns its place from #885: an agent whose finished stop is
    anchor-held (#838) has a prompt saying "your next stop is <room>" while a
    current-stop-only menu offers no same-building destination at all -- in
    #760 batch 7 the model then picked the nearest *name* on the menu, a
    lookalike room in a building 53 minutes away, and walked 55 minutes on it.
    The menu must offer the place the prompt promises.

    This is the single authority used both to curate cognition's travel choices
    and by :class:`Travel`'s parser gate, so free-text and oversized-enum
    fallbacks cannot bypass the model-facing menu.
    """
    schedule = getattr(getattr(character, "agent", None), "schedule", None)
    scheduled_name = getattr(schedule, "destination", None)
    current = getattr(character, "location", None)
    if schedule is None or not scheduled_name or current is None:
        return True

    scheduled = game.locations.get(scheduled_name)
    if scheduled is None:
        # Schedules are normally grounded during world construction.  If a
        # hand-built character carries an invalid stop, do not silently disable
        # all ordinary travel; the existing destination matching remains the
        # authoritative validation for that malformed setup.
        return True

    current_parent = _tile_address_parent(current)
    destination_parent = _tile_address_parent(destination)
    same_place = (
        current_parent is None
        or destination_parent is None
        or current_parent == destination_parent
    )
    if not same_place:
        return True
    if destination is scheduled:
        return current is not scheduled
    next_place = (getattr(schedule, "next_stop", None) or {}).get("place")
    next_loc = game.locations.get(next_place) if next_place else None
    if next_loc is not None and destination is next_loc:
        return current is not next_loc
    return False


def anchor_travel_refusal(game, character, destination):
    """Reason to refuse a leg that cannot beat the next pinned stop, or ``None``.

    The hard travel gate `docs/design/anchor-hold-context-826.md` held in
    reserve, armed by #885: in #760 batch 7 an agent whose context truthfully
    said "your next stop starts in 15 min" and "Houston Hall 53 min" still
    picked the 53-minute leg (a confusable-name slip its own reasoning
    contradicted) and walked 55 minutes on it. More context cannot fix an
    intent-vs-pick mismatch; a refusal that names the numbers can -- it becomes
    a #636 failure memory, and the model picks again next tick.

    Inert unless the loop stamped a clock (live runs only -- the bake threads
    none), the world has a map, and the schedule has an upcoming stop pinned to
    a still-future ``start_hour``. Walking to that anchored stop's own building
    or to the current scheduled stop is always legal, however late -- refusing
    the plan itself would strand the agent.
    """
    clock = getattr(game, "sim_clock", None)
    step_idx = getattr(game, "sim_clock_step", None)
    world_map = getattr(game, "world_map", None)
    schedule = getattr(getattr(character, "agent", None), "schedule", None)
    tile = getattr(character, "tile", None)
    address = getattr(destination, "tile_address", None)
    if clock is None or step_idx is None or world_map is None or not address:
        return None
    if schedule is None or tile is None:
        return None
    entries = getattr(schedule, "schedule", None) or []
    index = getattr(schedule, "stop_index", 0)
    gap_from = getattr(
        world_map, "walk_steps_from", getattr(world_map, "tile_gap_from", None)
    )
    if gap_from is None:
        return None
    if destination.name == getattr(schedule, "destination", None):
        return None
    now = clock.time_at(step_idx)
    minutes_now = now.hour * 60 + now.minute
    for entry in entries[index:]:
        hour = entry.get("start_hour")
        # Same validity rule as the renderer (#862): a raw out-of-range anchor
        # must not bind. Same no-day-roll convention as advance() (#863).
        if hour is None or hour not in range(24):
            continue
        until = hour * 60 - minutes_now
        if until <= 0:
            continue
        anchored = game.locations.get(entry.get("place"))
        if destination is anchored:
            return None
        parent = _tile_address_parent(destination)
        if parent is not None and parent == _tile_address_parent(anchored):
            return None
        walk = clock.minutes_for_steps(gap_from(tuple(tile), address))
        if walk <= until:
            return None
        return (
            f"Walking to {destination.name} takes about {walk} min, but your "
            f"next pinned stop -- {entry.get('activity')} at "
            f"{entry.get('place')} -- starts in {until} min. Go somewhere "
            f"nearer, or head to {entry.get('place')}."
        )
    return None


class Travel(base.Action):
    """Move the acting character to a named location (matched from the command).

    e.g. ``"travel to Hobbs Cafe"``. The logical move happens here; turning it
    into a believable on-screen walk is the exporter's job (it reads the new
    location's tile address and asks the pathfinder for a route)."""

    ACTION_NAME = "travel"
    ACTION_DESCRIPTION = "Travel to a named location in town"
    # The hub's engine connections are named ``to <location>``.  Register the
    # complete routed phrase as a multi-word alias so the parser selects Travel
    # before its generic direction detector sees that exit text and routes the
    # command through Go, bypassing this class's precondition gate.
    ACTION_ALIASES = ["travel to"]
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
        if not travel_destination_allowed(self.game, self.character, self.destination):
            scheduled = self.character.agent.schedule.destination
            if self.character.location is self.game.locations.get(scheduled):
                if _tile_address_parent(self.character.location) is None:
                    message = (
                        f"You are already at your scheduled stop, {scheduled}. "
                        "Stay here to perform, wait, or talk; this campus-wide "
                        "stop has no separate travel destination."
                    )
                else:
                    message = (
                        f"You are already at your scheduled stop, {scheduled}. "
                        "Stay here to perform, wait, or talk; only travel when "
                        "leaving for a genuinely different building."
                    )
            else:
                message = (
                    f"Keep heading to your scheduled stop, {scheduled}. "
                    f"Do not detour to {self.destination.name} within the same "
                    "place; travel to the scheduled stop or to a genuinely "
                    "different building."
                )
            self.parser.fail(message)
            return False
        refusal = anchor_travel_refusal(self.game, self.character, self.destination)
        if refusal:
            self.parser.fail(refusal)
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
    """The engine's Drink with Penn's boil-experiment specifics kept local.

    The generic sickness arc -- a sickening drink sets ``is_sick`` (+ a
    ``sickness`` GameEvent), boiled water cures it (+ ``recovery``) -- was
    upstreamed into the engine's Drink by #464; this subclass overrides only
    the ``_sickens`` gate and the effect hooks to pin what stays Penn's (#300):

    * the sicken gate: raw water (``requires_boiling`` and not ``is_boiled``)
      sickens -- the pair is deliberate: properties default to False, so
      gating on ``is_boiled`` alone would sicken every future drinkable. The
      cure is no longer overridden here: the engine's Drink already cures on
      *boiled* water only (aking526's #464 review moved that narrow rule
      upstream), which is what the #301 "did it learn to boil?" comparison
      needs;
    * the authoritative outcome counters (#595): ``drank_unboiled`` /
      ``drank_safe``, read directly by the experiment harness instead of
      parsing the event log;
    * the one-shot transition markers ``just_sickened`` / ``just_recovered``
      consumed by ``cognition.remember_outcome``, and the vivid
      ``sick_self_description`` wording the engine's #634 self-line emits.

    Registered with the same "drink" action name, so it overrides the
    built-in for this game only."""

    def _sickens(self) -> bool:
        # Penn's rule: this drink is raw water the agent did NOT boil first.
        return self.item.get_property(
            "requires_boiling"
        ) and not self.item.get_property("is_boiled")

    # No _cures override: the engine's Drink already cures on boiled water only
    # (aking526's #464 review moved the narrow rule upstream -- one rule, no
    # engine<->Penn divergence to decode later).

    def _apply_health_effects(self):
        if self.character.get_property("is_dead"):
            # The engine skips the arc on a corpse too; checked here as well
            # so the #595 counters below never stamp a drink that just killed.
            return
        # Authoritative outcome (#595): stamp which kind of drink this was.
        # "safe", not "boiled", for the else-branch: it also counts outside
        # the boil world, where safe drinks needn't involve a stove.
        if self._sickens():
            self.character.set_property(
                "drank_unboiled",
                (self.character.get_property("drank_unboiled") or 0) + 1,
            )
        else:
            self.character.set_property(
                "drank_safe",
                (self.character.get_property("drank_safe") or 0) + 1,
            )
        super()._apply_health_effects()

    def _sicken(self):
        super()._sicken()
        # Wording for the engine's is_sick self-line (#634): describe_for
        # emits this while sick -- one line, Penn's vivid phrasing.
        self.character.set_property(
            "sick_self_description",
            "You feel violently ill -- your stomach is cramping.",
        )
        # One-shot marker: this drink is what just sickened the character,
        # as opposed to an already-sick character drinking something clean.
        # Consumed (and cleared) by cognition.remember_outcome so the
        # high-importance memory attaches to the actual transition.
        self.character.set_property("just_sickened", True)

    def _recover(self):
        super()._recover()
        # One-shot marker mirroring just_sickened: cognition.remember_outcome
        # keys off it to write the "feel better" memory to the agent's card.
        self.character.set_property("just_recovered", True)


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
