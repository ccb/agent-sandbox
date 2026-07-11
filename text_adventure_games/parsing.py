"""The Parser

The parser is the module that handles the natural language understanding in
the game. The players enter commands in text, and the parser interprets them
and performs the actions that the player intends.  This is the module with
the most potential for improvement using modern natural language processing.
The implementation that I have given below only uses simple keyword matching.
"""

import inspect
import re

from text_adventure_games import games

from .things import Character, Item, Location
from . import actions, blocks
from .enums import ActionName, Direction, Role
from .reporting import Channel, Message, default_renderer, wrap_text

# Maps the one-letter direction shortcuts ("n", "s", "e", "w") onto canonical
# Direction members. Up/down/in/out have no single-letter alias today; if
# games add new shortcuts, extend here rather than in get_direction.
_DIRECTION_ALIASES: dict[str, Direction] = {
    "n": Direction.NORTH,
    "s": Direction.SOUTH,
    "e": Direction.EAST,
    "w": Direction.WEST,
}

# Canonical direction names recognized by get_direction (alongside any exit
# names a location declares). The cardinals and the vertical/in-out set are
# matched the same way now -- on word boundaries, and only when the command is
# bare or movement-verb-led (see get_direction) -- so short names like "in"
# no longer misfire inside unrelated words ("examine", "drink").
_SUBSTRING_DIRECTIONS = (
    Direction.NORTH,
    Direction.SOUTH,
    Direction.EAST,
    Direction.WEST,
)
_GO_SUFFIX_DIRECTIONS = (
    Direction.UP,
    Direction.DOWN,
    Direction.OUT,
    Direction.IN,
)

# Verbs that introduce a movement command. A direction/exit is treated as a GO
# only when the command is one of these followed by a destination, or is a bare
# direction/exit -- never merely because a direction's letters appear in some
# other word. ("enter"/"exit"/"leave" are deliberately excluded: exit names can
# themselves start with them, e.g. the "enter tunnel" connection.)
_MOVEMENT_VERBS = (
    "go",
    "walk",
    "run",
    "head",
    "travel",
    "move",
    "climb",
    "ride",
    "drive",
)


