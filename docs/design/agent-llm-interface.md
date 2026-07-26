# What the LLM sees and may do — the agent ↔ model interface

**Scope.** This documents the interface between the generative agents and the
live model for the **live-LLM MVP** (issue #261, epic #266): the Penn campus
sim served by `godot-generative-agents/backend/penn/serve_penn.py --brain llm`, watched
live in the Godot viewer. The model is **Anthropic Claude Haiku
(`claude-haiku-4-5`)** for every call, declared in the world's simulation
config (`godot-generative-agents/backend/penn/world_data_upenn.yaml`, the `llm:`
block) and pinned by `generative-agents/tests/test_penn_live_llm.py`.

The same interface backs the Smallville batch runner
(`backend/run_simulation.py`) — the MVP reuses it unchanged; nothing here is
Penn-specific except the cast and the counts.

## The shape of the loop

Agents do **not** free-run: the classical-planning engine stays in charge, and
the model is consulted at three well-defined moments. Every command the model
produces re-enters the engine's **precondition gate**
(`actions/*.check_preconditions`) — the model can only do what the rules of
the world permit, and a rejected command simply leaves the agent idle for that
tick (an `ACTION_FAILED` trigger offers the planner a revision, a no-op under
the static planner).

An agent is asked to *decide* only at a **decision point**: when it is neither
walking a path nor performing an activity (`backend/run_simulation.py`,
`step()`). Walking and performing consume ticks without any model call, which
is what keeps a 1200-step day at ~tens of calls rather than ~thousands.

## Tool 1 — `choose_action` (deciding)

Rendered per call by `LLMAgent._decide_structured`
(`text_adventure_games/npc.py`), invoked once per agent per decision point.

- **System message** — the `npc_decision.prompty` template
  (`text_adventure_games/prompt_templates/`): the agent's first-person persona
  (from `world_data_upenn.yaml`) plus its active goals, if any. No output
  instruction — the tool schema is the output contract.
- **User message** — the observation, built by
  `backend/smallville_agents.observe_and_decide`:
  1. the engine's location description for this agent (`game.describe_for`),
  2. what it currently **perceives**: co-located events plus the residents and
     objects within its vision radius (`vision_r: 8` tiles),
  3. a **retrieved-memories block**: the most relevant records from its private
     memory stream (recency x importance x relevance scoring, ~800-token
     budget) — observations, its seeded day plan, past chats, reflections.
- **Tool schema** (`build_choose_action_tool`):

  | field | type | meaning |
  |---|---|---|
  | `reasoning` | string | one short sentence explaining the choice (surfaced on the viewer's agent card) |
  | `action` | enum `["travel", "perform"]` | the verb — a **closed enum**, so the model can only pick a command the parser knows |
  | `arguments` | string | the rest of the command, e.g. `to Van Pelt — Kamin Gallery` |

  The engine assembles `"<action> <arguments>"` and routes it through the
  parser + precondition gate like any other command. If the structured call
  returns nothing, one free-text `chat` fallback is tried (same template,
  with the labeled Reasoning/Action instruction appended).

## Tool 2 — `speak` (conversing)

Rendered per dialogue line by `LLMAgent._converse_structured`, driven by
`text_adventure_games/conversation.converse`.

- **When**: after movement each tick, `maybe_converse` pairs up **settled,
  co-located** agents — hearing is perception-gated for Penn
  (`penn_world._gate_conversations_by_perception`: conversation range ==
  sight range, `vision_r` 8 tiles), so agents can never talk across the map.
  Each pair then cools down for `conversation_cooldown_steps: 90` steps — and
  their Nth conversation waits N× that, so a pair can't re-open the same meeting
  on a clock (#803).
- **System message** — `npc_decision.prompty` (persona + goals); the free-text
  fallback uses `npc_dialogue.prompty` instead.
- **User message** — the conversation so far plus the partner's name. Opening a
  conversation, the closing instruction greets a stranger or resumes with someone
  the agent already remembers talking to (#803).
- **Tool schema** (`build_speak_tool`):

  | field | type | meaning |
  |---|---|---|
  | `utterance` | string (required) | the next line, in character; `""` says nothing and ends the conversation |
  | `done` | boolean | true when this is the closing line (a goodbye still gets heard) |

  A conversation runs at most `conversation_max_exchanges: 6` back-and-forth
  lines. Every line is written into **both** participants' memory streams as
  `CHAT` records and onto the replay frame's `chat` field — that is what the
  viewer renders as speech bubbles with a conversation link.

  Under `--brain llm` the scripted `meetings:` dialogue injector **stands
  down** entirely: the authored rendezvous routing still steers the cast
  together (Diego ↔ Sofia at the Kamin Gallery, Tanaka ↔ Sofia at Irvine),
  but every on-screen line is the model's.

## Tools 3 & 4 — `salient_questions` and `record_insight` (reflecting)

Driven by `text_adventure_games/reflection.py` (`LLMReflector`), checked after
every successful action; a pass runs only once ~30 importance-points of new
memories have accrued since the last one.

- **System message** — `reflect_system.prompty`.
- **User message** — the agent's recent memory records, numbered.
- **`salient_questions`** asks the model for the 2–3 questions those memories
  raise; **`record_insight`** is then called once per question to distill an
  insight citing the memory numbers it rests on. Insights are written back to
  the stream as `REFLECTION` memories (importance-weighted, so they surface in
  future retrievals and on the viewer's agent card).

## What is deliberately NOT model-driven (MVP)

| piece | what runs instead | why |
|---|---|---|
| **Daily planning** (free brains only) | `MockPlanner` replaying the authored YAML schedules | Since #787 `--brain llm` also plans its own day: `--plan` defaults to `auto`, which is `llm` under a paying brain and `schedule` otherwise. `LLMPlanner` (#397) validates stops against the world's full location set (+3 calls/agent at attach). It is **free-play** — a generated day is not guaranteed to reproduce the scripted rendezvous — so `--plan schedule` forces the hand-tuned authored day back, and the free mock/scripted brains (the bake, every offline replay) are untouched. |
| **Parsing / narration** | the deterministic `parsing.Parser` | the Penn game never installs `LlmParser`, so the `match_*` / `narrate_*` templates are not in play. |
| **Perception & retrieval** | keyword scoring over the memory stream | no embedding client is wired in the MVP (opt-in via issue #76's `EmbeddingClient` later). |

## How many LLM calls is a day?

For the MVP cast — 3 agents (Diego 5 stops, Tanaka 2, Sofia 3 = **10
schedule stops**), 1200 steps ≈ a 08:00–11:20 campus morning:

| call site | template | arithmetic | typical calls/day |
|---|---|---|---|
| decide (`choose_action`) | `npc_decision` | 2 per stop (one *travel*, one *perform* on arrival) x 10 stops | **20** |
| decide free-text fallback (`chat`) | `npc_decision` | only when the structured call returns nothing (~10%) | **~2** |
| converse (`speak`, one call per line) | `npc_decision` (+ `npc_dialogue` fallback) | 2 authored rendezvous x ~7 calls (≤6 lines + a closing/declining call) | **~14** |
| plan (`day_outline` + `hourly_plan` + `minute_plan`) | `plan_system` | `--plan schedule`: static, no model. `--plan llm` (the default under a live brain, #787): 3 calls/agent at attach + 1 per revision trigger | **~9+** live / **0** under `--plan schedule` |
| reflect (`salient_questions` + ≤3 `record_insight`) | `reflect_system` | ~2 passes/agent x ~3.5 calls | **~21** |
| **total** | | | **≈ 65–70** (worst case ≲ 130); ~10 fewer under `--plan schedule` |

**Cost** at the ledger's Haiku prices ($1 in / $5 out per MTok; prompts ~0.7–1.3k
tokens, outputs ~0.1–0.4k): ≈ 54k input + 8k output ≈ **$0.10 per day**, worst
case < $0.40. The `llm:` block's `max_cost_usd: 5.0` is a hard kill-switch —
`PennStepper.tick()` ends the day the moment cumulative spend reaches it.

Failed calls (outage, rate limit) return `None`: the agent idles one tick and
asks again. Note they also record **no cost**, so during an outage the
kill-switch cannot trip — the stalled tokens/min meter in the viewer's run
monitor is the outage signal.

## Where every call is visible

Each call is recorded in the shared `UsageLedger`
(`text_adventure_games/usage.py`: tokens, cache split, latency, priced cost,
actor/turn attribution) and:

- printed live, one line per request, by the **terminal monitor**
  (`backend/llm_monitor.py`, on by default in `serve_penn.py`) with its
  cognitive role — `decide` / `converse` / `reflect` — resolved per call;
- summed by **`GET /usage`**, which the Godot run-monitor HUD polls (tokens/min,
  spend, budget row);
- streamable to a JSONL artifact via the engine's `RunLog` (unchanged — the
  monitor is a write-through view of the same ledger, never a replacement).

The monitor's buffered records (`LlmCallMonitor.drain()`) are the seam a later
PR can pump into the live event feed so the web viewer can render the same
per-request table.
