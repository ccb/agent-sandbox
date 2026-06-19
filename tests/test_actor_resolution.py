import pytest

from text_adventure_games import games, things
from text_adventure_games.actions import things as a_things
from text_adventure_games.actions import fight, consume, locations, rose, fish
from text_adventure_games.actions.base import Action


def _two_char_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    alice = things.Character("alice", "a guard", "I guard.")
    bob = things.Character("bob", "a thief", "I sneak.")
    game = games.Game(room, player, characters=[alice, bob])
    room.add_character(alice)
    room.add_character(bob)
    return game


def test_acting_character_returns_explicit_actor():
    game = _two_char_game()
    alice = game.characters["alice"]
    action = Action(game, actor=alice)
    assert action.acting_character("anything at all") is alice


def test_acting_character_falls_back_to_command_scan():
    game = _two_char_game()
    action = Action(game)  # actor=None
    assert action.acting_character("get key") is game.player
    assert action.acting_character("alice get key") is game.characters["alice"]


def test_get_character_exclude_skips_named_candidate():
    game = _two_char_game()
    alice = game.characters["alice"]
    bob = game.characters["bob"]
    assert game.parser.get_character("alice and bob") is alice
    assert game.parser.get_character("alice and bob", exclude=alice) is bob


@pytest.mark.parametrize(
    "action_cls,command",
    [
        (a_things.Get, "get key"),
        (a_things.Drop, "drop key"),
        (a_things.Inventory, "inventory"),
        (a_things.Examine, "examine key"),
        (a_things.Give, "give key to bob"),
        (a_things.Unlock_Door, "unlock door"),
        (fight.Attack, "attack bob"),
        (consume.Eat, "eat bread"),
        (consume.Drink, "drink water"),
        (consume.Light, "light lamp"),
        (locations.Go, "north"),
        (rose.Pick_Rose, "pick rose"),
        (rose.Smell_Rose, "smell rose"),
        (fish.Catch_Fish, "catch fish with pole"),
    ],
)
def test_action_accepts_and_stores_actor(action_cls, command):
    game = _two_char_game()
    alice = game.characters["alice"]
    action = action_cls(game, command, actor=alice)
    assert action.actor is alice


def _get_game_with_items():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    npc = things.Character("guard", "a guard", "I patrol.")
    key = things.Item("key", "a brass key")
    coin = things.Item("coin", "a gold coin")
    game = games.Game(room, player, characters=[npc])
    room.add_character(npc)
    room.add_item(key)
    room.add_item(coin)
    return game, npc, player


def test_explicit_actor_gets_item():
    game, npc, player = _get_game_with_items()
    game.parser.parse_command("get key", actor=npc)
    assert "key" in npc.inventory
    assert "key" not in player.inventory


def test_default_actor_is_player():
    game, npc, player = _get_game_with_items()
    game.parser.parse_command("get key")
    assert "key" in player.inventory


def test_legacy_name_prefix_still_resolves():
    game, npc, player = _get_game_with_items()
    game.parser.parse_command("guard get key")
    assert "key" in npc.inventory


def test_action_sequence_threads_actor():
    game, npc, player = _get_game_with_items()
    game.parser.parse_command("get key, get coin", actor=npc)
    assert "key" in npc.inventory
    assert "coin" in npc.inventory


def _give_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    guard = things.Character("guard", "a guard", "I guard.")
    thief = things.Character("thief", "a thief", "I sneak.")
    sword = things.Item("sword", "a sharp sword")
    game = games.Game(room, player, characters=[guard, thief])
    room.add_character(guard)
    room.add_character(thief)
    guard.add_to_inventory(sword)
    return game, guard, thief


def test_actor_gives_to_other_character():
    game, guard, thief = _give_game()
    game.parser.parse_command("give sword to thief", actor=guard)
    assert "sword" not in guard.inventory
    assert "sword" in thief.inventory


def test_recipient_excludes_actor_giver():
    # Actor (guard) is also named in the recipient slot; exclude must keep the
    # recipient from resolving back to the giver, so there is no self-give.
    game, guard, thief = _give_game()
    action = a_things.Give(game, "give sword to guard", actor=guard)
    assert action.giver is guard
    assert action.recipient is not guard


