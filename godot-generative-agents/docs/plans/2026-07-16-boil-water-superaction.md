# `boil water` superaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained `boil` action to the Penn backend so an agent can make raw water safe to drink, letting us test — today, on the mock brain — whether a sick agent chooses to boil water before drinking.

**Architecture:** One `Action` subclass (`BoilWater`) in `godot-generative-agents/backend/actions.py`, registered into the Penn verb set. It gates on the existing props (pot + stove + unboiled water in scope) and, in one `apply_effects`, flips every `requires_boiling`/not-`is_boiled` water item at the location to `is_boiled` and switches the stove on. No multi-step recipe, no new objects — deliberately the hand-authored baseline, not the #301 self-coding seam.

**Tech Stack:** Python 3.12, `text_adventure_games` engine (Action precondition/effect gate), pytest, uv.

## Global Constraints

- **Track:** godot-ga-main. Every touched file is under `godot-generative-agents/`; do NOT modify `text_adventure_games/`. Branch is `feat/boil-superaction` (already created off `godot-ga-main`).
- **Backend-local only:** the boil verb stays in `backend/actions.py` per the #464 precedent; upstreaming to the engine is out of scope.
- **Test command:** `uv run pytest godot-generative-agents/tests/test_boil_water.py -q` (run from repo root).
- **Format:** `uv run black .` before each commit.
- **Commit trailer:** every commit ends with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **No new objects / no "kettle":** the existing `pot` is the container; the `sink` is untouched.
- **Do not touch `DrinkPenn`:** it already takes the safe path once `is_boiled` is set.

---

### Task 1: `BoilWater` action — gate, effect, event

**Files:**
- Modify: `godot-generative-agents/backend/actions.py` (add `BoilWater` after `Deactivate`, ~line 224)
- Test: `godot-generative-agents/tests/test_boil_water.py` (add a `_pot()` helper + a new test block)

**Interfaces:**
- Consumes: `text_adventure_games.actions.base.Action`; engine helpers `acting_character(command, hint=...)`, `was_matched(thing, message)`, `parser.get_items_in_scope(character)`, `parser.ok(...)`, `parser.fail(...)`, `game.log_event(actor, action, summary="", payload=None)`.
- Produces: `backend.actions.BoilWater` with `ACTION_NAME = "boil"`. On success: sets `is_boiled=True` on every location item with `requires_boiling` and not `is_boiled`; sets the stove's `is_on=True`; logs a `"boiled"` `GameEvent` with `payload={"location": <name>, "items": [<names>]}`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `godot-generative-agents/tests/test_boil_water.py`:

```python
# -- BoilWater: the self-contained boil superaction (#300 test scaffold) -----

from backend.actions import BoilWater


def _pot():
    pot = Item("pot", "a cooking pot", "An empty steel pot. It could hold water.")
    pot.set_property(Property.GETTABLE, False)
    return pot


def _boil_world():
    """Tiny world with the boil verb + drink override, and Union stocked with a
    pot, a stove, and one unboiled cup."""
    game, char = _tiny_world(extra_actions=[BoilWater, DrinkPenn, Activate])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_stove())
    union.add_item(_cup())
    return game, char, union


def test_boil_is_registered():
    game, _ = _tiny_world(extra_actions=[BoilWater])
    assert game.parser.actions["boil"] is BoilWater


def test_boil_marks_water_safe_and_turns_stove_on():
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is True
    assert union.items["stove"].get_property("is_on") is True


def test_boiled_event_is_logged():
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    boiled = [e for e in game.events if e.action == "boiled"]
    assert len(boiled) == 1
    assert boiled[0].payload["location"] == "Union"
    assert boiled[0].payload["items"] == ["cup of murky water"]


def test_boil_then_drink_does_not_sicken():
    # The core end-to-end signal: once boiled, drinking the same water is safe.
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]


def test_boil_fails_without_a_pot():
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_stove())
    union.add_item(_cup())
    assert not game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is False


def test_boil_fails_without_a_stove():
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_cup())
    assert not game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is False


def test_boil_fails_with_nothing_to_boil():
    # Pot + stove present, but no unboiled water -> clean precondition failure.
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_stove())
    union.add_item(_cup(unboiled=False))
    assert not game.parser.parse_command("boil water", actor=char)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -q -k boil`
Expected: FAIL — `ImportError: cannot import name 'BoilWater' from 'backend.actions'` (collection error).

