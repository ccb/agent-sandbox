"""The Van Pelt library book loop (#616): check_out_book -> read.

Penn's first object-tier verb loop: books on a shelf in the Book Stacks, a
Penn-local check_out_book (shelf -> inventory, ownership stamped), and the
engine's Read unlocked by the checkout -- the book's content entering memory
is the payoff.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_book_loop_616.py -v
"""

from backend.actions import CheckOutBook, ReadPenn
from backend.build_world import _normalize_personas, build_world
from backend.cognition import (
    action_tools_for,
    attach_agents,
    memory_stream_for_persona,
    remember_outcome,
)
from backend.penn.penn_world import (
    PENN_ACTION_VERBS,
    PENN_EXTRA_ACTIONS,
    build_penn_world,
)
from backend.prompt_templates import render
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

# -- a tiny two-room world, no tile map -----------------------------------
LOCATIONS = [
    {
        "name": "Campus",
        "description": "The campus green.",
        "address": None,
        "hub": True,
    },
    {"name": "Stacks", "description": "The library book stacks.", "address": None},
]


def _persona(name="Testa"):
    return {
        "name": name,
        "home": "Campus",
        "persona": f"I am {name}, a test persona.",
        "emoji": "🙂",
        "start_tile": [0, 0],
        "schedule": [{"place": "Campus", "activity": "hanging out", "steps": 5}],
    }


def _tiny_world(
    names=("Testa",),
    extra_actions=(CheckOutBook, ReadPenn),
    offer=("check_out_book", "read"),
):
    """(game, chars) for a small world with the book verbs registered."""
    personas = _normalize_personas([_persona(n) for n in names])
    game, chars = build_world(
        None, personas, LOCATIONS, extra_actions=list(extra_actions)
    )
    attach_agents(chars, personas, extra_action_names=list(offer))
    return game, chars


def _book(name="field guide"):
    """A checkout-able library book, mirroring what penn_world will ship."""
    book = Item(name, f"a {name}", "A slim, well-thumbed volume.")
    book.set_property(Property.GETTABLE, False)
    book.set_property("library_book", True)
    book.set_property(Property.READABLE, True)
    book.set_property(
        Property.READ_TEXT, "Mushrooms with white gills are often poisonous."
    )
    return book


def _shelf():
    shelf = Item("book shelf", "a tall book shelf", "Rows of circulating books.")
    shelf.set_property(Property.GETTABLE, False)
    shelf.set_property("book_shelf", True)
    return shelf


def _move(game, char, place):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[place].add_character(char)


def _stocked_stacks(game):
    """Shelf + one book in the Stacks; returns the book."""
    stacks = game.locations["Stacks"]
    stacks.add_item(_shelf())
    book = _book()
    stacks.add_item(book)
    return book


# -- Task 1: the CheckOutBook gate + effects --------------------------------


def test_check_out_book_is_registered():
    game, _ = _tiny_world()
    assert game.parser.actions["check_out_book"] is CheckOutBook


def test_check_out_moves_book_to_inventory_and_stamps_borrower():
    game, chars = _tiny_world()
    char = chars["Testa"]
    book = _stocked_stacks(game)
    _move(game, char, "Stacks")

    assert game.parser.parse_command("check_out_book field guide", actor=char)
    assert char.is_in_inventory(book)
    assert book.get_property("checked_out_by") == "Testa"
    assert "field guide" not in game.locations["Stacks"].items


def test_second_borrower_is_rejected_with_the_holder_named():
    game, chars = _tiny_world(names=("Testa", "Rival"))
    _stocked_stacks(game)
    _move(game, chars["Testa"], "Stacks")
    _move(game, chars["Rival"], "Stacks")

    assert game.parser.parse_command("check_out_book field guide", actor=chars["Testa"])
    assert not game.parser.parse_command(
        "check_out_book field guide", actor=chars["Rival"]
    )
    assert (
        game.parser.last_fail_message
        == "The field guide is already checked out by Testa."
    )


def test_rechecking_out_your_own_book_is_refused():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")

    assert game.parser.parse_command("check_out_book field guide", actor=char)
    assert not game.parser.parse_command("check_out_book field guide", actor=char)
    assert game.parser.last_fail_message == "You already have field guide checked out."


def test_no_shelf_in_scope_is_gate_rejected():
    game, chars = _tiny_world()
    char = chars["Testa"]  # stays on Campus: no shelf in scope
    _stocked_stacks(game)

    assert not game.parser.parse_command("check_out_book field guide", actor=char)
    assert (
        game.parser.last_fail_message
        == "There is no library shelf to check a book out from here."
    )


