"""The live Penn server's building blocks (issues #263/#297).

Pins the three contracts the Godot live client stands on:

* ``penn_world.build_penn_world`` hands out the SAME configured Penn the bake
  uses -- personas, meetings, routing patches, perception-gated hearing (#297);
* ``serve_penn.PennStepper`` driven tick-by-tick reproduces ``simulate()``'s
  frames exactly (the live analogue of #296's byte-identical gate);
* ``serve_penn.LiveMeetingInjector`` fires authored dialogue only on genuine
  co-location, with the bake injector's pacing and clash rules.

Fully offline (mock brain, the tracked ``the_upenn`` matrix). Run from the
repo root::

    uv run pytest godot-generative-agents/tests/test_penn_live.py -v
"""

import sys
from pathlib import Path

import pytest

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.run_simulation import simulate  # noqa: E402
from backend.run_store import RunStore  # noqa: E402
from text_adventure_games.events import GameEvent  # noqa: E402
from penn_world import (  # noqa: E402
    build_penn_world,
    relationships_meta,
    replay_frame_entry,
)
from serve_penn import LiveMeetingInjector, PennStepper, _GameProxy  # noqa: E402

VISION_R = 8  # cognition.DEFAULT_VISION_R; the fog radius the viewer draws


# ------------------------------------------------------- build_penn_world


def test_build_penn_world_pieces():
    pw = build_penn_world()
    # The active cast: 3 of the 7 authored personas (the rest are commented out
    # in world_data_upenn.yaml while the live-LLM MVP keeps test runs cheap).
    assert len(pw.personas) == 3
    assert len(pw.meetings) == 2  # the meetings whose participants are active
    assert callable(pw.build_world_fn)
    # The routing patches are installed: walk_path is a closure over the map,
    # not the WorldMap method (a live server reusing this map inherits them).
    assert pw.world_map.walk_path.__name__ == "walk_path"
    assert type(pw.world_map).walk_path is not pw.world_map.walk_path


def test_build_penn_world_relationships():
    # The authored t=0 seed social graph (#252): one edge among the active cast
    # (Diego knows Tanaka from her lectures; Sofia knows nobody on purpose --
    # the pop-up's demo story is a first-year's graph growing over the day).
    pw = build_penn_world()
    assert pw.relationships == [
        {
            "a": "Diego Torres",
            "b": "Professor Tanaka",
            "kind": "lecture regular",
            "closeness": 2,
            "description": (
                "Diego sits in on Professor Tanaka's public guest lectures at "
                "Irvine whenever architecture and physics cross paths; she knows "
                "him by name from the question line."
            ),
        }
    ]


def test_relationships_meta_validation():
    # relationships_meta is the authoring gate: typos fail the bake/server boot
    # instead of drawing a wrong graph. Names sort within an edge, edges sort
    # by (a, b), and only the five contract keys survive.
    personas = [{"name": "Ana"}, {"name": "Bo"}, {"name": "Cy"}]
    out = relationships_meta(
        personas,
        [
            {"a": "Cy", "b": "Bo", "kind": "labmates", "closeness": 5},
            {"a": "Bo", "b": "Ana", "kind": "friends", "closeness": 3, "extra": 1},
        ],
    )
    assert out == [
        {"a": "Ana", "b": "Bo", "kind": "friends", "closeness": 3, "description": ""},
        {"a": "Bo", "b": "Cy", "kind": "labmates", "closeness": 5, "description": ""},
    ]
    with pytest.raises(ValueError):  # unknown name (a parked persona, say)
        relationships_meta(personas, [{"a": "Ana", "b": "Maya Chen"}])
    with pytest.raises(ValueError):  # self-edge
        relationships_meta(personas, [{"a": "Ana", "b": "Ana"}])
    with pytest.raises(ValueError):  # duplicate pair, either order
        relationships_meta(personas, [{"a": "Ana", "b": "Bo"}, {"a": "Bo", "b": "Ana"}])
    with pytest.raises(ValueError):  # closeness outside 1..5
        relationships_meta(personas, [{"a": "Ana", "b": "Bo", "closeness": 0}])
    with pytest.raises(ValueError):
        relationships_meta(personas, [{"a": "Ana", "b": "Bo", "closeness": 6}])


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
        "schema_version",
        "tile_px",
        "width",
        "height",
        "sec_per_step",
        "start",
        "vision_r",
        "personas",
        "relationships",
        "llm",
    }
    assert meta["vision_r"] == VISION_R
    assert len(meta["personas"]) == 3
    assert meta["llm"] is None  # the default stepper runs the mock brain
    # Each persona carries identity + schedule for the State Details inspector
    # (issue #408); vision_r stays a top-level global, not a per-persona key.
    assert all(
        set(p) == {"name", "emoji", "persona", "home", "schedule"}
        for p in meta["personas"]
    )
    # The seed social graph (#252): normalized edges among the active cast,
    # names sorted within each edge (a < b), for the viewer's social-graph
    # pop-up. Content itself is pinned by test_build_penn_world_relationships.
    cast = {p["name"] for p in meta["personas"]}
    for edge in meta["relationships"]:
        assert set(edge) == {"a", "b", "kind", "closeness", "description"}
        assert edge["a"] < edge["b"]
        assert {edge["a"], edge["b"]} <= cast