class Parser:
    """
    The Parser is the class that handles the player's input.  The player
    writes commands, and the parser performs natural language understanding
    in order to interpret what the player intended, and how that intent
    is reflected in the simulated world.
    """

    def __init__(self, game, echo_commands=False, renderer=None):
        # A list of the commands that the player has issued,
        # and the respones given to the player.
        self.command_history = []

        # Build default scope of actions
        self.actions = game.default_actions()

        # Build default scope of blocks - CCB: TODO - move blocks to the game class
        self.blocks = game.default_blocks()

        # A pointer to the game.
        self.game = game
        self.game.parser = self

        # Print the user's commands
        self.echo_commands = echo_commands

        # Set by fail() so the ReAct loop can read the reason without side-effects
        self.last_fail_message: str | None = None

        # How output is shown. The engine builds Messages (by Channel) and hands
        # them to a Renderer; the default picks a colored terminal renderer when
        # one fits, else a plain fallback. Web mode passes a WebRenderer.
        # Verbosity/color come from the game's RenderConfig when available,
        # falling back to the OUTPUT_LEVEL / NO_COLOR env vars otherwise.
        # See text_adventure_games/reporting.py.
        if renderer is not None:
            self.renderer = renderer
        else:
            render_cfg = getattr(game, "config", None)
            render_cfg = getattr(render_cfg, "render", None)
            if render_cfg is not None:
                self.renderer = default_renderer(
                    level=render_cfg.level,
                    no_color=render_cfg.no_color,
                    width=render_cfg.width,
                )
            else:
                self.renderer = default_renderer()

    def set_renderer(self, renderer):
        """Swap the renderer (e.g. a WebRenderer for the Flask app, or a
        CaptureRenderer in tests)."""
        self.renderer = renderer

    def _emit(self, channel: Channel, text: str, actor=None, meta=None):
        """Build a Message on *channel* and hand it to the renderer."""
        self.renderer.emit(
            Message(channel, text, actor=actor, turn=self.game.turn, meta=meta or {})
        )

    def ok(self, description: str):
        """Report a successful action's world narration. The first character is
        capitalized so narration always opens with a capital, even when it
        starts with a lower-cased name ("princess got ..." -> "Princess got
        ...")."""
        if description:
            description = description[0].upper() + description[1:]
        self._emit(Channel.NARRATION, description)
        self.add_description_to_history(description)

    def damage(self, description: str):
        """Report a wound landing on its own channel, so harm always arrives
        in one consistent voice: "Acid-Lashed - A welt across your back."."""
        self._emit(Channel.DAMAGE, description)
        self.add_description_to_history(description)

    def fail(self, description: str):
        """Report an action blocked by its preconditions. ``last_fail_message``
        is set so the ReAct Reflect step can read the reason."""
        self.last_fail_message = description
        self._emit(Channel.BLOCKED, description)

    def figure(self, key: str):
        """Cue an illustration: *key* names a card in the surface's registry.
        Text renderers stay silent below VERBOSE (a key is not prose); the web
        terminal draws the card inline. Never enters command history."""
        self._emit(Channel.FIGURE, key)

    @staticmethod
    def wrap_text(text: str, width: int = 80) -> str:
        """
        Keeps text output narrow enough to easily be read
        """
        return wrap_text(text, width)

    def add_command_to_history(self, command: str):
        message = {"role": Role.USER, "content": command}
        self.command_history.append(message)
        # CCB - todo - manage command_history size

    def add_description_to_history(self, description: str):
        message = {"role": Role.ASSISTANT, "content": description}
        self.command_history.append(message)
        # CCB - todo - manage command_history size

    def add_action(self, action: actions.Action):
        """
        Add an Action class to the list of actions a parser can use
        """
        self.actions[action.action_name()] = action

    def add_block(self, block):
        """
        Adds a block class to the list of blocks a parser can use. This is
        primarily useful for loading game states from a save.
        """
        self.blocks[block.__class__.__name__] = block

    def init_actions(self):
        self.actions = {}
        for member in dir(actions):
            attr = getattr(actions, member)
            if inspect.isclass(attr) and issubclass(attr, actions.Action):
                # dont include base class
                if not attr == actions.Action:
                    self.add_action(attr)

    def determine_intent(self, command: str, actor=None):
        """
        This function determines what command the player wants to do.
        Here we have implemented it with a simple keyword match. Later
        we will use AI to do more flexible matching.
        """
        # Resolve the acting character (the actor, else a player-default scan).
        # Used below only to interpret directions relative to where they stand.
        character = actor if actor is not None else self.get_character(command)
        command = command.lower()
        if "," in command:
            # Let the player type in a comma separted sequence of commands
            return ActionName.SEQUENCE

        # Specific-first: if a registered action's MULTI-WORD name or alias
        # appears in the command, it wins over the generic verb keywords below.
        # This lets game-defined verbs ("give axe to smith", "say yes") and
        # multi-word aliases route to their own action instead of being
        # pre-empted by "give"/"say"/"drop". Single-word verbs, directions, and
        # everything else fall through to the keyword logic. (Generalizes the
        # ad hoc "adopt goal" / "take off"-before-"take" precedence hacks below.)
        specific = self._match_specific_action(command)
        if specific is not None:
            return specific

        # Crafting verbs ("make stew", "cook", "combine string and stick") route
        # to CRAFT -- but only when the game has registered recipes, so a game
        # without crafting is unaffected (and "make a wish"-style multi-word
        # aliases already won above via specific-first). See crafting.py.
        if getattr(self.game, "recipes", None):
            first = command.split(" ", 1)[0]
            if first in actions.things.CRAFT_VERBS:
                return ActionName.CRAFT

        if "taste" in self.actions and (
            command in ("taste", "lick") or command.startswith(("taste ", "lick "))
        ):
            # TASTE must outrank the consume keywords below: "taste crate of
            # dates" contains "ate " and would otherwise EAT the crate.
            return "taste"

        if command in ("hint", "hints") or command.startswith(("hint ", "hints ")):
            # The hint booklet takes its topic as free text ("hint light",
            # "hint score") that the verb keywords below would otherwise
            # swallow ("light" in command -> LIGHT).
            return "hint"

        if (
            command.startswith("say ")
            or command.startswith("speak ")
            or command in ("say", "speak")
        ):
            # Speech routes here regardless of message content (a message may
            # contain other command words), and this also handles the "speak"
            # alias, which is not auto-registered.
            return ActionName.SAY
        elif command.split(" ", 1)[0] in ("throw", "hurl", "lob"):
            # A throw names a direction ("throw purse north") or a target; the
            # direction is the throw's argument, not a movement intent.
            return "throw"
        elif command.startswith("adopt goal"):
            # Goal-management verbs are matched explicitly: "drop goal ..." must
            # win over the inventory "drop" verb below, and both must beat the
            # generic longest-match fallback.
            return "adopt goal"
        elif command.startswith("drop goal"):
            return "drop goal"
        elif command.startswith("ask ") and " about " in command:
            # "ask <npc> about <topic>" is a Talk. ("talk to X about Y" already
            # routes via the specific-first "talk to" alias.) Gated on " about "
            # so "ask <npc> to follow" still falls through to the follow verb.
            return ActionName.TALK
        elif self.get_direction(command, character.location):
            # Check for the direction intent. (Checked before mount/dismount so
            # "ride west" / "drive east" stay MOVEMENT -- you ride a *direction*
            # when already aboard -- while "ride horse" falls through to MOUNT.)
            return ActionName.GO
        elif (
            command == "dismount"
            or command.startswith("dismount")
            or command.startswith("get off")
        ):
            return ActionName.DISMOUNT
        elif command.split(" ", 1)[0] in (
            "ride",
            "mount",
            "board",
        ) or command.startswith(("get on", "hop on", "climb aboard")):
            # Get aboard a vehicle (see vehicles.py / Item.make_vehicle). "get
            # on"/"hop on" are caught here, before the "get "/GET branch below.
            return ActionName.MOUNT
        elif command == "look" or command == "l":
            # when the user issues a "look" command, re-describe what they see
            return ActionName.DESCRIBE
        elif command.startswith("look ") or command.startswith("l "):
            # "look around/here" re-describes the room; "look <direction>"
            # surveys that exit (handled by Describe); "look [at] <thing>"
            # examines it. Without this, "look north" matched nothing.
            rest = command.split(" ", 1)[1].strip()
            if rest.startswith("at "):
                rest = rest[3:].strip()
            if rest in ("around", "round", "here", ""):
                return ActionName.DESCRIBE
            if self.get_direction(rest, character.location):
                return ActionName.DESCRIBE
            return ActionName.EXAMINE
        elif "examine " in command or command.startswith("x "):
            return ActionName.EXAMINE
        elif command.startswith("take off") or command.startswith("remove "):
            # Must precede the "take "/get branch -- "take " is a substring of
            # "take off" and would otherwise route equipment removal to Get.
            return ActionName.TAKE_OFF
        elif command.startswith("stow ") or command.startswith("unequip "):
            return ActionName.UNWIELD
        elif "take " in command or "get " in command:
            return ActionName.GET
        elif "light" in command:
            return ActionName.LIGHT
        elif "drop " in command:
            return ActionName.DROP
        elif command.startswith("break") or command.startswith("smash"):
            return ActionName.BREAK
        elif (
            "eat " in command
            or "eats " in command
            or "ate " in command
            or "eating " in command
        ):
            return ActionName.EAT
        elif "drink" in command:
            return ActionName.DRINK
        elif "give" in command or command.startswith("hand "):
            # A custom give-action ("give gem to wizard") whose item AND
            # recipient both appear -- in ANY word order -- wins over the
            # built-in Give, so "give wizard the gem" / "hand wizard the gem"
            # still reach it (issue #171). Also routes the "hand" alias here,
            # which the bare-"give" keyword check used to miss. Falls back to the
            # built-in Give when no custom give-action matches.
            return self._match_give_action(command) or ActionName.GIVE
        elif "attack" in command or "hit " in command or "hits " in command:
            return ActionName.ATTACK
        elif "inventory" in command or command == "i":
            return ActionName.INVENTORY
        elif command == "wait" or command == "z":
            return ActionName.WAIT
        elif command in ("help", "h", "commands", "?") or command.startswith("help"):
            return ActionName.HELP
        elif "quit" in command:
            return ActionName.QUIT
        else:
            # Longest registered action name -- OR single-word alias -- that
            # appears in the command, on WORD BOUNDARIES, not as a bare substring.
            # (Substring matching here routed "dragon" to GO, because "go" sits
            # inside "dra-go-n"; same class as "give" inside "forgive".) Single-
            # word aliases are honored too, so a custom verb's short alias
            # ("jump"/"fall") routes to it (multi-word aliases already won via
            # _match_specific_action). We return the action's NAME even when an
            # alias matched, so the lookup in parse_action still resolves.
            best_name, best_len = None, -1
            for _, action in self.actions.items():
                phrases = [action.action_name()] + list(
                    getattr(action, "ACTION_ALIASES", []) or []
                )
                for phrase in phrases:
                    if phrase and re.search(rf"\b{re.escape(phrase)}\b", command):
                        if len(phrase) > best_len:
                            best_name, best_len = action.action_name(), len(phrase)
            return best_name

    def _match_specific_action(self, command):
        """The longest registered ACTION_NAME / ACTION_ALIAS that is MULTI-WORD
        and appears in *command* (already lowercased), or None.

        Multi-word only, so single-word generic verbs (give/say/drop/...) are
        still resolved by the keyword chain in determine_intent. Aliases are
        honored here (the keyword fallback ignores them)."""
        best = None
        best_name = None
        for _, action in self.actions.items():
            phrases = [action.action_name()] + list(
                getattr(action, "ACTION_ALIASES", []) or []
            )
            for phrase in phrases:
                if phrase and " " in phrase and phrase.lower() in command:
                    if best is None or len(phrase) > len(best):
                        best, best_name = phrase, action.action_name()
        return best_name

    def _match_give_action(self, command):
        """A registered custom give-action whose item AND recipient both appear
        in *command*, in any word order (issue #171), or ``None``.

        A custom give-action names itself -- or aliases itself -- ``give {item}
        to {recipient}``. Matching on the (item, recipient) PAIR rather than the
        literal phrase is what lets reversed/alternate phrasings ("give smith
        the axe", "hand the smith my axe") route to the custom action instead of
        being swallowed by the built-in Give. Canonical "give {item} to
        {recipient}" already wins earlier via :meth:`_match_specific_action`, so
        this only fires for the variants. The most specific (longest combined
        item+recipient) match wins, and an unmatched give falls back to the
        built-in Give."""
        best_name, best_score = None, -1
        for _, action in self.actions.items():
            phrases = [action.action_name()] + list(
                getattr(action, "ACTION_ALIASES", []) or []
            )
            for phrase in phrases:
                match = re.fullmatch(r"give (.+?) to (.+)", phrase.lower())
                if match is None:
                    continue
                item, recipient = match.group(1), match.group(2)
                if self._word_in(item, command) and self._word_in(recipient, command):
                    score = len(item) + len(recipient)
                    if score > best_score:
                        best_name, best_score = action.action_name(), score
        return best_name

    @staticmethod
    def _word_in(phrase, command):
        """True if *phrase* occurs in *command* on word boundaries (so "king"
        matches "the king" but not "kingdom"). Both are already lowercased."""
        return re.search(rf"\b{re.escape(phrase)}\b", command) is not None

    def parse_action(self, command: str, actor=None) -> actions.Action:
        """
        Routes an action described in a command to the right action class for
        performing the action.
        """
        if self.echo_commands:
            self._emit(Channel.COMMAND, command)
        return self.peek_action(command, actor=actor)

    def peek_action(self, command: str, actor=None) -> actions.Action:
        """Build the Action a command would route to WITHOUT echoing or running
        it. Constructing the action matches its target (item/character/exit) via
        ``match_item`` / ``get_character``, but ``check_preconditions`` /
        ``apply_effects`` never run. Used by the simultaneous gather phase to read
        an intent's action name and the resource it claims (issue #42), where a
        full ``parse_command`` would prematurely echo and mutate the world."""
        command = command.lower().strip()
        if command == "":
            return None
        intent = self.determine_intent(command, actor=actor)
        if intent in self.actions:
            action = self.actions[intent]
            return action(self.game, command, actor=actor)
        return None

    def npc_ok(self, description: str):
        """Report an NPC's action narration (rendered distinctly from the
        player's own narration)."""
        self._emit(Channel.NPC_NARRATION, description)
        self.add_description_to_history(description)

    def conflict(self, actor: str, description: str):
        """Report that *actor* lost a contested resource this round (issue #42).

        Distinct from :meth:`fail`: it's not a precondition error, it's the
        outcome of two characters reaching for the same thing in a simultaneous
        round. Goes on its own ``CONFLICT`` channel so a renderer can tell the
        contention story, and is deliberately kept OUT of command_history (the
        loser's private setback must not leak into other characters'
        observations)."""
        self._emit(Channel.CONFLICT, description, actor=actor)

    # ------------------------------------------------------------------
    # Agent trace (the ReAct loop's Observe / Think / Act / Reflect).
    #
    # Each goes to the renderer on its own Channel and is deliberately NOT
    # added to command_history: an NPC's reasoning is private, so it must never
    # leak into other characters' observations.
    # ------------------------------------------------------------------

    def agent_observation(self, actor: str, text: str):
        self._emit(Channel.AGENT_OBSERVATION, text, actor=actor)

    def agent_reasoning(self, actor: str, text: str):
        self._emit(Channel.AGENT_REASONING, text, actor=actor)

    def agent_action(self, actor: str, command: str):
        self._emit(Channel.AGENT_ACTION, command, actor=actor)

    def agent_reflection(self, actor: str, text: str):
        self._emit(Channel.AGENT_REFLECTION, text, actor=actor)

    def npc_log(self, message: str):
        """Legacy agent-trace shim (a single pre-formatted line). Prefer the
        typed ``agent_*`` methods above; kept so older callers keep working."""
        self._emit(Channel.AGENT_REASONING, message)

    def turn_header(self, turn: int = None, time: str = None):
        """Ask the renderer to mark a turn boundary (terminal renderers draw a
        rule; others may ignore it)."""
        if turn is None:
            turn = self.game.turn
        if time is None:
            time = self.game.current_time()
        self.renderer.turn_header(turn, time)

    def parse_command(self, command: str, actor=None) -> bool:
        # add this command to the history
        self.add_command_to_history(command)
        action = self.parse_action(command, actor=actor)
        if not action:
            # The command didn't name an action. If the game has posed a
            # question (issue #110, Game.pose_prompt), read this as the answer
            # before giving up -- e.g. a bare "wits" answers "wits or steel?".
            forwarded = self._answer_to_prompt(command, actor)
            if forwarded is not None:
                # Clear first so the dispatched command may pose a new prompt
                # (and so a non-matching answer can't loop back in here).
                self.game.clear_prompt()
                return self.parse_command(forwarded, actor=actor)
            self.fail("I'm not sure what you want to do.")
            return False
        # Resolve the acting character and where they stand *before* the action
        # runs. A GO moves them, but the action belongs (in the event log) to the
        # place it was taken -- so "flee south" counts as a disturbance of the
        # room you fled, not the one you arrived in. The actor is threaded in
        # explicitly (the player via Game.do_command, an NPC via its behavior),
        # falling back to scanning the command only when none was supplied.
        acting = actor if actor is not None else self.get_character(command)
        origin_loc = acting.location if acting is not None else None
        origin = origin_loc.name if origin_loc is not None else None
        action()
        success = getattr(action, "_preconditions_passed", False)
        if success:
            # Remember the action that just ran *on the actor* -- not a single
            # global field -- so the NPC turn loop can read its in-game duration
            # when charging the per-turn budget (issue #24), correctly per
            # character even when several act in one round.
            if acting is not None:
                acting.last_action = action
            # Where it ended up, and (for a move) which way -- so perception can
            # tell a departure from an arrival and name the direction.
            dest_loc = acting.location if acting is not None else None
            dest = dest_loc.name if dest_loc is not None else None
            direction = None
            if (
                origin_loc is not None
                and dest_loc is not None
                and dest_loc is not origin_loc
            ):
                direction = next(
                    (d for d, r in origin_loc.connections.items() if r is dest_loc),
                    None,
                )
            radius = action.audible_radius() if hasattr(action, "audible_radius") else 0
            # Log it with its actor, origin/destination, and how far the sound
            # carries. Disturbance triggers (Game.disturbances_this_round) and
            # agent perception read these per-round events rather than the single
            # global last_action, so they see every actor's move and survive a
            # switch to per-agent turns (#25).
            #
            # (An ActionSequence re-enters parse_command per sub-command, so one
            # comma-separated command logs each sub-command plus the wrapping
            # "sequence" action — a future event-log consumer (#9) should expect that.)
            payload = {
                "location": origin,
                "dest": dest,
                "dir": direction,
                "heard_radius": radius,
            }
            if radius > 0:
                # How the sound reads to someone who only hears it (no sight).
                payload["sound"] = action.sound_description()
            self.game.log_event(
                acting.name if acting is not None else None,
                action.action_name(),
                command,
                payload=payload,
            )
            # A loud action carries to nearby rooms -- let the player hear it
            # from afar if they're within earshot but not where it happened.
            if radius > 0:
                self._player_overhears(action, origin, radius)
        return success

    def _player_overhears(self, action, origin, radius):
        """Narrate a loud action to the player when they're within its sound
        radius but in a different room (so they can't see it)."""
        game = self.game
        player = getattr(game, "player", None)
        if player is None or player.location is None or origin is None:
            return
        if not hasattr(game, "audible_rooms"):
            return
        heard = game.audible_rooms(origin, radius)
        if player.location.name not in heard:
            return  # at the source (sees it) or out of earshot
        direction = heard[player.location.name]
        where = f"the {direction}" if direction else "somewhere nearby"
        self.ok(f"From {where} you hear {action.sound_description()}.")

    def get_character(
        self,
        command: str,
        hint: str = None,
        split_words=None,
        position=None,
        exclude=None,
    ) -> Character:
        """
        This method tries to match a character's name in the command.
        If no names are matched, it returns the default value. A candidate
        equal to ``exclude`` is skipped (used to keep an action's target from
        resolving to its own actor).
        """
        command = command.lower()
        if split_words:
            for word in split_words:
                if word in command:
                    parts = command.split(word, 1)
                    command_before_word = parts[0]
                    command_after_word = parts[1]
                    if position == "before":
                        command = command_before_word
                    if position == "after":
                        command = command_after_word
                    break
        for name in self.game.characters.keys():
            if name.lower() in command:
                candidate = self.game.characters[name]
                if exclude is not None and candidate is exclude:
                    continue
                return candidate
        # A character's aliases match too -- "give dates to jackals" finds the
        # "jackal pack" (same substring rule as names).
        for candidate in self.game.characters.values():
            if exclude is not None and candidate is exclude:
                continue
            for alias in getattr(candidate, "aliases", ()):
                if alias in command:
                    return candidate
        return self.game.player

    def get_character_location(self, character: Character) -> Location:
        return character.location

    def match_item(
        self, command: str, item_dict: dict[str, Item], hint: str = None
    ) -> Item:
        """
        Check whether the name any of the items in this dictionary match the
        command. If so, return Item, else return None.
        """
        matched_items = {}
        match_len = {}  # how specific each match was -- length of the matched token
        for item_name in item_dict:
            item = item_dict[item_name]
            # the item matches if its name -- or any registered alias ("cot" for
            # "army cot") -- appears in the command, or it matches the hint
            names = [item_name, *getattr(item, "aliases", ())]
            hits = [n for n in names if n in command]
            if hits:
                matched_items[item_name] = item
                match_len[item_name] = max(len(n) for n in hits)
            if hint and (item_name in hint or hint in item_name):
                matched_items[item_name] = item
                match_len.setdefault(item_name, 0)

        if len(matched_items) == 0:
            return None
        # if there are multiple items that are matched
        # then try to return one matches the hint
        elif len(matched_items) > 1 and hint:
            # exact match with hint
            if hint in matched_items:
                item = matched_items[hint]
                return item
            # hint in item name
            for item_name in matched_items:
                if hint in item_name or item_name in hint:
                    item = matched_items[item_name]
                    return item
        # Otherwise prefer the most specific match: the longest name/alias that
        # appeared in the command, so "rancher keys" beats "keys" and "army cot"
        # beats "cot" rather than returning whichever was registered first.
        best_name = max(matched_items, key=lambda n: match_len.get(n, 0))
        return matched_items[best_name]

    def match_topic(self, command: str, topics: dict[str, str]) -> str | None:
        """Pick the conversation topic a command refers to, or None.

        *topics* maps a topic keyword to its canned line (the Talk action looks
        up the line). The deterministic parser matches by substring -- the
        longest topic keyword that appears in the command wins, so "ask the
        hermit about the prophecy" resolves to "prophecy". The LLM parser
        overrides this to match by meaning."""
        command = command.lower()
        for key in sorted(topics, key=len, reverse=True):
            if key.lower() in command:
                return key
        return None

    def _answer_to_prompt(self, command: str, actor) -> str | None:
        """If a prompt is posed (issue #110) and *command* answers it, return the
        command to dispatch in its place; else None. Only the player answers
        prompts -- an NPC actor (acting via its behavior) is never reading the
        question posed to the player."""
        if actor is not None and actor is not self.game.player:
            return None
        prompt = self.game.pending_prompt()
        if prompt is None:
            return None
        return self.match_prompt(command, prompt)

    def match_prompt(self, command: str, prompt) -> str | None:
        """Read *command* as an answer to a posed Prompt (see prompts.py), and
        return the command to dispatch, or None if it doesn't answer it.

        A free-text prompt forwards the whole reply to its verb. A choice prompt
        matches the player's words against the option keywords (longest first,
        on word boundaries so "no" doesn't fire inside "north"); the LLM parser
        overrides this to match by meaning."""
        if prompt.free_text:
            return f"{prompt.forward_as} {command}".strip()
        cmd = command.lower()
        for keyword in sorted(prompt.options, key=len, reverse=True):
            if re.search(rf"\b{re.escape(keyword.lower())}\b", cmd):
                return prompt.options[keyword]
        return None

    def get_items_in_scope(self, character=None) -> dict[str, Item]:
        """
        Returns a list of items in character's location and in their inventory
        """
        if character is None:
            character = self.game.player
        items_in_scope = {}
        for item_name in character.location.items:
            item = character.location.items[item_name]
            # Hidden items stay out of scope until a SEARCH reveals them.
            if item.get_property("is_hidden"):
                continue
            items_in_scope[item_name] = item
        for item_name in character.inventory:
            items_in_scope[item_name] = character.inventory[item_name]
        # What a character has on -- worn or wielded -- is in scope too: you can
        # EXAMINE the gown you're wearing or the sword in your hand, unlock a
        # door with a sheathed key, and so on. (GET/DROP/GIVE build their own
        # scopes and guard the worn/wielded cases, so they're unaffected.)
        for item_name in character.worn:
            items_in_scope[item_name] = character.worn[item_name]
        for item_name in character.wielded:
            items_in_scope[item_name] = character.wielded[item_name]
        # Items inside an OPEN holder that is itself in scope are reachable
        # too -- a blanket in a boat, a candle on a table, an item in a
        # carried bag. Recursive: an open jar standing on a plinth is two
        # holders deep and still within arm's reach (CCB: 'taste brain' at
        # the seal found nothing at one level).
        frontier = list(items_in_scope.values())
        while frontier:
            holder = frontier.pop()
            for cname, citem in holder.accessible_contents().items():
                if cname not in items_in_scope:
                    items_in_scope[cname] = citem
                    frontier.append(citem)
        return items_in_scope

    def get_direction(self, command: str, location: Location = None) -> str:
        """
        Converts aliases for directions into its canonical direction name.

        Returns the direction as a string (Direction members ARE strings via
        the str-mixin enum, so the return type is compatible with the
        existing dict lookups in Location.connections).
        """
        command = command.lower().strip()
        # Single-letter shortcuts only fire on the bare command -- "n", "s",
        # not "open the box".
        if command in _DIRECTION_ALIASES:
            return _DIRECTION_ALIASES[command]

        # NPC commands are actor-prefixed ("troll go north"); strip a leading
        # character name so the movement-verb check below sees "go north".
        for cname in self.game.characters:
            cl = cname.lower()
            if command.startswith(cl + " "):
                command = command[len(cl) + 1 :].strip()
                break

        # Location-specific travel synonyms ("enter tomb" -> north): matched
        # on the EXACT typed command, before any verb-stripping, so "climb
        # tomb" and "enter tomb" can aim at different exits.
        if location:
            direction = location.direction_aliases.get(command)
            if direction is not None:
                return direction

        # Candidate names: canonical directions plus any exit names this
        # location declares. Longest first, so a multi-word exit ("to hobbs
        # cafe") wins over a short one ("to") that is a prefix of it.
        names = [(str(d), d) for d in _SUBSTRING_DIRECTIONS + _GO_SUFFIX_DIRECTIONS]
        if location:
            names += [(exit.lower(), exit) for exit in location.connections.keys()]
        names.sort(key=lambda pair: len(pair[0]), reverse=True)

        # Strip a leading movement verb ("go north" -> target "north"). A bare
        # movement verb names no destination.
        target = command
        led = False
        for verb in _MOVEMENT_VERBS:
            if command == verb:
                return None
            if command.startswith(verb + " "):
                target = command[len(verb) + 1 :].strip()
                led = True
                break

        # Movement is recognized when the (verb-stripped) command IS a direction
        # / exit name, or -- only if a movement verb led the command -- a name
        # appears in it on word boundaries ("go through the north gate"). A bare
        # direction with no verb is matched by the exact check. Crucially, a
        # name is NEVER matched as a mere substring of another word, so an "in"
        # exit no longer fires inside "examine".
        for name, value in names:
            if target == name:
                return value
            if led and re.search(rf"\b{re.escape(name)}\b", target):
                return value
        return None


