"""Unit tests for ``backend.live`` -- the self-stepping loop core (#349/#262).

Everything here is pure stdlib (no fastapi/httpx), so this file runs even
without the ``server`` extra: the loop, log, and controller are exercised
directly, the way ``tests/test_api.py`` then exercises them over HTTP/WS.
"""

import asyncio
import threading

from backend.live import EventLog, LiveRunController, ScriptedStepper, run_loop

# A tick short enough to keep the suite fast, long enough to be a real sleep.
TICK = 0.005


class FakeStepper:
    """A hand-cranked SimStepper that records how it was driven."""

    def __init__(self, finish_after=None):
        self._step = 0
        self.finish_after = finish_after
        self.reset_calls = 0
        self.lock_was_held: bool | None = None  # filled in by tick()
        self.probe_lock: threading.Lock | None = None

    @property
    def step(self):
        return self._step

    def meta(self):
        return {"tile_px": 8, "personas": [{"name": "a", "emoji": "x"}]}

    def tick(self):
        if self.probe_lock is not None:
            self.lock_was_held = self.probe_lock.locked()
        if self.finish_after is not None and self._step >= self.finish_after:
            return None
        frame = {"a": {"x": self._step, "y": 0, "act": "walking", "e": "x"}}
        self._step += 1
        return frame

    def reset(self):
        self._step = 0
        self.reset_calls += 1


# ---------------------------------------------------------------- EventLog


def test_controller_can_start_paused():
    # --start-paused (serve_penn's --brain llm default): the loop boots armed
    # but not ticking, so a paying brain's first call waits for resume().
    ctl = LiveRunController(FakeStepper(), threading.Lock(), start_paused=True)
    assert ctl.paused is True
    ctl.resume()
    assert ctl.paused is False
    # And the default is unchanged: loops auto-run unless asked not to.
    assert LiveRunController(FakeStepper(), threading.Lock()).paused is False


def test_event_log_cursors_are_monotonic_and_1_based():
    log = EventLog()
    assert log.latest_cursor() == 0
    assert log.oldest_cursor() is None
    first = log.append("frame", step=0)
    second = log.append("status", reason="paused")
    assert (first["cursor"], second["cursor"]) == (1, 2)
    assert log.latest_cursor() == 2
    assert log.oldest_cursor() == 1


def test_event_log_since_filters_and_empty_tail():
    log = EventLog()
    for step in range(5):
        log.append("frame", step=step)
    tail = log.since(3)
    assert [r["cursor"] for r in tail] == [4, 5]
    assert log.since(5) == []  # an empty tail is an empty list, promptly
    assert [r["cursor"] for r in log.since(0)] == [1, 2, 3, 4, 5]


def test_event_log_eviction_keeps_cursor_numbering():
    log = EventLog(max_records=3)
    for step in range(6):
        log.append("frame", step=step)
    assert log.latest_cursor() == 6
    assert log.oldest_cursor() == 4  # 1-3 evicted, numbering unchanged
    tail = log.since(0)
    assert [r["cursor"] for r in tail] == [4, 5, 6]
    # The client-side gap test: first returned cursor > since + 1.
    assert tail[0]["cursor"] > 0 + 1


def test_event_log_append_wakes_subscribers():
    async def scenario():
        log = EventLog()
        waiter = log.subscribe()
        waiter.clear()
        log.append("frame", step=0)
        await asyncio.wait_for(waiter.wait(), timeout=1.0)
        log.unsubscribe(waiter)
        return True

    assert asyncio.run(scenario())


# ------------------------------------------------------ LiveRunController


def test_controller_tick_once_holds_lock_and_returns_frame():
    lock = threading.Lock()
    stepper = FakeStepper()
    stepper.probe_lock = lock
    controller = LiveRunController(stepper, lock)
    result = controller.tick_once()
    assert stepper.lock_was_held is True
    assert result["step"] == 0  # the index of the frame this tick produced
    assert result["agents"]["a"]["x"] == 0
    assert result["generation"] == 0
    assert result["events"] == []
    assert controller.tick_once()["step"] == 1


def test_controller_pause_resume_reset_state():
    stepper = FakeStepper()
    controller = LiveRunController(stepper, threading.Lock())
    controller.tick_once()
    controller.pause()
    assert controller.paused
    controller.resume()
    assert not controller.paused
    controller.reset()
    assert stepper.reset_calls == 1
    assert controller.generation == 1
    assert controller.status() == {"running": False, "paused": False, "step": 0}


# ---------------------------------------------------------------- run_loop


