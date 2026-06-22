"""Action template emitters.

Each ``emit_*`` function takes a spec id and a params dict and returns a
Python source string defining one ``actions.Action`` subclass. The patterns
mirror ``notebooks/hw1_solution/action_castle.py`` so the regenerated module
is behaviorally indistinguishable from the reference.
"""

from __future__ import annotations

from ._common import humanize_property, python_class_name, q as _q  # noqa: F401

# ----------------------------------------------------------------------
# unlock_with_key (mirrors Action Castle's Unlock_Door)
# ----------------------------------------------------------------------


def emit_unlock_with_key(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    lock = params["lock_item"]
    key = params["key_item"]
    unlocked_property = params["unlocked_property"]
    action_name = f"unlock {lock}"
    description = f"Unlock a {lock} with a {key}"
    return f"""\
class {cls}(actions.Action):
    ACTION_NAME = {_q(action_name)}
    ACTION_DESCRIPTION = {_q(description)}
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.key = self.parser.match_item(
            {_q(key)}, self.parser.get_items_in_scope(self.character)
        )
        self.lock = self.parser.match_item(
            {_q(lock)}, self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.lock, "There's no {lock} here."):
            return False
        if not self.loc_has_item(self.character.location, self.lock):
            return False
        if not self.has_property(
            self.lock, {_q(unlocked_property)}, "The {lock} is not locked."
        ):
            return False
        if not self.was_matched(
            self.key, f"{{self.character.name}} does not have the {key}."
        ):
            return False
        if not self.is_in_inventory(self.character, self.key):
            return False
        return True

    def apply_effects(self):
        self.lock.set_property({_q(unlocked_property)}, False)
        self.parser.ok(f"{{self.character.name}} unlocked the {lock}.")
"""


# ----------------------------------------------------------------------
# read_inscription_to_banish (mirrors Action Castle's Read_Runes)
# ----------------------------------------------------------------------


def emit_read_inscription_to_banish(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    inscribed = params["inscribed_item"]
    target = params["target_character"]
    required = params["required_property"]
    banished = params["banished_property"]
    drop_inv = params.get("drop_target_inventory", True)
    remove = params.get("remove_target_from_scene", True)
    action_name = params.get("action_name", f"read {inscribed}")
    description = params.get(
        "action_description", f"Read the inscription on the {inscribed}"
    )

    lines = [
        f"class {cls}(actions.Action):",
        f"    ACTION_NAME = {_q(action_name)}",
        f"    ACTION_DESCRIPTION = {_q(description)}",
        "    ACTION_ALIASES = []",
        "    PLAYER_CUSTOM = True",
        "",
        "    def __init__(self, game, command, actor=None):",
        "        super().__init__(game, actor=actor)",
        "        self.character = self.acting_character(command)",
        f"        self.inscribed = self.parser.match_item(",
        f"            {_q(inscribed)}, self.parser.get_items_in_scope(self.character)",
        "        )",
        f"        self.target = self.parser.get_character({_q(target)})",
        "",
        "    def check_preconditions(self) -> bool:",
        "        if not self.was_matched(",
        f'            self.inscribed, "You don\'t see anything to read here."',
        "        ):",
        "            return False",
        "        if not self.is_in_inventory(self.character, self.inscribed):",
        "            return False",
        "        if not self.was_matched(",
        f'            self.target, "The inscription is a banishment spell, but there is nothing to banish here."',
        "        ):",
        "            return False",
        "        if not self.at(",
        "            self.target,",
        "            self.character.location,",
        f'            "The inscription is a banishment spell, but there is nothing to banish here.",',
        "        ):",
        "            return False",
        "        if not self.has_property(",
        f"            self.inscribed,",
        f"            {_q(required)},",
        f"            \"Nothing happens. Perhaps the {inscribed} needs to be {required.removeprefix('is_')}?\",",
        "        ):",
        "            return False",
        "        return True",
        "",
        "    def apply_effects(self):",
        f"        self.parser.ok(",
        f'            f"{{self.character.name.capitalize()}} reads the inscription on the {inscribed}."',
        "        )",
    ]
    if drop_inv:
        lines += [
            "",
            "        # Drop target's inventory before removing them from the scene.",
            "        items = list(self.target.inventory.keys())",
            "        for item_name in items:",
            "            item = self.target.inventory[item_name]",
            "            drop = actions.Drop(",
            '                self.game, f"{self.target.name} drops {item.name}"',
            "            )",
            "            if drop.check_preconditions():",
            "                drop.apply_effects()",
        ]
    lines += [
        "",
        f"        self.target.set_property({_q(banished)}, True)",
        f'        self.parser.ok(f"{{self.target.name}} is banished.")',
    ]
    if remove:
        lines += [
            "        if self.target.location is not None:",
            "            self.target.location.remove_character(self.target)",
        ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# propose_marriage (mirrors Action Castle's Propose)
# ----------------------------------------------------------------------


def emit_propose_marriage(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    required_state = params["required_emotional_state"]
    married_prop = params["set_property_on_pair"]
    royalty_prop = params.get("royalty_property")
    return f"""\
class {cls}(actions.Action):
    ACTION_NAME = "propose"
    ACTION_DESCRIPTION = "Propose marriage to someone"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        words = ["propose", "marry"]
        self.proposer = self.acting_character(
            command, hint="proposer", split_words=words, position="before"
        )
        self.propositioned = self.parser.get_character(
            command,
            hint="propositioned",
            split_words=words,
            position="after",
            exclude=self.proposer,
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.proposer, "They aren't here."):
            return False
        if not self.was_matched(self.propositioned, "They aren't here."):
            return False
        if self.proposer == self.propositioned:
            self.parser.fail(f"{{self.proposer.name}} cannot marry themself")
            return False
        if not self.at(
            self.propositioned,
            self.proposer.location,
            f"{{self.propositioned.name}} and {{self.proposer.name}} aren't in the same location.",
        ):
            return False
        if not self.property_equals(
            self.proposer, "emotional_state", {_q(required_state)}
        ):
            return False
        if not self.property_equals(
            self.propositioned, "emotional_state", {_q(required_state)}
        ):
            return False
        if self.has_property(
            self.proposer,
            {_q(married_prop)},
            f"{{self.proposer.name}} is already married",
            display_message_upon=True,
        ):
            return False
        if self.has_property(
            self.propositioned,
            {_q(married_prop)},
            f"{{self.propositioned.name}} is already married",
            display_message_upon=True,
        ):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(f"{{self.propositioned.name.capitalize()}} says YES!")
        self.proposer.set_property({_q(married_prop)}, True)
        self.propositioned.set_property({_q(married_prop)}, True)
        self.parser.ok(
            f"{{self.propositioned.name}} and {{self.proposer.name}} are now married."
        )
        {'if self.proposer.get_property(' + _q(royalty_prop) + ') or self.propositioned.get_property(' + _q(royalty_prop) + '):' if royalty_prop else 'pass'}
        {'    self.proposer.set_property(' + _q(royalty_prop) + ', True)' if royalty_prop else ''}
        {'    self.propositioned.set_property(' + _q(royalty_prop) + ', True)' if royalty_prop else ''}
"""


# ----------------------------------------------------------------------
# wear_item (mirrors Action Castle's Wear_Crown)
# ----------------------------------------------------------------------


def emit_wear_item(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    item = params["item"]
    required = params["required_actor_property"]
    set_prop = params["set_actor_property"]
    action_name = f"wear {item}"
    description = f"Put on the {item}"
    permission_msg = f"You must be {humanize_property(required)} to wear the {item}."
    return f"""\
class {cls}(actions.Action):
    ACTION_NAME = {_q(action_name)}
    ACTION_DESCRIPTION = {_q(description)}
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            {_q(item)}, self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        if not self.has_property(
            self.character, {_q(required)}, {_q(permission_msg)}
        ):
            return False
        return True

    def apply_effects(self):
        self.character.set_property({_q(set_prop)}, True)
        self.parser.ok(
            f"{{self.character.name.capitalize()}} dons the {item}."
        )
"""


# ----------------------------------------------------------------------
# sit_on_furniture (mirrors Action Castle's Sit_On_Throne)
# ----------------------------------------------------------------------


def emit_sit_on_furniture(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    furniture = params["furniture_item"]
    required = params["required_actor_property"]
    set_prop = params["set_actor_property"]
    action_name = f"sit on {furniture}"
    description = f"Sit on the {furniture}"
    permission_msg = (
        f"You must be {humanize_property(required)} to sit on the {furniture}."
    )
    return f"""\
class {cls}(actions.Action):
    ACTION_NAME = {_q(action_name)}
    ACTION_DESCRIPTION = {_q(description)}
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.furniture = self.parser.match_item(
            {_q(furniture)}, self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        if not self.was_matched(self.furniture, "The {furniture} couldn't be found."):
            return False
        if not self.at(
            self.furniture, self.character.location, "The {furniture} isn't here."
        ):
            return False
        if not self.has_property(
            self.character,
            {_q(required)},
            {_q(permission_msg)},
        ):
            return False
        return True

    def apply_effects(self):
        self.character.set_property({_q(set_prop)}, True)
        self.parser.ok(
            f"{{self.character.name.title()}} sits on the {furniture}."
        )
"""


# ----------------------------------------------------------------------
# npc_taunt (mirrors Growl/Snarl/Warn/Threaten/Haunt/Pound_Fists)
# ----------------------------------------------------------------------


def _split_words_for(verb: str) -> list[str]:
    return [verb]


def emit_npc_taunt(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    verb = params["verb"]
    template_string = params["template_string"]
    requires_falsy = params.get("requires_actor_property_falsy")
    description = params.get("action_description", f"NPC taunt: {verb}")

    # The taunt may target another character or be solo (e.g. "pound fists").
    has_target = "{target}" in template_string

    lines = [
        f"class {cls}(actions.Action):",
        f"    ACTION_NAME = {_q(verb)}",
        f"    ACTION_DESCRIPTION = {_q(description)}",
        "    ACTION_ALIASES = []",
        "    PLAYER_CUSTOM = True",
        "    NPC_ONLY = True",
        "",
        "    def __init__(self, game, command, actor=None):",
        "        super().__init__(game, actor=actor)",
        f"        self.character = self.acting_character(",
        f"            command, split_words={_q(verb)!s}.split('|'), position='before'",
        "        )",
    ]
    if has_target:
        lines += [
            "        self.target = self.parser.get_character(",
            f"            command, split_words=[{_q(verb)}], position='after',",
            "            exclude=self.character,",
            "        )",
        ]
    lines += [
        "",
        "    def check_preconditions(self) -> bool:",
    ]
    if has_target:
        lines += ["        if not self.at(self.character, self.target.location):"]
        lines += ["            return False"]
    if requires_falsy:
        lines += [
            f"        if self.character.get_property({_q(requires_falsy)}):",
            f'            self.parser.fail(f"{{self.character.name}} has been banished.")',
            "            return False",
        ]
    lines += ["        return True", ""]

    # Emit apply_effects with the template string converted.
    converted = _convert_template_string(template_string, has_target=has_target)
    lines += [
        "    def apply_effects(self):",
        f"        description = {converted}",
        "        self.parser.npc_ok(description)",
    ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# npc_kill (mirrors Action Castle's Ghost_Touch)
# ----------------------------------------------------------------------


def emit_npc_kill(action_id: str, params: dict) -> str:
    cls = python_class_name(action_id)
    verb = params["verb"]
    template_string = params["template_string"]
    sets_target_property = params["sets_target_property"]
    requires_falsy = params.get("requires_actor_property_falsy")
    description = params.get("action_description", f"NPC kill: {verb}")

    has_target = "{target}" in template_string

    lines = [
        f"class {cls}(actions.Action):",
        f"    ACTION_NAME = {_q(verb)}",
        f"    ACTION_DESCRIPTION = {_q(description)}",
        "    ACTION_ALIASES = []",
        "    PLAYER_CUSTOM = True",
        "    NPC_ONLY = True",
        "",
        "    def __init__(self, game, command, actor=None):",
        "        super().__init__(game, actor=actor)",
        "        self.character = self.acting_character(",
        f"            command, split_words=[{_q(verb)}], position='before'",
        "        )",
    ]
    if has_target:
        lines += [
            "        self.target = self.parser.get_character(",
            f"            command, split_words=[{_q(verb)}], position='after',",
            "            exclude=self.character,",
            "        )",
        ]
    lines += [
        "",
        "    def check_preconditions(self) -> bool:",
    ]
    if has_target:
        lines += ["        if not self.at(self.character, self.target.location):"]
        lines += ["            return False"]
    if requires_falsy:
        lines += [
            f"        if self.character.get_property({_q(requires_falsy)}):",
            "            self.parser.fail(",
            f'                f"{{self.character.name}} has been banished."',
            "            )",
            "            return False",
        ]
    lines += ["        return True", ""]
    converted = _convert_template_string(template_string, has_target=has_target)
    lines += [
        "    def apply_effects(self):",
        f"        description = {converted}",
        "        self.parser.npc_ok(description)",
    ]
    if has_target:
        lines += [f"        self.target.set_property({_q(sets_target_property)}, True)"]
    else:
        lines += [
            f"        self.character.set_property({_q(sets_target_property)}, True)"
        ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# flavor_response (player-side, no state change)
# ----------------------------------------------------------------------


def emit_flavor_response(action_id: str, params: dict) -> str:
    """A custom action that matches a verb literal and prints a message.

    Used for verbs the source describes as having a flavor response but no
    state change -- e.g. ``shake machine`` / ``punch machine`` / ``kick
    machine`` against a powered-off vending machine. The action succeeds
    (so the turn passes; the world ticks), prints the configured message,
    and changes nothing.

    Optional preconditions:
      * ``requires_in_scope``: an item name that must be in the actor's
        scope (location items or inventory).
      * ``at_location``: a location name; the actor must be there.
      * ``consumes_item``: an item name that must be in the actor's
        inventory; it is removed when the action runs (e.g. tossing a coin
        into a well -- the coin is gone for good).

    Optional matching:
      * ``aliases``: extra phrasings that route here too. Custom-action
        precedence matches a verb OR any alias, so a "toss penny" action can
        also answer to "drop penny" (see parsing.Parser.determine_intent).

    Optional effects:
      * ``ends_game``: when truthy, the action ends the game after printing
        its message -- for in-place lethal/terminal verbs whose source text
        ends in "THE END" (e.g. ``FIGHT BANDITS`` -> dragged off and eaten).
        Sets ``game.game_over`` + ``game_over_description``, which
        ``Game.is_game_over()`` already honors (mirrors the game-over-on-entry
        path in ``actions/locations.py``). Use this instead of a no-op
        flavor_response when the rule is a dead end, so the game actually
        stops rather than printing a death message and continuing.
      * ``at_location_message``: paired with ``at_location`` -- when the actor
        is somewhere else, print THIS line as ordinary narration (a gentle
        redirect) instead of the default "Nothing happens." block. Use for
        verbs that only make sense in one place but shouldn't read as an error
        elsewhere (e.g. "propose" away from the romantic spot).
    """
    cls = python_class_name(action_id)
    verb = params["verb"]
    template_string = params["template_string"]
    description = params.get("action_description", f"Flavor response: {verb}")
    requires_in_scope = params.get("requires_in_scope")
    at_location = params.get("at_location")
    at_location_message = params.get("at_location_message")
    consumes_item = params.get("consumes_item")
    aliases = params.get("aliases") or []
    ends_game = params.get("ends_game")
    requires_actor_properties = params.get("requires_actor_properties") or {}
    sets_actor_properties = params.get("sets_actor_properties") or {}

    lines = [
        f"class {cls}(actions.Action):",
        f"    ACTION_NAME = {_q(verb)}",
        f"    ACTION_DESCRIPTION = {_q(description)}",
        f"    ACTION_ALIASES = {list(aliases)!r}",
        "    PLAYER_CUSTOM = True",
        "",
        "    def __init__(self, game, command, actor=None):",
        "        super().__init__(game, actor=actor)",
        "        self.character = self.acting_character(command)",
    ]
    if requires_in_scope:
        lines += [
            f"        self.scope_item = self.parser.match_item(",
            f"            {_q(requires_in_scope)},",
            f"            self.parser.get_items_in_scope(self.character),",
            "        )",
        ]
    if consumes_item:
        lines += [
            f"        self.consumed = self.parser.match_item(",
            f"            {_q(consumes_item)},",
            f"            self.parser.get_items_in_scope(self.character),",
            "        )",
        ]
    lines += [
        "",
        "    def check_preconditions(self) -> bool:",
    ]
    if requires_in_scope:
        lines += [
            "        if not self.was_matched(",
            f'            self.scope_item, "There\'s no {requires_in_scope} here."',
            "        ):",
            "            return False",
        ]
    if at_location:
        wrong_loc = (
            f"            self.parser.ok({_q(at_location_message)})"
            if at_location_message
            else '            self.parser.fail("Nothing happens.")'
        )
        lines += [
            f"        if self.character.location.name != {_q(at_location)}:",
            wrong_loc,
            "            return False",
        ]
    if consumes_item:
        lines += [
            "        if not self.is_in_inventory(self.character, self.consumed):",
            "            return False",
        ]
    for prop_name, expected in requires_actor_properties.items():
        py_val = (
            "True"
            if expected is True
            else "False" if expected is False else _q(expected)
        )
        lines += [
            f"        if self.character.get_property({_q(prop_name)}) != {py_val}:",
            '            self.parser.fail("Nothing happens.")',
            "            return False",
        ]
    lines += ["        return True", ""]
    converted = _convert_flavor_string(template_string)
    lines += [
        "    def apply_effects(self):",
        f"        self.parser.ok({converted})",
    ]
    for prop_name, value in sets_actor_properties.items():
        py_val = "True" if value is True else "False" if value is False else _q(value)
        lines += [f"        self.character.set_property({_q(prop_name)}, {py_val})"]
    if consumes_item:
        # The item is used up -- discard it from the actor (gone for good).
        lines += ["        self.character.discard_item(self.consumed)"]
    if ends_game:
        # Terminal verb: end the game after the message (e.g. a fatal fight).
        # Game.is_game_over() reads game_over, so this stops the loop.
        lines += [
            f"        self.game.game_over = True",
            f"        self.game.game_over_description = {converted}",
        ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# transform_item (player-side, mutates the target item's properties)
# ----------------------------------------------------------------------


def emit_transform_item(action_id: str, params: dict) -> str:
    """A custom action that mutates one or more properties on a target item.

    Covers verbs like ``open soda`` (sets ``is_open: true``), ``smash
    bottle`` (sets ``is_broken: true``), or ``light torch`` substitutes when
    the engine's built-in Light isn't what's wanted. The action requires the
    item to be in the actor's scope (or inventory if ``requires_in_inventory``
    is true), applies every property in ``sets_properties``, and prints the
    configured message.

    Optional preconditions:
      * ``requires_in_inventory``: bool (default false). When true, the item
        must be in the actor's inventory.
      * ``requires_properties``: dict {property: expected value}. The
        action fails if any expected value doesn't match.

    Optional effects:
      * ``sets_actor_properties``: dict {property: value}. Properties set
        on the acting character (the player typically). Use for state
        the engine reads off the actor -- ``has_sword`` for a guard
        gate, ``is_champion`` as a win flag.
      * ``ends_game``: when truthy, marks ``game.game_over`` after the
        message. Use for terminal verbs whose source text ends with "THE
        END" (a coronation, a death).
    """
    cls = python_class_name(action_id)
    verb = params["verb"]
    item = params["item"]
    template_string = params["template_string"]
    sets_properties = params["sets_properties"]
    sets_actor_properties = params.get("sets_actor_properties") or {}
    requires_inv = bool(params.get("requires_in_inventory", False))
    requires_properties = params.get("requires_properties") or {}
    ends_game = params.get("ends_game")
    description = params.get("action_description", f"Transform: {verb}")

    lines = [
        f"class {cls}(actions.Action):",
        f"    ACTION_NAME = {_q(verb)}",
        f"    ACTION_DESCRIPTION = {_q(description)}",
        "    ACTION_ALIASES = []",
        "    PLAYER_CUSTOM = True",
        "",
        "    def __init__(self, game, command, actor=None):",
        "        super().__init__(game, actor=actor)",
        "        self.character = self.acting_character(command)",
        f"        self.item = self.parser.match_item(",
        f"            {_q(item)}, self.parser.get_items_in_scope(self.character)",
        "        )",
        "",
        "    def check_preconditions(self) -> bool:",
        f'        if not self.was_matched(self.item, "There\'s no {item} here."):',
        "            return False",
    ]
    if requires_inv:
        lines += ["        if not self.is_in_inventory(self.character, self.item):"]
        lines += ["            return False"]
    for prop_name, expected in requires_properties.items():
        if isinstance(expected, bool):
            if expected:
                lines += [
                    f"        if not self.has_property(",
                    f"            self.item, {_q(prop_name)},",
                    f"            f\"The {item} is not {prop_name.removeprefix('is_').replace('_', ' ')} yet.\"",
                    "        ):",
                    "            return False",
                ]
            else:
                lines += [
                    f"        if self.item.get_property({_q(prop_name)}):",
                    f"            self.parser.fail(f\"The {item} is already {prop_name.removeprefix('is_').replace('_', ' ')}.\")",
                    "            return False",
                ]
        else:
            lines += [
                f"        if self.item.get_property({_q(prop_name)}) != {_q(expected)}:",
                f'            self.parser.fail("It\'s not the right state for that.")',
                "            return False",
            ]
    lines += ["        return True", ""]

    converted = _convert_flavor_string(template_string, item_var="self.item")
    lines += [
        "    def apply_effects(self):",
        f"        self.parser.ok({converted})",
    ]
    for prop_name, value in sets_properties.items():
        py_val = "True" if value is True else "False" if value is False else _q(value)
        lines += [f"        self.item.set_property({_q(prop_name)}, {py_val})"]
    for prop_name, value in sets_actor_properties.items():
        py_val = "True" if value is True else "False" if value is False else _q(value)
        lines += [f"        self.character.set_property({_q(prop_name)}, {py_val})"]
    if ends_game:
        lines += [
            f"        self.game.game_over = True",
            f"        self.game.game_over_description = {converted}",
        ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Shared template-string conversion (flavor + transform)
# ----------------------------------------------------------------------


def _convert_flavor_string(template: str, item_var: str = "self.item") -> str:
    """Convert a spec template string into an f-string, allowing {item}
    and {actor} placeholders.

    Placeholders accepted in the spec:
      {actor}        -> self.character.name
      {actor.title}  -> self.character.name.capitalize()
      {item}         -> {item_var}.name (default: self.item.name)
      {item.title}   -> {item_var}.name.capitalize()

    Unknown {placeholders} are kept literal as ``{{...}}``.
    """
    out = []
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "{":
            end = template.find("}", i)
            if end == -1:
                out.append("{{")
                i += 1
                continue
            placeholder = template[i + 1 : end]
            mapping = {
                "actor": "{self.character.name}",
                "actor.title": "{self.character.name.capitalize()}",
                "item": "{" + item_var + ".name}",
                "item.title": "{" + item_var + ".name.capitalize()}",
            }
            out.append(mapping.get(placeholder, "{{" + placeholder + "}}"))
            i = end + 1
        elif ch == "}":
            out.append("}}")
            i += 1
        else:
            out.append(ch)
            i += 1
    body = "".join(out).replace('"', '\\"')
    return f'f"{body}"'


def _convert_template_string(template: str, has_target: bool) -> str:
    """Turn a spec template string into a Python f-string.

    Placeholders accepted in the spec:
      {actor}   -> self.character.name
      {actor.title}  -> self.character.name.capitalize()
      {target}  -> self.target.name
      {target.title} -> self.target.name.capitalize()

    Any other braces are kept literal (i.e. emitted as ``{{...}}``).
    """
    out = []
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "{":
            end = template.find("}", i)
            if end == -1:
                out.append("{{")
                i += 1
                continue
            placeholder = template[i + 1 : end]
            replacement = _placeholder_replacement(placeholder, has_target)
            out.append(replacement)
            i = end + 1
        elif ch == "}":
            out.append("}}")
            i += 1
        else:
            out.append(ch)
            i += 1
    body = "".join(out)
    # Escape quotes for a double-quoted f-string.
    body = body.replace('"', '\\"')
    return f'f"{body}"'


def _placeholder_replacement(placeholder: str, has_target: bool) -> str:
    """Map a {placeholder} from the spec to an f-string interpolation."""
    mapping = {
        "actor": "{self.character.name}",
        "actor.title": "{self.character.name.capitalize()}",
    }
    if has_target:
        mapping["target"] = "{self.target.name}"
        mapping["target.title"] = "{self.target.name.capitalize()}"
    return mapping.get(placeholder, "{{" + placeholder + "}}")