def test_bake_meta_carries_relationships(tmp_path, monkeypatch):
    # Bake/live parity for the seed graph: the replay file's meta.relationships
    # is the same validated list the live handshake serves, because both come
    # from penn_world.relationships_meta at build time.
    import json

    import generate_penn_replay

    out = tmp_path / "r.json"
    monkeypatch.setattr(
        sys, "argv", ["generate_penn_replay.py", "--steps", "2", "--out", str(out)]
    )
    assert generate_penn_replay.main() == 0
    baked_meta = json.loads(out.read_text())["meta"]
    live_meta = PennStepper(num_steps=2, world=build_penn_world()).meta()
    assert baked_meta["relationships"] == live_meta["relationships"]
    assert len(baked_meta["relationships"]) == 1  # Diego -- Tanaka, the seed edge


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


def test_stepper_persists_frames_memories_and_finish(tmp_path):
    # The #304 live wiring: every tick lands in the store as it happens, and
    # the day's end flips the run to "finished".
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=5, world=build_penn_world(), run_store=store)
    run_id = stepper.run_id
    frames = [stepper.tick() for _ in range(5)]
    assert store.read_frames(run_id) == frames
    run = store.get_run(run_id)
    assert run["status"] == "running" and run["steps"] == 5 and run["cost"] == 0.0
    assert run["manifest"] == stepper.meta()
    # The t=0 plan memory alone guarantees at least one row per persona.
    for name in stepper.order:
        assert store.last_memory_id(run_id, name) >= 0
    assert stepper.tick() is None  # the day ends...
    assert store.get_run(run_id)["status"] == "finished"
    assert stepper.tick() is None  # ...and stays finished (idempotent)
    assert store.get_run(run_id)["status"] == "finished"


def test_stepper_persists_game_events(tmp_path):
    # The #307 live wiring: GameEvents flush to events.jsonl on a cursor of
    # their own -- draining the change feed must not starve persistence --
    # and the day's close catches events logged after the final tick (the
    # POST /world/event window).
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=2, world=build_penn_world(), run_store=store)
    run_id = stepper.run_id
    stepper.tick()
    # An intervention lands between ticks (api.py's /world/event shape).
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="a siren wails")
    )
    stepper.drain_events()  # the feed reads first; persistence must still see all
    stepper.tick()
    assert store.read_events(run_id) == [e.to_primitive() for e in stepper.game.events]
    assert "a siren wails" in {e["summary"] for e in store.read_events(run_id)}
    # A straggler after the last tick is flushed by the day's close.
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="last call")
    )
    assert stepper.tick() is None  # end of day -> _finish_run tail-flushes
    assert store.read_events(run_id) == [e.to_primitive() for e in stepper.game.events]
    assert store.read_events(run_id)[-1]["summary"] == "last call"


