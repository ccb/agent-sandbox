# Event Markers on the Timeline Scrubber (#249)

**Issue:** #249 · **Branch:** `feat/timeline-markers-249` off `godot-ga-main` ·
**Review track:** godot-ga-main (viewer GDScript only; no Python, no map data).

## Goal

Scrubbing a 1200-step replay is blind: interesting moments (a conversation
starting, a reflection forming, an arrival, a sickness event) leave no trace on
the timeline. Add colored tick marks over the playback scrubber so you can see
where the moments are and click to jump to them.

## Current state (verified)

- The scrubber is an `HSlider` built in `agent_panel.gd:315-321`; its value is
  the 0-based frame index, max = last frame index (`set_progress`,
  `agent_panel.gd:588`). User drags emit `seek_requested(step)`; live mode
  hides the scrubber entirely (`set_live`, `agent_panel.gd:531`).
- The panel is pure UI — `viewer.gd` owns the replay and pushes state in.
  `_rows`/`_active` (the tracked character) are panel-internal; `_refresh()`
  (`agent_panel.gd:647`) is the single place row highlighting reacts to
  tracking changes.
- `viewer.gd:_load_replay_from_text` (line 458) reads `meta`, `frames`, and
  `memory_streams` — it does **not** read the top-level `events` key that #476
  bakes into every replay. In baked-replay mode the run-monitor HUD is hidden
  (`_setup_hud`), so baked `events` currently have **no consumer**; this
  feature is their first.
- `act` strings are `"<activity> @ UPenn:<Building>:<area>"`; `_building_of`
  (`viewer.gd:1142`) extracts the building and returns `""` on malformed input.
- During a travel leg the act is `"walking to <place> @ <address>"`
  (`run_simulation.py:200`) and the address is already the **destination's** —
  so an address/building change marks *departure*, and the reliable arrival
  signal is the `"walking to "` prefix disappearing (the same convention
  `serve_penn.py:209` already keys on).
- Replay shapes are pinned by the #305 contract (`backend/contract.py`):
  `EventState = {turn, actor, action, summary, payload}`;
  `MemoryRecord = {kind, importance, text, created_turn}`; `AgentFrame.chat`
  is `[[speaker, line], ...]` or null.

## Design

### 1. Marker collection — `scripts/replay_markers.gd` (new)

A static helper (no scene node): `collect(frames, names, memory_streams,
events) -> Array[Dictionary]`, each marker `{step: int, kind: String,
agent: String, label: String}`. Four sources:

| kind | source | rule | tick color |
|---|---|---|---|
| `event` | replay `events` | one marker per record; step = `turn`, agent = `actor`, label = `"actor: summary"` | red (the LIVE-badge red, `0.82, 0.20, 0.15`) |
| `chat` | frames | frame N's `chat` non-empty where frame N-1's was empty/null, per agent (conversation onset, not continuation) | pack blue `#0099db` |
| `reflection` | `memory_streams` | records with `kind == "reflection"`; step = `created_turn` | purple |
| `arrival` | frames | frame N-1's `act` starts with `"walking to "` and frame N's does not, per agent (NOT a building change: during travel the act address is already the destination's, so an address change marks departure) | pack green `#3e8948` |

Defensive rules: skip records whose step falls outside `0..frames.size()-1`;
a missing `events` key or empty `memory_streams` just yields no markers of
that kind. Arrival labels name the destination building via the building
segment of frame N's act address — move `_building_of` out of `viewer.gd`
into `replay_markers.gd` as a static function and have `viewer.gd` call it
there (one definition, no drift; the helper stays viewer-independent).

`viewer.gd:_load_replay_from_text` calls `collect(...)` once per load and
hands the result to the panel. Live mode never calls it (no scrubber to mark).

### 2. Marker strip — `scripts/timeline_markers.gd` (new)

A ~10px-tall custom-draw `Control` inserted into the sidebar column
immediately **above** the scrubber (drawing onto the `HSlider` itself would
fight the theme's grabber art and its drag hit-testing). API:

- `set_markers(markers: Array, total: int)` — the full collected list + the
  last frame index (the scrubber's max), stored; triggers redraw.
- `set_filter(agent: String)` — `""` = show all; otherwise only markers whose
  `agent` matches (kind `event` markers match on `actor`). Triggers redraw.
- signal `marker_clicked(step: int)`.

`_draw()` paints one 2px vertical tick per visible marker at
`x = step / float(total) * width`, colored by kind; coincident markers
overdraw (fine at this size). Mouse click seeks to the nearest marker within
~4px, else to the step under the cursor; either way it emits
`marker_clicked(step)`. Hover sets `tooltip_text` to the nearest markers'
labels (up to 3, joined by newlines), e.g.
`"step 412 — Sofia Alvarez arrives at Houston Hall"`.

### 3. Panel wiring — `agent_panel.gd`

- Build the strip in `_ready()` right before `_scrubber`; expose
  `set_timeline_markers(markers, total)` for the viewer, forwarding to the
  strip.
- Route `marker_clicked` into the existing `seek_requested` signal — one seek
  path, viewer-side code unchanged.
- Tracking filters the strip: `_on_pressed`/`clear_active` already funnel into
  `_refresh()`; add `_markers.set_filter(_active)` there, so tracking an agent
  collapses the strip to that agent's storyline and untracking restores all.
- `set_live(true)` hides the strip alongside the scrubber (same visibility
  toggle).

### 4. Out of scope

- Live-mode markers (no scrubber to mark; the HUD event log #502/#507 covers
  live).
- Marker kinds beyond the four above; a legend UI (tooltips carry the
  meaning); user-configurable kind toggles.
- Any Python or replay-format change — this is a pure consumer of pinned
  shapes.

## Verification

- `./godot-generative-agents/run_smoke_test.sh` passes (scene loads, campus
  paints).
- Manual, against a fresh 400-step mock bake: ticks appear; colors match the
  four kinds; clicking a tick seeks; tracking Sofia filters to her markers;
  the strip vanishes in live mode; a pre-#476 replay (no `events` key) still
  loads with the other three marker kinds intact.