- [ ] **Step 3: Implement `BoilWater`**

Add to `godot-generative-agents/backend/actions.py`, immediately after the `Deactivate` class (end of file, ~line 224):

```python
class BoilWater(base.Action):
    """Boil the raw water in the room so it's safe to drink (#300 test scaffold).

    A deliberately self-contained "superaction": it gates on the real props
    being present (a pot, a stove, and water that needs boiling) and, in one
    step, marks every unboiled water item at the location ``is_boiled`` and
    switches the stove on. It does NOT model the multi-step recipe -- filling
    from the sink, putting the pot on the stove, heating over time -- because
    that emergent assembly is the self-coding experiment (#299/#301). This is
    the hand-authored "correct answer" so we can test, today, whether an agent
    chooses to boil raw water before drinking it. Registered under a new "boil"
    verb; the engine has no such action, so nothing is overridden."""

    ACTION_NAME = "boil"
    ACTION_DESCRIPTION = "Boil water on a stove to make it safe to drink"
    # Typed tool slot (issues #356/#485). ``target`` is optional and advisory:
    # the action boils all the raw water in the room regardless of the exact
    # string, so "boil water" (the schedule mock's phrasing) and a tool brain's
    # structured pick parse identically.
    ARGUMENTS_SCHEMA = {
        "target": {
            "type": "string",
            "description": "what to boil, e.g. 'water'",
            "required": False,
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="cook")

    def _scope(self):
        return self.parser.get_items_in_scope(self.character)

    def _has_named_item(self, name: str) -> bool:
        return any(item.name == name for item in self._scope())

    def _stove(self):
        for item in self._scope():
            if item.name == "stove" and item.get_property("is_device"):
                return item
        return None

    def _unboiled_water(self):
        loc = self.character.location
        if loc is None:
            return []
        return [
            item
            for item in loc.items.values()
            if item.get_property("requires_boiling")
            and not item.get_property("is_boiled")
        ]

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is here to boil water."):
            return False
        if self.character.location is None:
            self.parser.fail("There is nowhere to boil water.")
            return False
        if not self._has_named_item("pot"):
            self.parser.fail("There's no pot here to boil water in.")
            return False
        if self._stove() is None:
            self.parser.fail("There's no stove here to heat it on.")
            return False
        if not self._unboiled_water():
            self.parser.fail("There's nothing here that needs boiling.")
            return False
        return True

    def apply_effects(self):
        stove = self._stove()
        stove.set_property("is_on", True)
        boiled = self._unboiled_water()
        for water in boiled:
            water.set_property("is_boiled", True)
        self.game.log_event(
            self.character.name,
            "boiled",
            summary=f"{self.character.name} boiled water on the {stove.name}",
            payload={
                "location": getattr(self.character.location, "name", None),
                "items": [w.name for w in boiled],
            },
        )
        return self.parser.ok(
            f"{self.character.name.capitalize()} fills the pot at the {stove.name} "
            "and boils the water until it's safe to drink."
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -q -k boil`
Expected: PASS (the new `boil` tests, plus the pre-existing `test_boiled_water_is_safe_to_drink` matched by `-k boil`).

