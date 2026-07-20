# Day-Plans Pop-up: Planned vs. Actual Ribbons (#251)

**Issue:** #251 · **Branch:** `feat/day-plan-ribbon-251` off `godot-ga-main`,
cut **after** `feat/timeline-markers-249` merges (both touch `agent_panel.gd`
and the `viewer.gd` wiring) · **Review track:** godot-ga-main (viewer GDScript
only; no Python, no replay-format change).

## Goal

Show each agent's authored day plan as a timeline ribbon beside what they
actually did, so plan-vs-reality drift (travel time, contention retries, a
sickness detour) is visible at a glance. The issue predates the current
architecture: it asks for a `generate_penn_replay.py` change to embed
`daily_plan.json`, but the plan is **already in the replay** —
`meta.personas[].schedule` is pinned by the #305 contract (`ScheduleStop =
{place, activity, emoji, steps}`, `steps: null` = rest of the day). This is
viewer-only.

## Current state (verified)

- The pop-up pattern is established twice: `heatmap_panel.gd` (H) and
  `social_graph_panel.gd` (G) are pure-UI Controls that get the replay via
  `set_replay(...)` — holding `_frames` **by reference**, so live appends flow
  in — are driven by `show_up_to(step)`, and emit `close_requested`. The
  viewer toggles them from a sidebar icon button + a hotkey
  (`viewer.gd:1278-1283`).
- Sidebar icon buttons use 16px hand-drawn bitmap glyphs where the Cute
  Fantasy pack has no matching icon (`FLAME_ROWS`/`GRAPH_ROWS`/`CAMERA_ROWS`
  pattern in `agent_panel.gd`).
- `viewer.gd` keeps `_persona_detail[name]` = the full persona meta entry
  (name/emoji/persona/home/schedule) and passes it to the persona inspector,
  which already renders the schedule **textually** (`_build_schedule`,
  `persona_inspector.gd:227`). The ribbon complements that with a visual,
  cross-agent view.
- Schedule `place` names do **not** always match the act address's building
  segment: room-level locations exist ("Van Pelt — Kamin Gallery" lives at
  `UPenn:Van Pelt Library:Kamin Gallery`), and two of them are scheduled in
  the current world. String-matching place names against buildings would
  therefore mispair. What saves us: a travel-leg act is
  `"walking to <place> @ <address>"` (`run_simulation.py:200`) — it carries
  the schedule's **exact place name** together with that place's **resolved
  address**, and a perform frame at the stop carries the **same address**
  (verified against a real bake). So the place→address mapping is learnable
  from the frames themselves, exactly, with no heuristics. The
  `"walking to "` prefix convention is already relied on by
  `serve_penn.py:209`.
- Per-persona `TINTS` are kept in step across viewer/minimap/heatmap by
  copy — but ribbon segment colors are keyed by **place**, not persona, so no
  new copy of TINTS is needed.

## Design

### 1. Pop-up — `scripts/day_plan_panel.gd` (new)

Follows `social_graph_panel.gd`'s skeleton: dimmed modal backdrop
(`BACKDROP_COLOR`), a titled panel, a close button, `close_requested`,
click-outside closes. Content: one row per agent —

```
Diego   plan   ██████░░░░░░▒▒▒▒▒▒██████████
        actual ████░░░░░░░░▒▒▒▒▒▒▒▒████████   ▼ cursor at current step
```

- **API:** `set_replay(frames, names, persona_detail)` (frames by reference,
  live-safe) and `show_up_to(step)` (moves the cursor, extends the actual
  ribbons). Both mirror the heatmap contract so `viewer.gd`'s wiring is
  symmetrical.
- **Time axis:** 0 to `axis_len` where `axis_len = max(frames.size(),
  largest sum of a persona's explicit planned steps)` — stable under live
  growth, exact for baked replays. One shared axis for every row, cursor line
  at the current step.
- **Planned ribbon (full width, known up front):** segments laid end-to-end
  per schedule stop, width proportional to `steps`; `null`-steps stops split
  the remaining axis equally (in authored worlds only the last stop is null,
  which then absorbs the rest of the day). A persona without a `schedule` key
  (older replay) gets one neutral-grey bar labeled "no authored plan".
- **Actual ribbon (fills as time passes):** per frame `0..step`, one axis
  slot; steps beyond the current playback position stay empty — same "up to
  now" philosophy as the heatmap, and spoiler-free. Slot classification, in
  order:
  1. act starts with `"walking to <place>"` → **in transit** toward that
     stop: the place's color at ~45% alpha ("late because still walking"
     reads differently from "off-plan");
  2. the act address (after `" @ "`) equals a resolved place address → **at
     the stop**: solid place color;
  3. anything else → neutral grey ("other").
- **Place→address resolution:** a scan of the frames collects
  `place → address` from every `"walking to <place> @ <address>"` act (baked:
  once at load; live: incrementally as frames arrive). A place the agent
  never walks to stays unresolved — its planned segment still gets a color,
  and matching perform frames simply fall to grey (rare: it means the agent
  was there from step 0).
- **Palette:** colors keyed by schedule place name, assigned in order of
  first appearance across all schedules (a small fixed palette of
  distinguishable hues on the parchment theme); planned segments and actual
  slots share the key, so a matching pair reads instantly. A legend row at
  the bottom lists place → color; grey is listed as "off-plan / other"
  (transit already reads as the faded destination color, not grey).
- **Seek:** clicking anywhere on a ribbon emits `seek_requested(step)` with
  the step under the cursor. The viewer routes it into the same seek path as
  the scrubber, and ignores it in live mode (matching the existing
  belt-and-braces guard around live seeks, `viewer.gd:1265`).
- **Tooltips:** hovering a planned segment names the stop ("2. lunch @
  Houston Hall — 200 steps"); hovering an actual slot names its
  classification ("walking to Houston Hall" / "at Houston Hall" /
  "off-plan: <building>").

### 2. Wiring — `agent_panel.gd` + `viewer.gd`

- New sidebar icon button in the view-controls row: a hand-drawn 16px
  **calendar/ribbon glyph** (same palette conventions as the flame/graph
  glyphs), tooltip "Day plans — planned vs. actual, up to now (T)", emitting a
  new `day_plans_requested` signal.
- `viewer.gd`: instantiate the pop-up in the scene like the other two
  (`$DayPlanLayer/DayPlanPanel`), `set_replay(...)` from both the baked
  loader and `_spawn_from_meta` (live/reset), `show_up_to` pushed on every
  step change while visible, `_toggle_day_plans()` on the panel signal and
  **KEY_T** (unused today), `close_requested` hides it. Live mode: the pop-up
  works (planned is known from the handshake meta; actual accumulates by
  reference); only seek clicks are ignored.

### 3. Out of scope

- Embedding anything new in the replay (the schedule is already in `meta`;
  when #397 makes plans dynamic, whatever it writes into `schedule` renders
  here unchanged).
- Per-arena / sub-building resolution (building granularity only).
- Activity-level diffing ("planned lunch but studied") — place-level only.
- Replaying schedule *revisions* over time (needs #397's data model first).

## Verification

- `./godot-generative-agents/run_smoke_test.sh` passes.
- Manual, against a fresh 400-step mock bake: T and the sidebar button open
  the pop-up; three agents show plan/actual pairs; colors match between rows;
  the cursor tracks playback and the actual ribbons stop at "now"; clicking a
  ribbon seeks; in live mode the pop-up opens, ribbons grow with the feed, and
  clicks don't seek; a replay with a schedule-less persona shows the grey
  "no authored plan" bar.
