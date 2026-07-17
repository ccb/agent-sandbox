"""Offline coverage for the live-seam edges of ``backend.live`` + ``backend.api``
(issue #392).

The live-serving seam landed in #379/#380 and is exercised broadly by the
repo-root ``tests/test_api.py`` (the HTTP/WS surface) and ``tests/test_live_loop.py``
(the loop core). This file pins the branches those two leave untested -- all
drivable offline with the scripted stepper, no keys and no spend:

* the three WebSocket close codes -- 1008 (bad token), 1009 (oversized inbound
  frame), 1011 (a reader that fell behind the log's retention);
* ``GET /events`` surfacing eviction (``oldest_cursor`` + the gap signal) over
  HTTP, not just at the ``EventLog`` layer;
* ``POST /reset`` landing *mid-tick* -- both that the feed stays coherent
  end-to-end, and (deterministically, through the real ``run_loop``) that a tick
  whose generation a reset has bumped is dropped rather than published;
* resuming a run that has already finished -- it re-pauses with no bogus frame.

House rules, same as ``tests/test_api.py``'s live block: a fake ``SimStepper`` is
injected and the loop runs for real inside ``with TestClient(app):`` (the loop
rides the app lifespan, so a bare ``TestClient`` never starts it). Every wait
polls with a deadline; the one place ordering matters -- the reset-vs-tick race
-- drives the generation counter directly instead of sleeping.

Needs the ``server`` extra (fastapi + httpx + websockets); skipped cleanly if
absent, exactly like ``tests/test_api.py``.
"""

import asyncio
import contextlib
import threading
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from backend.api import create_app  # noqa: E402
from backend.live import (  # noqa: E402
    EventLog,
    LiveRunController,
    ScriptedStepper,
    run_loop,
)
from text_adventure_games import games, things  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402

# The world the API serves when a test only cares about the loop, not the game.
# A live SimStepper is what advances things; this game just answers /world_state.
_META = {
    "tile_px": 8,
    "width": 4,
    "height": 4,
    "personas": [{"name": "a", "emoji": "@"}],
}


def _tiny():
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A wood.")
    field.add_connection("north", forest)
    player = things.Character("player", "you", "I explore.")
    return games.Game(field, player, characters=[])


def _walker(on_tick=None):
    """A never-finishing ``SimStepper``: agent "a" walks east a tile per tick."""
    return ScriptedStepper(
        lambda step: {"a": {"x": step, "y": 0, "act": "walking @ demo", "e": "@"}},
        meta=_META,
        on_tick=on_tick,
    )


def _finishing(after):
    """A ``SimStepper`` that runs *after* ticks, then reports finished (``None``)."""
    return ScriptedStepper(
        lambda step: (
            {"a": {"x": step, "y": 0, "act": "walking @ demo", "e": "@"}}
            if step < after
            else None
        ),
        meta=_META,
    )


def _live_client(stepper=None, **kwargs):
    """A ``TestClient`` over a live app. Use as ``with _live_client() as c:``."""
    kwargs.setdefault("tick_seconds", 0.01)
    return TestClient(create_app(_tiny(), stepper=stepper or _walker(), **kwargs))