def test_a_non_book_cannot_be_checked_out():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    mug = Item("mug", "a chipped mug", "A chipped coffee mug.")
    game.locations["Stacks"].add_item(mug)
    _move(game, char, "Stacks")

    assert not game.parser.parse_command("check_out_book mug", actor=char)
    assert game.parser.last_fail_message == "The mug isn't a library book."


def test_an_unknown_title_is_not_matched():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")

    assert not game.parser.parse_command("check_out_book necronomicon", actor=char)
    assert game.parser.last_fail_message == "I don't see that book on the shelf."


# -- Task 2: ReadPenn — typed slot + #581 pacing ----------------------------


def _tool_names(game, char):
    return {t["name"] for t in action_tools_for(game, char)}


def test_read_override_is_registered():
    game, _ = _tiny_world()
    assert game.parser.actions["read"] is ReadPenn


def test_read_tool_advertises_item_enum_and_pacing_slots():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")

    tools = {t["name"]: t for t in action_tools_for(game, char)}
    read = tools["read"]
    props = read["parameters"]["properties"]
    assert "field guide" in props["item"]["enum"]
    assert "item" in read["parameters"]["required"]
    # The #581 pacing opt-in: decide_with_action_tools detects these slots
    # verb-agnostically, so a live brain can linger over a book.
    assert "duration_minutes" in props
    assert "emoji" in props


def test_book_verbs_are_curated_by_scope():
    game, chars = _tiny_world()
    char = chars["Testa"]

    # Bare campus: no shelf, nothing READABLE -> neither verb is offered.
    assert "check_out_book" not in _tool_names(game, char)
    assert "read" not in _tool_names(game, char)

    # At the stocked stacks: the shelf affords checkout, READABLE affords read.
    _stocked_stacks(game)
    _move(game, char, "Stacks")
    assert "check_out_book" in _tool_names(game, char)
    assert "read" in _tool_names(game, char)


def test_read_follows_the_checked_out_book():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")
    assert game.parser.parse_command("check_out_book field guide", actor=char)

    # Back on campus, holding the book: read stays offered (it's in scope);
    # check_out_book does not (no shelf here).
    _move(game, char, "Campus")
    assert "read" in _tool_names(game, char)
    assert "check_out_book" not in _tool_names(game, char)
    assert game.parser.parse_command("read field guide", actor=char)


# -- Task 3: the Van Pelt furnishing ----------------------------------------


def test_van_pelt_stacks_are_furnished():
    pw = build_penn_world()
    game, _ = pw.build_world_fn(pw.world_map)
    stacks = game.locations["Van Pelt — Book Stacks"]

    assert stacks.items["book shelf"].get_property("book_shelf")
    assert not stacks.items["book shelf"].get_property(Property.GETTABLE)
    for title in ("campus history book", "star atlas"):
        book = stacks.items[title]
        assert book.get_property("library_book")
        assert book.get_property(Property.READABLE)
        assert book.get_property(Property.READ_TEXT)
        # Checkout is the only path into a pocket -- a plain get must refuse.
        assert not book.get_property(Property.GETTABLE)


def test_book_verbs_ride_the_penn_registries():
    assert CheckOutBook in PENN_EXTRA_ACTIONS
    assert ReadPenn in PENN_EXTRA_ACTIONS
    assert "check_out_book" in PENN_ACTION_VERBS
    assert "read" in PENN_ACTION_VERBS


# -- Task 4: memory both ends of the loop -----------------------------------


def test_render_pins_the_book_loop_memories():
    # Exact-pinned per the prompt_templates README escaping-guard convention.
    assert (
        render("reflection", verb="check_out_book", item="star atlas")
        == "I checked out star atlas from the library."
    )
    assert (
        render(
            "reflection",
            verb="read",
            item="star atlas",
            content="A chart of the winter sky.",
        )
        == 'I read star atlas. It said: "A chart of the winter sky."'
    )
    # A read of something with no read_text still gets a (plainer) memory.
    assert (
        render("reflection", verb="read", item="star atlas", content="")
        == "I read star atlas."
    )


def test_checkout_is_remembered():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")
    assert game.parser.parse_command("check_out_book field guide", actor=char)

    remember_outcome(char, "check_out_book field guide", 3)
    entries = memory_stream_for_persona(char.agent)
    assert entries[-1]["text"] == "I checked out field guide from the library."
    assert entries[-1]["importance"] == 3.0


def test_read_memory_carries_the_content():
    game, chars = _tiny_world()
    char = chars["Testa"]
    _stocked_stacks(game)
    _move(game, char, "Stacks")
    assert game.parser.parse_command("check_out_book field guide", actor=char)
    assert game.parser.parse_command("read field guide", actor=char)

    remember_outcome(char, "read field guide", 4)
    entries = memory_stream_for_persona(char.agent)
    assert entries[-1]["text"] == (
        "I read field guide. It said: "
        '"Mushrooms with white gills are often poisonous."'
    )
    assert entries[-1]["importance"] == 3.0


