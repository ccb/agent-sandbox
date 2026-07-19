"""The wish change-feed record + wishes.jsonl + replay bake (#622).

Mirrors the #551 deciding feed's structure -- emit (the engine's ``on_wish``
hook, already installed by #620/#621) -> buffer under a lock -> drain per tick
-> publish -- but the persistence half follows the #467 events precedent
instead (a growing ``wishes.jsonl``, ``skip_bad``-tolerant), since a wish, like
a GameEvent, is a permanent run record, not an ephemeral per-tick lifecycle
signal like ``deciding``.

Record shape: ``ActionWish.to_primitive()`` verbatim (actor/turn/location/
desired/reason/trigger/goals/scope/raw_command/meta) under a live-feed record
carrying its OWN top-level ``kind: "wish"`` -- NOT wrapped inside "engine" the
way llm_call/game_event rows are (contrast test_event_records.py).

Mock invariant: the mock brain never proposes and its authored commands always
parse, so under ``--brain mock`` (the default PennStepper) the wish buffer
never receives a record at all -- the feed is byte-identical BY VACUITY, not
by an explicit brain-identity gate (contrast #551's ``deciding`` sink, which
needs one because every decide, mock included, passes through it).

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_wish_feed.py -v
"""

import json
import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import run_simulation  # noqa: E402
from backend.build_world import _normalize_personas, build_world  # noqa: E402
from backend.run_simulation import simulate  # noqa: E402
from backend.run_store import RunStore  # noqa: E402
from text_adventure_games.wishes import (  # noqa: E402
    ActionWish,
    TRIGGER_PARSE_GAP,
    TRIGGER_PROPOSED,
)
from penn_world import PENN_EXTRA_ACTIONS, build_penn_world  # noqa: E402
from serve_penn import PennStepper  # noqa: E402


def _wish(**over):
    fields = dict(
        actor="Diego Torres",
        turn=0,
        location="UPenn:Van Pelt Library",
        desired="a bike rack near the library",
        reason="mine keeps getting stolen",
        trigger=TRIGGER_PROPOSED,
        goals=[],
        scope=[],
        raw_command=(
            "propose a bike rack near the library because mine keeps getting stolen"
        ),
    )
    fields.update(over)
    return ActionWish(**fields)


# --- hook installation + buffer/drain ---------------------------------------


def test_stepper_installs_on_wish_as_the_engine_hook():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.game.on_wish == stepper._on_wish


def test_stepper_buffers_and_drains_a_wish_record():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    wish = _wish()
    stepper.game.log_wish(wish)  # fires game.on_wish -> stepper._on_wish
    rows = stepper.drain_wishes()
    assert rows == [wish.to_primitive()]
    # Draining again is idempotent (buffer cleared) -- mirrors drain_events.
    assert stepper.drain_wishes() == []


def test_stepper_buffers_multiple_wishes_in_order():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    first = _wish(desired="a working printer")
    second = _wish(trigger=TRIGGER_PARSE_GAP, desired="dance with the statue")
    stepper.game.log_wish(first)
    stepper.game.log_wish(second)
    assert stepper.drain_wishes() == [first.to_primitive(), second.to_primitive()]


def test_reset_restarts_the_wish_buffer():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    stepper.game.log_wish(_wish())
    stepper.reset()
    assert stepper.drain_wishes() == []  # the old day's buffer didn't survive
    stepper.game.log_wish(_wish(desired="after reset"))
    assert [w["desired"] for w in stepper.drain_wishes()] == ["after reset"]


# --- the mock invariant, pinned (#622 acceptance) ---------------------------


def test_mock_stepper_emits_no_wish_records():
    # The core invariant: --brain mock (PennStepper's default) never calls
    # propose and its authored travel/perform commands always parse, so
    # game.wishes -- and this buffer -- stay empty for the whole run. The feed
    # is byte-identical to a world with no wish channel at all.
    stepper = PennStepper(num_steps=5, world=build_penn_world())
    for _ in range(5):
        stepper.tick()
    assert stepper.game.wishes == []
    assert stepper.drain_wishes() == []


