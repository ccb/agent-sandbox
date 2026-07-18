"""The Van Pelt library book loop (#616): check_out_book -> read.

Penn's first object-tier verb loop: books on a shelf in the Book Stacks, a
Penn-local check_out_book (shelf -> inventory, ownership stamped), and the
engine's Read unlocked by the checkout -- the book's content entering memory
is the payoff.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_book_loop_616.py -v
"""

from backend.actions import CheckOutBook
from backend.build_world import _normalize_personas, build_world
from backend.cognition import attach_agents
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
    extra_actions=(CheckOutBook,),
    offer=("check_out_book",),
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
