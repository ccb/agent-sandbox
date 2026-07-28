# Agents that arrive nowhere: the decide-time context an agent needs about itself

Design for [#826](https://github.com/ccb/agent-sandbox/issues/826). Sibling of
`plan-llm-dialogue-795.md` — same shape: a live-run pathology, traced to the
prompt that produced it, fixed at the decide seam.

## The reported symptom

In `#760` batch 4 (`run-20260727-190111-f15134`, 12 sim-hours, 5 agents,
`claude-sonnet-5` at effort medium) Priya Nair spent the last **2 h 15 min** of
the day walking and arrived nowhere. She alternated between Van Pelt's Moelis
Reading Room and Houston Hall, flipping to the other errand each time she got
somewhere. Four of five agents spent 29–37% of the day walking; Mateo Vasquez
switched destinations 16 times.

## The stated mechanism is wrong

#826 attributes this to "a re-decide retargets it mid-walk", and proposes a
commitment mechanism for in-flight journeys. **Nothing retargets mid-walk.**

The decision gate is `not st["path"]` (`backend/run_simulation.py:396`): an
agent with tiles left to walk is never added to `due` and is never asked to
decide. `frames.jsonl` agrees — every destination change sits on a segment
boundary with no tiles remaining. Priya's three legs are *contiguous* walk
segments (3505–3848, 3849–4192, 4193–4319) with no frame between them: the path
emptied, and on the very next tick she departed again.

So the count in the issue is right and the label is wrong. This is an
**arrival-boundary** defect: the agent re-decides one tick after arriving, on
context that has not caught up with what it just did. A journey-commitment
mechanism would add a lock for something the loop already guarantees.

## What the recorded prompts actually show

From `cassette.jsonl`, her decides at turns 3505 / 3849 / 4193 (17:44 / 18:41 /
19:38). Four defects compound.

### 1. Her retrieved memories are 100% intentions, for three straight hours

From 17:04 to 19:59 the same six `plan`/`chat` records fill all six retrieval
slots, only reordered. One is from turn 2 — 10 hours earlier. **Not one record
of anything she did.** At 18:41 she reads:

```
 - [plan, turn 2619] I agreed with Maya Chen: Grab coffee at Houston Hall café
   with Maya, then head to Van Pelt's Moelis Reading Room to study genetics…
 - [plan, turn 2] I agreed with Maya Chen: Head to Van Pelt Library with Maya…
 - [plan, turn 2344] I agreed with Maya Chen: Grab coffee with Maya at the cart…
 - [chat, turn 2344] Maya Chen is my study buddy since freshman bio…
 - [chat, turn 3161] Maya Chen is my study buddy since freshman bio…
 - [chat, turn 2889] Maya Chen's usual order is an iced oat milk latte…
```

Two mechanisms in `memory.retrieve` produce this:

* `retrieve(touch=True)` — the decision-time path — sets `last_accessed_turn` to
  the current turn on every hit. A retrieved record therefore scores recency
  `1.0` next time. Once an importance-8.0 commitment memory
  (`commitment_memory.prompty`, #778) is in the block it stays in the block.
* Her own outcome records are importance 2.0 (`remember_outcome`) and decay at
  `0.95^n`. A 344-step walk is `0.95^344 ≈ 3e-8`. Her memory of setting out
  survives roughly 100 turns — 17 sim-minutes. The leg takes 57.

She is left reading her intentions with no evidence about their status, so she
re-derives the same intention at every arrival. Her own words: "Coffee run is
wrapping up", "Coffee run is basically done" — while having spent the entire
time in transit.

### 2. The elapsed clause never renders

`decide_context.prompty` carries "You have been on this stop for N min", the one
signal that would have said *you have been on a 10-minute coffee errand for two
hours*. It is absent from all three prompts.

`run_simulation.py:735-739` re-anchors `st["stop_since"] = step_idx` on **every**
arrival. She decides one tick later, so `elapsed` is 0 and the sentence is
dropped. The signal is erased by the act of arriving — for any agent that
arrives and re-decides, which is every traveling agent.

### 3. The stop pointer is frozen

All three prompts read `Your plan's current stop: Quick coffee cart run with
Maya before studying at Van Pelt Library (planned ~10 min)` — unchanged across
2 h 15 min. `schedule.advance()` fires only for an on-plan perform; she got
coffee at Houston Hall while the stop named Van Pelt Library, so the stop was
never credited, and after 17:44 she only ever traveled.

### 4. Travel cost is invisible at decide time

The issue's gap #2, confirmed. The exits list prices a 0-minute in-building hop
identically to a 57-minute cross-campus leg. `planner.median_travel_minutes()`
exists and reaches only the planner (`serve_penn.py:1116`).

## Evidence that the fix works: prompt-level A/B

Her turn-3849 prompt replayed against `claude-sonnet-5` with the run's effective
parameters (adaptive thinking, effort medium, `max_tokens` 4096, no temperature
— PR #820), 2 reps per arm. The control reproduces the bug verbatim, so this
decide is a faithful bench.

| arm | choice | its stated reason |
|---|---|---|
| control (recorded prompt) | `travel` → Houston Hall (57 min) | "Quick coffee cart run with Maya before settling in at Van Pelt to study" |
| + elapsed clause | `travel` → Moelis — *where she already stands* | "We've lingered way past the planned 10-minute coffee run" |
| + walk-minutes line | `travel` → Van Pelt Library (1 min) | still chasing coffee; the mistake now costs 1 min, not 57 |
| + "Recently, you:" | **`study`** | "Already at Moelis Reading Room **after the coffee run with Maya**, so time to settle in" |
| all three | **`study`** | "We've **already gotten coffee** and **lingered long enough**" |

Her prompt header already read `VAN PELT — MOELIS READING ROOM`. Knowing *where
she is* was never the problem; she cannot see *what she did*. Only the own-action
block flips the decision on its own. Elapsed breaks the coffee loop but leaves
her deciding a no-op travel to where she stands. Walk-minutes only shrinks the
cost of the mistake. Together they produce the best reasoning, citing both
history and overrun.

`study` was offered to Priya all day and she used it **zero** times in 4,320
frames; the fix reaches for it unprompted, which is #827's complaint.

Cost of the A/B: 20 calls, $0.20.

Caveat, stated plainly: one agent, 2 reps per arm, and the table is a **single
decide**. Turn 4193 was replayed too, but its control did not reproduce its
recorded choice (it chose a fourth coffee session rather than the recorded
return trip), so it is not a clean bench and is excluded — its treatment arms
did choose "coffee run is done, go study", which is the right call, but against
a control that had already broken. This is prompt-level evidence that the added
context changes the decision, not a run-level measurement that the thrash rate
drops — see Validation.

The A/B harness lives in the PR description rather than the tree: it reads a
run directory that is git-ignored (`runs/run-*/`, #760 batch 4) and spends real
money, so it is not a test.

## The fix

Three signals at the decide seam, all in the Penn cognition layer. Nothing in
`text_adventure_games/` changes; retrieval scoring is not touched.

### F1 — fix the elapsed clock (a bug)

`stop_since` is re-anchored in three places. Two of them were wrong, and the
review found the second only after the first was fixed — so this is the whole
rule, not the arrival branch alone: **re-anchor when, and only when, the stop
pointer actually moves or the agent reaches the stop's own place.**

1. *The schedule advances* — a genuinely new stop. Correct already.
2. *Arrival* (`backend/run_simulation.py`, the walk branch) — re-anchor only
   when the arrival is at the stop's own place, so the walk there is excluded
   but an off-plan arrival cannot erase the clock:

   ```python
   if not st["path"]:
       if at_scheduled_stop(char):
           st["stop_since"] = step_idx
   ```

3. *"Deviation completed"* — the pre-pass branch that un-latches an off-plan
   `perform` without advancing the pointer. It re-anchored unconditionally.
   Deleting that line is the rest of the fix: the pointer has not moved (that is
   the branch's whole meaning), so restarting its clock claims a stop just
   became current when it has been current all along.

Point 3 matters as much as point 2, because point 2 alone only helps an agent
that wanders off-plan and never settles. Priya *performed* a coffee errand every
time she arrived, so her clock was reset on the way out regardless. `#689`'s
`settle_after_dead_talk` routes through the same branch, so a merely **dropped
talk — at her own scheduled stop** — also wiped it.

Both are unreachable under the mock, which never deviates and never converses,
so the bundled bake stays byte-identical.

`at_scheduled_stop(char)` is the shared predicate: the furniture bias, the
perform settle's `on_plan` flag, the instantaneous-command emoji, this arrival
gate and `_credit_stop_for_conversation` each carried their own inline copy of
"is this character standing where its stop says", so the next change to what
that means had five places to miss.

> **Superseded by #831** (2026-07-28): the "Deviation completed" branch in
> point 3 above was deleted outright, and `_credit_stop_for_conversation`
> dropped its own place check -- so it is no longer one of `at_scheduled_stop`'s
> five callers. This section is left as-is for the historical record; do not
> reuse its caller count or list in a future enumeration pass.

**The sentence has to change too.** `elapsed` no longer means "time spent at the
place" — for an agent that never arrives, nothing re-anchors and the clock runs
on the stop it is neglecting, which is exactly the signal #826 needs. But
"You have been on this stop for 114 min" then asserts 114 minutes at a library
the agent has never entered: the same class of first-person falsehood as #812.
The template now reads **"This has been your current stop for N min."** — true
whether or not the agent ever showed up.

Under this rule Priya's 18:41 prompt would have read "This has been your current
stop for 57 min" against "(planned ~10 min)", and her 19:38 prompt "114 min". At
17:44 it still reads 0 — correct, and honest: leaving Houston Hall at 17:44 was
a reasonable decision. The fix speaks up on exactly the two decisions that were
wrong.

### F2 — the "Recently, you:" block (load-bearing)

**Marking.** Four write sites pass `tags={"action"}`: both in `remember_outcome`
(success and the #636 failure branch), `remember_decide_timeout`, and the
completed-conversation record `maybe_converse` writes itself. That last one is
easy to miss and was — `remember_outcome` returns early for `talk_to` because
"phase 1.5 of `maybe_converse` owns both branches", so the *failure* branch
routes back through `remember_outcome` and gets tagged while the *success* path
writes its own record. Untagged, a dropped talk would appear in the block and a
conversation that actually happened would not, in a social sim whose motivating
trace is "grab coffee *with Maya*".

Nothing else is tagged: the relationship note, the commitment plan, the #370
encounter and the viewer intervention are perceptions or intentions, not the
agent's own actions.

This reuses the `tags` field `AgentMemory.perceive` already uses for
`{"presence"}`: no new `MemoryKind`, no serialization change, no DB migration,
no reflection-filter change.

**Rendering.** New `cognition.recent_actions_block(agent, step, clock)` walks
`agent.memory.records` backwards, takes the newest 3 records tagged `"action"`,
and renders one line each through a new `recent_actions.prompty`:

```
Recently, you:
 - 57 min ago: I traveled to Van Pelt — Moelis Reading Room.
 - 67 min ago: I am grabbing a quick coffee with maya at the café counter.
 - 77 min ago: I am grabbing coffee with maya at houston hall café.
```

Record text is rendered **verbatim** — these are the agent's own memories, not
prose to rewrite, so `perform`'s present tense ("I am grabbing…") is left as
`reflection.prompty` wrote it. Minutes come from `clock.minutes_for_steps(step -
record.created_turn)`; the block returns `""` with no clock or no tagged records,
so the bake and every clockless offline test are unchanged.

**Placement.** Appended to `base` in `observe_and_decide` alongside the #580
context block and the #613 affordances line — after the environment text, before
the retrieved memory block. Same seam, same gating discipline.

**Why not fix retrieval instead.** A plan-kind quota, or
`exclude_kinds=("plan",)` at decide time (what #777 did for reflection), would
undo #778 — commitments belong in the decide prompt. Re-weighting importance or
recency changes every agent's every decision to fix one class of blindness. The
block is additive, local, and by construction immune to the scoring fight that
buried her history: it is a guarantee, not a bid.

Three records, hardcoded as a module constant beside the existing
`PRESENCE_CAP`-style constants. No config knob until a run wants a different
number.

### F3 — the walk-minutes line

New `cognition.walk_minutes_line(game, char, clock)`:

```
Walking from here takes at least about: Van Pelt — Moelis Reading Room 0 min;
Van Pelt Library 1 min; … College Hall 17 min; Houston Hall 27 min; …
```

Chebyshev tile gap from the character's current tile to each destination's
footprint, nearest first, destinations with no tiles dropped, `""` with no map or
no clock.

The arithmetic already has a home: `WorldMap.tile_gap(addr_a, addr_b)`
(`backend/world_map.py:126`) is the same Chebyshev over precomputed
`address_bbox` boxes, used by the #82 perception radius. Add its
point-source sibling beside it — `tile_gap_from(tile, address)`, the identical
formula with a degenerate 1×1 source box — and call that. Two reasons to anchor
on the agent's *tile* rather than its location's address: an agent standing on
the "Penn campus" hub has no address at all (the hub's is `None`), and that is
precisely a travel-decision point, so an address-to-address gap would render no
line exactly where it is most useful; and the bboxes are precomputed, so this
stays O(destinations) with no per-tile scan.

**`planner.py` is not touched.** `median_travel_minutes` does its own pairwise
Chebyshev anchored on `min(tiles)` — an arbitrary but deterministic pick, since
it has no vantage point — and `test_median_travel_minutes_is_a_chebyshev_lower_bound`
pins the number that produces. Unifying the two would either change the
planner's number or force an anchor parameter through both. Leaving it alone is
smaller and safer than extracting a shared helper.

The place the agent is standing in **is** listed, at 0 min: that "you are
already here" line is a signal in its own right, and it is what the A/B's
treatment arms carried.

Scope the list to the destinations the `travel` tool actually offers
(`sorted(game.locations)`, the enum `action_tools_for` fills in), so the prompt
prices exactly what the model can choose. Wording matches the planner's existing
hedge: "at least about".

`ponytail:` Chebyshev ignores walls and under-reports about 2× on this campus —
27 min to Houston Hall against a measured 58. Two accurate alternatives were
measured and rejected: calling the real pathfinder per destination costs **20 s
per decide** (18 A\* runs over a 245×279 grid, and it must not go through the
patched `walk_path`, whose rendezvous routing is stateful round-robin); a BFS
distance matrix precomputed per world build costs ~18 s at boot, and boot time is
exactly what overran `drive_run.sh`'s readiness gate in batch 4. The ordering,
which is what the decision needs, is already right.

## Rejected

* **A journey-commitment mechanism** (#826's gap #1). Already implemented — see
  "The stated mechanism is wrong".
* **An arrival settle** — force N minutes at the destination before re-deciding,
  mirroring `settle_after_dead_talk` (#689/#793). Bounds the thrash *rate*
  without touching the belief that causes it: she would wait five minutes at
  Moelis and still leave for coffee. It also freezes an agent with a real reason
  to move.
* **Unfreezing the stop pointer** — credit a stop whose activity ran at an
  unplanned place. A genuine defect (§3) but a separate one: it touches the
  advance gate the mock bake's byte-identity rests on, and `run_simulation.py`
  already carries a deliberate rejection of a general stop deadline. With F1
  landed the model *sees* the staleness, and the A/B shows it acts on it. Filed
  as **#831**, a sub-issue of #760.

## Testing

Offline and deterministic:

1. `test_recent_actions_block` — tagged records in, assert the rendered lines,
   newest-first ordering, the 3-record cap, untagged records excluded, and `""`
   with no clock and with no tagged records.
2. `test_walk_minutes_line` — a small fake map: assert nearest-first ordering,
   the minutes, tile-less destinations dropped, and `""` with no map. Plus
   `test_tile_gap_from` against `tile_gap`'s own fixture: a source tile inside a
   footprint reads 0, and the existing `tile_gap` numbers are unchanged.
3. `test_stop_since_survives_an_offplan_arrival` — the regression. Arrive at a
   place that is not the stop's place: `stop_since` unchanged, elapsed clause
   renders. Arrive at the stop's place: `stop_since` re-anchors, clause drops.
4. `test_prompt_templates` — pin both new templates' exact output, and update the
   usage table in `backend/prompt_templates/README.md` (required by CLAUDE.md).
5. The #640 bake byte-identity guard, 3×`PYTHONHASHSEED`. All three additions are
   clock-gated or real-brain-gated, so the bundled replay must not move.

Measurement, so the next live run can see this without hand-reading frames:

6. `tools/analyze_run.py` — an `arrived_then_departed` count per agent (a walk
   segment immediately followed by another walk segment), beside the existing
   `walking_share`. On batch 4 it reads Priya 4, Mateo 16, everyone else 0: the
   number that made this diagnosable.

## Validation

A `#760` batch-5 live run, compared against batch 4's Run B:

* `arrived_then_departed` — 20 across the run today; expect it near 0.
* `walking_share` — 29–37% for four of five agents today.
* believability `plan_coherence` — 6.68, the run's floor dimension, with Priya
  the `weakest` agent at 7.86 (#781/#817).

The prompt-level A/B is evidence the added context changes the decision; only a
run shows the rate falling.

**This invalidates existing cassettes.** `recording.request_key` hashes the whole
request, so every decide observation that gained the walk-minutes line, the
"Recently, you:" block or the reworded elapsed sentence misses on replay — the
#715 re-run bridge, `--resume`, and #734's Re-run button all re-run pre-#826
runs from scratch rather than byte-identically. Inherent to any prompt change
(#580, #613 and #795 each did the same) and not worth versioning cassettes over,
but batch 4's recordings are what the A/B above was built on, so it is worth
saying out loud rather than discovering at the next re-run.

## Files touched

| file | change |
|---|---|
| `backend/cognition.py` | `recent_actions_block`, `walk_minutes_line`, `at_scheduled_stop`, two calls in `observe_and_decide`, `tags={"action"}` at four write sites |
| `backend/prompt_templates/recent_actions.prompty` | new |
| `backend/prompt_templates/walk_minutes.prompty` | new |
| `backend/prompt_templates/decide_context.prompty` | the elapsed sentence, reworded (F1) |
| `backend/prompt_templates/README.md` | usage table |
| `backend/run_simulation.py` | both `stop_since` gates, and four inline predicates folded into `at_scheduled_stop` |
| `backend/world_map.py` | `tile_gap_from`, sharing `tile_gap`'s `_box_gap` |
| `tools/analyze_run.py` | `arrived_then_departed` |
| `tests/` | the four test groups above |

Paths are relative to `godot-generative-agents/`. Nothing in
`text_adventure_games/` changes, so this is a Godot/geo-owned review (CLAUDE.md).

Prompt cost, measured (`tiktoken`'s `cl100k_base` as a stand-in for the
model's own tokenizer, since the "+70 tokens" here was a guess the #826 review
caught): about +230 tokens per decide — roughly 60 for the "Recently, you:"
block's up to three lines, and roughly 170 for the walk-minutes destination
line, whose Penn rendering (`DECIDE_MAX_ENUM`-capped, same as the destination
enum it mirrors) is about 592 characters today. ~1,200 decides — still
negligible against a $10 run, and appended after the cached prefix (#822).
