"""Tests for affordance tags, worn/wielded slots, and equipment actions."""

import pytest

from text_adventure_games import actions, games, things
from text_adventure_games.enums import Property
from text_adventure_games.npc import tools_for


def _one_char_game():
    """A bare room with the player; tests add items as needed."""
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    game = games.Game(room, player, characters=[])
    return game


# ----------------------------------------------------------------------
# Round-trip serialization for the new slots
# ----------------------------------------------------------------------


def test_character_round_trips_worn_and_wielded():
    game = _one_char_game()
    player = game.player

    held = things.Item("ring", "a plain ring")
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)

    player.add_to_inventory(held)
    player.add_to_inventory(cloak)
    player.wear(cloak)
    player.add_to_inventory(sword)
    player.wield(sword)

    restored = things.Character.from_primitive(player.to_primitive())

    assert set(restored.inventory) == {"ring"}
    assert set(restored.worn) == {"cloak"}
    assert set(restored.wielded) == {"sword"}


def test_from_primitive_tolerates_old_data_without_slots():
    """Fixtures saved before the slots existed should still load."""
    legacy = {
        "name": "ghost",
        "description": "a spectre",
        "persona": "I haunt.",
        "inventory": {},
        "properties": {},
        "commands": [],
    }
    restored = things.Character.from_primitive(legacy)
    assert restored.worn == {}
    assert restored.wielded == {}


# ----------------------------------------------------------------------
# Wear / Take_Off
# ----------------------------------------------------------------------


def test_wear_moves_item_from_inventory_to_worn():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)

    assert game.parser.parse_command("wear cloak")
    assert "cloak" not in game.player.inventory
    assert "cloak" in game.player.worn


def test_wear_rejects_non_wearable_item():
    game = _one_char_game()
    rock = things.Item("rock", "a heavy rock")
    game.player.add_to_inventory(rock)

    assert not game.parser.parse_command("wear rock")
    assert "rock" in game.player.inventory
    assert "rock" not in game.player.worn


def test_take_off_returns_item_to_inventory():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    assert game.parser.parse_command("take off cloak")
    assert "cloak" in game.player.inventory
    assert "cloak" not in game.player.worn


# ----------------------------------------------------------------------
# Wield / Unwield
# ----------------------------------------------------------------------


def test_wield_moves_item_from_inventory_to_wielded():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)

    assert game.parser.parse_command("wield sword")
    assert "sword" not in game.player.inventory
    assert "sword" in game.player.wielded


def test_unwield_returns_item_to_inventory():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)
    game.player.wield(sword)

    assert game.parser.parse_command("unwield sword")
    assert "sword" in game.player.inventory
    assert "sword" not in game.player.wielded


# ----------------------------------------------------------------------
# Drop / Give reject equipped items
# ----------------------------------------------------------------------


def test_drop_fails_on_worn_item_then_succeeds_after_take_off():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    assert not game.parser.parse_command("drop cloak")
    assert "cloak" in game.player.worn

    assert game.parser.parse_command("take off cloak")
    assert game.parser.parse_command("drop cloak")
    assert "cloak" not in game.player.inventory
    assert "cloak" in game.player.location.items


def test_drop_fails_on_wielded_item():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)
    game.player.wield(sword)

    assert not game.parser.parse_command("drop sword")
    assert "sword" in game.player.wielded


def test_give_fails_on_worn_item():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    guard = things.Character("guard", "a guard", "I patrol.")
    game = games.Game(room, player, characters=[guard])
    room.add_character(guard)

    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    player.add_to_inventory(cloak)
    player.wear(cloak)

    assert not game.parser.parse_command("give cloak to guard")
    assert "cloak" in player.worn
    assert "cloak" not in guard.inventory


# ----------------------------------------------------------------------
# Observation surface
# ----------------------------------------------------------------------


def test_describe_for_lists_affordance_tags_on_items():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)

    obs = game.describe_for(game.player)
    assert "[wieldable, gettable]" in obs or "[gettable, wieldable]" in obs