def _fight_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    troll = things.Character("troll", "a troll", "I smash.")
    skeleton = things.Character("skeleton", "a skeleton", "I rattle.")
    club = things.Item("club", "a heavy club")
    club.set_property("is_weapon", True)
    game = games.Game(room, player, characters=[troll, skeleton])
    room.add_character(troll)
    room.add_character(skeleton)
    troll.add_to_inventory(club)
    return game, troll, skeleton


def test_actor_attacks_other_character():
    game, troll, skeleton = _fight_game()
    game.parser.parse_command("attack skeleton with club", actor=troll)
    assert skeleton.get_property("is_unconscious") is True


def test_attacker_does_not_target_self_via_exclude():
    game, troll, skeleton = _fight_game()
    action = fight.Attack(game, "attack troll", actor=troll)
    assert action.attacker is troll
    assert action.victim is not troll


def test_named_recipient_resolves_to_that_character():
    # A named, co-located target still resolves by name (the actor seam from #8).
    game, guard, thief = _give_game()
    action = a_things.Give(game, "give sword to thief", actor=guard)
    assert action.recipient is thief


def test_unnamed_give_has_no_target():
    # #81: an agent that names no recipient must NOT silently hand the item to
    # the player. The target resolves to None and the command fails with a
    # reason the ReAct loop can reflect on, instead of misfiring at the player.
    game, guard, thief = _give_game()
    ok = game.parser.parse_command("give sword", actor=guard)
    assert ok is False
    assert game.parser.last_fail_message == "Give it to whom?"
    assert "sword" in guard.inventory
    assert "sword" not in thief.inventory
    assert "sword" not in game.player.inventory


def test_unnamed_attack_has_no_target():
    # #81: an unnamed attack used to default its victim to the (co-located)
    # player. It must now report a missing target rather than striking them.
    game, troll, skeleton = _fight_game()
    ok = game.parser.parse_command("attack with club", actor=troll)
    assert ok is False
    assert game.parser.last_fail_message == "The character to attack wasn't matched."
    assert not skeleton.get_property("is_unconscious")
    assert not game.player.get_property("is_unconscious")


def _sim_shaped_game():
    """Mirror the generative-agents sim: a silent 'observer' stands in as the
    engine-required player and sits in a hub, while the agents act in a room
    elsewhere. An agent's unnamed action must not reach back to the observer."""
    hub = things.Location("Hub", "A quiet hub.")
    room = things.Location("Room", "A plain room.")
    hub.add_connection("to room", room)
    observer = things.Character("observer", "a silent observer", "I watch.")
    isabella = things.Character("isabella", "a cafe owner", "I serve coffee.")
    maria = things.Character("maria", "a student", "I study.")
    bread = things.Item("bread", "a loaf of bread")
    game = games.Game(hub, observer, characters=[isabella, maria])
    room.add_character(isabella)
    room.add_character(maria)
    isabella.add_to_inventory(bread)
    return game, observer, isabella, maria


def test_unnamed_give_does_not_reach_uncolocated_player():
    game, observer, isabella, maria = _sim_shaped_game()
    ok = game.parser.parse_command("give bread", actor=isabella)
    assert ok is False
    assert game.parser.last_fail_message == "Give it to whom?"
    assert "bread" in isabella.inventory
    assert "bread" not in observer.inventory
    assert "bread" not in maria.inventory


def test_npc_can_target_player_by_name():
    # Action Castle relies on NPCs attacking the player by NAMING them, which
    # must keep resolving to the player even though unnamed targets now go None.
    game, troll, skeleton = _fight_game()
    action = fight.Attack(game, "attack player with club", actor=troll)
    assert action.victim is game.player
    ok = game.parser.parse_command("attack player with club", actor=troll)
    assert ok is True
    assert game.player.get_property("is_unconscious") is True


def test_actor_moves_through_exit():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A dark forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "the player", "I explore.")
    npc = things.Character("guard", "a guard", "I patrol.")
    game = games.Game(field, player, characters=[npc])
    field.add_character(npc)
    game.parser.parse_command("go north", actor=npc)
    assert npc.location is forest


def test_actor_eats_own_food():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    npc = things.Character("guard", "a guard", "I patrol.")
    bread = things.Item("bread", "a loaf of bread")
    bread.set_property("edible", True)
    game = games.Game(room, player, characters=[npc])
    room.add_character(npc)
    npc.add_to_inventory(bread)
    game.parser.parse_command("eat bread", actor=npc)
    assert "bread" not in npc.inventory
    assert npc.get_property("is_hungry") is False
