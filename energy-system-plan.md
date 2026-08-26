# Energy/food system — implementation plan for Action Castle

## 1. Energy bar — where does it live?

Add it in `things/characters.py`, `Character.__init__` (line 70-137). Right
after line 75 (`self.set_property(Property.IS_DEAD, False)`), add:

```python
self.set_property(Property.ENERGY, DEFAULT_ENERGY)
```

And in `enums.py`, add `ENERGY = "energy"` to the `Property` enum (near line
56, alongside `IS_HUNGRY`). Add `DEFAULT_ENERGY = 50` as a module constant in
`characters.py` near the existing `MAX_ACTIONS_PER_TURN`/`DEFAULT_VISION_R`
constants (line 26) — that's the file's existing convention for tunable
defaults. This makes energy exist on every character for free — no
per-adventure wiring needed. Serialization (`to_primitive`/`from_primitive`)
is generic over `self.properties`, so it round-trips automatically.

## 2. Per-action deduction

There's no universal `apply_effects` wrapper — every `Action` subclass
overrides it independently. The real hook is `Game.do_command()` in
`games.py`, in the `if success:` block (~line 316-338), which already
special-cases `FREE_ACTION` (Inventory/Help don't cost a turn). Mirror that
pattern: follow the existing `DURATION`/`get_duration()` precedent on
`Action` (`actions/base.py` line 97, 111-117) and add an analogous
`ENERGY_COST` class attr + `get_energy_cost()` method, defaulting to some flat
cost (e.g. 1), then deduct it in `do_command`'s success branch — skip the
deduction for `FREE_ACTION`s the same way turn-cost is skipped.

## 3. Per-turn deduction — agreed, simpler for Action Castle

`Game.end_turn()` (games.py 369-390) already loops every living character.
Add a flat decrement there (e.g. -1 energy per turn for everyone, or scale by
`self.clock.minutes_per_turn` if you want it time-based later). This is the
lowest-effort option and doesn't require touching the action dispatch path at
all — start here today and treat per-action cost (#2) as a stretch goal.

## 4. Is there an `is_food` property?

No — confirmed no `IS_FOOD`/`FOOD` member exists, and Action Castle has zero
food/drink items today (no apple, no ale — only `Property.EDIBLE`/`DRINKABLE`
exist as generic affordances, used elsewhere like
`tomb_of_nassak_an_rah.py`). The troll's `is_hungry=True` currently has
nothing to eat to fix it. You'll need to:

1. Create a new `Item` (e.g. `bread = things.Item("bread", "a loaf of bread")`)
2. `bread.set_property(Property.EDIBLE, True)`
3. Add a restore amount via a plain string property since `Property` is an
   intentionally open set per its docstring — e.g.
   `bread.set_property("energy_value", 30)`

Then in `Eat.apply_effects` (`actions/consume.py` line 43-69), after line 52,
read it back:

```python
self.character.set_property(
    Property.ENERGY,
    min(100, current + item.get_property("energy_value")),
)
```

## 5. Which class to edit to create the property?

`Character.__init__` in `things/characters.py` (default value) + `Property`
enum in `enums.py` (the name). Nothing else needs touching for storage —
`Thing.properties` (base.py) is a generic `defaultdict(bool)` already.

## Test scaffold

`tests/test_energy.py` — plain `test_*` functions + `pytest.fixture`,
matching the `tiny_game` convention in `test_triggers.py`/`test_time_model.py`
(no `unittest.TestCase`, bare `assert`). Covers: default energy on
construction, eating restores energy (capped at 100, gated on `EDIBLE`),
per-turn decay via `end_turn()` (floored at 0), and NPC decay symmetry. Two
stretch tests for per-action cost are `@pytest.mark.skip`'d until #2 is
implemented.
