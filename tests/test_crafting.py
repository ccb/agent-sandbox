"""The reusable crafting system (crafting.py + the Craft action).

Builds tiny games with recipes and exercises the core: combine ingredients into
a new item, by output name / by ingredients / bare-verb-at-a-station; required
tools (present, not consumed); tag matching with count>1; location gating; and
that a game without recipes is unaffected.
"""

import pytest

from text_adventure_games import games, things, Recipe, Ingredient
from text_adventure_games.enums import ActionName
from text_adventure_games.reporting import CaptureRenderer, Channel


def _bow(_game):
    return things.Item(
        "bow", "a crude bow", "A bow lashed together from a stick and string."
    )


def _game(recipes=(), room_items=(), inv=()):
    room = things.Location("Workshop", "A workshop.")
    player = things.Character("you", "the player", "I craft.")
    for it in room_items:
        room.add_item(it)
    game = games.Game(room, player, characters=[])
    for r in recipes:
        game.add_recipe(r)
    for it in inv:
        player.add_to_inventory(it)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, player, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def _bow_recipe(**kw):
    return Recipe(name="bow", inputs=["string", "stick"], output=_bow, **kw)


# --- core ------------------------------------------------------------------


def test_make_by_output_name_consumes_inputs_and_produces_output():
    game, player, cap = _game(
        recipes=[_bow_recipe()],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")
    assert "bow" in player.inventory
    assert "string" not in player.inventory and "stick" not in player.inventory
    assert _said(cap, "make bow") or _said(cap, "bow")


def test_missing_ingredient_reports_the_gap_and_changes_nothing():
    game, player, cap = _game(
        recipes=[_bow_recipe()], inv=[things.Item("stick", "a stick")]
    )
    game.do_command("make bow")
    assert _said(cap, "You need string")
    assert "bow" not in player.inventory
    assert "stick" in player.inventory  # nothing consumed


def test_craft_by_ingredients():
    game, player, cap = _game(
        recipes=[_bow_recipe()],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("combine string and stick")
    assert "bow" in player.inventory


def test_bare_verb_picks_the_satisfiable_recipe():
    game, player, cap = _game(
        recipes=[_bow_recipe()],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("craft")  # no target -> the one recipe we can make
    assert "bow" in player.inventory


def test_result_text_is_shown_when_given():
    game, player, cap = _game(
        recipes=[_bow_recipe(result_text="You lash the stick and string into a bow.")],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")
    assert _said(cap, "lash the stick and string")


# --- tools (station / instrument: present, not consumed) -------------------


def test_tool_must_be_present():
    game, player, cap = _game(
        recipes=[_bow_recipe(tools=["workbench"])],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")  # no workbench here
    assert _said(cap, "You need workbench")
    assert "bow" not in player.inventory


def test_tool_present_is_used_but_not_consumed():
    bench = things.Item("workbench", "a sturdy workbench")
    bench.set_property("gettable", False)
    game, player, cap = _game(
        recipes=[_bow_recipe(tools=["workbench"])],
        room_items=[bench],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")
    assert "bow" in player.inventory
    assert "workbench" in game.player.location.items  # the tool stays


# --- tag matching + count>1 ------------------------------------------------


def test_tag_ingredient_consumes_count_of_matching_items():
    table = Recipe(
        name="table",
        inputs=[Ingredient(tag="plank", count=2)],
        output=lambda g: things.Item("table", "a table"),
    )
    oak = things.Item("oak plank", "an oak plank")
    oak.set_property("plank", True)
    birch = things.Item("birch plank", "a birch plank")
    birch.set_property("plank", True)
    game, player, cap = _game(recipes=[table], inv=[oak, birch])
    game.do_command("make table")
    assert "table" in player.inventory
    assert "oak plank" not in player.inventory and "birch plank" not in player.inventory


def test_tag_count_not_met_reports_gap():
    table = Recipe(
        name="table",
        inputs=[Ingredient(tag="plank", count=2)],
        output=lambda g: things.Item("table", "a table"),
    )
    oak = things.Item("oak plank", "an oak plank")
    oak.set_property("plank", True)
    game, player, cap = _game(recipes=[table], inv=[oak])  # only one plank
    game.do_command("make table")
    assert "table" not in player.inventory
    assert _said(cap, "2 plank")


# --- location gating -------------------------------------------------------


def test_location_gated_recipe():
    r = _bow_recipe(location="Forge")
    game, player, cap = _game(
        recipes=[r],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")  # we're in the Workshop, not the Forge
    assert _said(cap, "can't make that here")
    assert "bow" not in player.inventory


# --- crafting is opt-in: no recipes -> verbs stay inert --------------------


def test_crafting_verbs_are_inert_without_recipes():
    game, player, cap = _game()  # no recipes
    assert game.parser.determine_intent("make bow") != ActionName.CRAFT
    game.do_command("make bow")
    assert _said(cap, "not sure")


def test_crafting_verb_routes_to_craft_when_recipes_exist():
    game, player, cap = _game(recipes=[_bow_recipe()])
    assert game.parser.determine_intent("cook") == ActionName.CRAFT
    assert game.parser.determine_intent("make bow") == ActionName.CRAFT


def test_boil_is_a_craft_verb_635():
    # #635: `boil` joins the craft verbs so a natural "boil <recipe>" phrasing
    # reaches CRAFT -- the Penn boil arc's corrective verb -- instead of routing
    # nowhere. Inert without recipes, exactly like every other craft verb.
    game, player, cap = _game()  # no recipes
    assert game.parser.determine_intent("boil bow") != ActionName.CRAFT
    game, player, cap = _game(
        recipes=[_bow_recipe()],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    assert game.parser.determine_intent("boil bow") == ActionName.CRAFT
    game.do_command("boil bow")
    assert "bow" in player.inventory


def test_recipe_is_repeatable_with_fresh_ingredients():
    game, player, cap = _game(
        recipes=[_bow_recipe()],
        inv=[things.Item("string", "a string"), things.Item("stick", "a stick")],
    )
    game.do_command("make bow")
    assert "bow" in player.inventory
    # restock and craft again -> a second, distinct bow factory call succeeds
    player.add_to_inventory(things.Item("string", "a string"))
    player.add_to_inventory(things.Item("stick", "a stick"))
    game.player.inventory.pop("bow")  # set the old one aside
    game.do_command("make bow")
    assert "bow" in player.inventory


# --- known / recipe-book gating (issue #135) -------------------------------


def _string_and_stick():
    return [things.Item("string", "a string"), things.Item("stick", "a stick")]


def test_default_recipes_stay_craftable_unchanged():
    # `known` defaults True, so every existing recipe/game is unaffected.
    game, player, cap = _game(recipes=[_bow_recipe()], inv=_string_and_stick())
    game.do_command("make bow")
    assert "bow" in player.inventory


def test_unknown_recipe_is_not_craftable_even_with_ingredients():
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.do_command("make bow")
    assert "bow" not in player.inventory  # gated despite having the ingredients
    # An UNLEARNED recipe (#628 split): "haven't learned yet", not "don't know
    # how" -- the latter is now reserved for a target that names no recipe at
    # all, and logs a craft_gap wish (which an unlearned recipe must not).
    assert _said(cap, "haven't learned")
    assert not _said(cap, "don't know how")
    assert game.wishes == []


def test_bare_verb_skips_unknown_recipes():
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.do_command("craft")  # bare verb: first satisfiable *known* recipe
    assert "bow" not in player.inventory
    assert _said(cap, "nothing you can make")


def test_learn_recipe_makes_it_craftable():
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.learn_recipe("bow")
    game.do_command("make bow")
    assert "bow" in player.inventory


def test_learn_recipe_is_case_insensitive_and_matches_aliases():
    recipe = Recipe(
        name="bow",
        aliases=["longbow"],
        inputs=["string", "stick"],
        output=_bow,
        known=False,
    )
    game, player, cap = _game(recipes=[recipe], inv=_string_and_stick())
    game.learn_recipe("LONGBOW")  # learned by alias, in a different case
    game.do_command("make bow")
    assert "bow" in player.inventory


def test_known_recipe_missing_ingredients_still_shows_the_gap():
    # The "don't know how" gate is only for UNKNOWN recipes; a known recipe you
    # simply lack ingredients for still gives the helpful gap message.
    game, player, cap = _game(recipes=[_bow_recipe()], inv=[])  # no ingredients
    game.do_command("make bow")
    assert "bow" not in player.inventory
    assert _said(cap, "You need")  # ingredient gap, not "don't know how"


def test_by_ingredients_resolution_is_also_gated():
    # The gate is a single chokepoint, so resolution path #2 (by ingredients) is
    # gated too -- not just by-name and bare-verb.
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.do_command("combine string and stick")
    assert "bow" not in player.inventory
    assert _said(cap, "haven't learned")  # unlearned, not truly unknown (#628)
    assert game.wishes == []


def test_learning_one_recipe_does_not_unlock_another():
    raft = Recipe(
        name="raft",
        inputs=["log"],
        output=lambda g: things.Item("raft", "a raft"),
        known=False,
    )
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False), raft], inv=_string_and_stick()
    )
    game.learn_recipe("raft")  # learn the OTHER recipe
    game.do_command("make bow")
    assert "bow" not in player.inventory  # the bow stays gated
    assert _said(cap, "haven't learned")  # unlearned, not truly unknown (#628)
    assert game.wishes == []


def test_gated_recipe_without_a_name_is_rejected():
    # A known=False recipe needs a name/alias to be learnable, so omitting one is
    # a construction error -- fail fast for the author rather than silently
    # producing a permanently un-craftable recipe.
    with pytest.raises(ValueError):
        Recipe(inputs=["string", "stick"], output=_bow, known=False)


# --- craft_gap wish capture (#628, Option B) --------------------------------
#
# A recipe-ful world's "make <target-with-no-matching-recipe>" used to die
# silently in check_preconditions -- no GameEvent, no wish. Split from the
# unlearned-recipe case above: a truly unknown target still gets the "don't
# know how" message, but now also logs a craft_gap wish (the demand-capture
# gap issue #628 closes). Routing itself is unchanged (Option A, rejected).


def test_truly_unknown_target_logs_a_craft_gap_wish():
    # A bow recipe is registered (so the game routes "make ..." to CRAFT at
    # all), but "boiled water" names no recipe whatsoever -- truly unknown,
    # not just unlearned. No ingredients in hand, so the bare-verb fallback
    # (resolution path #3) can't silently satisfy the bow recipe instead.
    game, player, cap = _game(recipes=[_bow_recipe()], inv=[])
    game.do_command("make boiled water")
    assert "bow" not in player.inventory
    assert _said(cap, "don't know how")
    [wish] = game.wishes
    assert wish.trigger == "craft_gap"
    assert wish.desired == "make boiled water"
    assert wish.raw_command == "make boiled water"
    assert wish.actor == player.name
    assert wish.turn == game.turn
    assert wish.location == player.location.name


def test_unknown_target_with_only_an_unlearned_recipe_registered_still_gaps():
    # Guards the detection helper: an UNLEARNED recipe must not be mistaken
    # for a match on an unrelated target -- "boiled water" still doesn't name
    # the (unlearned) bow recipe, so it's truly unknown, craft_gap fires.
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.do_command("make boiled water")
    assert _said(cap, "don't know how")
    [wish] = game.wishes
    assert wish.trigger == "craft_gap"


def test_unlearned_recipe_logs_no_wish():
    # Case 1 (the learnable-enabler case) is not missing demand -- it's a
    # #135 learning gate -- so it must never produce a wish.
    game, player, cap = _game(
        recipes=[_bow_recipe(known=False)], inv=_string_and_stick()
    )
    game.do_command("make bow")
    assert _said(cap, "haven't learned")
    assert game.wishes == []