def test_describe_for_shows_worn_and_wielded_sections():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.add_to_inventory(sword)
    game.player.wear(cloak)
    game.player.wield(sword)

    obs = game.describe_for(game.player)
    assert "Worn: cloak" in obs
    assert "Wielded: sword" in obs


def test_describe_for_omits_sick_line_when_healthy_634():
    # Byte-identical for games that never sicken a character: no is_sick, no line.
    game = _one_char_game()
    assert "You feel ill." not in game.describe_for(game.player)


def test_describe_for_shows_and_hides_self_sick_line_634():
    game = _one_char_game()
    game.player.set_property("is_sick", True)
    assert "You feel ill." in game.describe_for(game.player)
    # Authorable wording overrides the neutral default.
    game.player.set_property("sick_self_description", "Your stomach is cramping.")
    obs = game.describe_for(game.player)
    assert "Your stomach is cramping." in obs
    assert "You feel ill." not in obs
    # Recovery: the line simply disappears once is_sick clears.
    game.player.set_property("is_sick", False)
    assert "cramping" not in game.describe_for(game.player)


def test_visible_description_shows_sickness_to_a_bystander_634():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    other = things.Character("Nadia", "a student", "I study.")
    game = games.Game(room, player, characters=[other])
    room.add_character(other)
    other.set_property("is_sick", True)
    obs = game.describe_for(player)
    assert "Nadia - Nadia, looking ill" in obs
    # Authorable, and dead/unconscious still take priority over sick.
    other.set_property("sick_description", "Nadia, pale and sweating")
    assert "Nadia, pale and sweating" in game.describe_for(player)
    other.set_property("is_dead", True)
    assert "looking ill" not in game.describe_for(player)
    assert "pale and sweating" not in game.describe_for(player)


def test_describe_for_omits_affordance_brackets_for_plain_scenery():
    game = _one_char_game()
    statue = things.Item("statue", "a marble statue")
    statue.set_property(Property.GETTABLE, False)
    game.player.location.add_item(statue)

    obs = game.describe_for(game.player)
    # Statue line should have no brackets at all.
    [line] = [l for l in obs.splitlines() if "statue" in l]
    assert "[" not in line


# ----------------------------------------------------------------------
# Inventory listing: carried, then worn, then wielded
# ----------------------------------------------------------------------


def _inventory_text(game):
    from text_adventure_games.reporting import CaptureRenderer, Channel

    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.parse_command("inventory")
    return cap.texts(Channel.NARRATION)[-1]


def test_inventory_lists_carried_then_worn_then_wielded():
    game = _one_char_game()
    p = game.player
    for it, wearable, wieldable in [
        (things.Item("ring", "a plain ring"), False, False),
        (things.Item("cloak", "a wool cloak"), True, False),
        (things.Item("sword", "a short sword"), False, True),
    ]:
        if wearable:
            it.set_property(Property.WEARABLE, True)
        if wieldable:
            it.set_property(Property.WIELDABLE, True)
        p.add_to_inventory(it)
    p.wear(p.inventory["cloak"])
    p.wield(p.inventory["sword"])

    text = _inventory_text(game)
    assert "inventory contains:" in text and "a plain ring" in text
    assert "Wearing:" in text and "a wool cloak" in text
    assert "Wielding:" in text and "a short sword" in text
    # Order: carried section, then Wearing, then Wielding.
    assert text.index("contains:") < text.index("Wearing:") < text.index("Wielding:")
    # The cloak/sword moved out of inventory, so they don't double-list there.
    assert text.index("Wearing:") < text.index("a wool cloak")


def test_inventory_shows_worn_even_with_empty_hands():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    text = _inventory_text(game)
    assert "is empty." in text  # nothing in hand
    assert "Wearing:" in text and "a wool cloak" in text


def test_inventory_truly_empty():
    game = _one_char_game()
    text = _inventory_text(game)
    assert "is empty." in text
    assert "Wearing:" not in text and "Wielding:" not in text


# ----------------------------------------------------------------------
# REQUIRED_AFFORDANCES: affordance-curated toolsets (issue #612)
#
# A verb declares its placement requirement as data; the toolset builder
# (npc.tools_for) and the precondition gate read the SAME declaration, so
# "which verbs make sense here?" cannot drift between the two.
# ----------------------------------------------------------------------


