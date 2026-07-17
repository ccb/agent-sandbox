# Viewer Fan-out for Co-located Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When two or more agents share a tile, fan their sprites into a small deterministic ring in the Godot viewer so all are visible — a rendering-only fix, no engine/backend/replay change.

**Architecture:** Mirror the #372 thinking-indicator pattern: put the pure logic in a new `scripts/agent_fanout.gd` (static, node-free) and headless-unit-test it, then call it from `viewer.gd`'s playback loop. The offset is view-only — an agent's logical tile is untouched, and nothing in the viewer maps sprite pixels back to a tile.

**Tech Stack:** Godot 4.6 / GDScript. Headless `.gd` unit tests (`extends SceneTree`).

## Global Constraints

- **Track:** `godot-ga-main` (viewer-only). Branch `feat/agent-fanout-560`, worktree `.claude/worktrees/agent-fanout-560`, off `godot-ga-main` (d3089e7). PR targets `godot-ga-main`.
- **No engine/backend/replay change.** Only `godot/` files. Do not touch Python, matrices, or replay data.
- **View-only offset.** The displacement changes where a sprite is *drawn*; the agent's logical tile (frame data) is unchanged. Add a comment saying so at the wiring site.
- **Test sentinel:** each headless `.gd` test must print `test_<name>: all checks passed` and `quit(1 if _failures > 0 else 0)`; `run_smoke_test.sh` greps `"all checks passed"`.
- **Commit trailer (every commit):** end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`.** Stage only the files each task names.
- Needs Godot 4.6 on PATH as `godot` (or the macOS app bundle) to run the tests / smoke test.
- Audience: first/second-year undergraduates — clear, readable code + comments.

**Paths (from worktree root):**
- viewer: `godot-generative-agents/godot/scripts/viewer.gd`
- new script: `godot-generative-agents/godot/scripts/agent_fanout.gd`
- new test: `godot-generative-agents/godot/tests/test_agent_fanout.gd`
- smoke runner: `godot-generative-agents/run_smoke_test.sh`

---

## File Structure

- `godot/scripts/agent_fanout.gd` — **create**: pure `groups()` + `offset()` static helpers.
- `godot/tests/test_agent_fanout.gd` — **create**: headless unit test.
- `godot/../run_smoke_test.sh` — **modify**: run the new test (grep its sentinel).
- `godot/scripts/viewer.gd` — **modify**: preload `AgentFanout`, group + offset in the playback loop.

---

## Task 1: `agent_fanout.gd` pure logic + headless test

**Files:**
- Create: `godot-generative-agents/godot/scripts/agent_fanout.gd`
- Create: `godot-generative-agents/godot/tests/test_agent_fanout.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh`

**Interfaces:**
- Produces:
  - `AgentFanout.groups(tiles: Dictionary) -> Dictionary` — `tiles` is `{name(String): Vector2i}`; returns `{Vector2i: Array[String]}` of names on each tile, **sorted by name**.
  - `AgentFanout.offset(index: int, count: int, tile_px: float) -> Vector2` — ring displacement; `count <= 1` → `Vector2.ZERO`.

- [ ] **Step 1: Write the failing test**

Create `godot/tests/test_agent_fanout.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/agent_fanout.gd (issue #560). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_agent_fanout.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const AgentFanout := preload("res://scripts/agent_fanout.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _initialize() -> void:
	# --- offset: a lone (or empty) tile is never moved ---
	_check(AgentFanout.offset(0, 1, 16.0) == Vector2.ZERO, "count 1 -> no offset")
	_check(AgentFanout.offset(0, 0, 16.0) == Vector2.ZERO, "count 0 -> no offset")

	# --- offset: N co-located agents fan into a ring within the cap radius ---
	var cap := 16.0 * 0.36
	var pts := []
	for k in range(3):
		pts.append(AgentFanout.offset(k, 3, 16.0))
	_check(pts[0] != pts[1] and pts[1] != pts[2] and pts[0] != pts[2],
		"count 3 -> three distinct offsets")
	for k in range(3):
		_check(pts[k].length() <= cap + 0.001, "offset %d within cap radius" % k)
	_check(absf(pts[0].angle_to(pts[1]) - TAU / 3.0) < 0.001, "offsets evenly spaced")

	# --- offset is deterministic ---
	_check(AgentFanout.offset(1, 4, 16.0) == AgentFanout.offset(1, 4, 16.0),
		"offset deterministic")

	# --- groups: bucket co-located names (sorted); split distinct tiles ---
	var g: Dictionary = AgentFanout.groups({
		"Bob": Vector2i(3, 3), "Ada": Vector2i(3, 3), "Cy": Vector2i(9, 1),
	})
	_check(g[Vector2i(3, 3)] == ["Ada", "Bob"], "co-located names bucketed + sorted")
	_check(g[Vector2i(9, 1)] == ["Cy"], "distinct tile separate")

	if _failures == 0:
		print("test_agent_fanout: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run it — verify it fails (script missing)**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_agent_fanout.gd`
Expected: FAIL — parse/preload error, `res://scripts/agent_fanout.gd` does not exist (non-zero exit, no sentinel).

- [ ] **Step 3: Create `agent_fanout.gd`**

Create `godot/scripts/agent_fanout.gd`:

```gdscript
extends RefCounted
## Pure helpers for spreading co-located agent sprites so stacks stay visible
## (issue #560). No scene/node state, so tests/test_agent_fanout.gd exercises
## them headless. VIEW-ONLY: these offsets nudge where a sprite is DRAWN; an
## agent's logical tile is unchanged (see the viewer.gd wiring).

# Ring geometry as fractions of the tile size, so it scales with tile_px and the
# sprites stay on/near the tile.
const _RADIUS_BASE := 0.15
const _RADIUS_STEP := 0.06
const _RADIUS_CAP := 0.36


static func groups(tiles: Dictionary) -> Dictionary:
	# tiles: {name(String): Vector2i}. Returns {Vector2i: Array[String]} of the
	# names sharing each tile, sorted by name so an agent's index within its group
	# is stable frame-to-frame (independent of iteration order).
	var by_tile := {}
	for name in tiles:
		var t: Vector2i = tiles[name]
		if not by_tile.has(t):
			by_tile[t] = []
		by_tile[t].append(name)
	for t in by_tile:
		by_tile[t].sort()
	return by_tile


static func offset(index: int, count: int, tile_px: float) -> Vector2:
	# Sub-tile displacement for agent `index` of `count` co-located agents.
	# count <= 1 -> ZERO (the common case, no cost). Otherwise a point on a ring:
	# angle TAU*index/count, radius scaling gently with count and capped near the
	# tile edge so the sprite stays on/around the tile.
	if count <= 1:
		return Vector2.ZERO
	var radius := minf(
		tile_px * (_RADIUS_BASE + _RADIUS_STEP * count), tile_px * _RADIUS_CAP
	)
	var angle := TAU * float(index) / float(count)
	return Vector2(cos(angle), sin(angle)) * radius
```

- [ ] **Step 4: Run the test — verify it passes**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_agent_fanout.gd`
Expected: all `ok:` lines, then `test_agent_fanout: all checks passed`, exit 0.

- [ ] **Step 5: Wire the test into `run_smoke_test.sh`**

In `run_smoke_test.sh`, immediately after the `test_thinking_indicator.gd` block (the last test before the blank line + the `exec … smoke_test.tscn`), add:

```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_agent_fanout.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 6: Run the smoke test — verify it still passes with the new sentinel**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0; output includes `test_agent_fanout: all checks passed` and the final `smoke_test: PASS`.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/godot/scripts/agent_fanout.gd \
        godot-generative-agents/godot/tests/test_agent_fanout.gd \
        godot-generative-agents/run_smoke_test.sh
git commit -m "$(cat <<'EOF'
feat(viewer): agent_fanout helper — ring offset for co-located sprites (#560)

Pure, headless-tested groups()/offset() (mirrors the #372 thinking-indicator
pattern): given each agent's tile this step, group co-located agents and return
a deterministic sub-tile ring offset (count<=1 -> zero). View-only; wired into
viewer.gd next. run_smoke_test.sh greps the new test's sentinel.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Note on `.uid` files:** Godot may generate `agent_fanout.gd.uid` / `test_agent_fanout.gd.uid` on first import. If they appear, stage them alongside their scripts (the repo tracks `.uid` for other scripts — see `git status`); do not `git add -A`.

---

## Task 2: Wire the fan-out into `viewer.gd`

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd`

**Interfaces:**
- Consumes: `AgentFanout.groups(tiles)` and `AgentFanout.offset(index, count, tile_px)` from Task 1.

**Background:** The playback loop at `viewer.gd:1760–1768` positions each agent via `node.position = pa.lerp(pb, frac)` with no offset. `_tile_px` (int, `viewer.gd:128`) is the tile size. Preloads live near `viewer.gd:123–126`.

- [ ] **Step 1: Preload the helper**

In `viewer.gd`, after the existing preload block (the `const ThinkingIndicator := preload(...)` line ~126), add:

```gdscript
const AgentFanout := preload("res://scripts/agent_fanout.gd")
```

- [ ] **Step 2: Group co-located agents once per frame, then offset each**

In the playback loop, replace this block (currently ~`viewer.gd:1760–1768`):

```gdscript
	for name in _names:
		var a: Dictionary = _frames[i][name]
		var b: Dictionary = _frames[j][name]
		var pa := _tile_to_world(int(a["x"]), int(a["y"]))
		var pb := _tile_to_world(int(b["x"]), int(b["y"]))
		var agent: Dictionary = _agents[name]
		agent["node"].position = pa.lerp(pb, frac)
		if show_trail:
			_update_trail(agent["trail"], name, i, agent["node"].position)
```

with:

```gdscript
	# Fan out co-located agents so stacked sprites stay visible (#560). Group by
	# each agent's tile THIS step; the per-agent offset below is VIEW-ONLY -- it
	# nudges where the sprite is drawn, not the agent's logical tile, so nothing
	# that reasons about tiles (heatmap dwell, picking, conversations) is affected.
	var fanout_tiles := {}
	for name in _names:
		var fa: Dictionary = _frames[i][name]
		fanout_tiles[name] = Vector2i(int(fa["x"]), int(fa["y"]))
	var fanout_groups: Dictionary = AgentFanout.groups(fanout_tiles)

	for name in _names:
		var a: Dictionary = _frames[i][name]
		var b: Dictionary = _frames[j][name]
		var pa := _tile_to_world(int(a["x"]), int(a["y"]))
		var pb := _tile_to_world(int(b["x"]), int(b["y"]))
		var agent: Dictionary = _agents[name]
		agent["node"].position = pa.lerp(pb, frac)
		var grp: Array = fanout_groups[Vector2i(int(a["x"]), int(a["y"]))]
		if grp.size() > 1:
			agent["node"].position += AgentFanout.offset(
				grp.find(name), grp.size(), float(_tile_px)
			)
		if show_trail:
			_update_trail(agent["trail"], name, i, agent["node"].position)
```

(The trail and everything below keep reading `agent["node"].position`, so they follow the offset sprite automatically. The rest of the loop body — the `moving`/`flip_h`/`frame` lines after `_update_trail` — is unchanged.)

- [ ] **Step 3: Verify the viewer still parses + loads (smoke test)**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0; every scene loads (`smoke_test: PASS`), and `test_agent_fanout: all checks passed` is present. A GDScript parse error in `viewer.gd` would fail scene loading here.

- [ ] **Step 4: Manual visual check (if a replay is available)**

If a bundled replay exists (or bake one: `LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 400`), launch `./godot-generative-agents/run.sh` → "Play the bundled replay", find a co-located moment (shared destination), and confirm the sprites fan into a legible ring — all visible, name labels + chat bubbles moving with them — while a lone agent sits exactly on its tile centre. (Document the result in the report; this step needs a display, so it may be deferred to the reviewer/user.)

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/godot/scripts/viewer.gd
git commit -m "$(cat <<'EOF'
feat(viewer): fan out co-located agent sprites in the playback loop (#560)

Group agents by their tile each frame and add AgentFanout.offset to each
co-located agent's drawn position, so stacked sprites spread into a ring and
stay individually visible. View-only: logical tiles are unchanged, so dwell/
picking/conversation logic is unaffected.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (after all tasks)

- [ ] `godot --headless --path godot-generative-agents/godot --script res://tests/test_agent_fanout.gd` → `all checks passed`, exit 0.
- [ ] `./godot-generative-agents/run_smoke_test.sh` → exit 0, includes `test_agent_fanout: all checks passed` + `smoke_test: PASS`.
- [ ] `git status --porcelain` shows only: `agent_fanout.gd`, `test_agent_fanout.gd`, `viewer.gd`, `run_smoke_test.sh` (+ any `.uid` for the new scripts) — no Python/backend/replay files.
- [ ] Manual: co-located agents fan into a ring; a single agent is unmoved.

## Self-review notes (author)

- **Spec coverage:** `agent_fanout.gd` groups+offset → Task 1; headless test + smoke sentinel → Task 1; viewer wiring + view-only comment → Task 2. All spec deliverables covered.
- **Placeholder scan:** none — complete GDScript for both files, the exact smoke-test line, and the exact before/after wiring block.
- **Type consistency:** `groups(Dictionary)->Dictionary`, `offset(int,int,float)->Vector2`; `_tile_px` is int and passed as `float(_tile_px)`; `grp` is `Array`, `grp.find(name)` gives the stable index.
- **View-only invariant:** enforced by construction (offset added to draw position only) and documented at the wiring site; verified during scoping that no viewer code maps sprite pixels back to a tile.
