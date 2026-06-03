from text_adventure_games import games, things
from text_adventure_games.actions import fight


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


def test_attack_without_held_weapon_fails_gracefully():
    # The weapon is matched from the attacker's inventory at construction, then
    # removed before the precondition check. The "doesn't have the weapon" branch
    # must fail cleanly (return False) instead of raising KeyError from a bad
    # format placeholder.
    game, troll, skeleton = _fight_game()
    action = fight.Attack(game, "attack skeleton with club", actor=troll)
    troll.remove_from_inventory(action.weapon)
    assert action.check_preconditions() is False