async def _drive(controller, log, until, timeout=2.0):
    """Run the loop until ``until(log)`` holds, then cancel it cleanly."""
    task = asyncio.create_task(run_loop(controller, log, TICK))
    try:
        async with asyncio.timeout(timeout):
            while not until(log):
                await asyncio.sleep(TICK)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _kinds(log):
    return [r["kind"] for r in log.since(0)]


def test_run_loop_produces_frames_and_stops_cleanly():
    async def scenario():
        log = EventLog()
        controller = LiveRunController(FakeStepper(), threading.Lock())
        await _drive(controller, log, lambda l: _kinds(l).count("frame") >= 2)
        records = log.since(0)
        assert records[0]["kind"] == "status" and records[0]["reason"] == "started"
        assert records[-1]["kind"] == "status" and records[-1]["reason"] == "stopped"
        frames = [r for r in records if r["kind"] == "frame"]
        assert [f["step"] for f in frames[:2]] == [0, 1]
        assert frames[0]["agents"]["a"] == {"x": 0, "y": 0, "act": "walking", "e": "x"}
        assert controller.running is False
        return True

    assert asyncio.run(scenario())


def test_run_loop_paused_skips_ticks_but_stays_alive():
    async def scenario():
        log = EventLog()
        controller = LiveRunController(FakeStepper(), threading.Lock())
        controller.pause()
        task = asyncio.create_task(run_loop(controller, log, TICK))
        await asyncio.sleep(TICK * 10)
        assert _kinds(log).count("frame") == 0  # paused from the start
        assert controller.running is True  # ...but the task is alive
        controller.resume()
        async with asyncio.timeout(2.0):
            while _kinds(log).count("frame") < 1:
                await asyncio.sleep(TICK)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    assert asyncio.run(scenario())


def test_run_loop_drops_stale_generation_frame():
    async def scenario():
        log = EventLog()
        stepper = FakeStepper()
        controller = LiveRunController(stepper, threading.Lock())
        # Simulate a reset racing an in-flight tick: bump the generation the
        # moment the stepper is asked to tick, so the loop sees a stale result.
        original_tick = stepper.tick

        def racing_tick():
            controller.generation += 1
            return original_tick()

        stepper.tick = racing_tick
        await _drive(controller, log, lambda l: l.latest_cursor() >= 1)
        await asyncio.sleep(TICK * 5)
        assert _kinds(log).count("frame") == 0  # every tick raced; none published
        return True

    assert asyncio.run(scenario())


def test_run_loop_finished_stepper_auto_pauses():
    async def scenario():
        log = EventLog()
        controller = LiveRunController(FakeStepper(finish_after=2), threading.Lock())
        await _drive(
            controller,
            log,
            lambda l: any(
                r["kind"] == "status" and r["reason"] == "finished" for r in l.since(0)
            ),
        )
        assert _kinds(log).count("frame") == 2
        assert controller.paused is True
        return True

    assert asyncio.run(scenario())


def test_run_loop_appends_engine_events_when_stepper_drains():
    async def scenario():
        log = EventLog()
        stepper = ScriptedStepper(
            [{"a": {"x": 0, "y": 0, "act": "idle", "e": "x"}}],
            on_tick=lambda step: [{"channel": "narration", "text": f"tick {step}"}],
        )
        controller = LiveRunController(stepper, threading.Lock())
        await _drive(controller, log, lambda l: "engine" in _kinds(l))
        engine = [r for r in log.since(0) if r["kind"] == "engine"]
        assert engine[0]["event"]["channel"] == "narration"
        assert engine[0]["step"] == 0
        return True

    assert asyncio.run(scenario())


# ---------------------------------------------------------- ScriptedStepper


def test_scripted_stepper_cycles_frames_and_resets():
    frames = [{"a": {"x": 1}}, {"a": {"x": 2}}]
    stepper = ScriptedStepper(frames, meta={"tile_px": 16})
    assert stepper.meta() == {"tile_px": 16}
    first, second, third = (stepper.tick() for _ in range(3))
    assert first and second and third
    assert (first["a"]["x"], second["a"]["x"], third["a"]["x"]) == (1, 2, 1)  # cycles
    assert stepper.step == 3
    stepper.reset()
    assert stepper.step == 0
    after = stepper.tick()
    assert after is not None and after["a"]["x"] == 1


def test_scripted_stepper_callable_none_means_finished():
    stepper = ScriptedStepper(lambda step: {"a": {"x": step}} if step < 2 else None)
    assert stepper.tick() == {"a": {"x": 0}}
    assert stepper.tick() == {"a": {"x": 1}}
    assert stepper.tick() is None
    assert stepper.step == 2  # the finished tick doesn't count