class LlmParser(Parser):
    """EXPERIMENTAL (untested against a live API). Intent *and* argument matching
    via an LLM, each constrained to the game's actual options.

    The second of the engine's two parsers. The default ``Parser`` handles
    verb-noun commands (ranking multi-word actions specific-first); ``LlmParser``
    handles flexible natural language ("hand the blacksmith my axe", "rouse the
    dragon") end to end: it overrides ``determine_intent`` AND the argument
    matchers (``get_character`` / ``match_item`` / ``get_direction``), since
    picking the right verb isn't enough -- "hand the blacksmith my axe" also needs
    "the blacksmith" resolved to the ``smith`` and "my axe" to the ``axe``.

    All four route through one primitive, :meth:`_pick_one`: the model chooses
    from an *enum* of the real options via structured outputs, so it can't
    hallucinate an action/character/item/exit that doesn't exist (a robust
    successor to the classic regex-over-a-numbered-list GPT parser). Options are
    described with their current location for disambiguation, and a ``hint``
    (e.g. "giver"/"recipient") is threaded through where the base API offers one.

    Graceful fallback: on any API error -- or when the model picks "none" -- each
    method defers to the deterministic ``Parser`` implementation, so a transient
    failure degrades to keyword matching rather than crashing the game. The
    deterministic parser covers canonical verb-noun input; the LLM covers the
    rest -- a natural hybrid.

    Cost note: a single command can trigger several LLM calls (intent + one per
    argument); spend is tracked by the usage ledger. ``anthropic`` is imported
    lazily, so importing this module adds no hard dependency. Requires the SDK +
    ANTHROPIC_API_KEY; the default model is ``claude-opus-4-8``.
    """

    def __init__(self, game, model="claude-opus-4-8", echo_commands=False):
        super().__init__(game, echo_commands=echo_commands)
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def _pick_one(self, instructions, options, query, allow_none=True):
        """Ask the model to choose one of *options* for *query*.

        *options* is an ordered ``{name: (description, value)}`` mapping. The
        model's choice is enum-constrained to the names (plus "none" when
        *allow_none*), so it can only return a real option. Returns the chosen
        value, or ``None`` (no match / "none"). Raises only on an API failure --
        callers catch that and fall back to the deterministic parser.
        """
        import json

        names = list(options.keys())
        enum = names + (["none"] if allow_none else [])
        listing = "\n".join(f"- {n}: {desc}" for n, (desc, _) in options.items())
        if allow_none:
            listing += "\n- none: nothing here matches"
        system = f"{instructions}\n\nChoices:\n{listing}\n\nReturn exactly one choice."
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=64,
            system=system,
            messages=[{"role": "user", "content": query}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"choice": {"type": "string", "enum": enum}},
                        "required": ["choice"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        choice = json.loads(text).get("choice")
        return options[choice][1] if choice in options else None

    def determine_intent(self, command, actor=None):
        # Catalogue from the CURRENT action set every call: custom actions are
        # registered after __init__ (set_parser / add_action), so caching it at
        # construction would omit every game-defined verb from the enum.
        options = {}
        for _, a in self.actions.items():
            desc = a.ACTION_DESCRIPTION or a.action_name()
            if getattr(a, "ACTION_ALIASES", None):
                desc += f" (aliases: {', '.join(a.ACTION_ALIASES)})"
            options[a.action_name()] = (desc, a.action_name())
        instructions = (
            "You are the parser for a text-adventure game. Choose the action that "
            "best matches the player's command by meaning."
        )
        try:
            choice = self._pick_one(instructions, options, command, allow_none=False)
        except Exception:
            choice = None
        return (
            choice if choice is not None else super().determine_intent(command, actor)
        )

    def get_character(self, command, hint=None, split_words=None, position=None):
        options = {}
        for name, ch in self.game.characters.items():
            loc = f" (currently in {ch.location.name})" if ch.location else ""
            label = (
                ("the player -- " if ch is self.game.player else "")
                + (ch.description or name)
                + loc
            )
            options[name] = (label, ch)
        instructions = (
            "You are the parser for a text-adventure game. Match the character the "
            "command refers to."
        )
        if hint:
            instructions += f" The character you want is the {hint}."
        try:
            ch = self._pick_one(instructions, options, command, allow_none=True)
        except Exception:
            ch = None
        return (
            ch
            if ch is not None
            else super().get_character(
                command, hint=hint, split_words=split_words, position=position
            )
        )

    def match_item(
        self, command: str, item_dict: dict[str, Item], hint: str = None
    ) -> Item:
        if not item_dict:
            return None
        options = {}
        for name, item in item_dict.items():
            loc = (
                f" (in {item.location.name})" if getattr(item, "location", None) else ""
            )
            options[name] = ((item.description or name) + loc, item)
        instructions = (
            "You are the parser for a text-adventure game. Match the item the "
            "command refers to."
        )
        if hint:
            instructions += f" Hint: {hint}."
        try:
            item = self._pick_one(instructions, options, command, allow_none=True)
        except Exception:
            item = None
        return (
            item if item is not None else super().match_item(command, item_dict, hint)
        )

    def match_topic(self, command: str, topics: dict[str, str]) -> str | None:
        if not topics:
            return None
        # Describe each topic by its line so the model can match by meaning
        # ("about the end of days" -> a "prophecy" topic), not just keyword.
        options = {key: (line, key) for key, line in topics.items()}
        instructions = (
            "You are the parser for a text-adventure game. The player is talking "
            "to a character; pick the topic they're asking about, or none."
        )
        try:
            topic = self._pick_one(instructions, options, command, allow_none=True)
        except Exception:
            topic = None
        return topic if topic is not None else super().match_topic(command, topics)

    def match_prompt(self, command: str, prompt) -> str | None:
        # Free-text answers are forwarded verbatim -- no model needed. Choice
        # answers are matched by meaning ("the clever option" -> "wits").
        if prompt.free_text or not prompt.options:
            return super().match_prompt(command, prompt)
        options = {kw: (kw, kw) for kw in prompt.options}
        instructions = (
            "You are the parser for a text-adventure game. The game asked the "
            "player a question; pick the option their reply chooses, or none."
        )
        if prompt.text:
            instructions += f" The question was: {prompt.text}"
        try:
            kw = self._pick_one(instructions, options, command, allow_none=True)
        except Exception:
            kw = None
        if kw is not None:
            return prompt.options[kw]
        return super().match_prompt(command, prompt)

    def get_direction(self, command: str, location: Location = None) -> str:
        options = {}
        if location:
            for direction, dest in location.connections.items():
                options[direction] = (f"{direction} -- toward {dest.name}", direction)
        if options:
            instructions = (
                "You are the parser for a text-adventure game. Match the exit the "
                "player wants to travel through."
            )
            try:
                d = self._pick_one(instructions, options, command, allow_none=True)
            except Exception:
                d = None
            if d is not None:
                return d
        return super().get_direction(command, location)
