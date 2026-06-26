"""The JSONRenderer change feed (issue #90).

The *delta* complement of the world-state snapshot (world_state.py): each engine
``Message`` becomes one JSON-able record that a 2D renderer (e.g. Godot)
subscribes to. Snapshot = "the world is X"; this feed = "X just happened".
"""

import json

from text_adventure_games import games, things
from text_adventure_games.reporting import NORMAL, Channel, JSONRenderer, Message


def test_records_each_message_as_a_jsonable_dict():
    r = JSONRenderer()
    r.emit(Message(Channel.NARRATION, "You open the door.", turn=1))
    r.emit(Message(Channel.AGENT_ACTION, "attack troll", actor="guard", turn=1))
    assert r.records[0] == {
        "channel": "narration",
        "text": "You open the door.",
        "actor": None,
        "turn": 1,
        "phase": None,
        "meta": {},
    }
    assert r.records[1]["channel"] == "agent_action"
    assert r.records[1]["actor"] == "guard"
    json.dumps(r.records)  # JSON-safe: must not raise


def test_drain_returns_and_clears():
    r = JSONRenderer()
    r.emit(Message(Channel.NARRATION, "x"))
    r.emit(Message(Channel.NARRATION, "y"))
    assert [d["text"] for d in r.drain()] == ["x", "y"]
    assert r.drain() == []  # cleared after draining


def test_sink_streams_records_live_without_buffering():
    out = []
    r = JSONRenderer(sink=out.append)
    r.emit(Message(Channel.NARRATION, "hi"))
    assert out[0]["text"] == "hi"
    assert r.records == []  # streamed to the sink, not buffered


def test_verbosity_filters_channels():
    r = JSONRenderer(level=NORMAL)  # NORMAL hides AGENT_OBSERVATION
    r.emit(Message(Channel.AGENT_OBSERVATION, "observed", turn=1))
    assert r.records == []
    r.emit(Message(Channel.NARRATION, "shown", turn=1))
    assert len(r.records) == 1


def test_meta_values_are_coerced_json_safe():
    # meta is a free-form dict; the feed must coerce non-JSON values (like the
    # snapshot half does) so json.dumps(records) can never raise.
    r = JSONRenderer()
    r.emit(
        Message(
            Channel.BLOCKED, "nope", meta={"reason": Channel.NARRATION, "x": object()}
        )
    )
    rec = r.records[0]
    assert rec["meta"]["reason"] == "narration"  # Enum -> .value
    assert isinstance(rec["meta"]["x"], str)  # arbitrary object -> str
    json.dumps(r.records)  # must not raise


def test_turn_header_is_recorded_as_an_event():
    r = JSONRenderer()
    r.turn_header(3, time="9:00 AM")
    assert r.records[0]["channel"] == "turn_header"
    assert r.records[0]["turn"] == 3


def test_captures_a_real_turn_end_to_end():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    game = games.Game(field, player, characters=[])
    feed = JSONRenderer()
    game.parser.set_renderer(feed)

    game.do_command("go north")

    assert any(rec["channel"] == "narration" for rec in feed.records)
    json.dumps(feed.records)  # the whole feed is JSON-safe
