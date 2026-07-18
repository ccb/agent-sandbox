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


# ----------------------------------------------------------------------
# Section C: the Game sink
# ----------------------------------------------------------------------


def _wish(**overrides):
    base = dict(
        actor="troll",
        turn=1,
        location="Field",
        desired="a ladder",
        reason="the wall is too high",
    )
    base.update(overrides)
    return ActionWish(**base)


def test_log_wish_appends_and_fires_streaming_callback():
    game = tiny_game()
    assert game.wishes == []  # empty by default; games that never wish are unchanged
    seen = []
    game.on_wish = seen.append  # the UsageLedger._on_record pattern (#622's tap)
    wish = _wish()
    game.log_wish(wish)
    assert game.wishes == [wish]
    assert seen == [wish]


def test_log_wish_without_callback_is_fine_and_emits_trace():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.log_wish(_wish())
    assert len(game.wishes) == 1
    [msg] = cap.by_channel(Channel.AGENT_WISH)
    assert msg.actor == "troll"
    assert msg.text == "a ladder — because the wall is too high"
    assert msg.meta["wish"]["trigger"] == "proposed"


def test_log_wish_trace_omits_empty_reason():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.log_wish(_wish(reason=""))
    [msg] = cap.by_channel(Channel.AGENT_WISH)
    assert msg.text == "a ladder"


# ----------------------------------------------------------------------
# Section D: the propose verb
# ----------------------------------------------------------------------


def test_propose_records_a_fully_populated_wish():
    game = tiny_game()
    troll = game.characters["troll"]
    troll.add_goal("cross the wall", things.characters.GoalType.SHORT)
    ok = game.parser.parse_command(
        "propose build a ladder because the wall is too high", actor=troll
    )
    assert ok is True
    [wish] = game.wishes
    assert wish.actor == "troll"
    assert wish.trigger == TRIGGER_PROPOSED
    assert wish.desired == "build a ladder"
    assert wish.reason == "the wall is too high"
    assert wish.location == "Field"
    assert wish.turn == game.turn
    assert "cross the wall" in wish.goals
    assert "player" in wish.scope  # co-located characters are in the snapshot
    assert wish.raw_command == "propose build a ladder because the wall is too high"


def test_propose_without_because_records_empty_reason():
    game = tiny_game()
    troll = game.characters["troll"]
    assert game.parser.parse_command("propose build a ladder", actor=troll)
    [wish] = game.wishes
    assert wish.desired == "build a ladder"
    assert wish.reason == ""


def test_bare_propose_fails_and_teaches_the_format():
    game = tiny_game()
    troll = game.characters["troll"]
    assert not game.parser.parse_command("propose", actor=troll)
    assert game.wishes == []
    assert (
        "propose <the action you need> because <why>" in game.parser.last_fail_message
    )


def test_propose_payload_with_direction_words_is_not_hijacked_to_go():
    # Regression guard for the determine_intent ordering: the direction check
    # (parsing.py, "elif self.get_direction(command, ...)") runs BEFORE the
    # command-initial-verb match, so without the early propose branch this
    # command would route to GO and move the troll north.
    game = tiny_game()
    troll = game.characters["troll"]
    assert game.parser.parse_command(
        "propose climb up and go north over the wall because i am stuck", actor=troll
    )
    assert troll.location.name == "Field"  # did NOT move
    [wish] = game.wishes
    assert wish.desired == "climb up and go north over the wall"


def test_propose_succeeds_for_the_player_too():
    game = tiny_game()
    assert game.parser.parse_command("propose whistle for a dog because i am lonely")
    [wish] = game.wishes
    assert wish.actor == "player"


def test_propose_lands_in_the_game_event_log():
    # parse_command logs every gate-passing action as a GameEvent — a wish is
    # an ordinary action, so recorded runs see it with zero extra plumbing.
    game = tiny_game()
    troll = game.characters["troll"]
    game.parser.parse_command("propose build a ladder because reasons", actor=troll)
    event = game.events[-1]
    assert event.action == "propose"
    assert event.actor == "troll"


def test_propose_spends_the_turn_like_any_action():
    # No FREE_ACTION flag: articulating the gap costs the turn — the wish is
    # itself measurable behavior (spec decision 2).
    from text_adventure_games.actions.wish import Propose

    assert not getattr(Propose, "FREE_ACTION", False)
    assert Propose.DURATION is None


def test_propose_appears_in_help():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.parse_command("help")
    listing = "\n".join(cap.texts(Channel.NARRATION))
    assert "propose" in listing
    assert "Record a request for an action the game doesn't offer" in listing


# ----------------------------------------------------------------------
# Section E: the tool-calling path (#356 machinery, no changes needed)
# ----------------------------------------------------------------------


def test_tools_for_offers_propose_with_desired_and_reason_slots():
    from text_adventure_games.npc import tools_for

    game = tiny_game()
    troll = game.characters["troll"]
    tools = {t["name"]: t for t in tools_for(game.parser, actor=troll)}
    assert "propose" in tools
    props = tools["propose"]["parameters"]["properties"]
    assert set(props) == {"reasoning", "desired", "reason"}
    assert tools["propose"]["parameters"]["required"] == ["desired"]


def test_tool_call_reassembles_the_because_grammar():
    from text_adventure_games.npc import command_from_tool_call

    game = tiny_game()
    command = command_from_tool_call(
        "propose",
        {"desired": "fill the pot from the sink", "reason": "boiling needs water"},
        game.parser,
    )
    assert command == "propose fill the pot from the sink because boiling needs water"


def test_choose_action_enum_includes_propose():
    from text_adventure_games.npc import build_choose_action_tool

    game = tiny_game()
    tool = build_choose_action_tool(list(game.parser.actions))
    assert "propose" in tool["parameters"]["properties"]["action"]["enum"]