- [ ] **Step 5: Format and commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boil-superaction
uv run black godot-generative-agents/backend/actions.py godot-generative-agents/tests/test_boil_water.py
git add godot-generative-agents/backend/actions.py godot-generative-agents/tests/test_boil_water.py
git commit -F - <<'EOF'
feat(boil): self-contained `boil water` action (#300 test scaffold)

Gates on pot + stove + unboiled water in scope; flips every raw-water item at
the location to is_boiled, switches the stove on, and logs a `boiled` event.
Deliberately no multi-step recipe -- that assembly is #301. Backend-local.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: Wire `boil` into the Penn verb set + real-world test

**Files:**
- Modify: `godot-generative-agents/backend/penn/penn_world.py` (line 47 `PENN_EXTRA_ACTIONS`, line 52 `PENN_ACTION_VERBS`, and the `from backend.actions import ...` line 33)
- Test: `godot-generative-agents/tests/test_boil_water.py`

**Interfaces:**
- Consumes: `backend.actions.BoilWater` (Task 1); `backend.penn.penn_world.build_penn_world`, `PENN_ACTION_VERBS`; `backend.cognition.attach_agents(extra_action_names=...)`.
- Produces: `BoilWater` present in `PENN_EXTRA_ACTIONS`; `"boil"` present in `PENN_ACTION_VERBS` — so a Penn brain (mock or real) may choose it and the real Houston Hall props support it.

- [ ] **Step 1: Write the failing tests**

Add to `godot-generative-agents/tests/test_boil_water.py` (after the existing `test_houston_hall_is_stocked_and_the_scenario_plays`, so `build_penn_world` is already imported):

```python
def test_boil_makes_houston_water_safe_in_the_real_world():
    """In the furnished Houston Hall, boiling makes the raw cups safe: a drink
    afterward does not sicken. (Contrast test_houston_hall_is_stocked...: with
    no boil verb, activating the stove heats nothing.)"""
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    assert game.parser.parse_command("boil water", actor=sofia)
    hall = game.locations["Houston Hall"]
    assert hall.items["cup of murky water"].get_property("is_boiled") is True
    assert hall.items["second cup of murky water"].get_property("is_boiled") is True
    assert game.parser.parse_command("get cup of murky water", actor=sofia)
    assert game.parser.parse_command("drink cup of murky water", actor=sofia)
    assert not sofia.get_property("is_sick")


def test_penn_action_verbs_include_boil():
    from backend.penn.penn_world import PENN_ACTION_VERBS
    from backend.cognition import attach_agents

    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, extra_action_names=PENN_ACTION_VERBS)
    assert "boil" in chars["Testa"].agent.action_names
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -q -k "houston_water_safe or verbs_include_boil"`
Expected: FAIL — `test_penn_action_verbs_include_boil` asserts `"boil"` not yet in the list; `test_boil_makes_houston_water_safe_in_the_real_world` fails because `parse_command("boil water", ...)` returns falsy (`boil` isn't registered in the Penn world).

- [ ] **Step 3: Wire it in**

In `godot-generative-agents/backend/penn/penn_world.py`:

Line 33 — extend the import:
```python
from backend.actions import Activate, Deactivate, DrinkPenn, BoilWater
```

Line 47 — add to the action set:
```python
PENN_EXTRA_ACTIONS = [Activate, Deactivate, DrinkPenn, BoilWater]
```

Line 52 — add the verb:
```python
PENN_ACTION_VERBS = ["get", "drink", "activate", "deactivate", "boil"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -q`
Expected: PASS (full file — the two new tests plus all pre-existing ones; the withheld-gap assertion in `test_houston_hall_is_stocked_and_the_scenario_plays` still holds because that test never calls `boil`).

- [ ] **Step 5: Format and commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boil-superaction
uv run black godot-generative-agents/backend/penn/penn_world.py godot-generative-agents/tests/test_boil_water.py
git add godot-generative-agents/backend/penn/penn_world.py godot-generative-agents/tests/test_boil_water.py
git commit -F - <<'EOF'
feat(boil): register `boil` in the Penn verb set (#300)

Add BoilWater to PENN_EXTRA_ACTIONS and "boil" to PENN_ACTION_VERBS so a Penn
brain may choose it; test that boiling makes the real Houston Hall cups safe.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Boil-first schedule variant + end-to-end mock run

**Files:**
- Modify: `godot-generative-agents/backend/penn/world_data_upenn.yaml` (the Houston Hall dinner stop, ~line 246 — add a commented boil-first variant)
- Test: `godot-generative-agents/tests/test_boil_water.py`

**Interfaces:**
- Consumes: `backend.run_simulation.simulate`, `backend.penn.penn_world.build_penn_world`, `PENN_EXTRA_ACTIONS`, `_furnish_boil_water` (all already imported at the bottom of the test file for the existing end-to-end test); `backend.build_world.build_world`, `_normalize_personas`.
- Produces: an acceptance test proving a full mock run where the agent boils first stays healthy; a documented (commented) schedule variant.

- [ ] **Step 1: Write the failing test**

Add to the end of `godot-generative-agents/tests/test_boil_water.py`:

```python
def test_end_to_end_mock_run_boil_then_drink_stays_healthy():
    """The scaffold's payoff: a mock-brain run where the agent boils before
    drinking never gets sick, and no sickness memory lands. Mirrors
    test_end_to_end_mock_run_agent_drinks_and_gets_sick, boil-first."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Boil",
        "home": "Houston Hall",
        "persona": "I am Testa Boil, a careful test persona.",
        "emoji": "🍵",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "boiling water before dinner",
                "emoji": "🍵",
                "steps": 3,
                "commands": [
                    "boil water",
                    "get cup of murky water",
                    "drink cup of murky water",
                ],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    memories = {}
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_memories=memories,
    )
    stream = memories["Testa Boil"]
    assert not any("terribly sick" in m["text"] for m in stream), [
        m["text"] for m in stream
    ]
```

- [ ] **Step 2: Run the test to verify it fails, then passes on the current code**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py::test_end_to_end_mock_run_boil_then_drink_stays_healthy -v`

This is an **acceptance/regression guard** over the pipeline built in Tasks 1–2. On a clean checkout of `godot-ga-main` (no `boil` verb) it would fail — `boil water` is unmatched, so the agent still drinks raw and the sick memory lands. On top of Tasks 1–2 it PASSES with no new production code. Expected here: PASS. If it fails, the `commands` normalization or verb wiring from Task 2 regressed — fix before continuing.

- [ ] **Step 3: Add the documented schedule variant**

In `godot-generative-agents/backend/penn/world_data_upenn.yaml`, find the Houston Hall dinner stop (~line 246):

```yaml
  - place: Houston Hall
    activity: meeting friends for dinner
    commands:
    - get cup of murky water
    - drink cup of murky water
```

Add, directly beneath it, a commented healthy-path variant (keeps the #300 sick-path demo as the default; uncomment to demo the scaffold in a live/baked run):

```yaml
  - place: Houston Hall
    activity: meeting friends for dinner
    commands:
    - get cup of murky water
    - drink cup of murky water
    # Boil-first variant (#300 boil superaction test scaffold): swap the two
    # `commands` above for the three below to demo the healthy path in a mock
    # run -- the agent boils the water first, so `drink` never sickens.
    #   - boil water
    #   - get cup of murky water
    #   - drink cup of murky water
```

- [ ] **Step 4: Run the full suite to confirm nothing regressed**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -q`
Expected: PASS (all tests). The YAML comment changes no behavior; `test_sofias_houston_hall_stop_carries_the_commands` still sees the unchanged default `["get cup of murky water", "drink cup of murky water"]`.

- [ ] **Step 5: Format and commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/boil-superaction
uv run black godot-generative-agents/tests/test_boil_water.py
git add godot-generative-agents/tests/test_boil_water.py godot-generative-agents/backend/penn/world_data_upenn.yaml
git commit -F - <<'EOF'
test(boil): end-to-end boil-then-drink mock run + documented schedule variant (#300)

Acceptance guard: a mock run that boils before drinking stays healthy, no
sickness memory. Add a commented boil-first variant to Sofia's Houston stop.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: Full-suite gate

**Files:** none (verification only).

- [ ] **Step 1: Run the whole Penn backend suite**

Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: PASS — the boil action is additive (new verb, new list entries, commented YAML), so no existing Penn test should change.

- [ ] **Step 2: Confirm formatting is clean**

Run: `uv run black --check godot-generative-agents/backend/actions.py godot-generative-agents/backend/penn/penn_world.py godot-generative-agents/tests/test_boil_water.py`
Expected: `All done!` / no files reformatted.

If both pass, the branch is ready for PR against `godot-ga-main` (use superpowers:finishing-a-development-branch).

---

## Notes for the implementer

- **Why `boil` is a brand-new verb, not a `Drink`/`Activate` override:** the engine has no `boil` action, so registering `BoilWater` under `ACTION_NAME = "boil"` adds a verb rather than shadowing one (unlike `DrinkPenn`, which intentionally overrides `drink`).
- **Scope vs. location items:** pot and stove are matched via `parser.get_items_in_scope(character)` (the convention `Activate`/`Deactivate` use — room fixtures are in scope). The water is flipped by iterating `character.location.items.values()` directly, so *all* raw water in the room is boiled in one go (deterministic regardless of which cup is drunk later).
- **`PennParser` routing:** unlike `activate`/`deactivate` (which collide with the engine's buggy `"ate "` substring check and are special-cased in `PennParser.determine_intent`), `boil` has no such collision — the default keyword match routes it. No parser change needed; `test_boil_is_registered` and the parse-command tests confirm routing.
- **Do not run any `tools/geo` script** — this change touches no map data or tmj; the props already exist in `penn_world.py`.