class _Study(actions.Action):
    """A tagged test verb: it declares that something 'studyable' must be in
    scope, and its gate calls the shared place-precondition helper -- the
    pattern an opted-in verb follows so offered <=> the gate's place-check."""

    ACTION_NAME = "study"
    ACTION_DESCRIPTION = "Study something studyable"
    REQUIRED_AFFORDANCES = ("studyable",)

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="studier")

    def check_preconditions(self):
        return self.has_affordance_in_scope(self.character)

    def apply_effects(self):
        self.parser.ok("You study for a while.")


class _Brew(actions.Action):
    """A verb with a multi-entry declaration: ALL tags must sit on ONE thing."""

    ACTION_NAME = "brew"
    ACTION_DESCRIPTION = "Brew tea from a full kettle"
    REQUIRED_AFFORDANCES = ("is_kettle", "is_full")

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="brewer")

    def check_preconditions(self):
        return self.has_affordance_in_scope(self.character)

    def apply_effects(self):
        self.parser.ok("You brew a pot of tea.")


def _offered(game, actor):
    """The set of tool names tools_for offers *actor* right now."""
    return {t["name"] for t in tools_for(game.parser, actor=actor)}


# --- the declaration + helper ---


def test_base_action_declares_no_affordances():
    # The inherited default is the empty tuple: a universal verb.
    assert actions.Action.REQUIRED_AFFORDANCES == ()


def test_universal_verb_is_in_scope_anywhere():
    # An empty declaration passes the helper even in a bare room.
    game = _one_char_game()
    assert actions.Wait.affordance_in_scope(game.player, game) is True


def test_affordance_in_scope_sees_a_location_item():
    game = _one_char_game()
    assert _Study.affordance_in_scope(game.player, game) is False
    desk = things.Item("desk", "a study desk")
    desk.set_property("studyable", True)
    game.player.location.add_item(desk)
    assert _Study.affordance_in_scope(game.player, game) is True


def test_affordance_in_scope_sees_the_inventory():
    game = _one_char_game()
    book = things.Item("workbook", "a workbook")
    book.set_property("studyable", True)
    game.player.add_to_inventory(book)
    assert _Study.affordance_in_scope(game.player, game) is True


def test_affordance_in_scope_sees_the_location_itself():
    # Location is a Thing, so an arena tag uses the same property mechanism.
    game = _one_char_game()
    game.player.location.set_property("studyable", True)
    assert _Study.affordance_in_scope(game.player, game) is True


def test_affordance_in_scope_ignores_hidden_items():
    # A hidden item isn't actionable (it's out of parser scope), so it can't
    # afford a verb either.
    game = _one_char_game()
    desk = things.Item("desk", "a study desk")
    desk.set_property("studyable", True)
    desk.set_property("is_hidden", True)
    game.player.location.add_item(desk)
    assert _Study.affordance_in_scope(game.player, game) is False


def test_multi_entry_declaration_is_all_of_on_one_thing():
    game = _one_char_game()
    kettle = things.Item("kettle", "an empty kettle")
    kettle.set_property("is_kettle", True)
    pond = things.Item("pond", "a full pond")
    pond.set_property("is_full", True)
    game.player.location.add_item(kettle)
    game.player.location.add_item(pond)
    # The tags are split across two things: not enough.
    assert _Brew.affordance_in_scope(game.player, game) is False
    # Both tags on one thing: now the verb is afforded.
    kettle.set_property("is_full", True)
    assert _Brew.affordance_in_scope(game.player, game) is True


# --- the toolset filter (npc.tools_for) ---


def test_tools_for_always_offers_universal_verbs():
    game = _one_char_game()
    offered = _offered(game, game.player)
    assert "go" in offered and "wait" in offered


def test_tools_for_offers_tagged_verb_only_when_afforded():
    game = _one_char_game()
    game.parser.add_action(_Study)
    assert "study" not in _offered(game, game.player)

    desk = things.Item("desk", "a study desk")
    desk.set_property("studyable", True)
    game.player.location.add_item(desk)
    assert "study" in _offered(game, game.player)

    # The desk leaves scope -> the verb disappears again.
    game.player.location.remove_item(desk)
    assert "study" not in _offered(game, game.player)


