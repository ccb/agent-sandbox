"""Regression tests for the Action Castle III skeleton (Phase 2).

Locks in the world topology, the start inventory, the two darkness gates, and the
GO-NORTH-home ending. Companions, puzzles and the endgame land in later phases;
these tests guard the scaffold they'll build on.
"""

from text_adventure_games import things
from text_adventure_games.adventures import action_castle_3 as ac3
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    game = ac3.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _play(cmds):
    game, cap = _game()
    for c in cmds:
        game.do_command(c)
        if game.is_game_over():
            break
    return game, cap


def _said(cap, substring):
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


EXPECTED_ROOMS = {
    "Crossroads",
    "Dark Forest",
    "Bandit Camp",
    "Cavern Entrance",
    "Dark Cavern",
    "Fissure",
    "Mushroom Garden",
    "Spider Lair",
    "Deep Ravine",
    "Goblin Caves",
    "Throne Room",
    "Castle Ruins",
    "Wizard's Tower",
    "Dungeon",
    "Vault",
    "Dark Corridor",
    "Torture Chamber",
    "Sanctum",
    "Chaos Chapel",
    "Crypt",
    "Home",
}


# --- topology --------------------------------------------------------------


def test_all_rooms_present():
    game, _ = _game()
    assert set(game.locations) == EXPECTED_ROOMS


def test_every_exit_resolves_to_a_real_location():
    game, _ = _game()
    for name, loc in game.locations.items():
        for direction, dest in loc.connections.items():
            assert dest.name in game.locations, f"{name} '{direction}' -> dangling"


def test_no_room_has_duplicate_destination_exits():
    game, _ = _game()
    for name, loc in game.locations.items():
        dests = [d.name for d in loc.connections.values()]
        assert len(dests) == len(set(dests)), f"{name} has a duplicate-destination exit"


def test_key_connections_match_the_rulebook():
    game, _ = _game()
    loc = game.locations

    def goes(room, direction, dest):
        return loc[room].connections.get(direction) is loc[dest]

    assert goes("Crossroads", "east", "Castle Ruins")
    assert goes("Crossroads", "west", "Dark Forest")
    assert goes("Crossroads", "north", "Home")
    assert goes("Dark Forest", "south", "Cavern Entrance")
    assert goes("Dark Forest", "west", "Bandit Camp")
    assert goes("Cavern Entrance", "enter cavern", "Dark Cavern")
    assert goes("Dark Cavern", "enter fissure", "Fissure")
    assert goes("Dark Cavern", "east", "Mushroom Garden")
    assert goes("Mushroom Garden", "south", "Spider Lair")
    assert goes("Spider Lair", "west", "Deep Ravine")
    assert goes("Deep Ravine", "down", "Goblin Caves")
    assert goes("Goblin Caves", "east", "Throne Room")
    assert goes("Castle Ruins", "up", "Wizard's Tower")
    assert goes("Castle Ruins", "down", "Dungeon")
    assert goes("Dungeon", "west", "Vault")
    assert goes("Dungeon", "east", "Dark Corridor")
    assert goes("Dark Corridor", "east", "Torture Chamber")
    assert goes("Torture Chamber", "down", "Sanctum")
    assert goes("Sanctum", "west", "Chaos Chapel")
    assert goes("Chaos Chapel", "south", "Crypt")


# --- start inventory -------------------------------------------------------


def test_player_starts_with_a_backpack_of_essentials():
    game, _ = _game()
    backpack = game.player.inventory["backpack"]
    assert backpack.get_property("is_container")
    assert set(backpack.contents) == {"lantern", "dagger", "lockpicks"}
    assert backpack.contents["lantern"].get_property("flammable")
    assert not backpack.contents["lantern"].get_property("is_lit")
    # The waterskin is its own carried container (so its water sits one level deep).
    waterskin = game.player.inventory["waterskin"]
    assert waterskin.get_property("is_container") and not waterskin.contents


def test_max_score_is_100():
    game, _ = _game()
    assert game.max_score == 100


# --- darkness gates --------------------------------------------------------


def test_cannot_enter_caverns_without_a_lit_lantern():
    game, cap = _play(["west", "south"])  # -> Cavern Entrance, lantern still unlit
    assert game.player.location.name == "Cavern Entrance"
    assert game.locations["Cavern Entrance"].get_property("is_dark")
    game.do_command("enter cavern")
    assert _said(cap, "too dark")
    assert game.player.location.name == "Cavern Entrance"  # didn't descend


def test_lit_lantern_opens_the_cavern():
    game, _ = _play(["take lantern", "light lantern", "west", "south", "enter cavern"])
    assert game.player.location.name == "Dark Cavern"


