# Spec: action-wish capture — the demand side of the self-coding loop — #299 / #301

**Track:** this doc rides `godot-ga-main` (docs); implementation splits per issue —
engine slices (record/sink, `propose` verb, parse-gap capture) → `main`, backend
feed/artifact/tooling/experiment → `godot-ga-main`, per the CLAUDE.md branch rule.
**Date:** 2026-07-17
**Relates to:** #299 (self-coding epic), #301 (propose_code — the supply side),
#595 (choose-to-boil experiment), #617 (affordance-curated toolsets), #41
(missing *nouns*), PR #598 (deciding feed — the pattern sibling).
**Process:** issues first — nothing here gets implemented until the filed slate has
been through team review.

## Problem

Before an agent can *write* the action it's missing (#301), we need evidence of
*which* actions agents actually miss, and why. Today that demand signal is
invisible — a missing verb hides in three places:

- **The parser's no-verb path** (`parsing.py:487` on this tree; `:535` on
  `main`, where the fix lands) emits the same generic
  `"I'm not sure what you want to do."` as any blocked command; nothing records
  what was attempted. A failed parse never becomes a `GameEvent`, so it never
  reaches the backend feed either.
- **The LLM-fallback parser force-maps.** `LlmParser._pick_option` picks the
  *nearest existing* verb with no "none of these fit" option, so a genuinely
  missing verb usually executes as a wrong action instead of failing cleanly —
  the gap is converted into noise.
- **The native tool path is a closed menu.** `build_choose_action_tool` exposes
  the action vocabulary as a closed enum: an off-menu verb is *inexpressible*,
  not merely unavailable.

