# Prompt templates (generative-agents)

The Smallville port's agent-generated text lives here as
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
persona with a deterministic mock (`smallville_agents.SmallvilleMockClient`) that
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
from gen_agents.prompt_templates import render

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
| `plan_memory.prompty` | `smallville_agents.py` — `attach_agents()` | The day's PLAN memory seeded onto each persona at t=0: `Plan: go to <destination> and <activity>.`, plus `Today's stops: <itinerary>.` when the whole-day itinerary is given (#83). |
| `reflection.prompty` | `smallville_agents.py` — `remember_outcome()` | A persona's own action, as a first-person observation memory: `I traveled to <place>.` / `I am <activity>.` / `I did "<command>".` |
| `spatial_knowledge.prompty` | `seed.py` — `seed_spatial_knowledge()` | One place a persona knows up front (a Belief): `You know <place> — its <areas>.` / `You know <place>.` |
| `plan_system.prompty` | `planner.py` — `LLMPlanner._call()` (day / hourly / minute / revise) | **Real model prompt.** System message for the optional LLM daily planner (#83): plan one Smallville day in character. The per-level user message is assembled in code. |

## A note on escaping

Jinja autoescaping is **off** (Prompty's default), so the apostrophes, em dashes,
and double quotes in this text (`Isabella Rodriguez's apartment`, `— its`,
`I did "..."`) reach memory raw rather than as HTML entities. The tests in
`tests/test_prompt_templates.py` pin the exact rendered output and guard this.