def test_cannot_descend_to_dungeon_without_a_lit_lantern():
    game, cap = _play(["east"])  # -> Castle Ruins, unlit
    assert game.player.location.name == "Castle Ruins"
    game.do_command("down")
    assert _said(cap, "too dark")
    assert game.player.location.name == "Castle Ruins"


def test_lit_lantern_opens_the_dungeon():
    game, _ = _play(["take lantern", "light lantern", "east", "down"])
    assert game.player.location.name == "Dungeon"


# --- companions are placed in their rooms ----------------------------------


def test_companions_start_in_the_expected_rooms():
    game, _ = _game()
    assert "elf" in game.locations["Dark Forest"].characters
    assert "wizard" in game.locations["Wizard's Tower"].characters
    assert "dwarf" in game.locations["Spider Lair"].characters
    assert "cleric" in game.locations["Torture Chamber"].characters  # the captive
    assert "goblin queen" in game.locations["Throne Room"].characters


# --- the GO-NORTH-home ending ----------------------------------------------


def test_going_home_asks_for_confirmation_then_ends_the_game():
    game, cap = _play(["go home"])
    assert _said(cap, "Are you sure")
    assert game.pending_prompt() is not None  # a yes/no prompt is posed
    assert not game.is_game_over()
    game.do_command("yes")  # bare answer to the prompt -> confirm home
    assert game.is_game_over()
    assert _said(cap, "THE END")


def test_declining_to_go_home_keeps_the_game_going():
    game, cap = _play(["go home", "no"])
    assert not game.is_game_over()
    assert _said(cap, "isn't over yet")
    assert game.player.location.name == "Crossroads"


def test_skeleton_walkthrough_runs_and_ends():
    game, _ = _play(ac3.WALKTHROUGH_SKELETON)
    assert game.is_game_over()
    assert "home" in game._scored_keys


# --- Phase 3: recruiting the party -----------------------------------------

# Reach the captured cleric (Torture Chamber), filling the waterskin on the way.
RECRUIT_CLERIC = [
    "take lantern",
    "light lantern",
    "west",  # Crossroads -> Dark Forest
    "south",  # -> Cavern Entrance
    "fill waterskin",
    "north",  # -> Dark Forest
    "east",  # -> Crossroads
    "east",  # -> Castle Ruins
    "down",  # -> Dungeon (lantern lit)
    "east",  # -> Dark Corridor
    "east",  # -> Torture Chamber
]


def test_invite_elf_recruits_her_and_she_follows():
    game, cap = _play(["west", "invite elf"])  # -> Dark Forest
    elf = game.characters["elf"]
    assert elf.following is game.player
    assert _said(cap, "Together, nothing can stop us")
    # the party cascades when the player moves
    game.do_command("east")  # -> Crossroads
    assert game.player.location.name == "Crossroads"
    assert "elf" in game.player.location.characters


def test_invite_wizard_recruits_him():
    game, cap = _play(["take lantern", "light lantern", "east", "up", "invite wizard"])
    assert game.characters["wizard"].following is game.player
    assert _said(cap, "May the stars guide us")


def test_cannot_invite_the_cleric_before_rescuing_him():
    game, cap = _play(RECRUIT_CLERIC + ["invite cleric"])
    assert game.player.location.name == "Torture Chamber"
    assert _said(cap, "too weak to follow")
    assert game.characters["cleric"].following is not game.player


def test_rescuing_the_cleric_recruits_him_and_scores():
    game, cap = _play(RECRUIT_CLERIC + ["give water", "free man", "invite cleric"])
    cleric = game.characters["cleric"]
    assert _said(cap, "wounds knit shut")  # he heals once watered AND freed
    assert cleric.following is game.player
    assert "cleric" in game._scored_keys and game.score >= 10
    # he travels with the party
    game.do_command("west")  # -> Dark Corridor
    assert "cleric" in game.player.location.characters


def test_freeing_the_dwarf_with_the_spider_present_is_fatal():
    game, cap = _play(
        [
            "take lantern",
            "light lantern",
            "west",
            "south",
            "enter cavern",
            "east",
            "south",
        ]
    )  # -> Spider Lair, spider still here
    assert game.player.location.name == "Spider Lair"
    game.do_command("free dwarf")
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "wrapped in a cocoon")


