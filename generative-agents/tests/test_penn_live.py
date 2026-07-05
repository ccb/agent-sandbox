"""The live Penn server's building blocks (issues #263/#297).

Pins the three contracts the Godot live client stands on:

* ``penn_world.build_penn_world`` hands out the SAME configured Penn the bake
  uses -- personas, meetings, routing patches, perception-gated hearing (#297);
* ``serve_penn.PennStepper`` driven tick-by-tick reproduces ``simulate()``'s
  frames exactly (the live analogue of #296's byte-identical gate);
* ``serve_penn.LiveMeetingInjector`` fires authored dialogue only on genuine
  co-location, with the bake injector's pacing and clash rules.

Fully offline (mock brain, the tracked ``the_upenn`` matrix). Run from
``generative-agents``::

    uv run pytest tests/test_penn_live.py -v
"""

import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = Path(__file__).resolve().parents[2] / "godot-generative-agents" / "sim"
sys.path.insert(0, str(_SIM_DIR))

from backend.run_simulation import simulate  # noqa: E402
from penn_world import build_penn_world, replay_frame_entry  # noqa: E402
from serve_penn import LiveMeetingInjector, PennStepper  # noqa: E402

VISION_R = 8  # SMALLVILLE_VISION_R; the fog radius the viewer draws


# ------------------------------------------------------- build_penn_world


def test_build_penn_world_pieces():
    pw = build_penn_world()
    assert len(pw.personas) == 7  # the authored Penn cast
    assert len(pw.meetings) == 4  # the authored meetings block
    assert callable(pw.build_world_fn)
    # The routing patches are installed: walk_path is a closure over the map,
    # not the WorldMap method (a live server reusing this map inherits them).
    assert pw.world_map.walk_path.__name__ == "walk_path"
    assert type(pw.world_map).walk_path is not pw.world_map.walk_path


def _move(char, location):
    if char.location is not None:
        char.location.remove_character(char)
    location.add_character(char)


def test_audience_gated_by_perception():
    # The #297 must-not-regress: the perception-gated hearing patch survives
    # the move out of the bake script. Hearing == sight radius, not same-room.
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    speaker = chars[pw.personas[0]["name"]]
    other = chars[pw.personas[1]["name"]]
    arenas = [
        loc
        for loc in game.locations.values()
        if getattr(loc, "tile_address", None) is not None
    ]
    near = arenas[0]
    far = next(
        loc
        for loc in arenas
        if pw.world_map.tile_gap(near.tile_address, loc.tile_address) > VISION_R
    )
    _move(speaker, near)
    _move(other, near)
    assert other in game.audience_for(speaker, "hello")  # standing together
    _move(other, far)
    assert other not in game.audience_for(speaker, "hello")  # out of range


# ------------------------------------------------------------ PennStepper


def test_stepper_matches_simulate_prefix():
    # The live analogue of #296's gate: N ticks of the stepper == the first N
    # frames of simulate(), through the same replay_frame_entry mapping. Two
    # FRESH worlds -- the routing patches carry round-robin state in closures,
    # so a world can't be driven twice and still route identically. (At N=40
    # no authored meeting has convened yet, so the live injector is quiet and
    # chat is None on both sides.)
    n = 40
    pw = build_penn_world()
    baked = simulate(
        pw.world_map,
        n,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
    )
    names = [p["name"] for p in pw.personas]
    expected = [{name: replay_frame_entry(f[name]) for name in names} for f in baked]

    stepper = PennStepper(num_steps=n, world=build_penn_world())
    live = [stepper.tick() for _ in range(n)]
    assert live == expected


def test_stepper_meta_shape():
    stepper = PennStepper(num_steps=5, world=build_penn_world())
    meta = stepper.meta()
    assert set(meta) == {
        "tile_px",
        "width",
        "height",
        "sec_per_step",
        "start",
        "vision_r",
        "personas",
    }
    assert meta["vision_r"] == VISION_R
    assert len(meta["personas"]) == 7
    assert all(set(p) == {"name", "emoji"} for p in meta["personas"])


def test_stepper_finishes_then_resets():
    stepper = PennStepper(num_steps=3, world=build_penn_world())
    first_day = [stepper.tick() for _ in range(3)]
    assert all(f is not None for f in first_day)
    assert stepper.tick() is None  # the day is over: the loop will auto-pause
    assert stepper.step == 3
    ledger = stepper.ledger
    stepper.reset()
    assert stepper.step == 0
    assert stepper.ledger is ledger  # money spent stays spent across resets
    assert stepper.tick() == first_day[0]  # a fresh day replays deterministically


# ---------------------------------------------------- LiveMeetingInjector


def _meeting(participants=("A", "B"), lines=2, label="test meeting"):
    return {
        "label": label,
        "at": "Somewhere",
        "participants": list(participants),
        "dialogue": [[participants[i % 2], f"line {i}"] for i in range(lines)],
    }


def _frame(**positions):
    return {
        name: {"x": x, "y": y, "act": "standing", "e": ":)", "chat": None}
        for name, (x, y) in positions.items()
    }


