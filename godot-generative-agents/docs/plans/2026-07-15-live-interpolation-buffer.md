# Live-Mode Interpolation Buffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Smooth live-mode playback across irregular tick arrivals — hold a small buffer lead, decelerate to a graceful stop into a stall, and drain a post-stall backlog at a bounded catch-up speed instead of teleporting.

**Architecture:** A pure `LivePacer` GDScript module (`extends RefCounted`, one static `factor(lead)` function) computes a clock-speed multiplier from how many ticks are buffered ahead of the playhead. `viewer.gd`'s `_process` multiplies that factor into its existing fixed-rate `_t` clock advance, live-mode only. All existing motion code (per-step `lerp`, trails, heatmap, clock) is unchanged; baked replay is byte-identical.

**Tech Stack:** Godot 4.6 / GDScript. Tests are headless `SceneTree` scripts (the project convention — not GUT), run via `godot --headless --path … --script res://tests/<file>.gd` and gated in `run_smoke_test.sh` by a printed success sentinel.

## Global Constraints

- **Viewer-only, `godot-ga-main` track.** Touches only `godot-generative-agents/`.
- **Baked replay byte-identical.** All new behavior gated on `_is_live`; when false the clock-advance math must be arithmetically identical to today.
- **Module pattern:** new logic modules are `extends RefCounted` with static methods, no scene/sim knowledge, mirroring `scripts/thinking_indicator.gd`.
- **Test pattern:** headless `SceneTree` script named `tests/test_<module>.gd`; a local `_check(cond, name)`; on success print exactly `test_<module>: all checks passed`; end with `quit(1 if _failures > 0 else 0)`. Wire the invocation into `run_smoke_test.sh` beside the other unit tests (before the final `exec … smoke_test.tscn` line).
- **Commit trailer (every commit):**
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`/`git add .`** — stage only the exact files listed in the step, including the Godot-generated `.uid` sidecars for new scripts.
- **Tuning constants:** `LEAD_TARGET = 2.0` ticks, `CATCHUP_MAX = 3.0` ×.
- The commands below assume the repo root is the current directory. `$GODOT` is the Godot 4.6 binary (as resolved by `run_smoke_test.sh` / `run.sh`); substitute your path if running a single test by hand.

---

### Task 1: `LivePacer` module + headless unit test + smoke wiring

**Files:**
- Create: `godot-generative-agents/godot/scripts/live_pacer.gd` (+ generated `godot-generative-agents/godot/scripts/live_pacer.gd.uid`)
- Create: `godot-generative-agents/godot/tests/test_live_pacer.gd` (+ generated `godot-generative-agents/godot/tests/test_live_pacer.gd.uid`)
- Modify: `godot-generative-agents/run_smoke_test.sh` (add one invocation line after the `test_thinking_indicator.gd` line, line ~50)

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `LivePacer.factor(lead: float, target := 2.0, catchup_max := 3.0) -> float` — the clock-speed multiplier. `lead` is buffered ticks ahead of the playhead (may be negative). Returns `0.0` when `lead <= 0`; ramps `lead/target` on `(0, target)`; returns `minf(1.0 + (lead - target), catchup_max)` for `lead >= target`. Continuous and monotonic non-decreasing. Task 2 calls this from `viewer.gd`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/godot/tests/test_live_pacer.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/live_pacer.gd (issue #372). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_live_pacer.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const LivePacer := preload("res://scripts/live_pacer.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _approx(a: float, b: float) -> bool:
	return absf(a - b) < 0.0001


func _initialize() -> void:
	# --- factor() curve, defaults target=2.0 catchup_max=3.0 ---
	_check(_approx(LivePacer.factor(0.0), 0.0), "lead 0 -> hold (0x)")
	_check(_approx(LivePacer.factor(1.0), 0.5), "lead 1 -> 0.5x (draining)")
	_check(_approx(LivePacer.factor(1.5), 0.75), "lead 1.5 -> 0.75x")
	_check(_approx(LivePacer.factor(2.0), 1.0), "lead 2 (target) -> 1x")
	_check(_approx(LivePacer.factor(3.0), 2.0), "lead 3 -> 2x (catch-up)")
	_check(_approx(LivePacer.factor(4.0), 3.0), "lead 4 -> 3x (cap reached)")
	_check(_approx(LivePacer.factor(5.0), 3.0), "lead 5 -> 3x (capped)")

	# --- negative lead holds ---
	_check(_approx(LivePacer.factor(-1.0), 0.0), "negative lead -> hold (0x)")

	# --- continuity at the knee: both branches yield 1.0 at lead == target ---
	_check(_approx(LivePacer.factor(2.0), 1.0), "knee is continuous at 1x")

	# --- monotonic non-decreasing across a sweep ---
	var prev := -1.0
	var mono := true
	for i in range(0, 61):  # lead 0.0 .. 6.0 step 0.1
		var f := LivePacer.factor(float(i) * 0.1)
		if f < prev - 0.0001:
			mono = false
		prev = f
	_check(mono, "factor is monotonic non-decreasing over lead 0..6")

	# --- custom args honored (target=4, max=2), distinct from defaults ---
	_check(_approx(LivePacer.factor(10.0, 4.0, 2.0), 2.0), "custom cap: factor(10,4,2) == 2.0")
	_check(_approx(LivePacer.factor(2.0, 4.0, 2.0), 0.5), "custom target: factor(2,4,2) == 0.5")

	if _failures == 0:
		print("test_live_pacer: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
$GODOT --headless --path godot-generative-agents/godot --script res://tests/test_live_pacer.gd 2>&1 | tail -20
```
Expected: FAIL — the `preload("res://scripts/live_pacer.gd")` cannot resolve (the module does not exist yet), so Godot reports a parse/load error and the sentinel line is **not** printed.

