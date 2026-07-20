# Boil-water action layer — design spec

**Date:** 2026-07-09 · **Status:** approved (FL) · **Branch:** feature off `godot-ga-main`
**Issues:** implements the world half of #300 · design anchor #446 · research epic #299 · related #446 comment (ScienceWorld verb mapping)

## Context

The Penn agents' entire action vocabulary is `travel` + `perform` (free text, no world
mutation). Issue #300 needs a world where drinking unboiled water makes an agent sick —
the motivation signal for the #299 self-coding experiment — and #446 needs first "real"
verbs that satisfy CCB's rubric (place, duration, visible state change, memory hook).

Key design insight (from ScienceWorld, argued in the #446 comment): **"boil" is not a
verb.** Verbs are dumb (`activate stove`, `wait`); boiling is a world *process* — which
this slice deliberately does **not** implement. Agents can toggle the stove; nothing
heats. That capability gap is the point: it is what the self-coding seam (#301) lets an
agent close.

## Approach decision

**Backend-local first, upstream after Thursday** (Approach B). All code lands in one PR
on `godot-ga-main`: the new verbs are `Action` subclasses in
`godot-generative-agents/backend/actions.py` (same pattern as the existing
`Travel`/`Act`), not in the shared engine library. Rationale:

- No cross-branch dependency (engine PR → `main` merge → sync-forward wait).
- Doesn't commit shared-engine API surface the day before the #446 meeting decides
  that API (rubric axis 5, `REQUIRED_AFFORDANCES`).
- Demoable mock-brain run for Thursday.
- The upstreaming debt is recorded as its own GitHub issue (see §6).

Other decisions: scenario lives in **Houston Hall** (existing matrix address
`UPenn:Houston Hall:lobby` — renders in the viewer today, thematically a dining space);
drink model is **get-then-drink** (zero change to `Drink` preconditions).

## §1 Verbs (`backend/actions.py`)

### `DrinkPenn(consume.Drink)`

- `ACTION_NAME` stays `"drink"`; registered via `custom_actions` so it overrides the
  built-in in the Penn parser.
- `apply_effects()`: call `super().apply_effects()` (inherits portions/thirst/taste
  handling, `consume.py:111-157`), then if the item has `requires_boiling` and not
  `is_boiled` (the pair matches #300's `is_boiled: false` phrasing; `requires_boiling`
  scopes the rule so default-False `is_boiled` can't sicken every future drinkable):
  - `character.set_property("is_sick", True)`
  - `parser.ok(...)` narration: "… drinks the murky water and begins to feel violently ill."
  - record a **`sickness` `GameEvent`** (`text_adventure_games/events.py:24`) with
    payload `{agent, item, location, step}` — #300's measurement hook, so #299's
    success criteria are computable from the run record / `GET /events` feed.

### `Activate` / `Deactivate`

- Backend-local subclasses mirroring `Light`/`Douse` (`consume.py:160-281`, ~50 lines each).
- Precondition: target item matched, co-located (not necessarily held — devices are
  fixtures), has `is_device` (plain-string property; the engine property set is open).
- Effect: toggle `is_on` True/False; narrate. **No downstream process effects** (the
  withheld gap).
- Known consideration: engine `Douse` carries a `"turn off"` alias
  (`consume.py:234-242`) and stays registered in the Penn parser. Authored commands and
  tool-offered verbs use `activate`/`deactivate` explicitly, so no routing conflict in
  practice; note it in the PR.

### Reused as-is

Engine `Get` (`actions/things.py:14`). `pour`, `put`, and any heat process are out of
scope (§Out-of-scope).

## §2 World data (`backend/penn/penn_world.py` + `world_data_upenn.yaml`)

The first `Item` instances ever created in the Penn world (the YAML currently has no
items; `build_world.py:155-164` builds only Locations). Placed into Houston Hall's
`location.items` at world-build time, in `build_penn_world()`
(`penn_world.py:266-301`) or a small helper it calls:

| Item | Properties |
|---|---|
| `sink` | `is_device`, not gettable |
| `stove` | `is_device`, not gettable |
| `pot` | `gettable` (prop for the future boil; no behavior yet) |
| `cup of murky water` ×2–3 (distinct names, e.g. "cup of murky water", "second cup of murky water") | `gettable`, `drinkable`, `requires_boiling`, `is_boiled: false` |

Personas: at least one persona gets a Houston Hall schedule stop (with §3 `commands:`)
so the encounter fires deterministically under the mock brain — proximity is
engineered, not hoped for (the #265 lesson).

## §3 Mock-brain authored commands (`smallville_agents.py`)

The mock brain only emits `travel`/`perform` from the YAML schedule
(`smallville_agents.py:122-171`), so it would never drink. Extension: a schedule stop
may carry an optional `commands:` list —

```yaml
- place: Houston Hall
  activity: getting a drink of water
  steps: 6
  commands:
    - get cup of murky water
    - drink cup of murky water
```

The mock brain replays these (one per decision, in order) while at the stop, before
falling back to `perform`. Real-LLM brains ignore `commands:` — they see the enlarged
verb set instead. `agent.action_names` for Penn grows to
`["travel", "perform", "get", "drink", "activate", "deactivate"]`
(wired where Penn attaches agents, not hard-coded for Smallville —
`smallville_agents.py:266` today).

## §4 Memory (`remember_outcome`, `smallville_agents.py:495-521`)

New branches beside travel/perform:

- `get` / `activate` / `deactivate` / uneventful `drink`: first-person reflection,
  importance **2.0** (same as travel/perform today).
- `drink` that set `is_sick` this step: first-person **"I drank the murky water and now
  I feel terribly sick."**, importance **8.0** — the high-importance observation #300
  names as the self-coder's motivation signal. Detection: check the drinker's
  `is_sick` transitioned during the action (capture before/after in the branch).

## §5 Tests (`godot-generative-agents/tests/`, offline/mock only)

Follow `test_penn_live.py` / `test_live_seam.py` patterns. New file, e.g.
`test_boil_water_scenario.py`:

1. **Unit — drink:** contaminated cup → `is_sick` set, narration contains "ill",
   `sickness` event recorded; clean drinkable item → no `is_sick`, no event.
2. **Unit — devices:** `activate stove` → `is_on`; `deactivate` clears it;
   `activate pot` (non-device) fails at the precondition gate with a readable reason.
3. **Integration — the #300 acceptance:** mock-brain run of the Penn world; the persona
   with the Houston Hall stop executes its `commands:`; assert the agent ends sick, an
   importance-8.0 observation is in its memory stream, the `sickness` event is in the
   event feed, and **no water is ever boiled** (stove `is_on` has no effect on any
   `is_boiled` flag).

Verification: `uv run pytest godot-generative-agents/tests/ -v` plus the existing suite
(`uv run pytest tests/ -v`) stays green; `uv run black .` clean.

## §6 Issues

- File now: **engine upstreaming issue** — "Engine slice: generic activate/deactivate
  verbs + contamination effect in Drink (upstream from the Penn backend)", targeted at
  `main` *after* Thursday's #446 meeting settles the verb API (rubric,
  `REQUIRED_AFFORDANCES`). Links #300/#446/#299 and this spec.
- The PR closes the world half of **#300** ("Closes #300" — the engine-verb caveat in
  #300 is satisfied backend-locally; the upstreaming issue carries the remainder).

## §7 Spec location

This file lives under `godot-generative-agents/docs/specs/` (not root `docs/`) so the
PR stays entirely within `godot-generative-agents/` and rides the `godot-ga-main`
review track per CLAUDE.md.

## Acceptance criteria (from #300)

- In a mock-brain run: an agent drinks, gets sick, and the observation appears in its
  memory stream (visible via the memory endpoint / baked JSON).
- Sickness events + cause are logged (event feed / run record) — #299's metrics are
  computable.
- No agent can boil water. The stove toggles; nothing heats.

## Out of scope

- Any heat-transfer / boiling process (deliberately withheld — #299/#301 territory).
- `pour`, `put`, liquid containers beyond the fixed cups.
- Engine-library (`text_adventure_games/`) changes — deferred to the upstreaming issue.
- Viewer UI for sickness beyond the existing event feed (viewer work tracked elsewhere).
- Smallville: `the_ville` behavior unchanged; new verbs/commands are Penn-wired only.