def test_stepper_reset_closes_the_run_and_opens_a_new_one(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=3, world=build_penn_world(), run_store=store)
    first = stepper.run_id
    stepper.tick()
    # An event logged after the tick still belongs to the first run --
    # reset() tail-flushes before closing the row (#307).
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="bell rings")
    )
    stepper.reset()
    second = stepper.run_id
    assert first != second
    assert store.get_run(first)["status"] == "reset"
    assert store.get_run(second)["status"] == "running"
    assert {r["id"] for r in store.list_runs()} == {first, second}
    assert store.read_events(first)[-1]["summary"] == "bell rings"
    assert store.read_events(second) == []  # the new day starts clean
    # The default stays storeless (and byte-identical -- the simulate-mirror
    # test above pins it): a bare stepper has no run id.
    assert PennStepper(num_steps=1, world=build_penn_world()).run_id is None


def test_stepper_threads_cognition_tools():
    # The #514 plumbing: the flag rides the stepper into attach_agents, which
    # stamps the engine attribute the decide tool loop and the converse path
    # read. _build() re-reads it from the stepper, so POST /reset keeps it.
    stepper = PennStepper(num_steps=3, world=build_penn_world(), cognition_tools=True)
    assert stepper.chars  # guard: the all() below actually checked someone
    assert all(c.agent.cognition_tools is True for c in stepper.chars.values())
    stepper.reset()
    assert all(c.agent.cognition_tools is True for c in stepper.chars.values())


def test_stepper_default_leaves_cognition_tools_off():
    # No flag: agents keep the engine default (attach_agents only stamps when
    # on), so the default live server stays byte-identical to today.
    stepper = PennStepper(num_steps=3, world=build_penn_world())
    assert stepper.chars
    assert all(c.agent.cognition_tools is False for c in stepper.chars.values())


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


def test_injector_reset_rearms_for_a_second_day():
    # Each meeting fires at most once per run; reset() re-arms it, so a second
    # simulated day (PennStepper.reset() rebuilds the world and calls this) plays
    # the authored dialogue again. Fire-once, drift, and clash are covered above;
    # this pins the re-arm the DONE->ARMED transition depends on.
    meeting = _meeting(lines=1)  # need = 1*14 + 2 = 16 frames
    injector = LiveMeetingInjector([meeting], vision_r=8)

    frame = _frame(A=(0, 0), B=(1, 0))  # day 1: fires on co-location
    injector.apply(frame, 0)
    assert frame["A"]["chat"] == meeting["dialogue"]

    frame = _frame(A=(0, 0), B=(1, 0))  # run the window out: FIRING -> DONE
    injector.apply(frame, 16)
    assert frame["A"]["chat"] is None

    frame = _frame(A=(0, 0), B=(1, 0))  # spent: co-located again, stays quiet
    injector.apply(frame, 30)
    assert frame["A"]["chat"] is None

    injector.reset()  # a fresh day re-arms it
    frame = _frame(A=(0, 0), B=(1, 0))
    injector.apply(frame, 0)
    assert frame["A"]["chat"] == meeting["dialogue"]  # armed again, fires again


# --------------------------------------------------------------- _GameProxy


def test_game_proxy_delegates_and_follows_the_post_reset_swap():
    # create_app(game) captures the served game ONCE, but PennStepper.reset()
    # rebuilds a fresh world -- a NEW Game object (the routing patches carry
    # round-robin state in closures, so the old world can't be reused). serve_penn
    # therefore hands the API a _GameProxy, whose every attribute resolves against
    # whichever game the stepper currently owns -- so /world_state serves the new
    # day the instant a reset lands, rather than a stale pinned object.
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    proxy = _GameProxy(stepper)

    # __getattr__ delegates to the live stepper.game (attribute and bound method).
    first_game = stepper.game
    assert proxy.turn == first_game.turn
    assert proxy.to_world_state.__self__ is first_game

    stepper.reset()  # rebuilds: stepper.game is a brand-new object
    assert stepper.game is not first_game
    assert proxy.turn == stepper.game.turn  # the proxy followed the swap...
    assert proxy.to_world_state.__self__ is stepper.game  # ...never pinned the old one