- [ ] **Step 3: Write the minimal implementation**

Create `godot-generative-agents/godot/scripts/live_pacer.gd`:

```gdscript
extends RefCounted
## Pure pacing logic for the live interpolation buffer (issue #372): given how
## many ticks are buffered ahead of the playhead (`lead`), return the clock-speed
## multiplier that keeps live playback smooth and near-real-time across irregular
## tick arrivals. No scene, no sim knowledge -- viewer.gd feeds it live state and
## applies the result to its `_t` clock. Headless-tested (tests/test_live_pacer.gd).


static func factor(lead: float, target := 2.0, catchup_max := 3.0) -> float:
	# lead <= 0       : starved (playhead at the head, nothing to ease toward) -> hold.
	# 0 < lead < target: buffer draining -> ease to a stop (ramp 0 -> 1x across the interval).
	# lead >= target  : healthy or backlog -> 1x, then +1x per extra buffered tick, capped.
	if lead <= 0.0:
		return 0.0
	if lead < target:
		return lead / target
	return minf(1.0 + (lead - target), catchup_max)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
$GODOT --headless --path godot-generative-agents/godot --script res://tests/test_live_pacer.gd 2>&1 | tail -20
```
Expected: PASS — prints `  ok: …` per check and the sentinel `test_live_pacer: all checks passed`; process exits 0.

- [ ] **Step 5: Wire the test into the smoke script**

In `godot-generative-agents/run_smoke_test.sh`, immediately after the existing `test_thinking_indicator.gd` block (line ~50) and before the `# exec so this script's exit code …` comment, add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_live_pacer.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Run the full smoke test to confirm the wiring**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh; echo "exit=$?"
```
Expected: the `test_live_pacer` sentinel appears among the unit-test output and the script finishes `exit=0` (scenes load + all unit tests green). If Godot import cache is cold on a fresh checkout, `run.sh`/the script's own `--import` step handles it; re-run once if the first pass reports an import build.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/live_pacer.gd \
        godot-generative-agents/godot/scripts/live_pacer.gd.uid \
        godot-generative-agents/godot/tests/test_live_pacer.gd \
        godot-generative-agents/godot/tests/test_live_pacer.gd.uid \
        godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): LivePacer.factor — bounded catch-up pacing curve (#372)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Note: the `.uid` files are generated by Godot the first time the scripts are imported (Step 4/6). If they are not yet present when you stage, run the smoke test once more (it imports), then add them. Do not hand-author `.uid` contents.

---

### Task 2: Wire the pacer into `viewer.gd`'s live clock

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`
  - preload block (line ~126, beside `ThinkingIndicator`)
  - a constants line (near `THINKING_STALL_MS`, line ~226)
  - the `_process` clock-advance block (lines ~1701-1706)

**Interfaces:**
- Consumes: `LivePacer.factor(lead, target, catchup_max) -> float` from Task 1.
- Produces: no new public symbol; changes live-mode playback pacing in place.

- [ ] **Step 1: Add the `LivePacer` preload**

In `viewer.gd`, after the existing line (line ~126):
```gdscript
const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")
```
add:
```gdscript
const LivePacer := preload("res://scripts/live_pacer.gd")
```

- [ ] **Step 2: Add the tuning constants**

