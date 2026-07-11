from .things import Location, Character
from .things.characters import DEFAULT_VISION_R
from .clock import GameClock
from .config import GameConfig
from . import parsing, actions, blocks, perception
from .enums import EventKind, Property
from .events import GameEvent
from .triggers import Trigger, at_turn

import json
import inspect
from collections import namedtuple

# Affordance properties surfaced in describe_for() so an agent can see, at a
# glance, what the engine will let it do with an item. Kept as a tuple of
# strings so a game can extend it via a new Property member without touching
# this list -- the values resolve through Thing.get_property either way.
_AFFORDANCE_KEYS = (
    Property.GETTABLE,
    Property.EDIBLE,
    Property.DRINKABLE,
    Property.FLAMMABLE,
    Property.WEARABLE,
    Property.WIELDABLE,
)


def _format_item(item) -> str:
    """Render an item as 'name - description [aff1, aff2]'.

    The bracketed affordance hint is omitted when no well-known affordance
    is set, so scenery (no tags) reads the same as before.
    """
    base = f"{item.name} - {item.description}"
    tags = [str(k) for k in _AFFORDANCE_KEYS if item.get_property(k)]
    if tags:
        base += f" [{', '.join(tags)}]"
    return base


class Game:
    """
    The Game class keeps track of the state of the world, and describes what
    the player sees as they move through different locations.

    Internally, we use a graph of Location objects and Item objects, which can
    be at a Location or in the player's inventory.  Each locations has a set of
    exits which are the directions that a player can move to get to an
    adjacent location. The player can move from one location to another
    location by typing a command like "Go North".
    """

    def __init__(
        self,
        start_at: Location,
        player: Character,
        characters=None,
        custom_actions=None,
        time_config=None,
        turn_mode=None,
        config=None,
    ):
        self.start_at = start_at
        self.player = player

        # Unified config (see config.py). Every field defaults to the engine's
        # historical value, so an omitted config -- or a bare GameConfig() -- is
        # a no-op. The explicit `time_config`/`turn_mode` arguments still work and
        # take precedence over the config's clock/turn_mode, for back-compat.
        self.config = config if config is not None else GameConfig()

        # Print the special commands associated with items in the game (helpful
        # for debugging and for novice players).
        self.give_hints = self.config.engine.give_hints

        # Records history of commands, states, and descriptions
        self.game_history = []

        # The journal: every turn-consuming player command, in order (the iOS
        # app design, docs/design/ios-tomb-app.md §2). Because a game is
        # deterministic once its RNG is seeded, (seed, journal) IS the save
        # file: restore = rebuild + replay(). FREE actions (Inventory, Help)
        # and failed commands change no state, so they are not recorded.
        self.journal: list[str] = []

        self.game_over = False
        self.game_over_description = None

        # Scoring (cross-cutting). Inert by default: a game that never calls
        # award() and leaves max_score at 0 behaves exactly as before. Games
        # with a point table set max_score and call award() at each milestone.
        self.score = 0
        self.max_score = 0
        self._scored_keys = set()
        # InvisiClues-style progressive hints (hints.py): registered topics,
        # per-topic reveal depth, and the honesty counter games may stamp on
        # the final score. Progress replays from the journal (HINT is a
        # journaled free action), so saves keep what was revealed.
        self.hints = []
        self.hint_progress = {}
        self.hints_taken = 0

        # Illustration cards already cued (show_figure fires once per key,
        # like award's idempotence set). Rebuilt by journal replay for free.
        self.figures_shown = set()

        # Add player to game and put them on starting point
        self.characters = {}
        self.add_character(player)
        self.start_at.add_character(player)
        self.start_at.has_been_visited = True

        # Add NPCs to game
        if characters:
            for c in characters:
                if isinstance(c, Character):
                    self.add_character(c)
                else:
                    err_msg = f"ERROR: invalid character ({c})"
                    raise Exception(err_msg)

        # Look up table for locations
        def location_map(location, acc):
            acc[location.name] = location
            for _, connection in location.connections.items():
                if connection.name not in acc:
                    acc = location_map(connection, acc)
            return acc

        self.locations = location_map(self.start_at, {})

        # Turn counter
        self.turn = 0

        # Event log (issue #6): append-only record of what happened each round
        self.events = []
        # Index into `events` marking the start of the current round (set by
        # do_command / run_simultaneous_round before the player acts). Lets a
        # react-phase trigger ask "what happened *this round*" without relying on
        # the turn counter, which increments mid-round (see disturbances_this_round).
        self._round_event_start = 0

        # Triggers (issue #6): rules fired in the post-round react phase
        self.triggers = []

        # Crafting recipes (see crafting.py). Empty by default, so games without
        # crafting are unchanged and the parser's crafting verbs stay inert.
        # Runtime-only (recipes hold a factory callable), like triggers.
        self.recipes = []

        # Recipes the player has discovered (issue #135). A recipe declared
        # known=False is craftable only once its name/alias is learned via
        # learn_recipe(); recipes with the default known=True ignore this set.
        self.learned_recipes = set()

        # Posed prompt (issue #110): a question the game is currently asking the
        # player (e.g. "wits or steel?"). Consulted by the parser as a fallback
        # for an otherwise-unrecognized command. Transient conversational state,
        # like a character's behavior -- not serialized. See prompts.py.
        self._pending_prompt = None

        # Optional in-game clock (issue #7). Time is opt-in: with neither a
        # time_config nor an enabled clock in the config, the turn counter still
        # increments but no clock exists. An explicit time_config (a GameClock or
        # a dict of GameClock kwargs) wins; otherwise config.clock builds one when
        # enabled.
        if time_config is not None:
            if isinstance(time_config, GameClock):
                self.clock = time_config
            elif isinstance(time_config, dict):
                self.clock = GameClock(**time_config)
            else:
                err_msg = f"ERROR: invalid time_config ({time_config})"
                raise Exception(err_msg)
        elif self.config.clock.enabled:
            clock_cfg = self.config.clock
            self.clock = GameClock(
                start_hour=clock_cfg.start_hour,
                start_minute=clock_cfg.start_minute,
                minutes_per_turn=clock_cfg.minutes_per_turn,
                periods=clock_cfg.periods,
            )
        else:
            self.clock = None

        # Turn mode (issue #25). "sequential" (default) is the classic loop:
        # the player acts, then each NPC observes and acts in order.
        # "simultaneous" runs a gather -> resolve round instead (see turns.py):
        # every NPC agent decides against the turn-start snapshot, then
        # commands resolve player-first and in initiative order. An explicit
        # turn_mode argument overrides config.engine.turn_mode.
        mode = turn_mode if turn_mode is not None else self.config.engine.turn_mode
        if mode not in ("sequential", "simultaneous"):
            err_msg = f"ERROR: invalid turn_mode ({mode})"
            raise Exception(err_msg)
        self.turn_mode = mode

        # Resolution phases (issue #42): an optional action -> phase-rank map that
        # orders the simultaneous resolve phase ("talk before move before fight").
        # config.engine.phases controls it: False (default) -> plain initiative
        # order; True -> turns.DEFAULT_PHASES; a dict -> that custom map. You can
        # still assign ``game.phases`` directly afterward.
        engine_phases = self.config.engine.phases
        if engine_phases is True:
            from .turns import DEFAULT_PHASES

            self.phases = DEFAULT_PHASES
        elif isinstance(engine_phases, dict):
            self.phases = engine_phases
        else:
            self.phases = None

        # Engine caps read from config (defaults reproduce the old module
        # constants). The trigger phase and the NPC turn loop read these.
        self._cascade_passes = self.config.engine.cascade_passes
        self._max_actions_per_turn = self.config.engine.max_actions_per_turn

        # Parser
        self.custom_actions = custom_actions
        self.set_parser(parsing.Parser(self))

        # Visit each location and add any blocks found to parser
        seen_before = {}
        for name, location in self.locations.items():
            if len(location.blocks) > 0 and name not in seen_before:
                for b in location.blocks:
                    self.parser.add_block(b)
                    seen_before[name] = True

    def do_command(self, command: str) -> bool:
        """
        Public entry point for processing a player command. In the default
        sequential mode, parses the command and, if successful, runs the
        end-of-turn phase (increment turn counter, run NPC behaviors). In
        simultaneous mode (issue #25), runs a gather -> resolve round instead.
        """
        if self.turn_mode == "simultaneous":
            # Local import: turns.py imports npc.py, and the default
            # sequential path shouldn't need either module to run.
            from .turns import run_simultaneous_round

            return run_simultaneous_round(self, command)

        # A comma-separated list is a sequence: run each sub-command as its own
        # full turn, so NPC turns and the react phase (triggers) fire *between*
        # them -- behaving exactly as if the commands were typed one per line. A
        # trigger keyed to a state you only pass through mid-sequence (e.g.
        # visiting a room) still fires. Empty segments (a trailing/doubled comma)
        # are skipped; a game-ending sub-command stops the rest.
        if "," in command:
            results = []
            for part in command.split(","):
                part = part.strip()
                if not part:
                    continue
                if self.is_game_over():
                    break
                results.append(self.do_command(part))
            return all(results) if results else False

        # A finished game closes the parser (CCB: the dead were still walking).
        # Only verbs that leave the ended story intact pass: RESTORE a save,
        # SCRIPT the record, RESTART (for shells that offer it above this
        # loop) -- and the read-only ledger (INVENTORY, SCORE), so the final
        # accounting of wounds and slots can be studied post-mortem.
        if self.is_game_over():
            first = command.strip().split(" ", 1)[0].lower()
            if first not in (
                "restore",
                "script",
                "restart",
                "inventory",
                "inv",
                "i",
                "score",
                "hint",
                "hints",
            ):
                self.parser.fail(
                    (
                        "The story has ended. "
                        if self.is_won()
                        else "Death has this expedition now. "
                    )
                    + "Type RESTORE to return to a saved position, or "
                    "RESTART to begin anew."
                )
                return False

        # The player is the subject of any command entered here, so pass them as
        # the explicit actor. This keeps the event log correct even when the
        # command names another character (e.g. "attack troll") — without it the
        # parser falls back to scanning the command for a name and would mis-log
        # the event under the named target instead of the player.
        self._round_event_start = len(self.events)  # this command begins a round
        success = self.parser.parse_command(command, actor=self.player)
        if success:
            # A FREE action (Inventory, Help) is the player consulting their
            # own memory, not the character acting: it reports without
            # advancing the round -- no turn tick, no NPC turns, no triggers.
            # config.engine.meta_actions_cost_turns restores the classic
            # everything-costs-time behavior.
            last = getattr(self.player, "last_action", None)
            if (
                getattr(last, "FREE_ACTION", False)
                and not self.config.engine.meta_actions_cost_turns
            ):
                # A JOURNALED free action costs no turn but must survive the
                # (seed, journal) replay -- HINT reveals, e.g., would silently
                # vanish from a restored game otherwise.
                if getattr(last, "JOURNALED", False):
                    self.journal.append(command)
                return success
            # A turn-consuming success enters the journal (a comma-sequence
            # journals part by part via the recursion above, so a replay of
            # the journal never re-splits). Failed commands and FREE actions
            # change no state and are deliberately absent.
            self.journal.append(command)
            self.end_turn()
        return success

    def replay(self, commands, quiet: bool = True) -> int:
        """Re-run *commands* through :meth:`do_command`, by default with
        rendering suppressed -- the restore half of a (seed, journal) save
        (docs/design/ios-tomb-app.md §2). Returns the number of commands run.

        Replayed commands re-enter :attr:`journal` exactly as they did live, so
        after a replay the journal equals the commands that succeeded -- saving
        again works without special cases. Stops early if the game ends.
        """
        from .reporting import CaptureRenderer

        old_renderer = self.parser.renderer
        if quiet:
            self.parser.set_renderer(CaptureRenderer())
        ran = 0
        try:
            for command in commands:
                if self.is_game_over():
                    break
                self.do_command(command)
                ran += 1
        finally:
            if quiet:
                self.parser.set_renderer(old_renderer)
        return ran

    def end_turn(self):
        """
        Called after a successful player command. Increments the turn counter,
        gives each living, conscious NPC a chance to act, and then runs the
        react phase: triggers (including scheduled events) whose conditions
        are now true.
        """
        self.turn += 1
        for character in list(self.characters.values()):
            if character is self.player:
                continue
            if character.get_property(Property.IS_DEAD) or character.get_property(
                Property.IS_UNCONSCIOUS
            ):
                continue
            if character.location is None:
                continue
            character.take_turn(self)
            if self.is_game_over():
                break
        if not self.is_game_over():
            self._run_triggers()

    def log_event(self, actor, action, summary="", payload=None):
        """Append a GameEvent to the event log (issue #6)."""
        self.events.append(GameEvent(self.turn, actor, action, summary, payload))

    def emit_sound(self, location, radius, description):
        """Emit an ambient noise at *location* -- a sound that no actor's command
        produced (a slamming door, a wailing baby, distant thunder).

        Logs a ``EventKind.SOUND`` event whose payload matches a noisy action's
        (``location``/``heard_radius``/``sound``), so perception and startle
        reactions treat it exactly like the sound of an action: it is heard in its
        origin room and carries ``radius`` hops outward. The source owns its
        volume -- the door declares "I am loud," not whatever reacts to it.

        ``radius`` is the number of room-hops the sound carries beyond its origin
        (>= 1 for a noise meant to be heard). A player within earshot but in
        another room overhears it narrated, mirroring a loud action."""
        loc = location if hasattr(location, "name") else self.locations.get(location)
        loc_name = getattr(loc, "name", location)
        payload = {
            "location": loc_name,
            "dest": None,
            "dir": None,
            "heard_radius": radius,
            "sound": description,
        }
        self.log_event(None, EventKind.SOUND, description, payload=payload)
        # Let a player in earshot but elsewhere overhear it (same courtesy the
        # parser extends to a loud action; the source room narrates it itself).
        player = getattr(self, "player", None)
        if (
            radius > 0
            and loc_name
            and player is not None
            and player.location is not None
        ):
            heard = self.audible_rooms(loc_name, radius)
            if player.location.name in heard:
                direction = heard[player.location.name]
                where = {
                    "up": "above",
                    "down": "below",
                }.get(
                    direction, f"the {direction}" if direction else "somewhere nearby"
                )
                self.parser.ok(f"From {where} you hear {description}.")

    def disturbances_this_round(self, location_name):
        """``(actor_name, action_name)`` for every action taken at
        ``location_name`` during the current round (since the player's command
        began this turn).

        This is the multi-agent-safe way to ask "what just happened here." It
        reads the round's logged events rather than the single global
        ``parser.last_action`` -- so it sees *every* actor's move, not merely
        whoever acted last, and keeps working once turns become per-agent (#25)."""
        return [
            (e.actor, e.action)
            for e in self.events[self._round_event_start :]
            if (e.payload or {}).get("location") == location_name
        ]

    def sounds_audible_at(self, location, exclude=None):
        """The sounds heard at *location* this round, as a list of
        ``{"description", "direction", "origin"}`` dicts.

        A "sound" is any event with ``heard_radius > 0`` -- a noisy action or an
        ``emit_sound`` ambient noise. It is audible in its origin room
        (``direction`` None) and ``radius`` hops outward (``direction`` = the way
        back toward the source, from :meth:`audible_rooms`). This is the
        multi-agent-safe stimulus a startle reaction reads: "is there any sound
        where I'm standing?" -- near or far, by the same hearing machinery
        perception uses. ``exclude`` (an actor name) drops a thing's own sounds so
        it never startles at itself."""
        loc_name = getattr(location, "name", location)
        sounds = []
        for e in self.events[self._round_event_start :]:
            payload = e.payload or {}
            radius = payload.get("heard_radius") or 0
            if radius <= 0:
                continue
            if exclude is not None and e.actor == exclude:
                continue
            origin = payload.get("location")
            if not origin:
                continue
            description = payload.get("sound") or "a commotion"
            if origin == loc_name:
                sounds.append(
                    {"description": description, "direction": None, "origin": origin}
                )
            else:
                reach = self.audible_rooms(origin, radius)
                if loc_name in reach:
                    sounds.append(
                        {
                            "description": description,
                            "direction": reach[loc_name],
                            "origin": origin,
                        }
                    )
        return sounds

    def entered_this_round(self, thing, location):
        """True if *thing* moved *into* *location* during the current round.

        Reads the round's movement events (a successful move logs origin in
        ``payload["location"]`` and destination in ``payload["dest"]``), so it is
        multi-agent-safe and sees arrivals by any actor. This is the stimulus a
        :class:`~text_adventure_games.reactions.Reaction` keys on when it should
        fire the moment a particular creature is driven into a room -- e.g. the
        poacher's countdown starting when the doe is cornered."""
        thing_name = getattr(thing, "name", thing)
        loc_name = getattr(location, "name", location)
        for e in self.events[self._round_event_start :]:
            if e.actor != thing_name:
                continue
            payload = e.payload or {}
            if payload.get("dest") == loc_name and payload.get("location") != loc_name:
                return True
        return False

    def add_disturbance_trigger(
        self,
        location,
        reaction,
        *,
        loud=None,
        safe=None,
        extra=None,
        present=None,
        exclude=None,
        name=None,
    ):
        """Register a trigger that fires when something disturbs ``location``
        this round, calling ``reaction(game, cause)``.

        A disturbance is, in order: whatever ``extra(game)`` reports -- a
        scene-specific noise such as a slamming door or a wailing baby, returned
        as a cause phrase (or None); or a *loud* action taken at the location by
        a present actor (its name in ``loud``); or -- if ``safe`` is given
        instead of ``loud`` -- any action there NOT in ``safe`` (the "anything
        but X" framing a standoff uses). ``present(game)`` optionally gates the
        whole thing on the threat still being active; ``exclude`` names an actor
        whose own actions don't count.

        Multi-agent-safe: it inspects the round's events (disturbances_this_round),
        never ``parser.last_action``."""
        loc_name = getattr(location, "name", location)

        def _cause(g):
            if extra is not None:
                reported = extra(g)
                if reported:
                    return reported
            for actor, act in g.disturbances_this_round(loc_name):
                if actor == exclude:
                    continue
                disturbing = (
                    act in loud
                    if loud is not None
                    else (safe is not None and act not in safe)
                )
                if disturbing:
                    return (
                        "your sudden racket"
                        if actor == g.player.name
                        else f"the {actor}'s racket"
                    )
            return None

        self.add_trigger(
            name or f"disturbance:{loc_name}",
            lambda g: (present is None or present(g)) and _cause(g) is not None,
            lambda g: reaction(g, _cause(g)),
            repeatable=True,
        )

    def add_trigger(self, name, condition, action, repeatable=False):
        """Register a Trigger evaluated in the post-round react phase (issue #6)."""
        trigger = Trigger(name, condition, action, repeatable)
        self.triggers.append(trigger)
        return trigger

    def add_reaction(self, thing, reaction):
        """Attach a :class:`~text_adventure_games.reactions.Reaction` to *thing*
        and register it for the react phase.

        Sets the reaction's ``owner`` and ``game``, appends it to
        ``thing.reactions``, and wires it into the trigger driver so it is
        evaluated each round after every actor has moved: the reaction's
        ``check_preconditions`` becomes the trigger condition (it stashes
        ``cause``) and its ``apply_effects`` the trigger action.
        ``Reaction.REPEATABLE`` selects one-shot (the default -- flee/wake once)
        vs. re-arming-every-round semantics.

        Runtime-only, like ``behavior``: re-attach reactions in ``build_game``;
        they are never serialized."""
        reaction.owner = thing
        reaction.game = self
        thing.reactions.append(reaction)
        self.add_trigger(
            reaction.name,
            lambda g, r=reaction: r.check_preconditions(),
            lambda g, r=reaction: r.apply_effects(),
            repeatable=reaction.REPEATABLE,
        )
        return reaction

    def add_recipe(self, recipe):
        """Register a crafting Recipe (see crafting.py). The Craft action and the
        parser's crafting verbs consult ``self.recipes``."""
        self.recipes.append(recipe)
        return recipe

    def learn_recipe(self, name):
        """Mark a crafting recipe known by *name* (issue #135), making a recipe
        declared ``known=False`` craftable. Wire this to a recipe book, an NPC,
        examine text, etc. Case-insensitive; matches a recipe's name or any of
        its aliases (see ``Recipe.names``)."""
        self.learned_recipes.add(str(name).lower())

    def pose_prompt(self, prompt):
        """Pose a question to the player (issue #110). While it is pending, the
        parser reads an otherwise-unrecognized command as the answer. Posing a
        new prompt replaces any previous one. See prompts.py."""
        prompt.location = self.player.location.name if self.player.location else None
        self._pending_prompt = prompt
        return prompt

    def pending_prompt(self):
        """The question currently posed to the player, or None."""
        return self._pending_prompt

    def clear_prompt(self):
        """Withdraw any posed prompt."""
        self._pending_prompt = None

    def relocate(self, character, destination) -> None:
        """Move *character* to *destination* (bookkeeping only -- no narration).

        The single low-level "a character changes location" primitive. Movement
        verbs (Go) and games that teleport characters route through here, so
        following (drag_followers) and any future location-change concerns have
        one chokepoint."""
        src = character.location
        if src is not None and character.name in getattr(src, "characters", {}):
            src.remove_character(character)
        destination.add_character(character)  # also sets character.location

        # A ridden vehicle/mount travels with its rider (actions/vehicles.py):
        # move it into the destination room so it's there to dismount or ride on.
        vehicle = getattr(character, "riding", None)
        if vehicle is not None:
            src_room = getattr(vehicle, "location", None)
            if src_room is not None and vehicle.name in getattr(src_room, "items", {}):
                src_room.remove_item(vehicle)
            destination.add_item(vehicle)

        # A posed question (issue #110) is moot once the player walks away from
        # where it was asked -- unless it was marked sticky.
        prompt = self._pending_prompt
        if (
            character is self.player
            and prompt is not None
            and not prompt.sticky
            and prompt.location != destination.name
        ):
            self._pending_prompt = None

    def drag_followers(self, leader, _visited=None) -> None:
        """Move everyone following *leader* to the leader's current location, then
        recurse (so a follow-chain A->B->C all arrives together). Cycle-safe.

        Called as part of the leader's MOVE (see Go / a game's relocate), so a
        follower travels during the leader's turn -- not on its own later turn --
        which keeps following correct regardless of turn order or turn mode. A
        follower may decline a destination via its ``follow_filter`` (e.g. a
        companion who won't enter the castle); it then stays put but keeps
        following, ready to rejoin when the leader returns."""
        if _visited is None:
            _visited = {leader.name}
        dest = leader.location
        if dest is None:
            return
        leader_ref = "you" if leader is self.player else leader.name
        for other in list(self.characters.values()):
            if (
                other.name in _visited
                or getattr(other, "following", None) is not leader
            ):
                continue
            _visited.add(other.name)
            follow_filter = getattr(other, "follow_filter", None)
            if follow_filter is not None and not follow_filter(dest):
                # Announce the refusal once per "stuck" episode, not again on
                # every subsequent step the leader takes while it waits behind.
                if not getattr(other, "_follow_refusal_announced", False):
                    self.parser.npc_ok(
                        f"{other.name.capitalize()} won't go any farther."
                    )
                    other._follow_refusal_announced = True
                continue
            if other.location is dest:
                # The leader stepped back into the room where the follower was
                # waiting -- it's already at their side, so don't re-announce.
                other._follow_refusal_announced = False
                self.drag_followers(other, _visited)
                continue
            self.relocate(other, dest)
            other._follow_refusal_announced = False
            self.parser.npc_ok(f"{other.name.capitalize()} follows {leader_ref}.")
            self.drag_followers(other, _visited)

    def _run_triggers(self):
        """React phase: fire triggers whose conditions are now true.

        Re-evaluates in bounded passes so a trigger can enable another one
        (cascading), but each trigger fires at most once per round and the chain
        is capped at config.engine.cascade_passes (default MAX_CASCADE_PASSES)
        to prevent infinite loops.
        """
        fired_this_round = set()
        for _ in range(self._cascade_passes):
            newly_fired = False
            for trigger in self.triggers:
                if trigger in fired_this_round:
                    continue
                if trigger.fired and not trigger.repeatable:
                    continue
                if trigger.condition(self):
                    trigger.action(self)
                    trigger.fired = True
                    fired_this_round.add(trigger)
                    self.log_event(
                        EventKind.TRIGGER, trigger.name, f"{trigger.name} fired"
                    )
                    newly_fired = True
            if not newly_fired:
                break

    def schedule_event(self, turn: int, callback, name=None):
        """
        Schedule a one-shot event: `callback(game)` will run in the react phase
        of the round in which the turn counter reaches `turn` (after all
        characters have acted). Scheduling for a turn that has already passed
        fires the event in the next round's react phase.

        This is convenience sugar for the trigger system (issue #6): it
        registers a non-repeatable trigger with an `at_turn(turn)` condition,
        so scheduled events follow trigger semantics — they fire at most once,
        run in the react phase, and are recorded in the event log. Returns the
        underlying Trigger.

        For a recurring event, schedule a future turn from the callback:

            def every_morning(game):
                ...do something...
                game.schedule_event(game.turn + 4, every_morning)

        (Or use `add_trigger` with the `every(n)` condition and
        `repeatable=True` for a fixed cadence.)
        """
        if not isinstance(turn, int) or turn < 0:
            err_msg = f"ERROR: invalid schedule turn ({turn})"
            raise Exception(err_msg)
        if not callable(callback):
            err_msg = f"ERROR: schedule callback is not callable ({callback})"
            raise Exception(err_msg)
        if name is None:
            name = f"scheduled@turn{turn}"
        return self.add_trigger(name, at_turn(turn), callback, repeatable=False)

    def current_time(self):
        """
        The in-game time as a string, e.g. '8:45 AM (morning)', or None if
        this game has no clock configured.
        """
        if self.clock is None:
            return None
        return self.clock.describe(self.turn)

    def game_loop(self):
        """
        A simple loop that starts the game, loops over commands from the user,
        and then stops if the game's state says the game is over.
        """
        self.parser.parse_command("look")

        while True:
            # When a clock is configured, show the in-game time in the prompt.
            time_str = self.current_time()
            prompt = f"\n[{time_str}] > " if time_str else "\n> "
            command = input(prompt)
            self.do_command(command)
            if self.is_game_over():
                break

    def add_hint(self, hint):
        """Register a :class:`~text_adventure_games.hints.Hint` topic on the
        HINT menu. Order of registration is menu order."""
        self.hints.append(hint)

    def scored(self, key) -> bool:
        """Whether :meth:`award` has already paid *key* -- the public face of
        the idempotence set, for predicates (hints, triggers) that gate on
        a milestone having happened."""
        return key in self._scored_keys

    def show_figure(self, key, force=False):
        """Cue the illustration card *key*, once per game (repeats are no-ops,
        so re-examining a thing doesn't re-draw its card). Purely cosmetic:
        surfaces without a card registry ignore the FIGURE channel, and the
        set rebuilds on journal replay because the cueing commands re-run.

        ``force=True`` re-shows a spent key: for once-only STORY BEATS (an
        ambush springing, a first blow landing) that must play even when an
        earlier examine already drew the creature's card. The caller owns
        making sure the beat itself can't repeat."""
        if not key or (key in self.figures_shown and not force):
            return
        self.figures_shown.add(key)
        self.parser.figure(key)

    def award(self, key, points, msg=None):
        """Add *points* to the score once per *key* (idempotent), optionally
        announcing *msg*.

        The first call for a key scores; repeats are no-ops, so re-entering a
        scored room or re-triggering a milestone can't double-count. This is the
        scoring primitive every Parsely point table needs (Action Castle II/III
        both used to define their own identical copy). Games without scoring
        simply never call it.
        """
        if key in self._scored_keys:
            return
        self._scored_keys.add(key)
        self.score += points
        if msg:
            self.parser.ok(msg)

    def end_in_death(self, message):
        """End the game with a death message -- the prescribed-death path the
        Parsely books lean on (disturb the ooze, enter the moat unarmed, read
        the lethal inscription). Narrates *message*, then sets the game-over
        state so the loop stops on the next check.
        """
        self.parser.ok(message)
        self.game_over = True
        self.game_over_description = message

    def announce_ending(self, message, show_score=False):
        """Announce an ending epilogue exactly once, optionally appending the
        score line.

        Win/death *conditions* stay game-specific (``is_won`` / ``end_in_death``);
        this only factors the "say the epilogue once, with the score" bookkeeping
        that the multi-ending games repeat. Safe to call from a polled ``is_won``
        -- the once-guard means later polls don't re-print it.
        """
        if getattr(self, "_ending_announced", False):
            return
        self._ending_announced = True
        if show_score and self.max_score:
            message = f"{message}  (Score: {self.score}/{self.max_score})"
        self.parser.ok(message)

    def is_won(self) -> bool:
        """
        A conditional check intended for subclasses to use for defining the
        game's winning conditions.
        """
        return False

    def is_game_over(self) -> bool:
        """
        A conditional check that determines if the game is over. By default it
        checks if the player has died or won.
        """
        # Something has set the game over state
        if self.game_over:
            return True
        # The player has died
        if self.player.get_property(Property.IS_DEAD):
            self.game_over_description = "You have died. THE END"
            return True
        # The player has been knocked unconscious
        if self.player.get_property(Property.IS_UNCONSCIOUS):
            self.game_over_description = "You have been knocked unconscious. THE END"
            return True
        # Has the game has been won?
        return self.is_won()

    def add_character(self, character: Character):
        """
        Puts characters in the game
        """
        self.characters[character.name] = character
        # Apply the configured "recently heard" buffer size so it covers NPCs
        # added after construction too (Character.hear falls back to its module
        # default for characters never added to a game).
        character.heard_max = self.config.engine.heard_max

    def perceive(self, observer: Character) -> perception.Scene:
        """Resolve how *observer* perceives their current location -- the single
        shared perception step behind both :meth:`describe` (the human renderer)
        and :meth:`describe_for` (the agent renderer), so the two always see the
        same world (design: docs/design/perception.md).

        Returns a :class:`~text_adventure_games.perception.Scene`: the sight
        level plus the text to show in place of the room -- the room's own
        description when it can be seen, a veil's blurb (e.g. "It's pitch dark")
        when it can't. With no veils and a non-blind observer this resolves to
        ``Sight.CLEAR`` with the room's own description, so rendering is
        unchanged -- perception is zero-cost until a game opts in.
        """
        loc = observer.location
        sight, blurb = perception.sight_for(observer, loc)
        if sight == perception.Sight.NONE:
            text = blurb
        elif sight == perception.Sight.DIM:
            # A game may supply softer text for a half-seen room; else its own.
            text = getattr(loc, "dim_description", None) or loc.description
        else:
            text = loc.description
        return perception.Scene(sight=sight, description=text)

    def enable_senses(self):
        """Register the feel / listen / smell probe verbs (perception Layer 2).

        Opt-in: probes stay out of games that don't want them, keeping the verb
        set (and HELP) lean. Call this in ``build_game`` for an adventure that
        tags things ``perceptible_by`` touch/hearing/smell. Idempotent."""
        from .actions.senses import Feel, Listen, Smell, Taste

        for action in (Feel, Listen, Smell, Taste):
            self.parser.add_action(action)

    def describe(self) -> str:
        """
        Describe the current game state by first describing the current
        location, then listing any exits, and then describing any objects
        in the current location.

        Facets are gated by how well the player perceives the room (perception.py):
        in the dark you get only the "can't see" blurb; in a haze the room and
        its exits but not its contents; in the clear (the default) everything.
        """
        scene = self.perceive(self.player)
        description = self.player.location.name.upper() + "\n"
        if self.clock is not None:
            description += f"({self.current_time()})\n"
        description += scene.description + "\n"
        if scene.sight >= perception.Sight.DIM:
            description += self.describe_exits() + "\n"
        if scene.sight >= perception.Sight.CLEAR:
            description += self.describe_items() + "\n"
            description += self.describe_characters() + "\n"
        # self.parser.ok(description)
        return description

    def describe_current_location(self) -> str:
        """
        Describe the current location by printing its description field.
        """
        return self.player.location.description

    def describe_exits(self) -> str:
        """
        List the directions that the player can take to exit from the current
        location.
        """
        exits = []
        for direction in self.player.location.connections.keys():
            location = self.player.location.connections[direction]
            exits.append(f" * {direction.capitalize()} to {location.name}")
        description = ""
        if len(exits) > 0:
            description = "Exits:\n"
            for exit in exits:
                description += exit + "\n"
        return description

    def describe_items(self) -> str:
        """
        Describe what items are in the current location.
        """
        description = ""
        # Hidden items (concealed until a SEARCH reveals them) aren't listed.
        visible = [
            it
            for it in self.player.location.items.values()
            if not it.get_property("is_hidden")
        ]
        if len(visible) > 0:
            description = "You see:"
            for item in visible:
                qty = getattr(item, "quantity", 1)
                count = f" (x{qty})" if qty > 1 else ""
                description += f"\n * {item.name}{count} - {item.description}"
                if self.give_hints:
                    special_commands = item.get_command_hints()
                    for cmd in special_commands:
                        description += "\n\t" + cmd
                # A surface's contents are always in view ("on the table..."). A
                # container can opt in via ``contents_visible`` -- an open rowboat
                # you can see into, so its blanket is listed (and matches what GET
                # can already reach). The treasure hoard deliberately does NOT set
                # it, keeping its loot hidden until EXAMINE.
                shows_contents = item.get_property("is_surface") or (
                    item.get_property("is_container")
                    and item.is_open()
                    and item.get_property("contents_visible")
                )
                if shows_contents:
                    prep = item.preposition()
                    for inner in item.contents.values():
                        if inner.get_property("is_hidden"):
                            continue
                        description += f"\n   - {prep} it: {inner.description}"
        return description

    def describe_characters(self) -> str:
        """
        Describe what characters are in the current location.
        """
        description = ""

        if len(self.player.location.characters) > 1:
            description = "Characters:"
            for character_name in self.player.location.characters:
                if character_name == self.player.name:
                    continue
                character = self.player.location.characters[character_name]
                description += (
                    f"\n * {character.name} - {character.visible_description()}"
                )
        return description

    def describe_inventory(self) -> str:
        """
        Describes the player's inventory.
        """
        if len(self.player.inventory) == 0 and not self.player.wounds:
            empty_inventory = "You don't have anything."
            self.ok(empty_inventory, [], "Describe the player's inventory.")
        else:
            # descriptions = []  # JD logical issue?
            inventory_description = "In your inventory, you have:\n"
            for item_name in self.player.inventory:
                item = self.player.inventory[item_name]
                d = "* {item} - {item_description}\n"
                inventory_description += d.format(
                    item=item_name, item_description=item.description
                )
            # Vaarn item slots (slots.py): wounds fill the same gauge as gear,
            # so they list here; the slots line appears only for games that
            # opted a character in (slot_capacity set).
            if self.player.wounds:
                inventory_description += "Wounds:\n"
                for w in self.player.wounds:
                    note = (
                        f" ({w.slots} slot{'s' if w.slots != 1 else ''})"
                        if w.slots
                        else ""
                    )
                    inventory_description += f"* {w.name}{note} - {w.description}\n"
            if self.player.slot_capacity is not None:
                inventory_description += (
                    f"Slots: {self.player.slots_used()}/{self.player.slot_capacity}"
                )
                if self.player.is_encumbered():
                    inventory_description += " -- ENCUMBERED"
                inventory_description += "\n"
            self.ok(inventory_description)

    def describe_for(self, character: Character) -> str:
        """
        Describe the game world from a specific character's perspective.
        Used by NPC behaviors and the ReAct loop to observe their environment.
        """
        loc = character.location
        scene = self.perceive(character)
        lines = []

        def _visible_to(thing) -> bool:
            """Hidden Things (flagged ``secret_topic``) are perceived only by a
            character whose knowledge unlocks that topic (issue #45). Unflagged
            Things are always visible, so existing games are unchanged."""
            secret = thing.get_property("secret_topic")
            return not secret or character.knowledge.knows_about(secret)

        # Location -- the room text is what this character perceives (its own
        # description when seen, a veil's blurb in the dark), and exits/contents
        # are gated by how well it sees (perception.py). This is the same shared
        # perceive() the player's view uses, so agent and player never disagree
        # about what darkness or fog hides.
        lines.append(loc.name.upper())
        lines.append(scene.description)

        if scene.sight >= perception.Sight.DIM:
            # Exits
            if loc.connections:
                lines.append("Exits:")
                for direction, dest in loc.connections.items():
                    lines.append(f" * {direction.capitalize()} to {dest.name}")

        if scene.sight >= perception.Sight.CLEAR:
            # Items at location (hidden items are revealed only to those who know)
            visible_items = [it for it in loc.items.values() if _visible_to(it)]
            if visible_items:
                lines.append("Items here:")
                for item in visible_items:
                    lines.append(f" * {_format_item(item)}")

            # Other characters present (hidden ones revealed only to those who know)
            others = [
                c
                for name, c in loc.characters.items()
                if name != character.name and _visible_to(c)
            ]
            if others:
                lines.append("Characters here:")
                for c in others:
                    lines.append(f" * {c.name} - {c.visible_description()}")

        # Inventory
        if character.inventory:
            lines.append("Inventory:")
            for item_name, item in character.inventory.items():
                lines.append(f" * {_format_item(item)}")
        else:
            lines.append("Inventory: empty")

        if character.worn:
            lines.append(f"Worn: {', '.join(character.worn)}")
        if character.wielded:
            lines.append(f"Wielded: {', '.join(character.wielded)}")
        # Vaarn item slots (slots.py): agents that opted in see their gauge and
        # wounds, so a planner can reason about load and injury.
        if character.wounds:
            lines.append(
                "Wounds: "
                + ", ".join(f"{w.name} ({w.slots})" for w in character.wounds)
            )
        if character.slot_capacity is not None:
            gauge = f"Slots: {character.slots_used()}/{character.slot_capacity}"
            if character.is_encumbered():
                gauge += " (ENCUMBERED: you clatter when you move, and cannot climb)"
            lines.append(gauge)

        # Available actions
        action_names = sorted(self.parser.actions.keys())
        lines.append(f"Available actions: {', '.join(action_names)}")

        # What the character believes about the world (issue #45). This is the
        # character's world-model -- possibly incomplete or wrong -- not
        # omniscient ground truth, and not memory (#37, the episodic log).
        # render() returns "" for an un-seeded character, so an observation is
        # byte-identical to before unless beliefs were added.
        beliefs = character.knowledge.render()
        if beliefs:
            lines.append(beliefs)

        # Turn (with the in-game time when a clock is configured)
        if self.clock is not None:
            lines.append(f"Turn: {self.turn} ({self.current_time()})")
        else:
            lines.append(f"Turn: {self.turn}")

        return "\n".join(lines)

    def audience_for(self, speaker, message, target=None):
        """Return the characters who perceive *speaker*'s spoken *message*.

        This is the single audibility seam for dialogue. **Override it** to
        model a continuous or range-based world (hearing radius, line of sight,
        walls). The default policy is room-based: every character in the
        speaker's location except the speaker. Bystanders may overhear directed
        speech; *target* (the addressed character, or None for a broadcast) is
        passed so an override can treat the addressee specially, but the default
        ignores it.
        """
        loc = speaker.location
        if loc is None:
            return []
        return [c for c in loc.characters.values() if c is not speaker]

    def perceivable_locations(self, character) -> list[Location]:
        """Return the locations *character* can see into this turn (issue #80).

        This is the single **visibility** seam, the sight counterpart to
        :meth:`audience_for` (hearing). **Override it** to model a continuous or
        range-based world -- tile distance, line of sight, walls. The default
        policy is graph-based: a breadth-first walk over room ``connections`` out
        to the character's ``vision_r`` hops. ``vision_r == 0`` (the default)
        returns just the current room, so perception stays exactly as it was
        before #80 until a game opts in by widening a character's radius.

        Sight is deliberately *not* movement: the walk crosses ``blocks`` (a
        locked gate stops you walking through, not seeing through). A world that
        wants walls to block sight can override this to honor blocks.
        """
        loc = character.location
        if loc is None:
            return []
        radius = getattr(character, "vision_r", DEFAULT_VISION_R)
        # Breadth-first over the location graph, tracking each room's hop
        # distance so we stop expanding once we pass the radius. `seen` keys on
        # Location identity (a room reached by two paths is visited once).
        seen = {id(loc): loc}
        result = [loc]
        frontier = [loc]
        for _ in range(radius):
            nxt = []
            for room in frontier:
                for neighbor in room.connections.values():
                    if id(neighbor) not in seen:
                        seen[id(neighbor)] = neighbor
                        result.append(neighbor)
                        nxt.append(neighbor)
            frontier = nxt
            if not frontier:
                break  # radius exceeds the map; nothing more to reach
        return result

    def audible_rooms(self, origin, radius) -> dict:
        """``{room_name: direction_back_toward_origin}`` for rooms within
        ``radius`` hops of ``origin`` (a Location or its name), excluding the
        origin itself (issue #80 hearing).

        The hearing counterpart to :meth:`perceivable_locations`: a loud event's
        sound reaches these rooms, and each value is the exit *in that room* that
        points back toward the source -- so a listener can be told which way it
        came from. ``radius <= 0`` reaches nowhere (the sound stays in its room).
        """
        loc = origin if hasattr(origin, "connections") else self.locations.get(origin)
        if loc is None or radius <= 0:
            return {}
        result: dict = {}
        seen = {id(loc)}
        frontier = [loc]
        for _ in range(radius):
            nxt = []
            for room in frontier:
                for neighbor in room.connections.values():
                    if id(neighbor) in seen:
                        continue
                    seen.add(id(neighbor))
                    # the exit in `neighbor` that leads back toward the source
                    back = next(
                        (d for d, r in neighbor.connections.items() if r is room), None
                    )
                    result[neighbor.name] = back
                    nxt.append(neighbor)
            frontier = nxt
            if not frontier:
                break
        return result

    def set_parser(self, parser):
        """
        Use a different parser for this game.
        """
        self.parser = parser
        if self.custom_actions:
            for ca in self.custom_actions:
                if inspect.isclass(ca) and issubclass(ca, actions.Action):
                    self.parser.add_action(ca)
                else:
                    err_msg = f"ERROR: invalid custom action ({ca})"
                    raise Exception(err_msg)

    # The methods below read and write a game to JSON
    def to_primitive(self):
        """
        Serialize a game to json.

        Note: the clock's configuration is saved, but triggers (including
        scheduled events) are not — their conditions and actions are arbitrary
        functions and can't be serialized. Games that rely on them should
        re-register them after loading.
        """
        data = {
            "player": self.player.name,
            "start_at": self.start_at.name,
            "turn": self.turn,
            "time_config": self.clock.to_primitive() if self.clock else None,
            "game_history": self.game_history,  # TODO this is empty?
            "game_over": self.game_over,
            "game_over_description": self.game_over_description,
            "characters": [c.to_primitive() for c in self.characters.values()],
            "locations": [l.to_primitive() for l in self.locations.values()],
            "actions": sorted([a for a in self.parser.actions]),
        }
        return data

    def to_world_state(self):
        """A typed, deterministic, read-only snapshot of the whole world -- the
        structured feed a JSON exporter or the future Godot renderer polls
        (issue #90). See :mod:`text_adventure_games.world_state`. Pure: this
        never mutates the game."""
        from .world_state import world_state

        return world_state(self)

    def to_world_json(self) -> str:
        """:meth:`to_world_state` rendered as a JSON string."""
        return json.dumps(self.to_world_state().to_jsonable())

    @classmethod
    def default_actions(self):
        """
        Generates a dictionary of all actions packaged as part of this library
        """
        actions_found = {}
        for member in dir(actions):
            attr = getattr(actions, member)
            if inspect.isclass(attr) and issubclass(attr, actions.Action):
                # dont include base class
                if not attr == actions.Action:
                    actions_found[attr.action_name()] = attr
        return actions_found

    @classmethod
    def default_blocks(self):
        """
        Generates as dictionary of all blocks packaged as part of this library
        """
        blocks_found = {}
        for member in dir(blocks):
            attr = getattr(blocks, member)
            if inspect.isclass(attr) and issubclass(attr, blocks.Block):
                # dont include base class
                if not attr == blocks.Block:
                    # if this changes, also adjust _type in blocks.Block
                    blocks_found[attr.__name__] = attr
        return blocks_found

    @classmethod
    def from_primitive(cls, data, custom_actions=None, custom_blocks=None):
        """
        This complex method performs the huge job of converting a game from its
        primitive representation to fully formed python objects.

        There are three main parts to this method:

        1. Create skeletons for all characters and locations. Currently, items
           exist by being in a location or a character's inventory, and so this
           step also creates item skeletons. See the from_primitive methods for
           characters and locations for more.
        2. Replace fields in skeletons where an object's name exists with the
           actual objects. This step replaces fields where an object's name is
           stored instead of the actual object.
        3. Instantiate anything left that requires full object instances to
           work properly. Blocks require actual instances for everything.

        Once those steps are done, this method simply adds any remaining game
        fields to the game instance.
        """
        SkeletonContext = namedtuple(
            "SkeletonContext", ["characters", "locations", "items"]
        )

        # FIRST PASS

        characters = {
            c["name"]: Character.from_primitive(c) for c in data["characters"]
        }
        locations = {l["name"]: Location.from_primitive(l) for l in data["locations"]}
        items = {}
        context = SkeletonContext(characters, locations, items)

        # SECOND PASS

        # Characters
        for c in context.characters.values():
            # locations
            l = context.locations[c.location]
            c.location = l
            # inventory
            for item_name, item in c.inventory.items():
                #                if hasattr(item, "location") and item.location:
                #                    l_obj = context.locations[item.location]
                #                    item.location = l_obj
                #                elif hasattr(item, "owner") and item.owner:
                #                    c_obj = context.characters[item.owner]
                #                    item.owner = c_obj
                context.items[item_name] = item

        # Locations
        for l in context.locations.values():
            # characters
            for char_name, c in l.characters.items():
                c_obj = context.characters[char_name]
                l.characters[char_name] = c_obj
            # connections
            for dir_name, connection in l.connections.items():
                c_obj = context.locations[connection]
                l.connections[dir_name] = c_obj
            # items
            for item_name, item in l.items.items():
                if hasattr(item, "location") and item.location:
                    l_obj = context.locations[item.location]
                    item.location = l_obj
                elif hasattr(item, "owner") and item.owner:
                    c_obj = context.characters[item.owner]
                    item.owner = c_obj
                context.items[item_name] = item

        # THIRD PASS

        # Actions
        action_map = cls.default_actions()

        # Validate custom actions
        if custom_actions:
            for ca in custom_actions:
                if inspect.isclass(ca) and issubclass(ca, actions.Action):
                    action_map[ca.action_name()] = ca
                else:
                    err_msg = f"ERROR: invalid custom action ({ca})"
                    raise Exception(err_msg)

        # verify all commands from primitive data have an associated action
        action_names = list(action_map.keys())
        for action_name in data["actions"]:
            if action_name not in action_names:
                err_msg = "".join(
                    [
                        f"ERROR: unmapped action ({action_name}) found in ",
                        "primitive data",
                    ]
                )
                raise Exception(err_msg)

        # Blocks
        block_map = cls.default_blocks()

        # Validate custom blocks
        if custom_blocks:
            for cb in custom_blocks:
                if inspect.isclass(cb) and issubclass(cb, blocks.Block):
                    block_map[cb.__name__] = cb
                else:
                    err_msg = f"ERROR: invalid custom block ({cb})"
                    raise Exception(err_msg)

        # Instantiate all blocks for all locations
        # CCB - temporarially removing this.
        # for l in context.locations.values():
        #     for direction, block_data in l.blocks.items():
        #         # it is possible for two locations to have the same block, so
        #         # skip any that have already been instantiated
        #         if isinstance(block_data, blocks.Block):
        #             continue
        #         cls_type = block_map[block_data["_type"]]
        #         del block_data["_type"]
        #         # we will copy the properties of relevant items before we
        #         # install the block, so we can restore them after
        #         prop_map = {}
        #         # replace thing names in primitive with thing instances
        #         for param_name, param in block_data.items():
        #             if param in context.items:
        #                 param_instance = context.items[param]
        #             elif param in context.locations:
        #                 param_instance = context.locations[param]
        #             block_data[param_name] = param_instance
        #             prop_map[param_name] = param_instance.properties.copy()
        #         instance = cls_type.from_primitive(block_data)
        #         # restore properties found in primitive data
        #         for param_name, param in block_data.items():
        #             param.properties = prop_map[param_name]

        start_at = context.locations[data["start_at"]]
        player = context.characters[data["player"]]

        instance = cls(start_at, player, custom_actions=action_map.values())
        instance.turn = data.get("turn", 0)
        time_config = data.get("time_config")
        if time_config:
            instance.clock = GameClock.from_primitive(time_config)
        instance.game_history = data["game_history"]
        instance.game_over = data["game_over"]
        instance.game_over_description = data["game_over_description"]

        return instance

    def to_json(self):
        """
        Creates a JSON version of a game's primitive data.
        """
        data = self.to_primitive()
        data_json = json.dumps(data)
        return data_json

    @classmethod
    def from_json(cls, data_json, **kw):
        """
        Goes from JSON into actual game instances.
        """
        data = json.loads(data_json)
        instance = cls.from_primitive(data, **kw)
        return instance

    def save_game(self, filename):
        """
        Converts a game's state to JSON and then saves it to a file
        """
        save_data = self.to_json()
        with open(filename, "w") as f:
            f.write(save_data)

    @classmethod
    def load_game(cls, filename, **kw):
        """
        Reads a file with a game's state stored as JSON and converts it to a
        game instance.
        """
        with open(filename, "r") as f:
            save_data = f.read()
            return cls.from_json(save_data, **kw)