def test_full_dwarf_recruit_chain_needs_the_cleric_and_a_driven_off_spider():
    # Recruit the cleric, then march the party to the Spider Lair.
    game, cap = _play(
        RECRUIT_CLERIC
        + ["give water", "free man", "invite cleric"]
        + [
            "west",
            "west",
            "up",
            "west",
            "west",
            "south",
            "enter cavern",
            "east",
            "south",
        ]
    )
    assert game.player.location.name == "Spider Lair"
    assert "cleric" in game.player.location.characters  # the cleric followed

    # Stand in for SHOOT SPIDER (next PR): drive the spider off so freeing is safe.
    game.characters["spider"].set_property("driven_off", True)
    game.do_command("free dwarf")
    assert game.characters["dwarf"].get_property("freed")
    assert game.characters["dwarf"].get_property("poisoned")  # still poisoned

    game.do_command("invite dwarf")  # refused: still poisoned
    assert game.characters["dwarf"].following is not game.player

    game.do_command("heal dwarf")  # the cleric cures the poison
    assert not game.characters["dwarf"].get_property("poisoned")
    game.do_command("invite dwarf")
    assert game.characters["dwarf"].following is game.player
    assert "dwarf" in game._scored_keys


# --- Phase 4a: the bow chain (search -> crypt -> spell book -> sleep -> bow) -


def _solo_to(game, room):
    """Teleport just the player to a room (test-only shortcut past navigation)."""
    game.relocate(game.player, game.locations[room])


def _join(game, name):
    """Put a companion in the party at the player's side (test-only)."""
    ch = game.characters[name]
    ch.following = game.player
    game.relocate(ch, game.player.location)
    return ch


def test_search_dungeon_finds_the_pendant():
    game, cap = _play(["take lantern", "light lantern", "east", "down", "search"])
    assert game.player.location.name == "Dungeon"
    assert _said(cap, "find a shiny pendant")
    game.do_command("take pendant")
    assert "pendant" in game.player.inventory


def test_taking_the_spell_book_without_the_cleric_is_fatal():
    game, cap = _play(
        [
            "take lantern",
            "light lantern",
            "east",
            "down",
            "east",
            "east",
            "down",
            "west",
            "south",
        ]
    )  # -> Crypt, alone
    assert game.player.location.name == "Crypt"
    game.do_command("take book")
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "unholy ranks")


def test_cleric_with_pendant_turns_undead_and_you_take_the_book():
    game, _ = _game()
    _solo_to(game, "Crypt")
    cleric = _join(game, "cleric")
    cleric.set_property("has_pendant", True)
    game.do_command("turn undead")
    assert game.player.location.get_property("skeletons_cleared")
    game.do_command("take book")
    assert "spell book" in game.player.inventory
    assert not game.is_game_over()


def test_take_book_auto_turns_when_the_cleric_is_ready():
    game, _ = _game()
    _solo_to(game, "Crypt")
    _join(game, "cleric").set_property("has_pendant", True)
    game.do_command("take book")  # no explicit turn undead first
    assert "spell book" in game.player.inventory
    assert not game.is_game_over()


def test_returning_the_spell_book_to_the_wizard_scores():
    game, cap = _game()
    wizard = _join(game, "wizard")
    game.player.add_to_inventory(things.Item("spell book", "an arcane spell book"))
    game.do_command("give spell book to wizard")
    assert wizard.get_property("has_spellbook")
    assert "spell book" in wizard.inventory
    assert "spellbook" in game._scored_keys and game.score >= 5


def test_cast_sleep_needs_the_wizard_and_book_then_frees_the_bow():
    game, cap = _game()
    _solo_to(game, "Bandit Camp")
    wizard = _join(game, "wizard")
    # Without the spell book, the wizard can't cast.
    game.do_command("cast sleep")
    assert _said(cap, "wizard and his spell book")
    assert not game.characters["bandits"].get_property("asleep")
    # With it, the bandits drop and the bow becomes takeable.
    wizard.set_property("has_spellbook", True)
    game.do_command("cast sleep")
    assert game.characters["bandits"].get_property("asleep")
    game.do_command("take bow")
    assert "bow" in game.player.inventory


def test_returning_the_bow_to_the_elf_scores():
    game, _ = _game()
    elf = _join(game, "elf")
    game.player.add_to_inventory(things.Item("bow", "a fine elvish bow"))
    game.do_command("give bow to elf")
    assert elf.get_property("has_bow")
    assert "bow" in elf.inventory
    assert "bow" in game._scored_keys and game.score >= 5