In `viewer.gd`, immediately after the existing line (line ~226):
```gdscript
const THINKING_STALL_MS := 1500
```
add:
```gdscript
# Live interpolation buffer (issue #372): hold ~LEAD_TARGET ticks of lead so
# motion stays smooth across irregular arrivals; drain a post-stall backlog at
# up to CATCHUP_MAX x the normal rate rather than teleporting. See LivePacer.
const LEAD_TARGET := 2.0
const CATCHUP_MAX := 3.0
```

- [ ] **Step 3: Modify the `_process` clock advance**

In `viewer.gd` `_process`, replace this exact block (lines ~1701-1706):
```gdscript
	if not _paused:
		_t += delta * _speed
		_anim_t += delta * _speed
		# Hold the playhead at the final step: the replay has no more frames, so the
		# clock must stop here rather than tick on past the end of the simulation.
		_t = min(_t, float(last) * step_seconds)
```
with:
```gdscript
	if not _paused:
		# Live mode paces the clock by how many ticks are buffered ahead (issue
		# #372): hold a small lead, decelerate to a stop into a stall, and drain a
		# backlog at a bounded catch-up. Baked replay keeps pace == 1.0, so the
		# advance below is arithmetically identical to before -- byte-identical playback.
		var pace := 1.0
		if _is_live:
			var lead := float(last) - _t / step_seconds
			pace = LivePacer.factor(lead, LEAD_TARGET, CATCHUP_MAX)
		_t += delta * _speed * pace
		_anim_t += delta * _speed * pace
		# Hold the playhead at the final step: the replay has no more frames, so the
		# clock must stop here rather than tick on past the end of the simulation.
		_t = min(_t, float(last) * step_seconds)
```
(`last` is already defined just above as `_frames.size() - 1`.)

- [ ] **Step 4: Run the headless smoke test — scenes still load, replay unaffected**

Run:
```bash
./godot-generative-agents/run_smoke_test.sh; echo "exit=$?"
```
Expected: `exit=0` — every scene (including the baked-replay viewer) loads and paints, and all unit tests (incl. `test_live_pacer`) stay green. Because `_is_live` is false in the smoke scenes, `pace` stays `1.0` and replay playback is unchanged.

- [ ] **Step 5: Manual live verification with injected stalls**

Serve a live mock backend with artificial decision stalls, then follow it in the viewer:
```bash
# terminal 1
uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1 --stall-seconds 6
# terminal 2
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh
```
Confirm by eye (acceptance criteria from the spec):
- Agents **decelerate to a stop** as a stall approaches (no abrupt freeze), and the "thinking…" badge shows during the stall.
- When the stall ends and buffered frames arrive, agents **glide-catch-up** (visibly faster, capped at 3×) and settle back to normal speed — no teleport across campus.
- Switch to the bundled baked replay from the menu and confirm playback looks identical to before.

Record the result (pass/fail per bullet) in the task's review notes; this step has no automated assertion.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/godot/scripts/viewer.gd
git commit -m "feat(viewer): pace the live clock with LivePacer — smooth stalls + bounded catch-up (#372)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- LivePacer module + `factor` curve → Task 1 (Steps 3, matching curve table in the test Step 1). ✓
- Continuous/monotonic curve, custom args → Task 1 test (Step 1). ✓
- `viewer.gd` integration, composes with `_speed`, `_is_live`-gated, clamp retained → Task 2 (Step 3). ✓
- `_anim_t` paced identically → Task 2 (Step 3). ✓
- Thinking-badge synergy (no code change to `ThinkingIndicator`) → no task needed; Task 2 preserves the `i >= last` condition by not touching it, and the lead hold keeps it false during healthy following. ✓
- Headless unit test + `run_smoke_test.sh` wiring → Task 1 (Steps 1, 5, 6). ✓
- Manual `--stall-seconds` verification → Task 2 (Step 5). ✓
- Baked replay byte-identical → Task 2 (Step 3 comment + Step 4 smoke). ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step has complete GDScript. ✓

**3. Type consistency:** `LivePacer.factor(lead: float, target := 2.0, catchup_max := 3.0) -> float` is defined identically in the Interfaces block, the test (Task 1 Step 1), the implementation (Task 1 Step 3), and the call site (Task 2 Step 3). Constants `LEAD_TARGET`/`CATCHUP_MAX` match between definition (Task 2 Step 2) and use (Task 2 Step 3). `lead` derived as `float(last) - _t / step_seconds` matches the spec's definition. ✓
