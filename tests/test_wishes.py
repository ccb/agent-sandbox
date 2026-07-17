"""Tests for the action-wish demand channel (#620): the ActionWish record,
the Game.log_wish sink, the AGENT_WISH trace channel, and the propose verb."""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel
from text_adventure_games.wishes import (
    ActionWish,
    TRIGGER_PARSE_GAP,
    TRIGGER_PROPOSED,
)

# ----------------------------------------------------------------------
# Section A: the ActionWish record
# ----------------------------------------------------------------------


def test_action_wish_to_primitive_round_trips_all_fields():
    wish = ActionWish(
        actor="Sofia",
        turn=13,
        location="Houston Kitchen",
        desired="fill the pot from the sink",
        reason="boiling needs water in the pot",
        trigger=TRIGGER_PROPOSED,
        goals=["make the water safe to drink"],
        scope=["pot", "stove", "sink", "Diego"],
        raw_command="propose fill the pot from the sink because boiling needs water in the pot",
    )
    assert wish.to_primitive() == {
        "actor": "Sofia",
        "turn": 13,
        "location": "Houston Kitchen",
        "desired": "fill the pot from the sink",
        "reason": "boiling needs water in the pot",
        "trigger": "proposed",
        "goals": ["make the water safe to drink"],
        "scope": ["pot", "stove", "sink", "Diego"],
        "raw_command": "propose fill the pot from the sink because boiling needs water in the pot",
        "meta": {},
    }


def test_action_wish_defaults_are_empty_not_shared():
    a = ActionWish(actor=None, turn=0, location=None, desired="x")
    b = ActionWish(actor=None, turn=0, location=None, desired="y")
    a.goals.append("mutated")
    a.meta["k"] = "v"
    assert b.goals == [] and b.scope == [] and b.meta == {}
    assert a.reason == "" and a.trigger == TRIGGER_PROPOSED


def test_trigger_constants():
    # #621 (parse-gap capture) will use the reserved constant; pin both values
    # because wishes.jsonl consumers key on them (#622/#623).
    assert TRIGGER_PROPOSED == "proposed"
    assert TRIGGER_PARSE_GAP == "parse_gap"


# ----------------------------------------------------------------------
# Section B: the AGENT_WISH trace channel
# ----------------------------------------------------------------------


def tiny_game():
    """A small, isolated 2-room world (Field --north--> Forest) with a player
    and a troll, mirroring tests/test_agent_layer.py so this module stands
    alone."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def test_parser_agent_wish_emits_on_wish_channel_with_meta():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.agent_wish(
        "troll", "a ladder — because the wall is too high", wish={"desired": "a ladder"}
    )
    msgs = cap.by_channel(Channel.AGENT_WISH)
    assert len(msgs) == 1
    assert msgs[0].actor == "troll"
    assert msgs[0].meta == {"wish": {"desired": "a ladder"}}


def test_agent_wish_channel_is_agent_trace_and_normally_visible():
    from text_adventure_games.reporting import AGENT_CHANNELS, NORMAL, channel_visible

    # Grouped/attributed like the other ReAct trace channels, and visible at
    # NORMAL (a wish is at least as newsworthy as a reasoning line).
    assert Channel.AGENT_WISH in AGENT_CHANNELS
    assert channel_visible(Channel.AGENT_WISH, NORMAL)


def test_plain_renderer_formats_wish_line():
    from text_adventure_games.reporting import Message, PlainRenderer

    line = PlainRenderer()._format(
        Message(Channel.AGENT_WISH, "a ladder", actor="troll")
    )
    assert line == "troll [wish] a ladder"


def test_web_renderer_maps_wish_to_npc_wish_type():
    from text_adventure_games.webapp.web_parser import WebRenderer
    from text_adventure_games.reporting import Message

    web = WebRenderer()
    web.emit(Message(Channel.AGENT_WISH, "a ladder", actor="troll"))
    assert web.drain() == [{"type": "npc_wish", "text": "troll [wish] a ladder"}]
