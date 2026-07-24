# Spec: live-mode interpolation buffer — smooth pacing across irregular ticks (#372)

**Date:** 2026-07-15
**Issue:** #372 (Godot viewer: live-mode pacing — interpolate irregular ticks + a thinking indicator)
**Review track:** `godot-ga-main` (viewer-only change)

## Context

#372 has two halves. The **thinking-indicator** half shipped in #555
(`scripts/thinking_indicator.gd` + `thinking_badge.gd` + the `--stall-seconds`
debug hook on `serve_penn.py`). This spec covers the **remaining interpolation
buffer** half: keeping live agents moving believably through irregular,
stall-punctuated tick arrivals.

## Problem

The viewer (`godot/scripts/viewer.gd`) runs on a fixed-rate local clock `_t`
that advances `delta * _speed` every frame (`_speed` is the user's 1×/2× control),
in both baked-replay and live mode. Each frame it derives a step index and a
fraction and eases each agent between two poses:

```gdscript
var fpos := _t / step_seconds        # step_seconds = 0.10
var i := int(fpos)
var frac := fpos - float(i)
agent["node"].position = pa.lerp(pb, frac)   # ease step i -> i+1
```

In baked replay all frames exist up front, so there is always a step `i+1` to
glide toward. In live mode `_frames` grows as ticks arrive (`_apply_live_frame`),
and the clock is clamped to the head: `_t = min(_t, float(last) * step_seconds)`.

Live ticks arrive **irregularly**: walk-only ticks stream fast, but a decision
tick stalls for seconds while the backend waits on an LLM call. The fixed-rate
clock is decoupled from that irregular arrival stream, producing two bad regimes:

- **Fast period** — frames arrive faster than one per `step_seconds`, a backlog
  builds, and the playhead falls further and further behind real time
  (latency grows unbounded).
- **Stall** — no new frame arrives, the clock catches the head, `i >= last`, the
  ease segment collapses (`j == i`, `frac -> 0`), and agents **freeze on their
  exact tile**. This is the moment #555's badge labels — but the badge only
  *explains* the freeze; it does not fix the motion.

## Goal

Live mode feels as smooth as replay mode: positions glide between irregular tick
arrivals, decision stalls decelerate to a graceful stop (labeled "thinking" by
#555), and after a stall the view catches up to near-real-time at a **bounded**
speed rather than teleporting or accumulating latency. Baked replay is byte-identical.

## Design

### 1. `LivePacer` — a pure pacing module

New file `godot/scripts/live_pacer.gd`, following the `ThinkingIndicator` pattern
exactly: `extends RefCounted`, one static function, no scene or sim knowledge, so
it is exercised headless in isolation. `viewer.gd` feeds it the current lead and
multiplies the result into the clock advance.

Define **lead** continuously — buffered ticks ahead of the playhead:

```
lead = float(head) - _t / step_seconds        # head = _frames.size() - 1
```

```gdscript
extends RefCounted
## Pure pacing logic for the live interpolation buffer (issue #372): given how
## many ticks are buffered ahead of the playhead (`lead`), returns the clock-speed
## multiplier that keeps live playback smooth and near-real-time across irregular
## tick arrivals. No scene, no sim knowledge -- viewer.gd feeds it live state and
## applies the result to `_t`. Headless-tested (tests/test_live_pacer.gd).


static func factor(lead: float, target := 2.0, catchup_max := 3.0) -> float:
    # lead <= 0      : starved (playhead at the head, nothing to ease toward) -> hold.
    # 0 < lead < target: buffer draining -> ease to a stop (ramp 0 -> 1x across the interval).
    # lead >= target : healthy or backlog -> 1x, then +1x per extra buffered tick, capped.
    if lead <= 0.0:
        return 0.0
    if lead < target:
        return lead / target
    return minf(1.0 + (lead - target), catchup_max)
```

The curve is continuous and monotonic. Reference points with the chosen
`target = 2.0`, `catchup_max = 3.0`:

| lead | factor | behavior                                  |
|------|--------|-------------------------------------------|
| 0.0  | 0.0    | starved — hold at head (badge: "thinking")|
| 1.0  | 0.5    | buffer draining — decelerating            |
| 1.5  | 0.75   | buffer draining                           |
| 2.0  | 1.0    | steady state — real time                  |
| 3.0  | 2.0    | backlog — catching up                     |
| 4.0  | 3.0    | backlog — catch-up capped                 |
| 5.0  | 3.0    | backlog — still capped                    |

The low side (`lead < target`) gives a graceful **deceleration to a stop** as the
buffer drains, instead of a hard 1×→0× cut. The high side **drains backlog** at
bounded speed. Steady state is self-correcting: at a frame-per-`step_seconds`
arrival rate the controller parks lead at ~`target` (2). Initial buffering needs
no special case — with few frames `lead` is small so playback starts slow, and it
accelerates (capped) as frames accumulate toward the steady lead.

### 2. Integration (`viewer.gd`, `_process`, live branch only)

The single change is the clock-advance line. Everything downstream
(`i`/`frac`, `pa.lerp(pb, frac)`, trails, heatmap, clock label, scrubber pin) is
unchanged — the pacer only modulates *how fast `_t` advances*.

```gdscript
const LivePacer := preload("res://scripts/live_pacer.gd")   # near ThinkingIndicator preload
const LEAD_TARGET := 2.0     # ticks of buffer to hold before real-time (1x)
const CATCHUP_MAX := 3.0     # max multiple of normal rate while draining a backlog
...
if not _paused:
    var pace := 1.0
    if _is_live:
        var lead := float(_frames.size() - 1) - _t / step_seconds
        pace = LivePacer.factor(lead, LEAD_TARGET, CATCHUP_MAX)
    _t += delta * _speed * pace
    _anim_t += delta * _speed * pace          # walk animation tracks playback pace
    _t = min(_t, float(last) * step_seconds)   # existing clamp stays as a safety ceiling
```

Notes:
- `pace` composes multiplicatively with the user's `_speed`, so 1×/2× still works.
- The existing `min(_t, last*step_seconds)` clamp stays as a hard ceiling; with the
  pacer, `factor -> 0` as `lead -> 0` already decelerates `_t` before it reaches the
  head, so the clamp becomes a redundant-but-safe backstop.
- `_anim_t` (walk-cycle animation clock) is paced identically so footstep cadence
  matches the on-screen glide speed during catch-up.
- Baked replay: `_is_live` is false, `pace` stays 1.0 — the advance line is
  arithmetically identical to today, so replay is byte-identical.

### 3. Interaction with the thinking badge (#555)

No change to `ThinkingIndicator.should_show(...)`. Because the pacer now holds
~`LEAD_TARGET` ticks of lead, `i >= last` (`playhead_at_head`) is **false** during
healthy following, so the badge stays off while gliding — an improvement over the
pre-pacer behavior where the playhead routinely kissed the head. During a real
stall, lead drains to 0, the playhead reaches the head, `playhead_at_head` becomes
true, and after `THINKING_STALL_MS` (1500) with no new frame the badge fires
exactly as it does today. The two features reinforce each other.

## Testing

### Unit — `godot/tests/test_live_pacer.gd` (headless `SceneTree`)

Follows `test_thinking_indicator.gd` exactly: `extends SceneTree`, a local
`_check(cond, name)`, run via
`godot --headless --path godot-generative-agents/godot --script res://tests/test_live_pacer.gd`,
prints the sentinel `test_live_pacer: all checks passed`, exit 0 on success.
Add the same invocation line to `run_smoke_test.sh` (beside the
`test_thinking_indicator.gd` line) so CI/the smoke test runs it and greps the sentinel.

Checks over `LivePacer.factor` (default `target=2, max=3`):
- Table: `factor(0) == 0.0`, `factor(1) == 0.5`, `factor(2) == 1.0`,
  `factor(3) == 2.0`, `factor(4) == 3.0`, `factor(5) == 3.0` (capped),
  and a fractional point `factor(1.5) == 0.75`.
- Negative lead holds: `factor(-1) == 0.0`.
- Continuity at the knee: `factor(2)` reached from both branches equals 1.0.
- Monotonic non-decreasing across a swept range of lead values.
- Custom args honored: `factor(10, 4, 2)` respects `target`/`max`
  (e.g. caps at 2.0), distinct from the defaults.

Float comparisons use `is_equal_approx` (or an epsilon in `_check`).

### Manual / integration

`serve_penn.py --stall-seconds N` (the #555 hook) injects 5–10s decision stalls.
With the viewer following live, verify:
- Agents **decelerate to a stop** as the buffer drains into a stall (no abrupt
  freeze), and the thinking badge shows during the stall.
- When the stall ends and a burst of frames lands, agents **glide-catch-up at ≤3×**
  and settle back to 1× — no teleport across campus.
- Baked-replay playback is visually identical (run the bundled replay before/after).

## Scope / non-goals

- **In scope:** viewer-side pacing for live mode only; `LivePacer` module + the
  one `_process` integration + unit test + smoke-test wiring; composes with `_speed`;
  graceful stop and bounded catch-up.
- **Out of scope:** wall-clock/timestamp jitter-buffer machinery (the rejected
  Option B); backend loop-side pacing (#366); any scrubber/seek change (locked live
  already); per-agent thinking attribution (#551). Baked replay stays byte-identical.

## Acceptance criteria

1. Against a live backend with artificial 5–10s decision stalls, agents glide
   instead of teleporting, and after a stall catch up smoothly at bounded speed
   (≤ `CATCHUP_MAX`×), not in one jump.
2. The thinking cue shows during the stall (unchanged from #555) and stays off
   during healthy following.
3. Baked-replay mode is unaffected (byte-identical advance math when `_is_live`
   is false).
4. `test_live_pacer.gd` passes headless and is wired into `run_smoke_test.sh`.

## Files touched

- **New** `godot/scripts/live_pacer.gd` (+ generated `.uid`)
- **New** `godot/tests/test_live_pacer.gd` (+ generated `.uid`)
- **Modify** `godot/scripts/viewer.gd` (preload + two constants + the `_process`
  live-branch clock advance)
- **Modify** `run_smoke_test.sh` (add the `test_live_pacer.gd` invocation + sentinel grep)