The research ladder this fills: #595 asks whether an agent *chooses* an existing
tool from memory; **this layer asks whether it can *articulate* the missing
tool**; #301 asks whether it can *write* it. The run record is the experiment
data (#300's ethos: define the measurement alongside the content).

## Decisions

1. **Two capture triggers.** A wish record is created either **deliberately**
   (the agent explicitly proposes a missing action, with reasoning) or
   **automatically** (a command that matches no verb at all). Heuristic
   *precondition dead-end* detection (verb exists, chain is stuck) is
   deliberately deferred — hard to distinguish "missing enabler" from "agent
   being wrong", and it would pollute the demand data.
2. **The deliberate channel is a first-class verb.** `propose <what I need>
   because <why>` is a real engine `Action` that records the wish and spends
   the turn. Registered-verb status rides every existing rail for free: it
   appears in `agent.action_names`, gets a `tools_for` tool (making off-menu
   wants expressible on the tool path), parses on the free-text path, is
   drivable by the mock brain in offline tests, and lands in command history /
   `GameEvent`s like any action. The articulation is itself measurable
   behavior. *Alternative considered and rejected:* a zero-turn-cost
   side-channel (a `Wish:` label beside `Reasoning:`/`Action:`, plus a
   non-terminal tool) — it keeps sim dynamics unperturbed, but needs two
   divergent implementations, fights the tool loop's round accounting, is
   invisible to the run record without bespoke plumbing, and the mock brain
   can't exercise it.
3. **One record, one sink, engine-first.** A typed `ActionWish` and a single
   `game.log_wish(...)` entry point live in the engine library (every game gets
   them); the backend taps in through a streaming callback, never a parallel
   data path — the same one-fact discipline as #617's
   offered ⇔ gate-passes invariant.
4. **No write-time dedupe in v1.** Every record is kept; the aggregator
   collapses duplicates. (A "you already noted that" cooldown precondition on
   `propose` is a listed future option if wish-spam shows up in practice.)
5. **Issues before code.** The slate below goes through team review before any
   slice is implemented; each slice then gets its own PR review on its track.

## The record

```python
ActionWish(
    actor="Sofia",                    # character name
    turn=13,
    location="Houston Kitchen",
    desired="fill the pot from the sink",   # the action, as stated
    reason="boiling needs water in the pot",# because-clause; "" for parse gaps
    trigger="proposed",               # "proposed" | "parse_gap"
    goals=["make the water safe to drink"], # actor's goals at wish time
    scope=["pot", "stove", "sink", "Diego"],# things in scope — what WAS available
    raw_command="propose fill the pot from the sink because ...",
    meta={},                          # extension point
)
```

`goals` and `scope` are snapshots because the consumer — a human world-author,
or later #301's propose_code — needs the situation the want arose in, not just
the want. The sink: `game.wishes` (a list) plus `game.log_wish(...)`, which
appends, fires an optional `on_wish` callback (the `UsageLedger._on_record`
streaming pattern), and emits a trace on a new `Channel.AGENT_WISH` so wishes
are visible in narrated output the way agent reasoning already is.

## Capture path A — the `propose` verb (engine → `main`)

- Grammar: `propose <what I need> [because <why>]`; the payload splits on the
  first ` because `. Preconditions: payload non-empty (the fail message teaches
  the format). Effects: `log_wish(trigger="proposed")` + ok-message
  *"Noted — your request was recorded for the world's designers."* The turn is
  spent.
- Tool path: `propose` needs a free-text argument schema (it has no scope-enum
  slots, so `_build_action_tool`'s derived slots don't apply — a small custom
  schema hint).
- Prompt: one licensing sentence in `npc_decision.prompty` (use it only when no
  available action could accomplish what you need; then pursue your best real
  option next turn), with the pinned-output test and README-table updates that
  template changes require. The structured path carries the same guidance in
  the tool description.
- Available to the player too — player wishes are demand data as well.

## Capture path B — parse-gap capture (engine → `main`)

- At the no-verb fail (`parsing.py:487` here; `:535` on `main`):
  `log_wish(trigger="parse_gap", desired=<raw command>)` immediately before the
  generic fail. Unconditional
  (all actors — player typos are cheap noise the report filters); keeps the
  parser seam branch-free.
- **The one behavior change in the slate:** the LLM fallback gains an explicit
  "none of these fit" option **for agent-driven actors only** (actors carrying
  an attached agent — the `Character.set_agent` / `cognition.attach_agents`
  seam), so a missing verb fails cleanly (and gets captured) instead of
  force-mapping to the nearest existing verb. Human players keep best-effort
  matching. The
  Anthropic-native parser already has `allow_none` machinery to build on;
  flagged prominently for reviewers.

## Plumbing (backend → `godot-ga-main`)

- **Feed:** `PennStepper` installs `on_wish`, buffers records under a lock,
  drains per tick, and the live loop publishes `{cursor, kind: "wish", ...}` —
  the same emit → buffer → publish trio as the deciding feed (PR #598; same
  pattern, independent code, whichever merges second rebases trivially).
- **Mock invariant:** the mock brain never proposes and its authored commands
  always parse, so under `--brain mock` the buffer stays empty and the feed is
  byte-identical *by vacuity* — stated as an invariant and pinned with a test.
- **Persistence:** `wishes.jsonl` in the per-run `RunStore` directory (beside
  `frames.jsonl` / `events.jsonl`), one record per line; baked replays carry a
  `wishes` array so recorded runs keep their demand data.

## The report — most-wanted actions (tooling → `godot-ga-main`)

A small offline aggregator reads `wishes.jsonl` (or a baked replay) and emits
the ranked demand report: normalized desired-action phrase, count, distinct
agents, example reasons, first/last turn. Markdown for humans, JSON for
machines. This artifact is what a world-author reads, and later the input
queue for #301's propose_code. v1 groups by normalized string; LLM clustering
is future work.

## The experiment — boil-wish articulation (→ `godot-ga-main`)

Take the `world_data_boil.yaml` Houston scenario and **withhold the boil
Recipe** (a flag skips `game.add_recipe(_boil_recipe())`,
`penn_world.py:451`) — restoring exactly the capability gap #300 originally
shipped ("no agent can boil water yet — that's the point"). Seed the #595
aversive memory. Run the live brain across N seeds and measure the
**articulation rate**: the share of runs producing a `proposed` wish whose
desired action ≈ boil/heat the water, with reasoning referencing the sickness,
against a no-memory control. Success criteria are computable from
`wishes.jsonl` alone.

## The batch

| Issue | Slice | Track | Depends on |
|---|---|---|---|
| Epic | tracking + this design inlined | — | — |
| E1 | `ActionWish` + sink + `AGENT_WISH` channel + `propose` verb + prompt line | `main` | — |
| E2 | parse-gap capture + agent-only "none of these fit" fallback | `main` | E1 |
| B1 | `wish` feed kind + `wishes.jsonl` + replay bake | `godot-ga-main` | E1 + sync |
| B2 | most-wanted-actions aggregator | `godot-ga-main` | B1 |
| X1 | boil-wish articulation experiment (N seeds + control) | `godot-ga-main` | E1, B1 |
| V1 | viewer surfacing (💭 marker + panel row) — nice-to-have | `godot-ga-main` | B1 |

Build order: E1 → `main → godot-ga-main` sync → E2 ∥ B1 → B2 ∥ X1 (V1 trails).

## Out of scope / future

- **Dead-end heuristics** (missing *intermediate* enablers) — revisit once the
  two clean triggers have produced real data.
- **Write-time cooldown** on `propose` — only if wish-spam appears.
- **Recipe-grant bridge** — a wish matching a known-but-unregistered `Recipe`
  could be *granted* (`learn_recipe`) by the outer loop: a cheap demand→supply
  loop before full codegen. Natural follow-on experiment after X1.
- **Missing nouns** (#41) — "there's no kettle here" is object demand, not verb
  demand; same sink could carry it later via `meta`.
- **`not_offered` trigger** — once #617's curated toolsets land, "verb exists
  but isn't offered here" becomes a third, distinguishable trigger.
- **Mid-tick streaming** — wishes publish at tick boundaries like every feed
  record; the #605 begin-streaming work would cover them for free.
