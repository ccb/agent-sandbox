# Feature Roadmap

> **Status (2026-08-04):** four of the five features below **shipped** — the
> turn-based loop with NPC actions (`games.py`, `turns.py`), the LLM parser
> (landed as `llm_parser.py`, with the client in `llm_client.py` rather than the
> proposed `llm.py`), the time model (`clock.py`), and the event/trigger system
> (`events.py`, `triggers.py`). Feature 2 (LLM-generated descriptions) remains
> unbuilt. Each feature's "Current state" paragraph describes the **June 2026**
> engine it was planned against, not today's — this file is kept as the original
> spec; see [`AGENT-ARCHITECTURE.md`](AGENT-ARCHITECTURE.md) for the present.

This document outlines planned features for the text adventure framework, in rough dependency order. Each feature builds on the framework's existing architecture: the `Game` loop in `games.py`, the `Action` system (`check_preconditions()` → `apply_effects()`), the `Parser` routing pipeline, and the `Thing` hierarchy (`Location`, `Item`, `Character`).

---

## 1. Turn-Based Game Loop with NPC Actions

**Goal:** Transform the game from a single-player command loop into a turn-based system where all characters — player and NPCs — take actions each round.

**Current state:** The game loop (`Game.game_loop()`) is a tight `while True` that reads player input via `input()`, parses it, and checks game-over. There is no turn counter, no post-command hook, and NPCs are pure data containers with no behavioral logic.

### Design

Restructure the game loop into discrete rounds:

1. **Add `self.turn` counter** to `Game.__init__`, incremented each round.
2. **Introduce a round structure** in `game_loop()`:
   - Player turn: prompt for input, parse command (as today).
   - NPC turn: iterate over all non-player characters and call `character.take_turn(game)`.
   - Post-round: increment turn counter, check game-over and auto-triggers (see Feature 5).
3. **Add `Character.take_turn(game)`** method. The base implementation is a no-op (backward compatible). Subclasses or per-character behavior functions override it.

### NPC Behavior via ReAct Loop

For LLM-driven NPCs, `take_turn()` runs a ReAct (Reason + Act) loop:

1. **Observe:** Build a prompt from the character's `persona`, current `location.describe()`, visible items/characters, and recent `game_history` entries.
2. **Think:** Ask the LLM what the character should do and why, given their persona and goals.
3. **Act:** The LLM's chosen action is routed through the same `parser.parse_command()` pipeline (or directly instantiated as an `Action`), ensuring `check_preconditions()` gates the behavior.
4. **Reflect:** If preconditions fail, feed the failure message back to the LLM for a retry (with a cap of 2-3 attempts per turn to prevent infinite loops).

This reuses the existing pattern where actions can spawn other actions programmatically (e.g., `Give` instantiates `Eat` on the recipient), but generalized to any NPC decision.

### Key decisions

- **Action budget per NPC turn:** Allow 1 action per NPC per round (simple), or allow multi-step plans (complex). Start with 1.
- **Visibility of NPC actions:** NPC actions should produce `parser.ok()` messages visible to the player, narrated in third person ("The troll picks up the fish and devours it").
- **Ordering:** Player always acts first in a round. NPC order could be fixed (registration order) or randomized.
- **Non-LLM NPCs:** Support scripted behavior via simple callables (`Callable[[Character, Game], None]`) assigned to `character.behavior`, so not every NPC requires an LLM call.

### Files to modify

- `games.py` — round-structured loop, turn counter
- `things/characters.py` — `take_turn()` method, optional `behavior` attribute
- New file: `npc.py` or `agents.py` — ReAct loop implementation, prompt templates

---

## 2. LLM-Generated Descriptions

**Goal:** Use an LLM to generate rich, atmospheric descriptions of locations and objects based on their underlying properties, rather than relying solely on static strings.

**Current state:** Every `Thing` has a `description` (short) and optionally `examine_text` (long, items only). `Game.describe()` manually assembles room descriptions by concatenating location name, description, exits, items, and characters. The existing `GptParser.ok()` already rewrites final output through an LLM narrator, but it operates on the pre-assembled string — it can't reason about individual properties.

### Design

Introduce a description generation layer that sits between the raw game state and the output pipeline:

1. **Property-aware prompt construction:** Instead of passing the pre-assembled description string to an LLM, pass structured data — the location's name, its `properties` dict, its items (with their properties), its characters (with their properties and emotional states), exits, and any relevant recent history.
2. **`Thing.generate_description(context)`** method that calls the LLM with a prompt like: *"You are describing a {thing.name} in a text adventure. Its properties are: {properties}. Nearby: {context}. Write a 2-3 sentence atmospheric description."*
3. **Caching:** Generated descriptions should be cached (keyed on a hash of the relevant properties) so the LLM isn't called on every `look` command if nothing has changed. Invalidate cache when properties change.
4. **Layered approach:**
   - **Static base:** Keep `description` and `examine_text` as optional static overrides for game authors who want full control.
   - **Generated layer:** If no static description is set (or if a flag enables it), generate dynamically from properties.
   - **Narrator layer:** The existing `GptParser.ok()` rewriting can still apply on top for stylistic flair.