def test_crypt_questline_integration():
    # Recruit the cleric, grab the pendant in the dungeon en route, and clear the
    # crypt for the spell book -- the whole cleric+pendant arc, end to end.
    cmds = [
        "take lantern",
        "light lantern",
        "west",
        "south",  # Cavern Entrance
        "fill waterskin",
        "north",
        "east",
        "east",  # Castle Ruins
        "down",  # Dungeon
        "search",
        "take pendant",
        "east",
        "east",  # Torture Chamber
        "give water",
        "free man",
        "invite cleric",
        "give pendant to cleric",
        "down",
        "west",
        "south",  # -> Crypt (cleric in tow)
        "turn undead",
        "take book",
    ]
    game, _ = _play(cmds)
    assert game.player.location.name == "Crypt"
    assert not game.is_game_over()
    assert "spell book" in game.player.inventory
    assert game.characters["cleric"].get_property("has_pendant")


# --- Phase 4b: spider + web (opening the western path) ---------------------


def test_web_blocks_the_way_west_until_cleared():
    game, cap = _game()
    _solo_to(game, "Spider Lair")
    game.do_command("west")
    assert _said(cap, "web blocks")
    assert game.player.location.name == "Spider Lair"


def test_armed_elf_shoots_the_spider_and_scores():
    game, cap = _game()
    _solo_to(game, "Spider Lair")
    _join(game, "elf").set_property("has_bow", True)
    game.do_command("shoot spider")
    spider = game.characters["spider"]
    assert spider.get_property("driven_off")
    assert "spider" not in game.player.location.characters  # it fled
    assert "spider" in game._scored_keys and game.score >= 10


def test_shooting_needs_the_elf_and_her_bow():
    game, cap = _game()
    _solo_to(game, "Spider Lair")
    _join(game, "elf")  # no bow
    game.do_command("shoot spider")
    assert _said(cap, "elf and her bow")
    assert not game.characters["spider"].get_property("driven_off")


def test_clearing_the_web_with_the_spider_present_is_fatal():
    game, cap = _game()
    _solo_to(game, "Spider Lair")
    _join(game, "dwarf")  # spider still here
    game.do_command("use hatchet")
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "wrapped in a cocoon")


def test_shoot_then_hatchet_opens_the_ravine():
    game, _ = _game()
    _solo_to(game, "Spider Lair")
    _join(game, "elf").set_property("has_bow", True)
    _join(game, "dwarf")
    game.do_command("shoot spider")
    game.do_command("use hatchet")
    assert game.player.location.get_property("web_cleared")
    game.do_command("west")
    assert game.player.location.name == "Deep Ravine"


# --- Phase 4 (stew): crafting applied --------------------------------------


def test_fill_waterskin_puts_water_in_it():
    game, cap = _play(["west", "south", "fill waterskin"])  # -> Cavern Entrance
    assert game.player.location.name == "Cavern Entrance"
    waterskin = game.player.inventory["waterskin"]
    assert "water" in waterskin.contents


def test_take_mushroom_yields_a_cave_mushroom():
    game, _ = _play(
        [
            "take lantern",
            "light lantern",
            "west",
            "south",
            "enter cavern",
            "east",
            "take mushroom",
        ]
    )
    assert game.player.location.name == "Mushroom Garden"
    assert "cave mushroom" in game.player.inventory


def test_cooking_stew_needs_the_pot():
    # Hold the ingredients but stand somewhere without the pot.
    game, cap = _game()
    game.player.inventory["waterskin"].add_item(things.Item("water", "spring water"))
    game.player.add_to_inventory(things.Item("cave mushroom", "a cave mushroom"))
    game.do_command("make stew")  # at the Crossroads -- no pot
    assert _said(cap, "You need pot")
    assert "stew" not in game.player.inventory


def test_make_mushroom_stew_at_the_pot():
    # Gather water + a mushroom, carry them to the bandit-camp pot, and cook.
    cmds = [
        "take lantern",
        "light lantern",
        "west",  # Dark Forest
        "south",  # Cavern Entrance
        "fill waterskin",
        "enter cavern",  # Dark Cavern
        "east",  # Mushroom Garden
        "take mushroom",
        "west",  # Dark Cavern
        "up",  # Cavern Entrance
        "north",  # Dark Forest
        "west",  # Bandit Camp (the pot)
        "make stew",
    ]
    game, cap = _play(cmds)
    assert game.player.location.name == "Bandit Camp"
    assert "stew" in game.player.inventory
    assert "cave mushroom" not in game.player.inventory  # consumed
    assert "water" not in game.player.inventory["waterskin"].contents  # consumed


def test_giving_water_still_works_with_water_as_an_item():
    # The cleric rescue consumes the `water` item from the waterskin.
    game, _ = _play(RECRUIT_CLERIC + ["give water", "free man", "invite cleric"])
    assert game.characters["cleric"].following is game.player
    assert "water" not in game.player.inventory["waterskin"].contents