def test_tools_for_offers_tagged_verb_in_a_tagged_location():
    game = _one_char_game()
    game.parser.add_action(_Study)
    game.player.location.set_property("studyable", True)
    assert "study" in _offered(game, game.player)


def test_tools_for_without_actor_does_not_curate():
    # No actor -> no scope to read, so the filter stays out of the way
    # (mirrors how scope enums degrade without an actor).
    game = _one_char_game()
    game.parser.add_action(_Study)
    names = {t["name"] for t in tools_for(game.parser)}
    assert "study" in names


# --- the gate half of the invariant ---


def test_gate_helper_fails_with_a_fresh_reason():
    # The place-precondition helper reports WHY through parser.fail, so the
    # ReAct retry loop never reads a stale reason from an earlier failure.
    game = _one_char_game()
    game.parser.add_action(_Study)
    game.parser.parse_command("go north")  # fails: no such exit
    earlier = game.parser.last_fail_message

    assert not game.parser.parse_command("study")
    assert game.parser.last_fail_message != earlier
    assert game.parser.last_fail_message == "There is nothing to study here."


def test_offered_matches_the_gates_place_check():
    # The invariant, asserted directly: the verb is offered exactly when its
    # gate's place-check passes -- both read the same declaration.
    game = _one_char_game()
    game.parser.add_action(_Study)

    assert "study" not in _offered(game, game.player)
    assert not game.parser.parse_command("study")

    game.player.location.set_property("studyable", True)
    assert "study" in _offered(game, game.player)
    assert game.parser.parse_command("study")


# --- the engine declarations: Eat and Read ---


def test_eat_declares_edible_and_is_curated():
    assert actions.Eat.REQUIRED_AFFORDANCES == (Property.EDIBLE,)
    game = _one_char_game()
    assert "eat" not in _offered(game, game.player)

    apple = things.Item("apple", "a crisp apple")
    apple.set_property(Property.EDIBLE, True)
    game.player.location.add_item(apple)
    assert "eat" in _offered(game, game.player)


def test_eat_gate_reports_no_food_in_scope():
    game = _one_char_game()
    assert not game.parser.parse_command("eat")
    assert game.parser.last_fail_message == "There is nothing to eat here."


def test_eat_offered_but_gate_still_checks_possession():
    # Offered => the PLACE check passes; the gate still owns the rest. An
    # edible apple lying here offers `eat`, but eating it needs it in hand.
    game = _one_char_game()
    apple = things.Item("apple", "a crisp apple")
    apple.set_property(Property.EDIBLE, True)
    game.player.location.add_item(apple)

    assert "eat" in _offered(game, game.player)
    assert actions.Eat.affordance_in_scope(game.player, game) is True
    assert not game.parser.parse_command("eat apple")  # not carried yet

    assert game.parser.parse_command("get apple")
    assert game.parser.parse_command("eat apple")


def test_read_declares_readable_and_is_curated():
    assert actions.Read.REQUIRED_AFFORDANCES == (Property.READABLE,)
    game = _one_char_game()
    assert "read" not in _offered(game, game.player)

    sign = things.Item("sign", "a wooden sign")
    sign.set_property(Property.READABLE, True)
    sign.set_property(Property.READ_TEXT, "Beware of the troll.")
    game.player.location.add_item(sign)
    assert "read" in _offered(game, game.player)


def test_read_gate_keeps_its_or_and_invariant_is_one_directional():
    # Read's gate passes on READ_TEXT *or* READABLE (kept as-is, per review):
    # an item carrying only read_text still READs fine -- it just isn't
    # offered. So for Read the invariant is one-directional:
    # offered => the gate's place-check passes (never the converse).
    game = _one_char_game()
    note = things.Item("note", "a scribbled note")
    note.set_property(Property.READ_TEXT, "Meet me at dawn.")
    game.player.location.add_item(note)

    assert "read" not in _offered(game, game.player)  # not tagged READABLE
    assert game.parser.parse_command("read note")  # but the gate allows it
