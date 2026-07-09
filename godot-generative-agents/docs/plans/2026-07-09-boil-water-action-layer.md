# Boil-Water Action Layer Implementation Plan

> **Post-review rename (2026-07-09):** the shipped code uses
> `requires_boiling` + `is_boiled: False` (matching #300's phrasing) instead of
> this plan's `is_contaminated`. The pair avoids the default-False polarity trap
> (`is_boiled` alone would sicken every future drinkable). Code blocks below are
> the historical execution record — don't transcribe `is_contaminated` from them.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Penn agents their first world-mutating verbs — `drink` (contaminated water → `is_sick`), `activate`/`deactivate` (device toggles) — with props in Houston Hall, mock-brain command replay, and high-importance sickness memories, per the approved spec (`godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md`). Closes the world half of #300; engine upstreaming is tracked in #464.

**Architecture:** Backend-local `Action` subclasses in `godot-generative-agents/backend/actions.py` (same pattern as `Travel`/`Act`), registered via a new `extra_actions` parameter on `build_world`. World props placed by a `_furnish_boil_water(game)` helper in `penn_world.py`. The mock brain replays authored per-stop `commands:` from the YAML schedule. `remember_outcome` writes the sickness memory at importance 8.0. **No heat process exists — activating the stove deliberately does nothing to the water** (the #299 capability gap).

**Tech Stack:** Python 3.12, uv, pytest, PyYAML, the in-repo `text_adventure_games` engine (editable install).

## Global Constraints

- Everything runs offline under the mock brain — no API keys, no network, no LLM spend.
- Touch **only** `godot-generative-agents/` paths — never `text_adventure_games/`, root `tests/`, or root `docs/` (branch rule: this PR targets `godot-ga-main`).
- Work in a git worktree on branch `feat/boil-water-300`, cut from `godot-ga-main` (create via superpowers:using-git-worktrees). **The spec and this plan are untracked files — copy both into the worktree before the first commit.**
- The Smallville replay must stay byte-identical: existing determinism tests in root `tests/` and `godot-generative-agents/tests/` must pass unchanged.
- Format with `uv run black .` before each commit.
- All test commands run from the repo (worktree) root.
- New tests live in `godot-generative-agents/tests/test_boil_water.py` (one file, grown task by task).

## Shared test fixtures (used by Tasks 1–4)

Every task's tests import these helpers — they are written once in Task 1, at the top of `godot-generative-agents/tests/test_boil_water.py`:

```python
"""Boil-water action layer (#300): verbs, props, mock replay, memory.

Spec: godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md
"""

from backend.build_world import _normalize_personas, build_world
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

# -- a tiny two-room world, no tile map -----------------------------------
LOCATIONS = [
    {"name": "Campus", "description": "The campus green.", "address": None, "hub": True},
    {"name": "Union", "description": "The student union.", "address": None},
]


def _persona(schedule):
    return {
        "name": "Testa",
        "home": "Union",
        "persona": "I am Testa, a test persona.",
        "emoji": "🙂",
        "start_tile": [0, 0],
        "schedule": schedule,
    }


def _tiny_world(extra_actions=()):
    """(game, char) for a one-persona world with the given extra actions."""
    personas = _normalize_personas(
        [_persona([{"place": "Union", "activity": "hanging out", "steps": 5}])]
    )
    game, chars = build_world(None, personas, LOCATIONS, extra_actions=list(extra_actions))
    return game, chars["Testa"]


def _cup(contaminated=True):
    cup = Item("cup of murky water", "a cup of murky water", "Cloudy, untreated tap water.")
    cup.set_property(Property.DRINKABLE, True)
    if contaminated:
        cup.set_property("is_contaminated", True)
    return cup
```

---

### Task 1: `extra_actions` seam + `DrinkPenn` (contaminated water sickens)

**Files:**
- Modify: `godot-generative-agents/backend/build_world.py:131-207` (signature + `custom_actions`)
- Modify: `godot-generative-agents/backend/actions.py` (append `DrinkPenn`)
- Test: `godot-generative-agents/tests/test_boil_water.py` (new file)

**Interfaces:**
- Consumes: engine `consume.Drink` (`text_adventure_games/actions/consume.py:72`), `Game.log_event(actor, action, summary, payload)` (`games.py:326`).
- Produces: `build_world(world_map=None, personas=None, locations_data=None, extra_actions=None)`; class `DrinkPenn` with `ACTION_NAME = "drink"`. Later tasks import both.

- [ ] **Step 1: Commit the spec + plan docs** (first commit on the branch; copy both files into the worktree first if missing)

```bash
git add godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md godot-generative-agents/docs/plans/2026-07-09-boil-water-action-layer.md
git commit -m "docs(penn): spec + plan for the boil-water action layer (#300)"
```

- [ ] **Step 2: Write the failing tests** — create `godot-generative-agents/tests/test_boil_water.py` with the shared fixtures above, plus:

```python
from backend.actions import DrinkPenn


def test_drink_override_is_registered():
    game, _ = _tiny_world(extra_actions=[DrinkPenn])
    assert game.parser.actions["drink"] is DrinkPenn


def test_contaminated_drink_sickens_and_logs_event():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup())
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert char.get_property("is_sick") is True
    sick = [e for e in game.events if e.action == "sickness"]
    assert len(sick) == 1
    assert sick[0].payload["item"] == "cup of murky water"
    assert sick[0].payload["location"] == "Union"


def test_clean_drink_has_no_sickness():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup(contaminated=False))
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: FAIL — `ImportError: cannot import name 'DrinkPenn' from 'backend.actions'` (collection error).

- [ ] **Step 4: Add `extra_actions` to `build_world`** — in `godot-generative-agents/backend/build_world.py`, change the signature (line ~131):

```python
def build_world(
    world_map=None,
    personas: list[dict] | None = None,
    locations_data: list[dict] | None = None,
    extra_actions: list | None = None,
):
```

add one line to its docstring:

```
    ``extra_actions`` appends world-specific Action classes to the registry (the
    UPenn boil-water verbs, #300); an entry whose action_name matches a built-in
    (e.g. "drink") overrides it for this game.
```

and change the `TiledGame(...)` call (line ~200-207):

```python
        custom_actions=[Travel, Act, *(extra_actions or [])],
```

- [ ] **Step 5: Implement `DrinkPenn`** — append to `godot-generative-agents/backend/actions.py`:

```python
class DrinkPenn(consume.Drink):
    """The engine's Drink, plus the Penn boil-water twist (#300): drinking a
    liquid tagged ``is_contaminated`` sets ``is_sick`` on the drinker and logs a
    ``sickness`` GameEvent -- the measurable motivation signal the self-coding
    experiment (#299) needs. Registered with the same "drink" action name, so it
    overrides the built-in for this game only. No cure exists in this world:
    that gap is deliberate (see the spec; upstreaming tracked in #464)."""

    def apply_effects(self):
        super().apply_effects()
        if self.item.get_property("is_contaminated"):
            self.character.set_property("is_sick", True)
            self.parser.ok(
                f"{self.character.name.capitalize()} clutches their stomach -- "
                "that water was foul."
            )
            self.game.log_event(
                self.character.name,
                "sickness",
                summary=(
                    f"{self.character.name} got sick drinking {self.item.name}"
                ),
                payload={
                    "item": self.item.name,
                    "location": getattr(self.character.location, "name", None),
                },
            )
```

and add the import at the top of the file, next to the existing `base` import:

```python
from text_adventure_games.actions import base, consume
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 3 passed.

- [ ] **Step 7: Regression check + commit**

Run: `uv run pytest godot-generative-agents/tests/ -q` — expected: all pass.

```bash
uv run black godot-generative-agents/
git add godot-generative-agents/backend/actions.py godot-generative-agents/backend/build_world.py godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(backend): DrinkPenn -- contaminated water sickens the drinker (#300)"
```

---

### Task 2: `Activate` / `Deactivate` device verbs

**Files:**
- Modify: `godot-generative-agents/backend/actions.py` (append two classes)
- Test: `godot-generative-agents/tests/test_boil_water.py` (append)

**Interfaces:**
- Consumes: `base.Action` helpers (`was_matched`, `parser.match_item`, `parser.get_items_in_scope`), `_tiny_world` fixture.
- Produces: classes `Activate` (`ACTION_NAME = "activate"`) and `Deactivate` (`"deactivate"`), gating on item property `is_device`, toggling `is_on`. Task 5 imports them.

- [ ] **Step 1: Write the failing tests** — append to `test_boil_water.py`:

```python
from backend.actions import Activate, Deactivate


def _stove():
    stove = Item("stove", "a small electric stove", "A single coil burner.")
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    return stove


def test_activate_and_deactivate_toggle_a_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    game.locations["Union"].add_item(_stove())
    assert game.parser.parse_command("activate stove", actor=char)
    stove = game.locations["Union"].items["stove"]
    assert stove.get_property("is_on") is True
    # Already on: the second activate fails at the precondition gate.
    assert not game.parser.parse_command("activate stove", actor=char)
    assert game.parser.parse_command("deactivate stove", actor=char)
    assert stove.get_property("is_on") is False


def test_activate_rejects_a_non_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    pot = Item("pot", "a cooking pot", "An empty steel pot.")
    game.locations["Union"].add_item(pot)
    assert not game.parser.parse_command("activate pot", actor=char)
    assert not pot.get_property("is_on")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: FAIL — `ImportError: cannot import name 'Activate' from 'backend.actions'`.

- [ ] **Step 3: Implement both verbs** — append to `godot-generative-agents/backend/actions.py`:

```python
class Activate(base.Action):
    """Switch on a fixed device -- a stove, a sink (#300). Devices are room
    fixtures (in scope, not necessarily held), marked with ``is_device``; the
    only effect is the ``is_on`` flag. Deliberately no downstream process: the
    stove heats nothing until the self-coding experiment (#299) writes one.
    Distinct verb from the engine's Light ("turn on" alias) -- no flame here."""

    ACTION_NAME = "activate"
    ACTION_DESCRIPTION = "Switch on a device (a stove, a sink)"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch on."
        ):
            return False
        if not self.item.get_property("is_device"):
            self.parser.fail(f"The {self.item.name} isn't something you can switch on.")
            return False
        if self.item.get_property("is_on"):
            self.parser.fail(f"The {self.item.name} is already on.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_on", True)
        return self.parser.ok(f"The {self.item.name} hums to life.")


class Deactivate(base.Action):
    """Switch off a device -- the inverse of :class:`Activate`."""

    ACTION_NAME = "deactivate"
    ACTION_DESCRIPTION = "Switch off a device (a stove, a sink)"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch off."
        ):
            return False
        if not self.item.get_property("is_device"):
            self.parser.fail(f"The {self.item.name} isn't something you can switch off.")
            return False
        if not self.item.get_property("is_on"):
            self.parser.fail(f"The {self.item.name} is already off.")
            return False
        return True

    def apply_effects(self):
        self.item.set_property("is_on", False)
        return self.parser.ok(f"The {self.item.name} winds down and goes quiet.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
uv run black godot-generative-agents/
git add godot-generative-agents/backend/actions.py godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(backend): activate/deactivate device verbs (#300)"
```

---

### Task 3: Authored per-stop `commands:` — normalization, mock replay, `action_names`

**Files:**
- Modify: `godot-generative-agents/backend/build_world.py:81-113` (`_normalize_personas`)
- Modify: `godot-generative-agents/backend/smallville_agents.py:55-171` (`SmallvilleMockClient`), `:247-283` (`attach_agents`)
- Test: `godot-generative-agents/tests/test_boil_water.py` (append)

**Interfaces:**
- Consumes: `_normalize_personas`, `SmallvilleMockClient`, `attach_agents` as they exist today.
- Produces: normalized stops carry `"commands": list`; `SmallvilleMockClient._choose` replays them one per decision before `perform`; `agent.action_names` gains each authored command's verb. Tasks 5–6 rely on all three.

- [ ] **Step 1: Write the failing tests** — append to `test_boil_water.py`:

```python
from backend.smallville_agents import SmallvilleMockClient, attach_agents

COMMANDS = ["get cup of murky water", "drink cup of murky water"]


def _commands_persona():
    return _persona(
        [
            {
                "place": "Union",
                "activity": "hanging out",
                "steps": 5,
                "commands": list(COMMANDS),
            }
        ]
    )


def test_normalize_passes_commands_through():
    spec = _normalize_personas([_commands_persona()])[0]
    assert spec["schedule"][0]["commands"] == COMMANDS
    # Stops authored without commands get an empty list, uniformly.
    other = _normalize_personas(
        [_persona([{"place": "Union", "activity": "idling"}])]
    )[0]
    assert other["schedule"][0]["commands"] == []


def test_mock_brain_replays_authored_commands_then_performs():
    schedule = _normalize_personas([_commands_persona()])[0]["schedule"]
    brain = SmallvilleMockClient(schedule)
    away, here = "Campus\nThe green.", "Union\nThe union."
    assert brain._choose(away) == "travel to Union"
    assert brain._choose(here) == "get cup of murky water"
    assert brain._choose(here) == "drink cup of murky water"
    assert brain._choose(here) == "perform hanging out"
    assert brain._choose(here) == "perform hanging out"


def test_action_names_include_authored_verbs():
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    assert chars["Testa"].agent.action_names == ["travel", "perform", "drink", "get"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: the three new tests FAIL — `KeyError: 'commands'` / `AssertionError` (replay returns `perform hanging out` immediately; `action_names == ["travel", "perform"]`).

- [ ] **Step 3: Pass `commands` through normalization** — in `_normalize_personas` (`build_world.py:93-101`), add one key to the schedule-stop dict:

```python
                {
                    "place": stop["place"],
                    "activity": stop["activity"],
                    "emoji": stop.get("emoji", spec["emoji"]),
                    "steps": stop.get("steps"),  # None => stay for the rest of the day
                    # Authored one-shot commands the mock brain replays at this
                    # stop, one per decision, before settling into `perform`
                    # (#300 -- e.g. "get ..." then "drink ..." at Houston Hall).
                    "commands": list(stop.get("commands") or []),
                }
```

and in the legacy destination/activity branch (`:105-112`), add `"commands": [],` after the `"steps": None,` line.

- [ ] **Step 4: Replay in the mock brain** — in `SmallvilleMockClient`:

`__init__` (`smallville_agents.py:68-71`) gains one line after `self.stop_index = 0`:

```python
        # How many of the current stop's authored commands have been issued.
        self._commands_used = 0
```

`_choose` (`:122-125`) becomes:

```python
    def _choose(self, observation: str) -> str:
        if self._current_location(observation) != self.destination.lower():
            return f"travel to {self.destination}"
        queued = self._stop.get("commands") or []
        if self._commands_used < len(queued):
            command = queued[self._commands_used]
            self._commands_used += 1
            return command
        return f"perform {self.activity}"
```

`advance` (`:97-102`) resets the counter when it moves on:

```python
    def advance(self) -> bool:
        """Move to the next scheduled stop. Returns ``False`` if none remain."""
        if self.stop_index + 1 < len(self.schedule):
            self.stop_index += 1
            self._commands_used = 0
            return True
        return False
```

In `call_tool` (`:153-158`), generalize the reasoning line so authored verbs read sensibly:

```python
        verb, _, rest = command.partition(" ")
        if verb == "travel":
            reasoning = f"I'm on my way to {self.destination}."
        elif verb == "perform":
            reasoning = f"I've arrived, so I'll get on with {self.activity}."
        else:
            reasoning = f"While I'm here: {command}."
```

- [ ] **Step 5: Derive `action_names`** — in `attach_agents`, replace the assignment at `smallville_agents.py:264-266`:

```python
        # The verbs the structured tool may offer; the mock ignores the enum but a
        # well-formed schema keeps the seam honest for a real brain. Stops may
        # author extra one-shot commands (#300) -- offer their verbs too, so the
        # authored replay and a real brain see the same action space.
        authored_verbs = sorted(
            {
                cmd.split(" ", 1)[0]
                for stop in spec["schedule"]
                for cmd in stop.get("commands") or []
            }
        )
        agent.action_names = ["travel", "perform", *authored_verbs]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 8 passed.

- [ ] **Step 7: Regression check + commit** (the mock replay must not disturb Smallville determinism)

Run: `uv run pytest godot-generative-agents/tests/ -q && uv run pytest tests/ -q` — expected: all pass.

```bash
uv run black godot-generative-agents/
git add godot-generative-agents/backend/build_world.py godot-generative-agents/backend/smallville_agents.py godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(backend): authored per-stop commands -- mock replay + derived action_names (#300)"
```

---

### Task 4: Sickness memory — `remember_outcome` branches + `reflection.prompty`

**Files:**
- Modify: `godot-generative-agents/backend/smallville_agents.py:495-521` (`remember_outcome`)
- Modify: `godot-generative-agents/backend/prompt_templates/reflection.prompty`
- Modify: `godot-generative-agents/backend/prompt_templates/README.md` (reflection row: mention the drink/sick phrasing)
- Test: `godot-generative-agents/tests/test_boil_water.py` (append)

**Interfaces:**
- Consumes: `remember_outcome(char, command, step)`, `render("reflection", ...)`, `memory_stream_for_persona(agent)` (returns dicts with `kind`/`importance`/`text`/`created_turn`).
- Produces: drink memories — "I drank the {item} and now I feel terribly sick." at importance 8.0 when sick, 2.0 otherwise; `get`/`activate`/`deactivate` at 2.0 via the quoted fallback.

- [ ] **Step 1: Write the failing tests** — append to `test_boil_water.py`:

```python
from backend.smallville_agents import memory_stream_for_persona, remember_outcome


def _attached_char():
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    return chars["Testa"]


def test_sick_drink_is_remembered_at_high_importance():
    char = _attached_char()
    char.set_property("is_sick", True)  # DrinkPenn set this during apply_effects
    remember_outcome(char, "drink cup of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    sick = [e for e in entries if "terribly sick" in e["text"]]
    assert sick, f"no sick memory in {[e['text'] for e in entries]}"
    assert sick[-1]["importance"] == 8.0
    assert "I drank the cup of murky water" in sick[-1]["text"]


def test_clean_drink_is_remembered_at_normal_importance():
    char = _attached_char()
    remember_outcome(char, "drink cup of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    drank = [e for e in entries if e["text"] == "I drank the cup of murky water."]
    assert drank and drank[-1]["importance"] == 2.0


def test_get_is_remembered_at_normal_importance():
    char = _attached_char()
    remember_outcome(char, "get pot", 3)
    entries = memory_stream_for_persona(char.agent)
    got = [e for e in entries if e["text"] == 'I did "get pot".']
    assert got and got[-1]["importance"] == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: the three new tests FAIL — drink renders the fallback `I did "drink cup of murky water".` at importance 1.0.

- [ ] **Step 3: Extend the template** — replace `godot-generative-agents/backend/prompt_templates/reflection.prompty` in full:

```
---
name: reflection
description: >
  A persona's own successful action, recorded as a first-person observation
  memory (backend/smallville_agents.py, remember_outcome). The command verb
  selects the phrasing: arriving somewhere, doing an activity, drinking
  (with a sick variant for contaminated water, #300), or a quoted fallback
  for any other command. The memory's importance is chosen in Python (it is
  data, not text), so only the wording lives here.
inputs:
  verb:
    type: string
    description: The command verb -- "travel", "perform", "drink", or anything else.
  location:
    type: string
    description: The place arrived at (used when verb == "travel").
  activity:
    type: string
    description: What the persona is doing (used when verb == "perform").
  item:
    type: string
    description: What was drunk (used when verb == "drink").
  sick:
    type: boolean
    description: Whether this drink just sickened the persona (verb == "drink").
  command:
    type: string
    description: The raw command, quoted verbatim in the fallback (any other verb).
sample:
  verb: drink
  location: ""
  activity: ""
  item: cup of murky water
  sick: true
  command: ""
---
{%- if verb == "travel" -%}
I traveled to {{ location }}.
{%- elif verb == "perform" -%}
I am {{ activity }}.
{%- elif verb == "drink" and sick -%}
I drank the {{ item }} and now I feel terribly sick.
{%- elif verb == "drink" -%}
I drank the {{ item }}.
{%- else -%}
I did "{{ command }}".
{%- endif -%}
```

- [ ] **Step 4: Branch `remember_outcome`** — replace the body after `verb, _, rest = command.partition(" ")` (`smallville_agents.py:509-520`):

```python
    if verb == "travel":
        text = render("reflection", verb=verb, location=char.location.name)
        importance = 2.0
    elif verb == "perform":
        activity = char.get_property("activity") or rest.strip()
        text = render("reflection", verb=verb, activity=activity)
        importance = 2.0
    elif verb == "drink":
        # The contaminated-water effect (#300): DrinkPenn set is_sick during
        # apply_effects, so the sickness lands as a HIGH-importance first-person
        # memory -- the motivation signal the self-coding experiment (#299)
        # retrieves. (No cure exists in this world yet; a still-sick agent that
        # drinks again reinforces the memory, which is honest.)
        sick = bool(char.get_property("is_sick"))
        text = render("reflection", verb=verb, item=rest.strip(), sick=sick)
        importance = 8.0 if sick else 2.0
    elif verb in ("get", "activate", "deactivate"):
        # World-mutating one-shot verbs (#300): worth a normal-importance
        # memory, unlike the 1.0 catch-all below.
        text = render("reflection", verb=verb, command=command)
        importance = 2.0
    else:
        text = render("reflection", verb=verb, command=command)
        importance = 1.0
    agent.memory.add_observation(text, turn=step, importance=importance)
```

- [ ] **Step 5: Update the template README** — in `godot-generative-agents/backend/prompt_templates/README.md`, find the `reflection` row/entry and extend its description to mention the drink + sick variants (#300).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 11 passed.

- [ ] **Step 7: Commit**

```bash
uv run black godot-generative-agents/
git add godot-generative-agents/backend/smallville_agents.py godot-generative-agents/backend/prompt_templates/reflection.prompty godot-generative-agents/backend/prompt_templates/README.md godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(backend): drink outcomes in memory -- sickness at importance 8 (#300)"
```

---

### Task 5: Houston Hall props + Sofia's authored commands (the Penn wiring)

> **Amended during execution:** the original task text targeted Maya Chen in
> `backend/world_data_upenn.yaml` — but `build_penn_world()` loads
> `backend/penn/world_data_upenn.yaml` (via `WORLD_DATA`, `penn_world.py:38`),
> whose active MVP cast is Diego/Tanaka/Sofia (pinned at 3 by
> `test_penn_live.py`); Maya is commented out there. Sofia Ramirez already has a
> Houston Hall stop (her last stop of the day, no `steps`), so she carries the
> authored commands instead. Same spec requirement ("at least one persona routes
> through the room"), corrected file + persona.

**Files:**
- Modify: `godot-generative-agents/backend/penn/penn_world.py` (furnish helper + `build_world_fn`)
- Modify: `godot-generative-agents/backend/penn/world_data_upenn.yaml:239-240` (Sofia's Houston Hall stop)
- Test: `godot-generative-agents/tests/test_boil_water.py` (append)

**Interfaces:**
- Consumes: `build_penn_world()` (`penn_world.py:266`), `build_world(..., extra_actions=...)` (Task 1), `Activate`/`Deactivate` (Task 2), `DrinkPenn` (Task 1).
- Produces: `PENN_EXTRA_ACTIONS` list and `_furnish_boil_water(game)` in `penn_world.py`; Houston Hall stocked with sink/stove/pot/two cups on every Penn build (bake, live server, tests). Task 6 reuses both.

- [ ] **Step 1: Write the failing tests** — append to `test_boil_water.py`:

```python
from backend.penn.penn_world import build_penn_world


def test_houston_hall_is_stocked_and_the_scenario_plays():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    hall = game.locations["Houston Hall"]
    for name in ("sink", "stove", "pot", "cup of murky water", "second cup of murky water"):
        assert name in hall.items, f"{name} missing from Houston Hall"
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    assert game.parser.parse_command("get cup of murky water", actor=sofia)
    assert game.parser.parse_command("drink cup of murky water", actor=sofia)
    assert sofia.get_property("is_sick") is True
    assert any(e.action == "sickness" for e in game.events)
    # The withheld gap (#299): the stove turns on, and nothing heats.
    assert game.parser.parse_command("activate stove", actor=sofia)
    assert hall.items["second cup of murky water"].get_property("is_contaminated") is True


def test_sofias_houston_hall_stop_carries_the_commands():
    pw = build_penn_world()
    sofia = next(p for p in pw.personas if p["name"] == "Sofia Ramirez")
    stop = next(s for s in sofia["schedule"] if s["place"] == "Houston Hall")
    assert stop["commands"] == ["get cup of murky water", "drink cup of murky water"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: both FAIL — `sink missing from Houston Hall` and `stop["commands"] == []`.

- [ ] **Step 3: Furnish + register in `penn_world.py`** — add imports (match the file's existing import style — relative `..` if that is what the file uses):

```python
from backend.actions import Activate, Deactivate, DrinkPenn
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item
```

add near the top of the module:

```python
# The Penn-local verb set (#300): registered on top of Travel/Act via
# build_world(extra_actions=...). DrinkPenn overrides the engine's "drink".
# Upstreaming these into the engine library is #464.
PENN_EXTRA_ACTIONS = [Activate, Deactivate, DrinkPenn]
```

add the furnish helper above `build_penn_world`:

```python
def _furnish_boil_water(game) -> None:
    """Stock Houston Hall with the boil-water props (#300).

    The first Item instances in the Penn world: two contaminated cups (drink one
    and DrinkPenn makes you sick), a pot, and two fixed devices. Activating the
    stove sets ``is_on`` and deliberately nothing else -- no heat process exists;
    that capability gap is the point of the self-coding experiment (#299)."""
    hall = game.locations.get("Houston Hall")
    if hall is None:
        return
    sink = Item("sink", "a utility sink", "An old utility sink. The tap runs cloudy.")
    sink.set_property(Property.GETTABLE, False)
    sink.set_property("is_device", True)
    stove = Item("stove", "a small electric stove", "A single coil burner, dusty but working.")
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    pot = Item("pot", "a cooking pot", "An empty steel pot. It could hold water.")
    for name in ("cup of murky water", "second cup of murky water"):
        cup = Item(name, "a cup of murky water", "Cloudy, untreated tap water.")
        cup.set_property(Property.DRINKABLE, True)
        cup.set_property("is_contaminated", True)
        hall.add_item(cup)
    hall.add_item(sink)
    hall.add_item(stove)
    hall.add_item(pot)
```

and in `build_penn_world` (`:289-301`), replace the `build_world_fn=lambda wm: ...` line with a named closure defined just above the `return PennWorld(...)`:

```python
    def _build(wm):
        game, characters = build_world(
            wm, personas, locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return _gate_conversations_by_perception((game, characters))
```

and pass `build_world_fn=_build,` in the `PennWorld(...)` constructor call.

- [ ] **Step 4: Author Sofia's commands** — in `godot-generative-agents/backend/penn/world_data_upenn.yaml`, extend her Houston Hall stop (lines 239-240; it has no `emoji`/`steps` — add only the `commands:` block, preserving the file's 2-space list indentation):

```yaml
  - place: Houston Hall
    activity: meeting friends for dinner
    commands:
    - get cup of murky water
    - drink cup of murky water
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 13 passed.

- [ ] **Step 6: Regression check + commit** (the Penn live/replay tests build this world)

Run: `uv run pytest godot-generative-agents/tests/ -q` — expected: all pass.

```bash
uv run black godot-generative-agents/
git add godot-generative-agents/backend/penn/penn_world.py godot-generative-agents/backend/penn/world_data_upenn.yaml godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(penn): boil-water props in Houston Hall + Sofia's murky-water commands (#300)"
```

---

### Task 6: End-to-end acceptance — a mock-brain run drinks, sickens, remembers

> **Amended during execution:** the acceptance test exposed a latent defect —
> `attach_agents` commits every schedule through the engine's `planning.Stop`
> round-trip (`smallville_agents.py:353-354` → `to_schedule_entry`,
> `planning.py:68`), which doesn't carry the `commands` field, so authored
> commands were silently dropped before the mock brain saw them. Engine files
> are off-limits on this branch, so the fix is backend-local:
> `SmallvilleMockClient.replace_schedule` carries the current stop's authored
> `commands` onto an incoming entry at the same index that matches on
> (place, activity) and has none of its own — healing the attach-time
> round-trip while leaving genuinely new planner stops command-less. Round-trip
> support in the engine `Stop` joins the #464 upstreaming list.

**Files:**
- Modify: `godot-generative-agents/backend/smallville_agents.py` (`replace_schedule` carry-over)
- Test: `godot-generative-agents/tests/test_boil_water.py` (append)

**Interfaces:**
- Consumes: `simulate(world_map, num_steps, personas=..., build_world_fn=..., out_memories=...)` (`run_simulation.py:315`), `PENN_EXTRA_ACTIONS`, `_furnish_boil_water`, `build_penn_world` (Task 5).
- Produces: the #300 acceptance test, pinned.

- [ ] **Step 1: Write the failing-then-passing acceptance test** — append:

```python
from backend.penn.penn_world import PENN_EXTRA_ACTIONS, _furnish_boil_water
from backend.run_simulation import simulate


def test_end_to_end_mock_run_agent_drinks_and_gets_sick():
    """#300 acceptance: in a mock-brain run, an agent drinks, gets sick, and the
    high-importance observation lands in its memory stream."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Sip",
        "home": "Houston Hall",
        "persona": "I am Testa Sip, a thirsty test persona.",
        "emoji": "🥤",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "getting a drink of water",
                "emoji": "🥤",
                "steps": 3,
                "commands": ["get cup of murky water", "drink cup of murky water"],
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
    simulate(pw.world_map, 10, personas=personas, build_world_fn=build_fn,
             out_memories=memories)
    stream = memories["Testa Sip"]
    sick = [m for m in stream if "terribly sick" in m["text"]]
    assert sick, f"no sickness memory in {[m['text'] for m in stream]}"
    assert sick[0]["importance"] == 8.0
```

- [ ] **Step 2: Run it**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -v`
Expected: 14 passed. (If `memories["Testa Sip"]` is missing or the sick memory absent, debug via superpowers:systematic-debugging — the likely seams are `action_names` gating in `LLMAgent.decide` and the `out_memories` key shape — before touching any implementation.)

- [ ] **Step 3: Full verification + commit**

Run: `uv run pytest godot-generative-agents/tests/ -q && uv run pytest tests/ -q && uv run black --check .`
Expected: all pass, black clean.

```bash
git add godot-generative-agents/tests/test_boil_water.py
git commit -m "test(penn): end-to-end mock acceptance -- drink, sicken, remember (#300)"
```

---

### Task 7: PR to `godot-ga-main`

**Files:** none (git/GitHub only).

- [ ] **Step 1: Push the branch** (HTTPS with `gh` as credential helper — SSH keys aren't loaded)

```bash
git push -u origin feat/boil-water-300
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --base godot-ga-main --title "Boil-water action layer: first Penn verbs + Houston Hall props" --body "$(cat <<'EOF'
Implements the world half of #300 per the approved spec
(`godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md`).

- **Verbs (backend-local):** `DrinkPenn` (contaminated water → `is_sick` + a
  `sickness` GameEvent), `Activate`/`Deactivate` device toggles. Engine
  upstreaming is deliberately deferred to #464, pending the #446 verb-API
  discussion.
- **World:** Houston Hall stocked with sink/stove/pot/two contaminated cups —
  the first Items in the Penn world. Sofia's dinner stop now gets-and-drinks.
- **Mock replay:** schedule stops may author one-shot `commands:`; the mock
  brain replays them, so the scenario runs offline and deterministically.
- **Memory:** sickness lands at importance 8.0 ("I drank the cup of murky water
  and now I feel terribly sick.") — the #299 motivation signal.
- **The withheld gap:** the stove turns on; nothing heats. No agent can boil
  water — that's the point (#299/#301).

Closes #300. Refs #446, #464, #299.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Verify PR CI / report back** — confirm the PR page renders, the diff touches only `godot-generative-agents/`, and report the URL.

---

## Self-review notes

- Spec §1–§7 each map to a task: §1→1–2, §2→5, §3→3, §4→4, §5→1–6, §6→(issue #464 already filed; PR body links), §7→docs committed in Task 1.
- Type consistency checked: `extra_actions` (Tasks 1/5/6), `PENN_EXTRA_ACTIONS`, `_furnish_boil_water`, `commands` key, `is_device`/`is_on`/`is_contaminated`/`is_sick` strings are identical across tasks.
- Known judgment points for the executor, flagged intentionally: import style in `penn_world.py` (match the file), the README wording in Task 4 Step 5, and the Task 6 debug note.
