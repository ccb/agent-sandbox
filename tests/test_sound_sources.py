"""Phase 2 of the reactions design (docs/design/reactions.md): the sound-source
helpers. ``emit_sound`` lets a thing emit an ambient noise; ``sounds_audible_at``
answers "what sound is heard here this round" (the startle stimulus); and
``entered_this_round`` answers "did this creature just arrive here" (the countdown
stimulus). Pure additions -- no action carries volume yet (that lands in the
migration phase).
"""

from text_adventure_games import games, things
from text_adventure_games.enums import EventKind
from text_adventure_games.reporting import CaptureRenderer, Channel


def _line(*names):
    """A line of rooms wired north<->south: names[0] --north--> names[1] ... ."""
    rooms = [things.Location(n, f"Room {n}.") for n in names]
    for a, b in zip(rooms, rooms[1:]):
        a.add_connection("north", b)  # auto-wires b --south--> a
    player = things.Character("you", "the player", "I explore.")
    game = games.Game(rooms[0], player)
    return game, player, rooms


# --- emit_sound -------------------------------------------------------------


def test_emit_sound_logs_a_sound_event():
    game, player, (a,) = _line("A")
    game.emit_sound(a, 1, "a crash")
    e = game.events[-1]
    assert e.action == EventKind.SOUND and e.actor is None
    assert e.payload["location"] == "A"
    assert e.payload["heard_radius"] == 1
    assert e.payload["sound"] == "a crash"


def test_emit_sound_overheard_by_a_player_one_room_away():
    game, player, (a, b) = _line("A", "B")
    game.relocate(player, b)  # player is north, in B; the noise is in A
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.emit_sound(a, 1, "a wail")
    # Narrated to the player from the direction back toward the source.
    assert any(
        "From the south you hear a wail" in t for t in cap.texts(Channel.NARRATION)
    )


# --- sounds_audible_at ------------------------------------------------------


def test_sound_is_heard_in_its_origin_room():
    game, player, (a,) = _line("A")
    game.emit_sound(a, 1, "a crash")
    heard = game.sounds_audible_at(a)
    assert len(heard) == 1
    assert heard[0]["description"] == "a crash"
    assert heard[0]["direction"] is None  # same room


def test_sound_carries_to_an_adjacent_room_with_a_direction():
    game, player, (a, b) = _line("A", "B")
    game.emit_sound(a, 1, "a crash")
    heard = game.sounds_audible_at(b)
    assert len(heard) == 1
    assert heard[0]["direction"] == "south"  # B hears it from the south (back to A)


def test_sound_does_not_reach_beyond_its_radius():
    game, player, (a, b, c) = _line("A", "B", "C")
    game.emit_sound(a, 1, "a crash")  # carries one hop: reaches B, not C
    assert game.sounds_audible_at(b)
    assert game.sounds_audible_at(c) == []


def test_silent_events_are_not_sounds():
    game, player, (a,) = _line("A")
    game.log_event(
        "you", "examine", "examine rock", payload={"location": "A", "heard_radius": 0}
    )
    assert game.sounds_audible_at(a) == []


def test_exclude_drops_a_things_own_sound():
    game, player, (a,) = _line("A")
    game.log_event(
        "deer",
        "stomp",
        "stomp",
        payload={"location": "A", "heard_radius": 1, "sound": "stomping"},
    )
    assert game.sounds_audible_at(a)  # someone else would hear it
    assert (
        game.sounds_audible_at(a, exclude="deer") == []
    )  # the deer doesn't startle itself


# --- entered_this_round -----------------------------------------------------


def test_entered_this_round_detects_an_arrival():
    game, player, (a, b) = _line("A", "B")
    game.do_command("go north")  # player moves A -> B
    assert game.entered_this_round(player, b)
    assert not game.entered_this_round(player, a)


def test_entered_this_round_false_without_a_move():
    game, player, (a, b) = _line("A", "B")
    game.do_command("look")  # no movement
    assert not game.entered_this_round(player, a)
    assert not game.entered_this_round(player, b)