# -- Task 5: the full loop on the real campus (#616 acceptance) -------------


def test_full_book_loop_on_the_real_campus():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, extra_action_names=PENN_ACTION_VERBS)
    char = next(iter(chars.values()))

    # Away from the shelf: neither book verb is offered.
    _move(game, char, "College Hall")
    offered = {t["name"] for t in action_tools_for(game, char)}
    assert "check_out_book" not in offered
    assert "read" not in offered

    # At the stacks both are: the shelf affords checkout, READABLE affords read.
    _move(game, char, "Van Pelt — Book Stacks")
    offered = {t["name"] for t in action_tools_for(game, char)}
    assert "check_out_book" in offered
    assert "read" in offered

    # Checkout: shelf -> inventory, ownership stamped.
    assert game.parser.parse_command("check_out_book campus history book", actor=char)
    book = char.inventory["campus history book"]
    assert book.get_property("checked_out_by") == char.name
    assert "campus history book" not in game.locations["Van Pelt — Book Stacks"].items

    # The book follows the borrower: read stays offered away from the library.
    _move(game, char, "College Hall")
    assert "read" in {t["name"] for t in action_tools_for(game, char)}

    # Reading writes the content into memory -- the payoff of the loop.
    assert game.parser.parse_command("read campus history book", actor=char)
    remember_outcome(char, "read campus history book", 5)
    entries = memory_stream_for_persona(char.agent)
    assert entries[-1]["text"] == (
        'I read campus history book. It said: "College Hall opened in 1873; '
        "its green serpentine stone is so soft the university repairs it "
        'block by block."'
    )


# -- Final-review fix: the "book" hint must never out-rank the exact title --


def test_check_out_names_the_exact_book():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, extra_action_names=PENN_ACTION_VERBS)
    char = next(iter(chars.values()))
    _move(game, char, "Van Pelt — Book Stacks")

    assert game.parser.parse_command("check_out_book star atlas", actor=char)
    assert "star atlas" in char.inventory
    assert char.inventory["star atlas"].get_property("checked_out_by") == char.name
    assert "campus history book" in game.locations["Van Pelt — Book Stacks"].items


def test_contention_message_is_not_preempted_by_the_other_book():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, extra_action_names=PENN_ACTION_VERBS)
    char_a, char_b = list(chars.values())[:2]
    _move(game, char_a, "Van Pelt — Book Stacks")
    _move(game, char_b, "Van Pelt — Book Stacks")

    assert game.parser.parse_command("check_out_book star atlas", actor=char_a)
    assert not game.parser.parse_command("check_out_book star atlas", actor=char_b)
    assert (
        game.parser.last_fail_message
        == f"The star atlas is already checked out by {char_a.name}."
    )
    assert "campus history book" in game.locations["Van Pelt — Book Stacks"].items


def test_contention_beats_a_shorter_shelf_title():
    """#672 review: a still-shelved book whose name sits inside the requested
    title ("atlas" vs the borrowed "star atlas") must not win the match --
    the exact held title resolves, and the loser hears who has it."""
    game, chars = _tiny_world(names=("Testa", "Rival"))
    stacks = game.locations["Stacks"]
    stacks.add_item(_shelf())
    stacks.add_item(_book("atlas"))
    stacks.add_item(_book("star atlas"))
    _move(game, chars["Testa"], "Stacks")
    _move(game, chars["Rival"], "Stacks")

    assert game.parser.parse_command("check_out_book star atlas", actor=chars["Testa"])
    assert not game.parser.parse_command(
        "check_out_book star atlas", actor=chars["Rival"]
    )
    assert (
        game.parser.last_fail_message
        == "The star atlas is already checked out by Testa."
    )
    assert "atlas" in stacks.items  # the cousin never left the shelf


def test_contention_beats_a_nonbook_with_a_nested_name():
    """#672 review: a non-book in scope ("atlas", decorative) must not shadow
    the contention message for the borrowed "star atlas"."""
    game, chars = _tiny_world(names=("Testa", "Rival"))
    stacks = game.locations["Stacks"]
    stacks.add_item(_shelf())
    stacks.add_item(_book("star atlas"))
    stacks.add_item(Item("atlas", "a decorative atlas", "Not for circulation."))
    _move(game, chars["Testa"], "Stacks")
    _move(game, chars["Rival"], "Stacks")

    assert game.parser.parse_command("check_out_book star atlas", actor=chars["Testa"])
    assert not game.parser.parse_command(
        "check_out_book star atlas", actor=chars["Rival"]
    )
    assert (
        game.parser.last_fail_message
        == "The star atlas is already checked out by Testa."
    )
