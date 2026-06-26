"""Vehicles / mounts (engine feature): board, ride, gate exits, travel-with-rider."""

from text_adventure_games import games, things
from text_adventure_games.blocks import RequiresVehicle
from text_adventure_games.enums import ActionName
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world(horse_ready=False):
    field = things.Location("Field", "An open field. Woods lie west.")
    woods = things.Location("Woods", "Shady woods. The field is east.")
    field.add_connection("west", woods)  # also wires woods --east--> field
    field.add_block(
        "west",
        RequiresVehicle(
            field, "It's too far to travel on foot. Perhaps on horseback..."
        ),
    )
    horse = things.Item("horse", "a white mare")
    horse.set_property("gettable", False)
    horse.make_vehicle(ready=horse_ready)
    horse.set_property("mount_refusal_message", "The mare shies away from you.")
    field.add_item(horse)
    player = things.Character("you", "a rider", "I ride.")
    game = games.Game(field, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, field, woods, horse, player, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def test_make_vehicle_sets_flags():
    h = things.Item("bike", "a chopper").make_vehicle(ready=False)
    assert h.is_vehicle() and not h.vehicle_ready()
    h.set_property("vehicle_ready", True)
    assert h.vehicle_ready()


def test_parser_routes_ride_vehicle_vs_ride_direction():
    game, *_ = _world()
    assert game.parser.determine_intent("ride horse") == ActionName.MOUNT
    assert game.parser.determine_intent("get on horse") == ActionName.MOUNT
    assert game.parser.determine_intent("dismount") == ActionName.DISMOUNT
    assert game.parser.determine_intent("get off") == ActionName.DISMOUNT
    # "ride west" is movement (you ride a direction once aboard), not mounting
    assert game.parser.determine_intent("ride west") == ActionName.GO


def test_cannot_take_a_gated_exit_on_foot():
    game, field, woods, horse, player, cap = _world(horse_ready=True)
    game.do_command("go west")
    assert _said(cap, "on foot")
    assert player.location is field


def test_mount_refused_until_ready():
    game, field, woods, horse, player, cap = _world(horse_ready=False)
    game.do_command("ride horse")
    assert _said(cap, "shies away")
    assert player.riding is None
    # a game-specific verb (give apple / brush) would flip this:
    horse.set_property("vehicle_ready", True)
    game.do_command("ride horse")
    assert player.riding is horse


def test_riding_opens_the_gate_and_the_vehicle_travels_along():
    game, field, woods, horse, player, cap = _world(horse_ready=True)
    game.do_command("ride horse")
    assert player.riding is horse
    game.do_command("ride west")  # mounted -> the gate opens
    assert player.location is woods
    assert "horse" in woods.items and "horse" not in field.items  # came along
    game.do_command("dismount")
    assert player.riding is None
    assert "horse" in woods.items  # left here, where you got off


def test_dismount_with_no_ride_is_reported():
    game, *_rest, cap = _world(horse_ready=True)
    game.do_command("dismount")
    assert _said(cap, "not riding")


def test_riding_changes_the_arrival_verb():
    # On foot: "moved to". Riding: "<Name> rides the <vehicle> to <place>".
    game, field, woods, horse, player, cap = _world(horse_ready=True)
    game.parser.parse_command("ride horse")
    game.parser.parse_command("west")
    assert _said(cap, "rides the horse to Woods")
    assert not _said(cap, "you moved to Woods")


def test_ride_verb_is_customizable_per_vehicle():
    # A boat can say "rows" instead of the default "rides".
    game, field, woods, horse, player, cap = _world(horse_ready=True)
    horse.set_property("ride_verb", "rows")  # pretend it's a boat
    game.parser.parse_command("ride horse")
    game.parser.parse_command("west")
    assert _said(cap, "rows the horse to Woods")


def test_on_foot_arrival_is_unchanged():
    game, field, woods, horse, player, cap = _world(horse_ready=True)
    # No vehicle gate on the reverse trip; walk east on foot.
    player.location = woods
    game.parser.parse_command("east")
    assert _said(cap, "you moved to Field")
