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
from backend.cognition import action_tools_for, attach_agents
from backend.penn.penn_world import (
    PENN_ACTION_VERBS,
    PENN_EXTRA_ACTIONS,
    build_penn_world,
)
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
