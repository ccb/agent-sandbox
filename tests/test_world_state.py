"""Typed world-state export snapshot (issue #90).

A deterministic, JSON-able snapshot of the whole world that a structured
exporter or a future Godot renderer can poll. Pure + read-only: building it
never mutates the game.
"""

import json

from text_adventure_games import games, things
from text_adventure_games.things.characters import Goal, GoalType
from text_adventure_games.world_state import SCHEMA_VERSION, WorldState, world_state


def _two_room_game():
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game, field, forest, player, troll


def test_basic_shape_and_schema():
    game, *_ = _two_room_game()
    ws = world_state(game)
    assert isinstance(ws, WorldState)
    assert ws.schema_version == SCHEMA_VERSION
    assert ws.player == "player"
    assert ws.turn == game.turn
    assert [loc.name for loc in ws.locations] == ["Field", "Forest"]  # sorted
    assert {c.name for c in ws.characters} == {"player", "troll"}


def test_exits_include_reciprocal_edges():
    game, *_ = _two_room_game()
    ws = world_state(game)
    field = next(l for l in ws.locations if l.name == "Field")
    forest = next(l for l in ws.locations if l.name == "Forest")
    assert [(e.direction, e.to, e.blocked) for e in field.exits] == [
        ("north", "Forest", False)
    ]
    # add_connection auto-wires the reverse edge; the export carries it.
    assert [(e.direction, e.to, e.blocked) for e in forest.exits] == [
        ("south", "Field", False)
    ]


def test_player_flag_persona_and_location():
    game, *_ = _two_room_game()
    by = {c.name: c for c in world_state(game).characters}
    assert by["player"].is_player is True
    assert by["troll"].is_player is False
    assert by["troll"].persona == "I am hungry."
    assert by["troll"].location == "Field"


def test_item_at_location_vs_held_is_exclusive():
    game, field, _, player, _ = _two_room_game()
    rock = things.Item("rock", "a rock", "A grey rock.")
    rock.set_property("gettable", True)
    field.add_item(rock)
    sword = things.Item("sword", "a sword", "A sharp sword.")
    player.add_to_inventory(sword)

    ws = world_state(game)
    field_state = next(l for l in ws.locations if l.name == "Field")
    player_state = next(c for c in ws.characters if c.name == "player")

    assert [i.name for i in field_state.items] == ["rock"]
    assert "gettable" in field_state.items[0].affordances
    assert field_state.items[0].location == "Field"
    assert [i.name for i in player_state.inventory] == ["sword"]
    assert player_state.inventory[0].owner == "player"
    # exactly one place: the held sword is not on the ground.
    assert "sword" not in [i.name for i in field_state.items]


def test_goals_and_properties_export():
    game, *_, troll = _two_room_game()
    troll.goals = [Goal("Eat the player", GoalType.SHORT)]
    troll.set_property("is_dead", True)

    troll_state = next(c for c in world_state(game).characters if c.name == "troll")
    assert troll_state.goals[0].description == "Eat the player"
    assert troll_state.goals[0].type == "short"  # GoalType.SHORT.value
    assert troll_state.goals[0].done is False
    assert troll_state.properties.get("is_dead") is True


def test_clock_absent_then_present():
    game, *_ = _two_room_game()
    assert world_state(game).clock is None  # no time_config -> no clock

    field = things.Location("Field", "A field.")
    player = things.Character("player", "you", "I explore.")
    timed = games.Game(
        field, player, time_config={"start_hour": 8, "minutes_per_turn": 15}
    )
    cs = world_state(timed).clock
    assert cs is not None
    assert (cs.day, cs.hour, cs.minute) == (0, 8, 0)
    assert "8:00" in cs.time


def test_recent_events_tail():
    from text_adventure_games.events import GameEvent

    game, *_ = _two_room_game()
    for turn in range(30):
        game.events.append(GameEvent(turn=turn, actor="player", action="move"))
    ws = world_state(game)
    assert len(ws.events) <= 20  # bounded newest tail
    assert ws.events[-1].turn == 29


def test_determinism_and_purity():
    game, field, _, player, _ = _two_room_game()
    field.add_item(things.Item("rock", "a rock", "A rock."))
    before_turn, before_loc = game.turn, player.location

    a = json.dumps(world_state(game).to_jsonable(), sort_keys=True)
    b = json.dumps(world_state(game).to_jsonable(), sort_keys=True)
    assert a == b  # stable ordering -> byte-identical

    assert game.turn == before_turn  # building the snapshot mutated nothing
    assert player.location is before_loc


def test_to_jsonable_round_trips():
    game, *_ = _two_room_game()
    blob = json.dumps(world_state(game).to_jsonable())  # must not raise
    restored = json.loads(blob)
    assert restored["schema_version"] == SCHEMA_VERSION
    assert restored["player"] == "player"
    assert {loc["name"] for loc in restored["locations"]} == {"Field", "Forest"}


def test_game_to_world_state_and_json_methods():
    game, *_ = _two_room_game()
    assert game.to_world_state().player == "player"
    assert json.loads(game.to_world_json())["player"] == "player"


def test_event_payload_is_sorted_and_json_safe():
    from text_adventure_games.events import GameEvent

    game, field, *_ = _two_room_game()
    rock = things.Item("rock", "a rock", "A rock.")  # a non-serializable value
    game.events.append(
        GameEvent(turn=0, actor="player", action="move", payload={"z": 1, "a": rock})
    )
    ev = world_state(game).events[-1]
    assert list(ev.payload.keys()) == ["a", "z"]  # keys sorted for determinism
    assert isinstance(ev.payload["a"], str)  # the Item coerced to a string
    game.to_world_json()  # JSON-safe: must not raise


def test_item_quantity_is_exported():
    game, field, *_ = _two_room_game()
    coin = things.Item("coin", "a coin", "A coin.")
    coin.quantity = 5
    field.add_item(coin)
    coin_state = next(
        i for loc in world_state(game).locations for i in loc.items if i.name == "coin"
    )
    assert coin_state.quantity == 5


def test_webapp_world_state_route_serves_the_snapshot():
    # The /world_state HTTP endpoint puts the snapshot on the wire so an
    # out-of-process renderer (Godot) can poll it (issues #9 / #10).
    from text_adventure_games.webapp.app import app

    resp = app.test_client().get("/world_state")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert "player" in data and "locations" in data