def test_mock_run_feed_is_unaffected_by_the_wish_channel():
    """#622 review finding (Minor): a stronger, more direct pin than the
    buffer-emptiness check above. That test proves the buffer *happens to be*
    empty; this one proves the tick/frame stream a mock run publishes is
    genuinely unreachable by the wish channel -- byte-identical whether
    ``game.on_wish`` is installed at all -- by diffing two independently
    built steppers over the same deterministic mock schedule, one with the
    hook removed entirely (simulating a world with no wish channel wired).
    Any drift would mean the wish plumbing was leaking into the ordinary
    tick path; there is none, and neither run ever produces a ``kind:
    "wish"`` record."""
    wired = PennStepper(num_steps=5, world=build_penn_world())
    unwired = PennStepper(num_steps=5, world=build_penn_world())
    unwired.game.on_wish = None  # no wish channel wired at all

    wired_frames = [wired.tick() for _ in range(5)]
    unwired_frames = [unwired.tick() for _ in range(5)]
    assert wired_frames == unwired_frames  # the rest of the feed is untouched

    assert wired.game.wishes == unwired.game.wishes == []
    assert wired.drain_wishes() == unwired.drain_wishes() == []


# --- a scripted propose produces a wish within one tick (acceptance) -------


def test_stepper_publishes_a_scripted_propose_within_a_tick(monkeypatch):
    # Every persona is due to decide on step 0 (fresh state: no path, not
    # performing, not conversing) -- so stubbing observe_and_decide (the same
    # seam test_deciding_feed.py stubs) to return a "propose" command routes
    # it through the real parser on the very first tick, exactly like the
    # #622 acceptance scenario ("a live run with a scripted propose").
    monkeypatch.setattr(
        run_simulation,
        "observe_and_decide",
        lambda *a, **k: (
            "propose a bike rack near the library because mine keeps getting stolen"
        ),
    )
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    stepper.tick()
    rows = stepper.drain_wishes()
    assert rows, "a scripted propose must produce a wish record within one tick"
    assert all(r["trigger"] == "proposed" for r in rows)
    assert all(r["desired"] == "a bike rack near the library" for r in rows)
    assert all(r["reason"] == "mine keeps getting stolen" for r in rows)


# --- persistence: wishes.jsonl (#622, mirrors test_stepper_persists_game_events) --


def test_stepper_persists_wishes(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=2, world=build_penn_world(), run_store=store)
    run_id = stepper.run_id
    stepper.tick()
    stepper.game.log_wish(_wish(turn=stepper.game.turn))
    stepper.drain_wishes()  # the feed reads first; persistence must still see it
    stepper.tick()
    assert store.read_wishes(run_id) == [w.to_primitive() for w in stepper.game.wishes]
    assert store.read_wishes(run_id)[-1]["desired"] == "a bike rack near the library"
    # A straggler after the last tick is flushed by the day's close (#307's
    # POST /world/event window has a wish analogue: a wish logged after the
    # final tick but before the day formally ends).
    stepper.game.log_wish(_wish(turn=stepper.game.turn, desired="last call"))
    assert stepper.tick() is None  # end of day -> _finish_run tail-flushes
    assert store.read_wishes(run_id) == [w.to_primitive() for w in stepper.game.wishes]
    assert store.read_wishes(run_id)[-1]["desired"] == "last call"


def test_stepper_drops_a_bad_wish_instead_of_halting(tmp_path):
    # #637's tolerance, extended to wishes: one malformed record (an evolving
    # `meta` field the store's allowlist can't serialize) must be dropped and
    # counted, never halt the run.
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=2, world=build_penn_world(), run_store=store)
    run_id = stepper.run_id
    stepper.tick()
    good = _wish(turn=stepper.game.turn, desired="a working printer")
    bad = _wish(
        turn=stepper.game.turn,
        desired="unserializable",
        meta={"nope": object()},  # passes the key check, fails json.dumps
    )
    stepper.game.log_wish(good)
    stepper.game.log_wish(bad)
    stepper.tick()  # must NOT raise despite the bad wish
    desires = {w["desired"] for w in store.read_wishes(run_id)}
    assert "a working printer" in desires
    assert "unserializable" not in desires
    assert stepper.dropped_wishes == 1
    assert stepper.tick() is None
    assert store.get_run(run_id)["status"] == "finished"


