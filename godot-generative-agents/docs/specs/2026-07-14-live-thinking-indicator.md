# Live-Mode "Thinking" Indicator — viewer-inferred stall cue (#372)

**Issue:** #372 · **Branch:** `feat/live-thinking-372` off `godot-ga-main` ·
**Review track:** godot-ga-main (godot-only — viewer scripts + godot tests).
**Related:** #551 (authoritative "deciding" feed record — the shared signal this
cue later switches onto), #525 (web companion's equivalent thinking state),
#366 (backend pacing — the true source of decision stalls).

## Goal

Live mode follows a running backend whose **decision ticks stall for 5–10 s**
while the loop waits on LLM calls. Today the agent eases to the newest pose and
then sits still with **no cue** — indistinguishable from frozen/broken. Add a
**global "thinking…" affordance** during those stalls so the sim reads as
working, not broken. Baked-replay mode stays byte-identical (everything gated on
`_is_live`).

## Scope decision (from brainstorming)

- **Interpolation is already done — do not rebuild it.** Live mode reuses the
  same `_t`-driven render as replay; this spec only adds the stall cue.
- **Viewer-inferred (Option 1), not a backend signal.** The cue is derived
  locally from a stall; the authoritative per-agent "deciding" record is #551,
  which this indicator can later switch onto. Godot-only, no backend change.
- **Global cue, not per-agent.** Stall inference cannot attribute to one agent,
  so a per-agent bubble would mislead. Per-agent bubbles wait for #551.
- **Cue form:** an animated on-view "thinking…" badge **plus** the sidebar
  live-status line flipping to "thinking…".
- **Lead buffer is out of scope** (see §Current state) — the catch-up acceptance
  is already met.

## Current state (verified)

- **Live interpolation + bounded catch-up already work.** `viewer._process`
  (the same path for replay and live) advances `_t += delta * _speed` when not
  paused and clamps `_t = min(_t, float(last) * step_seconds)` where
  `last = _frames.size() - 1` is the live head; it renders by easing between
  `_frames[i]` and `_frames[i+1]` with `frac = _t/step_seconds - i`. So a burst
  of frames after a stall is chased at **bounded speed** (no warp), easing
  frame-to-frame. The issue's feared "teleport one tile per event then freeze"
  is not today's behavior — agents already glide and catch up smoothly. This is
  the same technique the original Generative Agents demo used (fixed-cadence
  playback + client-side tween between tiles); confirmed against
  `joonspk-research/generative_agents` (`reverie.py` writes per-step tile
  movement files; the Phaser frontend tweens between tiles). That reference
  implementation runs a strict **lockstep file handshake** and shows **no**
  waiting indicator — so there is no prior art to copy for the thinking cue.
- **Live ingestion:** change-feed records (`frame` / `status` / `engine`) arrive
  via WebSocket (`viewer._poll_ws`) or HTTP backfill (`_on_events_completed`),
  routed through `_apply_record` → `_apply_live_frame(step, agents)`, which
  appends/sets `_frames[step]`. `_backend_run_state` tracks
  running/paused/finished/stopped/waiting (`_set_backend_run_state`,
  `_on_live_status`). The sidebar status text is set via
  `_panel.set_live_status(...)`.
- **No "deciding" signal exists.** The feed carries `engine`/`llm_call` rows but
  nothing that says "a decision is pending right now" — hence inference here and
  #551 for the real thing.
- **Time source:** `Time.get_ticks_msec()` is available to GDScript for
  wall-clock stall measurement.

## Design

Three units — one pure and headless-tested, one small overlay Control, and the
`viewer.gd` wiring — mirroring the codebase's "test the logic, smoke the scene"
split.

### 1. `godot/scripts/thinking_indicator.gd` (new) — pure decision logic

Scene-free static helper, bytes-of-logic in / bool out, headless-tested:

- `should_show(is_live: bool, run_state: String, playhead_at_head: bool, ms_since_last_frame: int, threshold_ms: int) -> bool` — returns `true` iff
  **all** hold: `is_live`, `run_state == "running"`, `playhead_at_head`
  (the playhead has caught the live head, so there is nothing left to ease
  toward), and `ms_since_last_frame > threshold_ms`. Any other state → `false`
  (not live, paused/finished/stopped/waiting, still easing through buffered
  frames, or a frame arrived recently).
- `ellipsis(now_ms: int) -> String` — animates the label text, cycling
  `"thinking"` → `"thinking."` → `"thinking.."` → `"thinking..."` on a fixed
  period (e.g. one dot every 400 ms) derived from `now_ms`.

### 2. `godot/scripts/thinking_badge.gd` (new) — the on-view cue

A small `Control` (built in code, styled distinctly from the #245 speech
bubbles — a translucent pill near the top-centre of the view):

- `set_active(active: bool)` — show/hide; while active, its `_process` updates
  the label via `ThinkingIndicator.ellipsis(Time.get_ticks_msec())`. Inert when
  hidden. No sim knowledge.

### 3. `viewer.gd` wiring (all under `_is_live`)

- New state: `var _last_frame_ms := 0` and `const THINKING_STALL_MS := 1500`.
- In `_apply_live_frame`, stamp `_last_frame_ms = Time.get_ticks_msec()`
  **only when the head grows** (a genuinely new step is appended — not a
  backfill rewrite of an existing index), so the timer measures "time since the
  newest step arrived".
- In `_process` (live branch, after the existing render computes `i`/`last`):
  ```
  var stalled := ThinkingIndicator.should_show(
      _is_live, _backend_run_state, i >= last,
      Time.get_ticks_msec() - _last_frame_ms, THINKING_STALL_MS)
  ```
  Drive `_thinking_badge.set_active(stalled)`. On the rising edge flip the
  sidebar to `_panel.set_live_status("thinking…")`; when it clears (a frame
  arrived, or run-state left "running"), restore `"following backend"`. The
  stall logic owns the status text only while `run_state == "running"`, so it
  never overwrites a paused/finished/stopped message.
- `_thinking_badge` is instantiated once in `_ready` and added to the UI layer;
  it stays hidden in replay (`_is_live` false → `should_show` false → inactive),
  keeping baked replay byte-identical.

## Verification

- **`godot/tests/test_thinking_indicator.gd`** (headless, `extends SceneTree`,
  the `_check` + `all checks passed` convention, registered in
  `run_smoke_test.sh`): truth table for `should_show` —
  - not live → false
  - live + running + at-head + stale (> threshold) → true
  - live + running + at-head + fresh (< threshold) → false
  - live + running + **not** at-head (still easing) → false
  - live + paused → false; live + finished → false; live + waiting → false
  - and `ellipsis` returns the four expected strings across one period.
- **Smoke** (`run_smoke_test.sh`): all unit tests pass and every scene loads/
  paints with the badge node present (proves `viewer.gd`/`thinking_badge.gd`
  parse and instantiate). The badge overlay and the `_process` stall wiring need
  a running live backend, so they are **not** headless-unit-tested — stated
  boundary.
- **Manual acceptance (user):** run a live backend with artificial 5–10 s
  decision stalls — free, no keys: `serve_penn.py --stall-seconds 5`
  (the mock-brain debug flag that pauses every 10th step; `--brain llm` also
  stalls, for real). Confirm: agents glide (already), the badge + sidebar show
  "thinking…" during the stall, both clear and playback resumes smoothly when
  frames arrive, and baked-replay mode is unaffected.

## Out of scope

- Rebuilding interpolation / adding a lead buffer (catch-up acceptance already
  met by the shared render).
- Per-agent thinking bubbles and the authoritative "deciding" feed record
  (#551); the web companion's equivalent (#525); backend pacing (#366).
- Any change to the sim, backend, `.tmj`, replay path, or the #245 speech
  bubbles.