### Property feedback loop (optional, advanced)

Allow the LLM's generated descriptions to propose new properties:

1. Ask the LLM to return structured JSON alongside the prose: `{"description": "...", "suggested_properties": {"mossy": true, "dimly_lit": true}}`.
2. The game author can configure which properties are "open" (can be elaborated by the LLM) vs. "closed" (fixed by game logic).
3. Suggested properties are stored and influence future descriptions, creating an evolving world.

This must be carefully gated — LLM-suggested properties should never override mechanically significant properties (e.g., `is_locked`, `is_dead`) without explicit game logic.

### Key decisions

- **When to generate:** On first visit only? Every visit? On `examine` only? Recommend: generate on first visit, cache, regenerate on property change.
- **Cost control:** LLM calls are expensive. Batch location + item descriptions into a single call where possible. Use a small/fast model for descriptions.
- **Tone consistency:** Provide a game-level system prompt that sets the tone (e.g., "whimsical fairy-tale" for Action Castle, "grim noir" for a detective game). Store on `Game` as `self.narrator_style`.

### Files to modify

- `things/base.py` — `generate_description()` method, description cache
- `games.py` — `describe()` to use generated descriptions, narrator style config
- New file: `llm.py` — shared LLM calling utilities (model config, prompt templates, caching)

---

## 3. LLM-Based Command Parser

**Goal:** Replace the brittle keyword-matching parser with an LLM-powered intent resolver that understands natural language while preserving the precondition/effect action system.

**Current state:** `Parser.determine_intent()` is a cascade of `elif` keyword checks (e.g., `"take " in command` → `"get"`, `"attack" in command` → `"attack"`). Custom actions fall through to a loop that checks if any `ACTION_NAME` appears as a substring of the command. The `GptParser` (in `hw2_solution/`) already demonstrates the pattern — it overrides `determine_intent()`, `get_character()`, `match_item()`, and `get_direction()` to use `gpt_pick_an_option()`.

### Design

Build on the `GptParser` pattern but make it more robust and integrated:

1. **`LLMParser` class** extending `Parser`, overriding the same four methods:
   - `determine_intent(command)` — present the LLM with all available actions (their `ACTION_NAME` and `ACTION_DESCRIPTION`) plus the player's command. The LLM picks the best match or returns "none".
   - `match_item(command, item_dict, hint)` — present candidate items with descriptions; LLM picks.
   - `get_character(command, hint)` — present candidate characters; LLM picks.
   - `get_direction(command, location)` — present available exits; LLM picks.

2. **Preconditions remain hard-gated:** The LLM only resolves *which* action/item/character/direction the player meant. Once resolved, the normal `Action.__call__()` pipeline runs — `check_preconditions()` can still reject the action, and `apply_effects()` only runs if preconditions pass. The LLM never bypasses game logic.

3. **Disambiguation and clarification:** When the LLM is uncertain (e.g., "use the thing on the other thing"), instead of guessing, have it generate a clarifying question via `parser.fail("Did you mean X or Y?")`.

4. **Fallback chain:** Try keyword matching first (fast, free). If no match, fall back to LLM. This reduces LLM calls for unambiguous commands like `look`, `inventory`, `go north`.

### Improvements over existing GptParser

- **Structured output:** Use JSON mode or function calling instead of regex-parsing a number from free text. More reliable than `gpt_pick_an_option()`'s `r"\d+"` regex.
- **Context-aware matching:** Include the player's location, inventory, and recent history in the prompt so the LLM can resolve ambiguous references ("use it" → the item mentioned two commands ago).
- **Action aliases in prompts:** Include `ACTION_ALIASES` in the action descriptions so the LLM knows that "hit" and "strike" map to "attack".

### Key decisions

- **Latency:** LLM calls add 500ms-2s per command. The fallback chain (keyword first) mitigates this for common commands.
- **Model choice:** Use a small, fast model (e.g. Haiku) for parsing — it doesn't need to be creative, just accurate at classification.
- **Offline mode:** Keep the keyword parser as a fully functional fallback for when no API key is configured or for testing.

### Files to modify

- `parsing.py` — refactor `determine_intent()` to be more easily overridable
- New file: `llm_parser.py` — `LLMParser` class
- `llm.py` (from Feature 2) — shared LLM utilities

---

## 4. Time Tracking

**Goal:** Add a time system so the game world can change based on elapsed turns, enabling timed puzzles, NPC schedules, and environmental changes.

**Current state:** There is no concept of time. `game_history` is an unindexed list of messages. The game loop has no turn counter.

### Design

Introduce a lightweight time model:

1. **`Game.turn`** — integer, incremented once per round (after all characters have acted). Added in Feature 1's loop restructuring.

2. **`Game.clock`** — optional in-game time representation. Could be:
   - **Simple:** Just the turn counter. "Turn 1", "Turn 2", etc.
   - **Clock-based:** Map turns to in-game hours. E.g., game starts at 8:00 AM, each turn = 15 minutes. Configurable via `Game.time_config = {"start_hour": 8, "minutes_per_turn": 15}`.
   - **Period-based:** Divide time into named periods ("dawn", "morning", "afternoon", "dusk", "night") that change every N turns.