def test_storeless_stepper_drains_the_persist_buffer_every_tick():
    """#622 review finding (Important): ``_persist_pending_wishes()`` was
    only reachable per-tick through ``_persist_tick()``, itself only called
    ``if self.run_store is not None``. A live run with NO ``--persist`` store
    therefore never drained ``_wish_persist_buf`` on a tick -- only at
    ``_finish_run``/``_close_current_run`` -- so an endless, no-persist run
    driven by a proposing brain would grow that buffer without bound even
    though nothing was ever going to be written to disk. ``tick()`` must
    drain it directly when storeless, every tick, not just at the run's end.
    """
    stepper = PennStepper(num_steps=10, world=build_penn_world())
    assert stepper.run_store is None
    for i in range(5):
        stepper.game.log_wish(_wish(turn=i, desired=f"wish {i}"))
        stepper.game.log_wish(_wish(turn=i, desired=f"wish {i}b"))
        stepper.tick()
        # Drained every tick regardless of run_store -- never left to pile
        # up, even with nothing to persist it to.
        assert stepper._wish_persist_buf == []
    # The live feed buffer is a separate list, filled by the same _on_wish
    # call, and unaffected by this fix -- every wish still reaches it.
    assert len(stepper.drain_wishes()) == 10


def test_penn_stepper_reset_restarts_the_persist_cursor(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=2, world=build_penn_world(), run_store=store)
    stepper.game.log_wish(_wish(desired="before reset"))
    stepper.tick()
    stepper.reset()
    new_run_id = stepper.run_id
    stepper.game.log_wish(_wish(desired="after reset"))
    stepper.tick()
    assert [w["desired"] for w in store.read_wishes(new_run_id)] == ["after reset"]


# --- the bake carries a populated "wishes" array (#622 acceptance) ---------
# Mirrors test_event_records.py's _testa_sip_world/sickness-arc split exactly:
# content is pinned at the simulate() seam (a custom persona whose schedule
# scripts a real command, #300's `commands` field -- ScheduleMockClient plays
# it back verbatim, no LLM involved), and the real CLI bake is checked for
# presence/shape only (test_penn_replay_bake_writes_events_key's own words).


def _testa_wish_world():
    """A one-persona world whose first stop scripts a `propose` -- the #622
    acceptance scenario ("a live run with a scripted propose") at the
    simulate()/bake seam."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Wish",
        "home": "Houston Hall",
        "persona": "I am Testa Wish, a hopeful test persona.",
        "emoji": "\U0001f31f",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "wishing for a better campus",
                "emoji": "\U0001f31f",
                "steps": 3,
                "commands": [
                    "propose a working elevator because stairs are exhausting"
                ],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        return build_world(wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS)

    return pw, personas, build_fn


def test_simulate_out_wishes_carries_the_scripted_propose():
    """#622 acceptance, bake source: the run's ActionWish log comes back
    through out_wishes with the scripted propose's content intact."""
    pw, personas, build_fn = _testa_wish_world()
    wishes: list = []
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_wishes=wishes,
    )
    assert wishes, f"no wish record in {wishes}"
    record = wishes[0]
    assert record["actor"] == "Testa Wish"
    assert record["desired"] == "a working elevator"
    assert record["reason"] == "stairs are exhausting"
    assert record["trigger"] == "proposed"
    assert record["location"] == "Houston Hall"


def test_penn_replay_bake_writes_wishes_key(tmp_path, monkeypatch):
    """#622 acceptance, bake artifact: the replay JSON carries the run's
    wish log as a top-level `wishes` array (empty is fine for the default
    cast, which never wishes -- presence and shape are the contract; the
    scripted-propose *content* is pinned at the simulate() seam above,
    mirroring test_penn_replay_bake_writes_events_key)."""
    from backend.penn import generate_penn_replay

    out = tmp_path / "penn_replay.json"
    monkeypatch.setattr(
        sys, "argv", ["generate_penn_replay", "--steps", "8", "--out", str(out)]
    )
    assert generate_penn_replay.main() == 0
    replay = json.loads(out.read_text())
    assert isinstance(replay["wishes"], list)
    assert replay["wishes"] == []  # the default cast is the mock-brain vacuity case
    for record in replay["wishes"]:
        assert {
            "actor",
            "turn",
            "location",
            "desired",
            "reason",
            "trigger",
            "goals",
            "scope",
            "raw_command",
            "meta",
        } <= set(record)