def test_injector_fires_on_colocation_and_paces():
    meeting = _meeting(lines=2)  # need = 2*14 + 2 = 30 frames
    injector = LiveMeetingInjector([meeting], vision_r=8)
    for step in range(5):  # far apart: nothing fires
        frame = _frame(A=(0, 0), B=(50, 0))
        injector.apply(frame, step)
        assert frame["A"]["chat"] is None and frame["B"]["chat"] is None
    for step in range(5, 40):  # together: fires at 5, paints exactly 30 frames
        frame = _frame(A=(0, 0), B=(3, 0))
        injector.apply(frame, step)
        expected = meeting["dialogue"] if step < 35 else None
        assert frame["A"]["chat"] == expected and frame["B"]["chat"] == expected
    # Never re-fires, even on renewed co-location.
    frame = _frame(A=(0, 0), B=(1, 0))
    injector.apply(frame, 100)
    assert frame["A"]["chat"] is None


def test_injector_keeps_playing_after_drift():
    # Live code can't see the future: once fired, the exchange plays out even
    # if the participants wander apart (the documented simplification).
    injector = LiveMeetingInjector([_meeting(lines=2)], vision_r=8)
    frame = _frame(A=(0, 0), B=(3, 0))
    injector.apply(frame, 0)
    assert frame["A"]["chat"] is not None  # fired
    frame = _frame(A=(0, 0), B=(80, 0))  # drifted way out of range
    injector.apply(frame, 10)
    assert frame["A"]["chat"] is not None  # still painting (step 10 < 30)
    frame = _frame(A=(0, 0), B=(80, 0))
    injector.apply(frame, 30)
    assert frame["A"]["chat"] is None  # window over


def test_injector_clash_rules():
    # A shared participant mid-conversation blocks a second meeting from
    # arming; the blocked meeting fires later, at its next co-location.
    first = _meeting(("A", "B"), lines=1, label="first")  # need = 16
    second = _meeting(("B", "C"), lines=1, label="second")
    injector = LiveMeetingInjector([first, second], vision_r=8)
    frame = _frame(A=(0, 0), B=(2, 0), C=(4, 0))  # everyone together
    injector.apply(frame, 0)
    assert frame["A"]["chat"] == first["dialogue"]
    assert frame["C"]["chat"] is None  # B is busy in `first`
    frame = _frame(A=(0, 0), B=(2, 0), C=(4, 0))
    injector.apply(frame, 16)  # `first` finishes THIS step; B frees up after it
    assert frame["C"]["chat"] is None
    frame = _frame(A=(0, 0), B=(2, 0), C=(4, 0))
    injector.apply(frame, 17)
    assert frame["C"]["chat"] == second["dialogue"]  # now `second` fires


def test_injector_respects_existing_chat():
    # A participant already talking (later: a real-LLM conversation, #261)
    # blocks arming -- authored dialogue never garbles live dialogue.
    injector = LiveMeetingInjector([_meeting(("A", "B"))], vision_r=8)
    frame = _frame(A=(0, 0), B=(3, 0))
    frame["A"]["chat"] = [["A", "already talking to someone else"]]
    injector.apply(frame, 0)
    assert frame["B"]["chat"] is None  # did not arm over the live chat


def test_injector_waits_for_the_venue():
    # A meeting with a resolvable `at:` venue only fires once every participant
    # is SETTLED there -- never at spawn (Maya and Priya start a few tiles
    # apart in the dorms) and never mid-commute (a travel leg's act carries the
    # destination address the whole way).
    meeting = _meeting(lines=1)
    locations = [{"name": "Somewhere", "address": "UPenn:Somewhere:room"}]
    injector = LiveMeetingInjector([meeting], vision_r=8, locations=locations)

    frame = _frame(A=(0, 0), B=(1, 0))  # together, but acts aren't at the venue
    injector.apply(frame, 0)
    assert frame["A"]["chat"] is None

    frame = _frame(A=(0, 0), B=(1, 0))  # together, walking THERE: still no
    for name in ("A", "B"):
        frame[name]["act"] = "walking to Somewhere @ UPenn:Somewhere:room"
    injector.apply(frame, 1)
    assert frame["A"]["chat"] is None

    frame = _frame(A=(0, 0), B=(1, 0))  # settled at the venue: fires
    for name in ("A", "B"):
        frame[name]["act"] = "studying @ UPenn:Somewhere:room"
    injector.apply(frame, 2)
    assert frame["A"]["chat"] == meeting["dialogue"]


def test_injector_skips_bad_specs():
    bad = [
        {"label": "solo", "participants": ["A"], "dialogue": [["A", "hi"]]},
        {"label": "mute", "participants": ["A", "B"], "dialogue": []},
    ]
    injector = LiveMeetingInjector(bad, vision_r=8)
    frame = _frame(A=(0, 0), B=(1, 0))
    injector.apply(frame, 0)
    assert frame["A"]["chat"] is None and frame["B"]["chat"] is None
