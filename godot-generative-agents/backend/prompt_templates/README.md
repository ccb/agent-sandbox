# Prompt templates (generative-agents)

The generative-agents port's agent-generated text lives here as
[Prompty](https://prompty.ai) files (`.prompty`): YAML frontmatter (name,
description, documented inputs, a sample) followed by a
[Jinja2](https://jinja.palletsprojects.com/) template body. Keeping these here —
in the codebase, under version control — means each is one reviewable artifact
you can diff in a pull request, not an f-string spread across a function. There
is deliberately **no external prompt database or hosted service**: changing one
is a normal code change. (Part of
[#145](https://github.com/ccb/agent-sandbox/issues/145); mirrors the engine's own
`text_adventure_games/prompt_templates/`.)

Most of these are **not** live model prompts — by default the port drives every
persona with a deterministic mock (`cognition.ScheduleMockClient`) that
ignores the prompt, so what `plan_memory` / `reflection` / `spatial_knowledge`
hold is the agent's generated **memory and belief text**: the day's plan, the
first-person record of each action, and the places it knows up front.

The exception is **`plan_system`**: a real model system prompt for the optional
LLM daily planner (`planner.LLMPlanner`, issue #83), which only runs when a live
client is wired in. It is templated here for the same reason — one reviewable
artifact, no hosted prompt service.

## How they are rendered

`__init__.py` exposes one function:

```python
from backend.prompt_templates import render

text = render("reflection", verb="travel", location="Hobbs Cafe")
belief = render("spatial_knowledge", place="Johnson Park", areas="")
```

`render(name, **variables)` loads `<name>.prompty`, renders its Jinja2 body with
`variables`, and returns the resulting string. It uses Prompty's *render* step
only — not `prompty.prepare`/`execute` — because nothing here calls a model: the
rendered string is stored straight into the agent's memory/knowledge. A variable
the template doesn't reference is ignored; one left unset renders as empty.

## Where each template is used

Each is rendered from exactly one place. **Keep this table in sync when you add,
rename, remove, or re-wire a template.**

| Template | Rendered by | Used for |
| --- | --- | --- |
| `plan_memory.prompty` | `cognition.py` — `attach_agents()` | The day's PLAN memory seeded onto each persona at t=0: `Plan: go to <destination> and <activity>.`, plus `Today's stops: <itinerary>.` when the whole-day itinerary is given (#83). |
| `public_event.prompty` | `cognition.py` — `attach_agents()` | An announced public happening (a world YAML's validated `events:` entry) seeded as a t=0 observation into every agent's memory except the host's (#795): `There's <label> at <at> <when>, hosted by <host>. It's open to anyone.` — the `, hosted by <host>` clause drops when the event has none. Only reached when a real planner client is wired in; the mock replay never seeds it. |
| `reflection.prompty` | `cognition.py` — `remember_outcome()` / `remember_decide_timeout()` | A persona's own action, as a first-person observation memory: `I traveled to <place>.` / `I was <activity>.` (#851 — past tense like every other branch; this records a *finished* action, and #826's `recent_actions` block replays it under a "how long ago" prefix, so a present-tense "I am ..." told the agent its completed activity was still running) / `I drank the <item>.` (with sick / recovered variants for drinking contaminated vs. boiled water, #300) / `I boiled the water to make it safe to drink.` / `I waited; nothing needed doing.` (settled wait, #614) / `I went to talk to <person> about <topic>.` / `I went to talk to <person>.` (agent-initiated talk_to, #614) / `I studied <topic> for <N> minutes.` (#615) / `I ate the <item>.` (#615; deliberately hunger-neutral — the engine's `eat` clears `IS_HUNGRY` whether or not the persona was hungry, so a "no longer hungry" claim could be a false memory) / `I checked out <book> from the library.` (#616) / `I read <book>. It said: "<content>"` (#616) / `I did "<command>".` / `I tried to "<command>" but it didn't work: <reason>` (a failed/blocked attempt, #636; the `: <reason>` clause is dropped when the parser left no message) / `I was thinking about what to do at <place> but couldn't decide in time.` (a timed-out decide, #758; the `at <place>` clause is dropped when the persona stands nowhere) |
| `spatial_knowledge.prompty` | `seed.py` — `seed_spatial_knowledge()` | One place a persona knows up front (a Belief): `You know <place> — its <areas>.` / `You know <place>.` |
| `relationship_memory.prompty` | `seed.py` — `relationship_statements()` | One seeded relationship a persona starts the day knowing (#779), from its own side of the edge: `I know <other>: <kind>. <closeness sentence> <description>` — e.g. `I know Bethany Cole: rivals. We know each other a little. Omar and Bethany are the two front-runners…`. The `kind`, closeness sentence, and `description` clauses each drop when the edge left them blank. |
| `commitment_memory.prompty` | `cognition.py` — `apply_conversation_outcome()` | The commitment a finished conversation produced, as a first-person PLAN memory in that participant's stream (#778): `I agreed with <other>: <commitment>` — e.g. `I agreed with Chris Donnelly: Pizza place near campus with Chris Donnelly in about 20 minutes`. Written only when the #582 outcome pass reports `plans_changed: true` with a non-blank `commitment`; the transcript is never used as a fallback. Memory text, not a live model prompt. |
| `plan_system.prompty` | `planner.py` — `LLMPlanner._call()` (day / hourly / minute / revise) | **Real model prompt.** System message for the optional LLM daily planner (#83): plan one day in character for a Penn campus resident. The per-level user message is assembled in code, and it grounds every level with the run's clock window and retrieved memory (#795); the minute level's `minute_plan` tool asks for durations in minutes (not sim steps) — `LLMPlanner` converts once via `SimClock.steps_for_seconds`, so `Stop.steps` stays the internal unit. |
| `decide_context.prompty` | `cognition.py` — `decide_context_block()`, folded into `observe_and_decide`'s observation when the step loop threads a `SimClock` (#580) | **Real model prompt context.** The always-on decide slice: `Right now it is <time>.` + the plan's current stop (with planned minutes) + `This has been your current stop for <N> min.` Deliberately not "you have been here": an agent that wanders off-plan never arrives, nothing re-anchors the clock, and the stop it is neglecting keeps counting (#826) — so the second phrasing would be false for exactly the agent the sentence exists to warn. Appended after the environment text, so the deterministic mock never reads it. |
| `recent_actions.prompty` | `cognition.py` — `recent_actions_block()`, folded into `observe_and_decide`'s observation when the step loop threads a `SimClock` (#826) | **Real model prompt context.** The agent's own last few actions, newest first: `Recently, you:` + ` - <N> min ago: <memory text>` per action (`just now` under a minute). A guarantee rather than a retrieval bid — `retrieve(touch=True)` keeps refreshing high-importance commitment memories while the agent's own 2.0 outcome records decay out of contention, so an agent could otherwise read only its intentions and re-form them at every arrival. Appended after the environment text; the deterministic mock never reads it. |
| `walk_minutes.prompty` | `cognition.py` — `walk_minutes_line()`, folded into `observe_and_decide`'s observation when the step loop threads a `SimClock` and the world has a map (#826) | **Real model prompt context.** What a walk costs from where the agent stands: `Walking from here takes at least about: <name> <N> min; …`, nearest first, including the place it is already in at 0 min. Penn legs run ~57 sim-minutes but the exits list prices them all alike, so "quick" errands were free. A Chebyshev lower bound over precomputed bounding boxes (`WorldMap.tile_gap_from`) — it ignores walls and under-reports ~2×, hence "at least about". Appended after the environment text; the deterministic mock never reads it. |
| `nearby_affordances.prompty` | `cognition.py` — `nearby_affordances_line()`, appended into `observe_and_decide`'s observation on the real-brain tool path (#613) | **Real model prompt context.** One line naming visible-but-distant arenas + the affordance tags they carry (`Nearby, worth traveling to: <name> (<tags>); …`), so the brain can travel toward an affordance. Never widens the toolset; the deterministic mock never reads it. |
| `conversation_outcome.prompty` | `cognition.py` — `apply_conversation_outcome()` | **Real model prompt.** Presents a finished conversation's transcript and asks the participant, via the `conversation_outcome` tool, whether it changed their plans, when a concrete commitment starts, and whether the other person is worth remembering (#582/#829). `immediate` is reserved for an agreement to begin as soon as playback ends; it is a behavioral promise that may preempt the current activity, not a synonym for importance. Only reached when a real brain drove an actual conversation. |
| `importance_score.prompty` | `cognition.py` — `score_new_memories()` | **Real model prompt.** Lists a batch of an agent's newly-formed memories and asks, via the `score_memories` tool, for a 1-10 poignancy score each (#583). Only reached when a real brain is driving; the scores override the hardcoded importance constants (the floor on error / mock). |
| `encounter.prompty` | `cognition.py` — `maybe_react()` | First-person memory a mid-activity agent writes when another resident newly comes into mutual sight (#370): a cheap perceive pass records the encounter so a passed-by face is remembered even though no decision point fired. Memory text, not a live model prompt; only reachable when the react gate (`CognitionConfig.react_enabled`) is on. |
| `react.prompty` | `cognition.py` — `_consult_react()` | **Real model prompt.** Asks a walking agent — after noticing someone — whether to continue, stop for a greet (starting a #371 multi-tick conversation), or replan; paired with the `react` tool (#370). Live-brain only; the rule tier and brain-identity gate keep the mock bake byte-identical. |
| `believability_rubric.prompty` | `eval/believability.py` — `LlmJudge.score_agent()` | **Real model prompt.** The offline believability audit's judge rubric (#584): one agent's evidence digest (assembled in code by `evidence_text()`) plus the five scoring dimensions (including `world_grounding`, #780), graded via the `grade_believability` tool. Never rendered during a live sim — the audit reads a *finished* run's exported artifacts; on a declined/malformed reply (or under the free mock provider) the deterministic heuristic scores instead. |

## A note on escaping

Jinja autoescaping is **off** (Prompty's default), so the apostrophes, em dashes,
and double quotes in this text (`Isabella Rodriguez's apartment`, `— its`,
`I did "..."`) reach memory raw rather than as HTML entities. The root
`tests/test_prompt_templates.py` only pins the shared *engine's* templates
(`text_adventure_games/prompt_templates/`); the exact rendered output of these
Smallville/Penn templates is pinned by the memory tests in
`godot-generative-agents/tests/test_boil_water.py` and
`godot-generative-agents/tests/test_book_loop_616.py` (`remember_outcome`'s
`reflection` renders), which guard this escaping behavior for this package.
`decide_context`'s exact output is pinned by `godot-generative-agents/tests/test_decide_context.py`;
`nearby_affordances`'s by `godot-generative-agents/tests/test_affordance_wiring_613.py`;
`relationship_memory`'s by `godot-generative-agents/tests/test_relationship_seeding_779.py`;
`believability_rubric`'s by `godot-generative-agents/tests/test_believability_eval.py`;
`public_event`'s by `godot-generative-agents/tests/test_public_events_795.py`.