def _wait_for_events(client, predicate, timeout=5.0):
    """Poll ``GET /events?since=0`` until *predicate*(events) holds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = client.get("/events?since=0").json()["events"]
        if predicate(events):
            return events
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the change feed")


def _frame_count(events):
    return sum(e["kind"] == "frame" for e in events)


def _finished_count(events):
    return sum(e["kind"] == "status" and e.get("reason") == "finished" for e in events)


# --- WebSocket close codes (#262) ------------------------------------------


def test_ws_bad_token_closes_1008():
    # tests/test_api.py's test_ws_auth_header_or_query_token asserts the socket is
    # refused but not the code. #262 documents 1008 (policy violation) for a bad
    # token -- a browser client keys its re-auth on that code -- so pin it, for a
    # missing token and a wrong one alike.
    with _live_client(auth_token="s3cret") as c:
        for query in ("/ws", "/ws?token=wrong"):
            with pytest.raises(WebSocketDisconnect) as caught:
                with c.websocket_connect(query):
                    pass  # refused before the handshake completes
            assert caught.value.code == 1008


def test_ws_oversized_inbound_closes_1009():
    # The feed is server-push; the only inbound policing is the body-size cap,
    # enforced by hand in _drain_inbound because _BodySizeLimitMiddleware never
    # sees WS scopes. A client->server frame past the cap closes with 1009.
    with _live_client(max_body_bytes=1024) as c:
        with c.websocket_connect("/ws?since=0") as ws:
            assert ws.receive_json()["reason"] == "started"
            ws.send_text("x" * 2048)  # past the 1 KiB cap
            with pytest.raises(WebSocketDisconnect) as caught:
                for _ in range(50):  # drain any frames already queued, then the close
                    ws.receive_json()
            assert caught.value.code == 1009


def test_ws_behind_retention_closes_1011():
    # A reader slower than the log's retention is force-resynced: closed with 1011
    # and a re-sync reason. tests/test_live_loop.py pins the EventLog eviction;
    # this pins the socket close, driven deterministically. run_loop appends a
    # frame plus every drained engine record in one stretch WITHOUT awaiting, so a
    # single tick that drains more records than the log retains evicts the reader's
    # next cursor atomically -- no sleep can race in and read them first.
    burst = _walker(
        on_tick=lambda _step: [
            {"channel": "narration", "text": f"e{i}"} for i in range(20)
        ]
    )
    with _live_client(
        stepper=burst, tick_seconds=0.05, max_log_records=3, start_paused=True
    ) as c:
        with c.websocket_connect("/ws?since=0") as ws:
            assert ws.receive_json()["reason"] == "started"  # caught up, now waiting
            c.post("/resume")  # release the one burst tick
            with pytest.raises(WebSocketDisconnect) as caught:
                for _ in range(60):
                    ws.receive_json()
            assert caught.value.code == 1011
            assert "evict" in (caught.value.reason or "")


# --- GET /events under eviction (#262) -------------------------------------


def test_events_http_surfaces_eviction_and_the_gap():
    # tests/test_live_loop.py pins EventLog eviction; this pins /events surfacing
    # it over HTTP, so a poller (not only a socket) can detect a missed record:
    # once old records fall off, oldest_cursor climbs past 1, and the first record
    # returned jumps past since+1 -- the same gap signal WS closes 1011 on.
    with _live_client(max_log_records=3) as c:
        # Let the loop lap the tiny log so early records are evicted.
        _wait_for_events(c, lambda evs: evs and evs[-1]["cursor"] >= 8)
        data = c.get("/events?since=0").json()
        assert len(data["events"]) == 3  # only max_log_records retained
        assert data["oldest_cursor"] == data["events"][0]["cursor"] > 1  # head gone
        assert data["events"][0]["cursor"] > 0 + 1  # a gap vs since=0
        assert data["latest_cursor"] == data["events"][-1]["cursor"]
        # A poller that last saw an evicted cursor sees the gap the same way:
        # the first record returned is past since+1.
        stale = data["oldest_cursor"] - 2  # guaranteed below the retained window
        gapped = c.get(f"/events?since={stale}").json()
        assert gapped["events"][0]["cursor"] > stale + 1


# --- POST /reset mid-tick (#262/#349) --------------------------------------


def test_reset_while_a_tick_is_in_flight_stays_coherent():
    # tests/test_api.py resets only after /pause has quiesced the loop. This
    # resets MID-TICK: a tick is genuinely in flight (holding the app lock) when
    # /reset lands, so the reset's stepper.reset() + generation bump interleave
    # with a live tick. The feed must stay coherent -- the stepper rebuilt exactly
    # once, one 'reset' status, cursors still strictly increasing (they never
    # rewind) -- and the loop must keep stepping from 0 afterward, not wedge.
    entered, release = threading.Event(), threading.Event()
    reset_calls = []

    def frames(step):
        if step == 3:  # gate the 4th tick open, holding the lock
            entered.set()
            release.wait(timeout=5)
        return {"a": {"x": step, "y": 0, "act": "walking @ demo", "e": "@"}}

    stepper = ScriptedStepper(
        frames, meta=_META, on_reset=lambda: reset_calls.append(1)
    )
    with TestClient(create_app(_tiny(), stepper=stepper, tick_seconds=0.01)) as c:
        assert entered.wait(timeout=5)  # tick #3 is in flight, holding the lock
        holder = {}
        resetter = threading.Thread(
            target=lambda: holder.update(c.post("/reset").json())
        )
        resetter.start()
        time.sleep(0.05)  # let /reset queue on the app lock the tick holds
        release.set()  # tick #3 finishes; the lock frees; the reset runs
        resetter.join(timeout=5)

        assert holder["step"] == 0  # the reset rebuilt to t0
        assert reset_calls == [1]  # the stepper was rebuilt exactly once
        reset_cursor = holder["cursor"]
        # The loop keeps running (reset doesn't pause): a fresh step-0 frame lands.
        _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "frame" and e["cursor"] > reset_cursor and e["step"] == 0
                for e in evs
            ),
        )
        c.post("/pause")  # freeze the feed for the coherence assertions
        final = c.get("/events?since=0").json()["events"]
        cursors = [e["cursor"] for e in final]
        assert cursors == sorted(cursors)  # monotonic: cursors never rewind
        assert len(cursors) == len(set(cursors))  # and never duplicate
        resets = [e for e in final if e.get("reason") == "reset"]
        assert len(resets) == 1


def test_run_loop_drops_the_in_flight_tick_after_a_reset_bumps_generation():
    # The reset-vs-tick guard (#262), end-to-end through the same run_loop the app
    # runs -- not a monkeypatched tick. A tick is gated open mid-flight; the
    # generation is then bumped exactly as LiveRunController.reset() bumps it (from
    # another thread, lock-free -- the way the docstring says it's read); then the
    # tick is released. run_loop must compare the tick's now-stale generation
    # against the new one and DROP its frame. Deterministic: the bump lands before
    # the tick returns, so the comparison can't fall the other way -- no sleep.
    async def scenario():
        entered, release = threading.Event(), threading.Event()

        def frames(step):
            if step == 0:  # gate the first tick, then finish after it
                entered.set()
                release.wait(timeout=5)
                return {"a": {"x": 0}}
            return None

        stepper = ScriptedStepper(frames, meta=_META)
        controller = LiveRunController(stepper, threading.Lock())
        log = EventLog()
        task = asyncio.create_task(run_loop(controller, log, 0.001))
        loop = asyncio.get_running_loop()
        # Wait OFF the event loop for the tick to be in flight (waiting on the
        # event loop's thread would wedge run_loop, which needs it to tick).
        await loop.run_in_executor(None, lambda: entered.wait(timeout=5))
        controller.generation += 1  # a reset's effect, while the tick is in flight
        release.set()  # let the now-stale tick complete
        # The dropped tick advances the stepper; the next tick reports finished.
        async with asyncio.timeout(5):
            while not any(
                r["kind"] == "status" and r.get("reason") == "finished"
                for r in log.since(0)
            ):
                await asyncio.sleep(0.001)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return [r["kind"] for r in log.since(0)], stepper.step

    kinds, step = asyncio.run(scenario())
    assert step == 1  # the gated tick DID run and produce a frame...
    assert kinds.count("frame") == 0  # ...which was dropped for the stale generation
    assert kinds[0] == "status"  # started ...
    assert kinds[-1] == "status"  # ... stopped


# --- resume after finished (#349) ------------------------------------------


def test_resume_after_finished_repauses_with_no_bogus_frame():
    # /resume's contract: resuming a FINISHED run just re-checks the stepper -- it
    # pauses again, and (the part that matters) publishes no stale frame. After the
    # day finishes, /resume flips paused off, but the next tick finds the stepper
    # drained and re-pauses with a second 'finished' and the frame count unchanged.
    with _live_client(stepper=_finishing(after=2)) as c:
        _wait_for_events(c, lambda evs: _finished_count(evs) >= 1)
        before = c.get("/events?since=0").json()["events"]
        assert _frame_count(before) == 2  # exactly the two ticks the day had

        assert c.post("/resume").json()["paused"] is False  # resume flips it off...
        # ...but the very next tick finds the stepper finished and re-pauses.
        after = _wait_for_events(c, lambda evs: _finished_count(evs) >= 2)
        assert _frame_count(after) == 2  # no bogus frame slipped in on resume
        assert c.get("/live").json()["paused"] is True


# --- game_event rows on the engine feed (#467) ------------------------------


def test_game_event_rows_ride_the_engine_feed():
    """#467: a stepper's drained game_event rows come out of GET /events inside
    the ``engine`` envelope, exactly like llm_call rows (#398). serve_penn's
    PennStepper produces these rows for real (test_event_records.py); here a
    scripted stepper pins the transport."""
    record = {
        "turn": 1,
        "actor": "Sofia Ramirez",
        "action": "sickness",
        "summary": "Sofia Ramirez got sick drinking cup of murky water",
        "payload": {"item": "cup of murky water", "location": "Houston Hall"},
        "kind": "game_event",
    }
    stepper = _walker(on_tick=lambda step: [dict(record)] if step == 0 else [])
    with _live_client(stepper=stepper) as c:
        events = _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "engine" and e["event"].get("kind") == "game_event"
                for e in evs
            ),
        )
    rows = [
        e["event"]
        for e in events
        if e["kind"] == "engine" and e["event"].get("kind") == "game_event"
    ]
    assert rows == [record]


# --- run registry (#306) -----------------------------------------------------


def _stepper_with_store(tmp_path):
    """A fake live stepper carrying a real store with one finished and one
    'live' run. Ids chosen so the same-second id-DESC tiebreak lists the
    live run first (list_runs orders by created DESC, id DESC)."""
    from backend.run_store import RunStore

    store = RunStore(tmp_path / "runs")
    manifest = {"schema_version": 1, "personas": [{"name": "a"}], "llm": None}
    store.create_run(manifest, run_id="run-1-old")
    store.append_frame("run-1-old", 0, {"a": {"x": 0, "y": 0, "act": "walk", "e": "@"}})
    store.update_run("run-1-old", status="finished", steps=1)
    store.create_run(manifest, run_id="run-2-live")
    stepper = _walker()
    stepper.run_store = store
    stepper.run_id = "run-2-live"
    return stepper, store


def test_run_registry_lists_gets_exports_and_deletes(tmp_path):
    stepper, store = _stepper_with_store(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        listing = client.get("/runs").json()
        assert listing["available"] is True
        assert listing["current"] == "run-2-live"
        assert [r["id"] for r in listing["runs"]] == ["run-2-live", "run-1-old"]
        assert all("manifest" not in r for r in listing["runs"])
        row = client.get("/runs/run-1-old").json()
        assert row["manifest"]["personas"] == [{"name": "a"}]
        assert row["status"] == "finished"
        assert row["current"] is False
        from backend.penn.export_replay import build_replay

        assert client.get("/runs/run-1-old/replay").json() == build_replay(
            store, "run-1-old"
        )
        assert client.get("/runs/missing").status_code == 404
        assert client.get("/runs/missing/replay").status_code == 404
        assert client.delete("/runs/run-2-live").status_code == 409  # live run
        assert client.delete("/runs/run-1-old").json() == {
            "ok": True,
            "deleted": "run-1-old",
        }
        assert client.get("/runs/run-1-old").status_code == 404


def test_run_registry_without_a_store_is_available_false():
    with _live_client(_walker(), start_paused=True) as client:
        assert client.get("/runs").json() == {
            "available": False,
            "current": None,
            "runs": [],
        }
        assert client.get("/runs/any").status_code == 404
        assert client.get("/runs/any/replay").status_code == 404
        assert client.delete("/runs/any").status_code == 404
        assert client.post("/runs/any/resume").status_code == 404


def _resumable_stepper(tmp_path):
    """_stepper_with_store plus the #543 capability: a resume_run spy that
    adopts the id the way PennStepper's does (attribute assignment is the
    blessed way to give a fake stepper optional capabilities)."""
    stepper, store = _stepper_with_store(tmp_path)
    calls = []

    def resume_run(run_id):
        calls.append(run_id)
        if run_id == "run-hand-deleted":
            raise KeyError(f"unknown run id: {run_id}")
        if run_id == "run-strangers":
            raise ValueError("resume needs the same world YAML")
        stepper.run_id = run_id

    stepper.resume_run = resume_run
    return stepper, store, calls


def test_resume_endpoint_adopts_a_run(tmp_path):
    stepper, store, calls = _resumable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        body = client.post("/runs/run-1-old/resume").json()
        assert body["run_id"] == "run-1-old"
        assert body["paused"] is True  # adoption never touches the play button
        assert body["cursor"] >= 1
        assert calls == ["run-1-old"]
        # Run-scoping by adoption: the registry's "current" marker moved.
        assert client.get("/runs").json()["current"] == "run-1-old"
        # Followers got the documented rebuild signal, stamped with the run.
        events = client.get("/events?since=0").json()["events"]
        newest = [e for e in events if e["kind"] == "status"][-1]
        assert newest["reason"] == "reset"
        assert newest["run_id"] == "run-1-old"


def test_resume_endpoint_conflicts_and_errors(tmp_path):
    stepper, store, calls = _resumable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        # The live run 409s -- and never reaches the stepper.
        assert client.post("/runs/run-2-live/resume").status_code == 409
        assert calls == []
        # The stepper's own guards map onto the registry's statuses:
        # unknown id (KeyError) -> 404, refused resume (ValueError) -> 409.
        assert client.post("/runs/run-hand-deleted/resume").status_code == 404
        assert client.post("/runs/run-strangers/resume").status_code == 409


def test_resume_endpoint_without_capability_is_501(tmp_path):
    # A store alone is not enough: a stepper that cannot rebuild-from-a-run
    # (only PennStepper can today) answers 501, not a half-adopted 200.
    stepper, _store = _stepper_with_store(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs/run-1-old/resume").status_code == 501


# --- POST /runs create + adopt (#568) --------------------------------------


def _creatable_stepper(tmp_path):
    """_stepper_with_store plus the #568 capability: a create_run spy that
    opens + adopts a NEW run id the way PennStepper.create_run does (attribute
    assignment is the blessed way to give a fake stepper optional capabilities)."""
    stepper, store = _stepper_with_store(tmp_path)
    calls = []

    def create_run(world, *, steps=None):
        calls.append((world, steps))
        if world != "penn":
            raise KeyError(f"unknown world: {world}")
        manifest = {"schema_version": 1, "personas": [{"name": "a"}], "llm": None}
        run_id = store.create_run(manifest)  # store picks a fresh id
        stepper.run_id = run_id
        return run_id

    stepper.create_run = create_run
    return stepper, store, calls


def test_create_run_builds_and_adopts_a_new_run(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        body = client.post("/runs", json={"world": "penn", "steps": 50}).json()
        assert calls == [("penn", 50)]
        new_id = body["run_id"]
        assert new_id not in ("run-1-old", "run-2-live")  # a fresh id
        assert body["paused"] is True  # create never touches the play button
        assert body["cursor"] >= 1
        # Adoption moved the registry's "current" marker to the new run.
        assert client.get("/runs").json()["current"] == new_id
        # Followers got the documented rebuild signal, stamped with the run.
        events = client.get("/events?since=0").json()["events"]
        newest = [e for e in events if e["kind"] == "status"][-1]
        assert newest["reason"] == "reset"
        assert newest["run_id"] == new_id


def test_create_run_unknown_world_is_404(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={"world": "atlantis"}).status_code == 404


def test_create_run_invalid_body_is_422(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={}).status_code == 422  # world required
        assert (
            client.post("/runs", json={"world": "penn", "steps": 0}).status_code == 422
        )
        assert calls == []  # validation fails before the stepper is touched


def test_create_run_without_a_store_is_404(tmp_path):
    with _live_client(_walker(), start_paused=True) as client:
        assert client.post("/runs", json={"world": "penn"}).status_code == 404


def test_create_run_without_capability_is_501(tmp_path):
    # A store alone isn't enough: only PennStepper can build a world today.
    stepper, _store = _stepper_with_store(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={"world": "penn"}).status_code == 501


# --- GET /usage per-run view (#526) -----------------------------------------


def test_usage_merges_the_stepper_run_view():
    # A stepper offering run_usage() gets its per-run fields merged beside
    # the lifetime summary; the lifetime fields themselves are untouched.
    stepper = _walker()
    stepper.ledger = UsageLedger()
    stepper.run_usage = lambda: {
        "run_calls": 3,
        "run_cost_usd": 0.02,
        "run_by_actor": {"a": 0.02},
    }
    with _live_client(stepper, start_paused=True) as client:
        body = client.get("/usage").json()
    assert body["available"] is True
    assert body["calls"] == 0  # lifetime summary unchanged
    assert (body["run_calls"], body["run_cost_usd"]) == (3, 0.02)
    assert body["run_by_actor"] == {"a": 0.02}  # run-scoped per-agent (#569.2)


def test_usage_without_run_view_keeps_todays_shape():
    # A stepper without run_usage (the generic case) serves the pre-#526
    # response exactly -- no run_* keys appear.
    stepper = _walker()
    stepper.ledger = UsageLedger()
    with _live_client(stepper, start_paused=True) as client:
        body = client.get("/usage").json()
    assert body["available"] is True
    assert "run_calls" not in body and "run_cost_usd" not in body