3. **Time-aware descriptions:** Pass the current time/period to the description generator (Feature 2). A location described at night looks different than at noon.

4. **`Game.schedule`** — a list of `(turn_number, callback)` pairs for scheduled events. The post-round phase checks for and fires any events whose turn has arrived. This feeds directly into Feature 5 (auto-triggered actions).

### Key decisions

- **Granularity:** Start with simple turn counting. Add clock mapping later if games need it.
- **Time display:** Show "Turn N" (or the in-game time) in the prompt or status line.
- **Backward compatibility:** Time tracking is opt-in. If `Game.time_config` is `None`, the turn counter still increments but no clock is displayed.

### Files to modify

- `games.py` — `turn` counter, `clock` property, `schedule` list, time config
- `things/locations.py` — optional time-of-day property for descriptions

---

## 5. Auto-Triggered Actions

**Goal:** Allow actions to fire automatically when preconditions are met — on a timer, when someone enters a location, when a property changes, or on arbitrary conditions.

**Current state:** The closest analog is the `Block` system: `Block.is_blocked()` is a condition checked on every movement attempt. But blocks are read-only checks — they prevent movement, they don't cause effects. There is no event system or trigger mechanism.

### Design

Introduce a `Trigger` system that runs in the post-round phase of the game loop:

```
class Trigger:
    name: str
    condition: Callable[[Game], bool]
    action: Callable[[Game], None]
    repeatable: bool = False       # fire once or every time condition is met
    fired: bool = False
```

**The post-round phase** (added in Feature 1) iterates over all registered triggers:

```python
for trigger in self.triggers:
    if not trigger.fired or trigger.repeatable:
        if trigger.condition(self):
            trigger.action(self)
            trigger.fired = True
```

### Trigger types (built-in condition helpers)

1. **Timer trigger:** `condition = lambda game: game.turn >= N` — fires when turn N is reached. Variant: `game.turn % N == 0` for recurring events.
2. **Location trigger:** `condition = lambda game: character in location.characters` — fires when a specific character enters a location. Useful for ambushes, cutscenes, NPC dialogue.
3. **Property trigger:** `condition = lambda game: thing.get_property("is_X")` — fires when a property becomes true. E.g., when a door is unlocked, a guard is alerted.
4. **Compound triggers:** Combine conditions with `and`/`or`. E.g., "if the player is in the throne room AND has the crown AND the guard is unconscious".

### Trigger actions

Trigger actions can be:

- **Direct effects:** Arbitrary callables that mutate game state and call `parser.ok()` to narrate what happened.
- **Existing actions:** Instantiate and call an `Action` subclass (e.g., an NPC automatically attacks when the player enters their room). This reuses `check_preconditions()` — if the preconditions aren't met at fire time, the trigger action is suppressed.

### Relationship to other features

- **Feature 1 (NPC turns):** NPC behavior *is* a kind of trigger ("on this NPC's turn, run the ReAct loop"), but it runs in the NPC phase rather than the post-round phase. Keep them separate — NPC turns are per-character, triggers are global.
- **Feature 4 (time):** Timer triggers depend on the turn counter from Feature 4.
- **Feature 2 (descriptions):** A trigger could update a location's properties (e.g., `location.set_property("is_flooded", True)` after a timer), which in turn changes the generated description.

### Key decisions

- **Evaluation order:** Triggers fire after all characters have acted, so they see the fully updated world state for that round.
- **Cascading:** A trigger's action might cause another trigger's condition to become true. Support one level of cascading (re-evaluate after firing), but cap at a fixed depth to prevent infinite loops.
- **Registration API:** `game.add_trigger(name, condition, action, repeatable=False)` — simple enough for game authors to use in their `build_game()` functions.

### Files to modify

- New file: `triggers.py` — `Trigger` class and built-in condition helpers
- `games.py` — trigger registration, post-round evaluation phase

---

## Dependency Graph

```
Feature 4 (Time Tracking)
    |
    v
Feature 1 (Turn-Based Loop + NPC Actions)
    |           \
    v            v
Feature 5    Feature 3
(Triggers)   (LLM Parser)
    |
    v
Feature 2 (LLM Descriptions)
```

**Recommended implementation order:**

1. **Time Tracking** (Feature 4) — smallest change, adds `turn` counter, no dependencies.
2. **Turn-Based Loop** (Feature 1) — restructures game loop, adds NPC phase. Depends on turn counter.
3. **Auto-Triggered Actions** (Feature 5) — adds post-round trigger evaluation. Depends on structured loop.
4. **LLM Parser** (Feature 3) — independent of the above, but benefits from the shared `llm.py` utilities.
5. **LLM Descriptions** (Feature 2) — most ambitious, benefits from time-awareness and triggers that change properties.

Features 3 and 4-5 can be developed in parallel since they touch different parts of the system.
