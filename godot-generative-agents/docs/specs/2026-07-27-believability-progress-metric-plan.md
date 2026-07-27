# Believability Progress Metric — Implementation Plan (#781)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `backend.eval.believability`'s heuristic judge reward a day that
progresses instead of a day that repeats, so believability scores are usable for
run-over-run comparison.

**Architecture:** Five surgical changes inside one module. Three rewrite
`HeuristicJudge` dimension methods (`_plan_coherence`, `_memory_use`,
`_social_grounding`); two add judge-agnostic roll-up fields in `audit()` (the
weakest agent, and a repeat-conversation flag) that also render in the markdown
report. No new files, no new dependencies, no changes to the LLM judge's rubric,
and `believability.py` stays world-agnostic.

**Tech Stack:** Python 3.12, `uv`, pytest. The module is stdlib-only
(`argparse`, `datetime`, `json`, `random`, `re`, `dataclasses`, `pathlib`).

**Spec:** `godot-generative-agents/docs/specs/2026-07-27-believability-progress-metric.md`

## Global Constraints

- Every change lives in `godot-generative-agents/backend/eval/believability.py`
  and `godot-generative-agents/tests/test_believability_eval.py`. Touch nothing else
  except the two doc files in Task 8.
- Run tests from the **repo root**: `uv run pytest godot-generative-agents/tests/test_believability_eval.py -v`
- The module is **stdlib-only**. Do not add imports beyond what is already at the
  top of the file (`argparse`, `datetime`, `json`, `random`, `re`, `sys`,
  `dataclasses`, `pathlib`).
- **Do not modify** `_temporal_sanity`, `_world_grounding`, `_match_segments`,
  `LlmJudge`, `BELIEVABILITY_TOOL`, `_DIM_SCHEMA`, or `DIMENSIONS`. The rubric
  stays five dimensions.
- The two scrambled-control acceptance tests
  (`test_scrambled_frames_score_measurably_worse`,
  `test_swapped_plans_score_worse_on_plan_coherence`) must pass after **every**
  task. They are re-tightened in Task 7.
- `_scale(fraction)` maps 0–1 onto the 1–10 rubric scale — always return scores
  through it, never a raw fraction.
- Comments in this module explain *why*, cite issue numbers, and run to the file's
  existing density. Match that; do not add narration to obvious lines.
- Commit after each task with the message given in its final step.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `godot-generative-agents/backend/eval/believability.py` | the audit: evidence digest, two judges, roll-up, CLI | modify `_plan_coherence`, `_memory_use`, `_social_grounding`, `audit`, `render_markdown`; add module-level `_decisions_in`, `_repeat_loops`, and two threshold constants |
| `godot-generative-agents/tests/test_believability_eval.py` | pins the whole module, fully offline | add 8 tests; re-tighten 2 existing acceptance tests |
| `godot-generative-agents/backend/README.md` | backend tool docs | document the two new summary fields (Task 8) |
| `godot-generative-agents/docs/specs/2026-07-27-believability-progress-metric.md` | the spec | record the measured batch-1 result (Task 8) |

The module is 1,380 lines and organised by section banner comments. Each new
module-level helper goes immediately **above** the `HeuristicJudge` class, beside
`_content_words` and `_longest_nondecreasing`, under the existing banner.

---

### Task 1: `_plan_coherence` scores schedule progress, not coverage

Today `coverage` asks whether a segment matches *some* stop. It reads 100% for all
23 agents in the #760 batch-1 runs, because the act text carries its
`@ UPenn:Building:Room` address and the address always shares a word with the stop
it belongs to. Replace it with **progress** — how far through the schedule the day
actually got — and multiply by the existing `order` term.

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py:576-620`
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `_match_segments(ev) -> list[int | None]`, `_longest_nondecreasing(values: list[int]) -> int`, `_scale(fraction: float) -> float`, `AgentEvidence.schedule`, `AgentEvidence.segments` (all already exist).
- Produces: `HeuristicJudge._plan_coherence(ev: AgentEvidence) -> DimScore` — same signature, new scoring. Note string is now `"reached {n} of {m} planned stops in order; {p:.0%} of matched segments in plan order"`.

- [ ] **Step 1: Write the failing test**

Add to `godot-generative-agents/tests/test_believability_eval.py`, immediately after
`test_build_evidence_collects_decision_frames_with_retrieved_memories` (which ends
around line 327):

```python
# ------------------------------------------------------------ plan coherence


def _stalled_replay():
    """Ada never leaves the Cafe: one act for the whole run, so she reaches
    stop 1 of her 2-stop schedule instead of both."""
    replay = copy.deepcopy(make_replay())
    for frame in replay["frames"]:
        frame["Ada"] = _at_entry(CAFE, "eating breakfast", "T:Cafe:counter")
    return replay


def test_plan_coherence_penalises_a_day_that_never_advances():
    """#781: standing on one stop all day used to score a perfect 10 --
    coverage asked 'matches some stop', not 'advanced through the stops'."""
    judge = HeuristicJudge()
    intact = judge._plan_coherence(build_evidence(make_replay())["Ada"])
    stalled = judge._plan_coherence(build_evidence(_stalled_replay())["Ada"])

    assert intact.score == 10.0
    assert stalled.score == 5.5
    assert "reached 1 of 2 planned stops" in stalled.note
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py::test_plan_coherence_penalises_a_day_that_never_advances -v
```

Expected: FAIL. The stalled agent currently scores `10.0` (one segment matching one
stop gives coverage 1.0 and order 1.0), and the note reads
`"100% of the day on a planned stop; 100% of matched segments in plan order"`.

- [ ] **Step 3: Replace the method body**

In `believability.py`, replace the whole `_plan_coherence` method (lines 576–620)
with:

```python
    def _plan_coherence(self, ev: AgentEvidence) -> DimScore:
        """Did the agent get through its plan, in the plan's order?

        *progress*: how far through the schedule the day actually got -- the
        longest in-order run of DISTINCT matched stops, over the number of
        stops. *order*: of every matched segment, the fraction that appears in
        schedule order (longest non-decreasing run of stop indices).

        The two multiply, so a day has to both advance and stay in sequence.
        Progress alone would miss a shuffled day -- a scrambled run reaches the
        same stops, just not in that sequence, which only *order* sees.

        Progress replaces the old *coverage* term, which asked whether a segment
        matched **some** stop. That read 100% for every one of the 23 agents in
        the #760 batch-1 runs: the act text carries its "@ Building:Room"
        address, and the address always shares a word with the stop it belongs
        to, so coverage discriminated nothing and an agent parked on the
        "spending time" placeholder for 977 steps scored a perfect 10 (#781).
        """
        if not ev.segments or not ev.schedule:
            return DimScore(None, note="no schedule or no frames to compare")
        matches = self._match_segments(ev)
        matched_order = [m for m in matches if m is not None]
        if not matched_order:
            return DimScore(
                _scale(0.0), [], "the day never reached a single planned stop"
            )
        reached: list[int] = []
        for m in matched_order:
            if m not in reached:
                reached.append(m)
        stops_reached = _longest_nondecreasing(reached)
        progress = min(1.0, stops_reached / len(ev.schedule))
        order = _longest_nondecreasing(matched_order) / len(matched_order)
        evidence = []
        for seg, m in zip(ev.segments, matches):
            if m is not None and len(evidence) < 2:
                stop = ev.schedule[m]
                evidence.append(
                    f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): "
                    f"'{seg.act}' matches stop {m + 1} "
                    f"'{stop.get('activity', '')} at {stop.get('place', '')}'"
                )
        for seg, m in zip(ev.segments, matches):
            if m is None:
                evidence.append(
                    f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): "
                    f"'{seg.act}' matches no schedule stop"
                )
                break
        return DimScore(
            _scale(progress * order),
            evidence,
            f"reached {stops_reached} of {len(ev.schedule)} planned stops "
            f"in order; {order:.0%} of matched segments in plan order",
        )
```

- [ ] **Step 4: Run the new test and the full file**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: the new test PASSES. Both scrambled-control tests still PASS (they assert
`>= 1.0`; the margins widen to 2.16 and 4.5 — Task 7 tightens them). If any *other*
test fails, it is asserting on the old note wording — fix the assertion, not the
implementation.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "fix(#781): plan coherence scores schedule progress, not saturated coverage"
```

---

### Task 2: `_memory_use` counts decisions, not repainted frames

Frames carry the same `(act, memories)` every step an activity runs, and each
repaint is scored — so one lucky match is counted hundreds of times. Diego's "1200
decisions" in batch-1 are 14 real ones. Collapse them, the same way
`_segments_for` collapses acts and `_merge_growth_windows` (#799) collapses
conversations.

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py` — add `_decisions_in` above the `HeuristicJudge` banner (after `_longest_nondecreasing`, which ends line 524); rewrite `_memory_use` (lines 900-936)
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `AgentEvidence.retrievals` — a `list[dict]` with keys `step`, `act`, `reasoning`, `memories`; `_content_words(text: str) -> set[str]`.
- Produces: `_decisions_in(retrievals: list[dict]) -> list[dict]` — module-level, returns the subset of `retrievals` where `(act, memories)` changed. Used only by `_memory_use`.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_believability_eval.py`, after the
Task 1 test:

```python
# ------------------------------------------------------------ memory use


def test_memory_use_counts_decisions_not_repainted_frames():
    """#781: the producer repaints (act, memories) every step, so scoring each
    repaint counted one match hundreds of times."""
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    plan = [
        {
            "kind": "plan",
            "importance": 5.0,
            "text": "Plan: go to Cafe and eating breakfast.",
            "created_turn": 0,
        }
    ]
    shelving = [
        {
            "kind": "observation",
            "importance": 2.0,
            "text": "I am shelving books.",
            "created_turn": 40,
        }
    ]
    # 40 repaints of one decision, then two more decisions -- the second of
    # which retrieves a memory unrelated to what it is doing.
    ev.retrievals = (
        [
            {
                "step": s,
                "act": "eating breakfast @ T:Cafe:counter",
                "reasoning": None,
                "memories": plan,
            }
            for s in range(40)
        ]
        + [
            {
                "step": 40,
                "act": "shelving books @ T:Library:spot",
                "reasoning": None,
                "memories": shelving,
            },
            {
                "step": 41,
                "act": "shelving books @ T:Library:spot",
                "reasoning": None,
                "memories": plan,
            },
        ]
    )

    score = judge._memory_use(ev)
    assert score.note == "2/3 decisions used a relevant memory"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py::test_memory_use_counts_decisions_not_repainted_frames -v
```

Expected: FAIL with the note reading `"41/42 decisions used a relevant memory"` —
all 40 repaints scored separately.

- [ ] **Step 3: Add the helper**

In `believability.py`, insert immediately after `_longest_nondecreasing` (which
ends at line 524) and before the
`# ---- The deterministic heuristic judge` banner:

```python
def _decisions_in(retrievals: list[dict]) -> list[dict]:
    """Collapse repainted retrieval frames into one entry per decision.

    A frame carries the act and the memories retrieval surfaced for it, and the
    producer repaints both unchanged for every step the activity runs. Scoring
    each repaint counted one match once per step -- 1200 frames of Diego's #760
    batch-1 run are 14 decisions -- which handed a monotonous day a perfect
    memory-use score (#781). Keeping only the frames where ``(act, memories)``
    changes leaves one entry per actual decision.

    Same collapse ``_segments_for`` does for acts and ``_merge_growth_windows``
    (#799) does for conversations.
    """
    decisions: list[dict] = []
    previous = None
    for r in retrievals:
        key = (r["act"], json.dumps(r["memories"], sort_keys=True))
        if key != previous:
            decisions.append(r)
            previous = key
    return decisions
```

- [ ] **Step 4: Rewrite `_memory_use`**

Replace the whole `_memory_use` method with:

```python
    def _memory_use(self, ev: AgentEvidence) -> DimScore:
        """Were the memories retrieved for each decision relevant to it?

        A decision frame carries the memories retrieval surfaced for it; a
        relevant retrieval shares a content word with the action taken (or the
        reasoning given for it). Counted once per *decision*, not once per
        frame -- see :func:`_decisions_in` (#781).
        """
        decisions = _decisions_in(ev.retrievals)
        if not decisions:
            return DimScore(None, note="no decision frames carry retrieved memories")
        relevant = 0
        evidence = []
        for r in decisions:
            decision_words = _content_words(f"{r['act']} {r.get('reasoning') or ''}")
            hit = None
            for mem in r["memories"]:
                if _content_words(mem.get("text", "")) & decision_words:
                    hit = mem
                    break
            if hit is not None:
                relevant += 1
                if len(evidence) < 2:
                    evidence.append(
                        f"step {r['step']} ({ev.time_at(r['step'])}): retrieved "
                        f"'{hit['text']}' while '{r['act']}'"
                    )
            elif len(evidence) < 3:
                evidence.append(
                    f"step {r['step']} ({ev.time_at(r['step'])}): none of the "
                    f"{len(r['memories'])} retrieved memories relate to "
                    f"'{r['act']}'"
                )
        fraction = relevant / len(decisions)
        return DimScore(
            _scale(fraction),
            evidence,
            f"{relevant}/{len(decisions)} decisions used a relevant memory",
        )
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "fix(#781): memory use scores decisions, not repainted frames"
```

---

### Task 3: `_social_grounding` credits conversation novelty

A pair re-running the same conversation eight times scored a perfect 10.0 — every
window was co-located, valid, and (because their streams by then contained
everything they had said) grounded. Add a fourth term: how much of a conversation
is *new* relative to earlier conversations between the same participants.

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py:694-770`
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `_content_words`, `AgentEvidence.conversations` (a `list[Conversation]` with `.start`, `.end`, `.participants`, `.transcript`), `AgentEvidence.positions`, `AgentEvidence.vision_r`, `AgentEvidence.memory_texts`.
- Produces: `HeuristicJudge._social_grounding(ev, evidence_by_name) -> DimScore` — same signature. Per-conversation weights become `0.3` co-location, `0.3` grounding, `0.1` speaker validity, `0.3` novelty.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_believability_eval.py`:

```python
# ------------------------------------------------------------ social grounding


FIRST_CHAT = [
    ["Ada", "The pancakes here are excellent."],
    ["Bea", "The pancakes really are excellent."],
]
SECOND_CHAT = [
    ["Ada", "My shelving rota starts at noon."],
    ["Bea", "My weights session starts at noon."],
]


def _social_score(second_transcript):
    """Ada's social grounding when her pair's second conversation carries
    *second_transcript*. Both windows fall while Ada and Bea walk together,
    so co-location and speaker validity are identical either way and only
    novelty moves."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    windows = [_convo(1, 2, FIRST_CHAT), _convo(3, 4, second_transcript)]
    for ev in evidence.values():
        ev.conversations = list(windows)
    return judge._social_grounding(evidence["Ada"], evidence)


def test_social_grounding_penalises_a_rerun_conversation():
    """#781: the #778 loop pairs re-ran one conversation and scored 10/10."""
    fresh = _social_score(SECOND_CHAT)
    rerun = _social_score(FIRST_CHAT)

    assert fresh.score - rerun.score >= 1.0
    assert any("new to this pair" in line for line in rerun.evidence)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py::test_social_grounding_penalises_a_rerun_conversation -v
```

Expected: FAIL — `fresh.score` and `rerun.score` are currently identical (novelty
is not scored), so the difference is `0.0`.

- [ ] **Step 3: Add novelty to the scoring loop**

In `_social_grounding`, change the loop header to sort explicitly and track spoken
vocabulary per pair. Replace:

```python
        scores = []
        evidence = []
        for conv in ev.conversations:
```

with:

```python
        scores = []
        evidence = []
        # Per-pair vocabulary so far, for the novelty term below. Windows are
        # already start-ordered; sorting says so rather than relying on it.
        spoken: dict[frozenset[str], set[str]] = {}
        for conv in sorted(ev.conversations, key=lambda c: (c.start, c.end)):
```

Then replace the block that appends the score and evidence:

```python
            scores.append(0.4 * coloc + 0.4 * grounding + 0.2 * valid)
            evidence.append(
                f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                f"conversation between {', '.join(conv.participants)} -- "
                f"co-located {coloc:.0%} of the window, "
                f"{grounded}/{substantive} substantive lines grounded in both "
                f"streams"
            )
```

with:

```python
            # Novelty: how much of this window is new to this pair. A pair
            # re-running the same conversation scored a perfect 10 before --
            # every re-run is co-located, valid, and grounded in streams that
            # by then contain everything they have already said (#781). Decays
            # monotonically across the #778 loops (1.00 -> 0.04) and stays high
            # for pairs whose conversations actually go somewhere.
            pair = frozenset(conv.participants)
            said_before = spoken.get(pair, set())
            window_words = _content_words(" ".join(text for _, text in lines))
            novelty = (
                len(window_words - said_before) / len(window_words)
                if window_words
                else 1.0
            )
            spoken[pair] = said_before | window_words

            scores.append(0.3 * coloc + 0.3 * grounding + 0.1 * valid + 0.3 * novelty)
            evidence.append(
                f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                f"conversation between {', '.join(conv.participants)} -- "
                f"co-located {coloc:.0%} of the window, "
                f"{grounded}/{substantive} substantive lines grounded in both "
                f"streams, {novelty:.0%} of its words new to this pair"
            )
```

Also extend the method's docstring — replace its closing line
`memory streams (not confabulation)?"""` with:

```python
        memory streams (not confabulation); and does each conversation say
        anything the pair has not already said (#781)?
        """
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "fix(#781): social grounding credits conversation novelty"
```

---

### Task 4: a silent agent who had the chance gets scored

`social_grounding` returns `None` for an agent who never spoke, and `None` drops
out of every mean. Wesley Okafor stood within sight of another agent for 23% of
batch-1's R4 and never said a word — and was the highest-scoring agent in the
whole batch at 9.67. Score a silent agent who had the opportunity; keep `n/a` for
one who genuinely never did.

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py` — add `SILENT_COLOCATION_FLOOR` beside `DIMENSIONS` (after line 370); replace the early return at line 704-705
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `AgentEvidence.positions`, `.vision_r`, `.n_steps`, `.name`; the `evidence_by_name` parameter already passed to `_social_grounding`.
- Produces: module constant `SILENT_COLOCATION_FLOOR = 0.10`.

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tests/test_believability_eval.py`:

```python
def test_social_grounding_scores_a_silent_agent_who_had_the_chance():
    """#781: never speaking used to mean n/a, which drops out of the mean --
    R4's silent Wesley Okafor was the top-scoring agent in the batch."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    for ev in evidence.values():
        ev.conversations = []

    score = judge._social_grounding(evidence["Ada"], evidence)
    assert score.score == 1.0
    assert "never spoke" in score.note
    assert "55%" in score.note  # Ada is within sight of Bea for 33 of 60 steps


def test_social_grounding_stays_na_for_an_agent_who_was_never_near_anyone():
    """The floor only penalises a missed opportunity, not solitude."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    for ev in evidence.values():
        ev.conversations = []
    evidence["Ada"].positions = [(500, 500)] * evidence["Ada"].n_steps

    assert judge._social_grounding(evidence["Ada"], evidence).score is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -k silent_agent -v
uv run pytest godot-generative-agents/tests/test_believability_eval.py -k never_near_anyone -v
```

Expected: the first FAILS (`score.score` is `None`, not `1.0`); the second PASSES
already (it pins behaviour the change must preserve).

- [ ] **Step 3: Add the constant**

In `believability.py`, immediately after the `DIMENSIONS` tuple (which closes on
line 370), add:

```python
# A silent agent this co-located had someone to talk to and did not. Below it,
# social grounding stays n/a -- solitude is not a social failure (#781).
SILENT_COLOCATION_FLOOR = 0.10
```

- [ ] **Step 4: Replace the early return**

In `_social_grounding`, replace:

```python
        if not ev.conversations:
            return DimScore(None, note="no conversations observed for this agent")
```

with:

```python
        if not ev.conversations:
            near = sum(
                1
                for step in range(ev.n_steps)
                if any(
                    step < len(other.positions)
                    and (ev.positions[step][0] - other.positions[step][0]) ** 2
                    + (ev.positions[step][1] - other.positions[step][1]) ** 2
                    <= ev.vision_r**2
                    for name, other in evidence_by_name.items()
                    if name != ev.name
                )
            )
            fraction = near / ev.n_steps if ev.n_steps else 0.0
            if fraction < SILENT_COLOCATION_FLOOR:
                return DimScore(
                    None, note="no conversations observed for this agent"
                )
            # Scored, not skipped: an n/a drops out of every mean, so never
            # speaking used to be free (#781). Flat, because the dimension has
            # nothing to grade -- the note carries what actually happened.
            return DimScore(
                _scale(0.0),
                [
                    f"within sight of another agent for {near} of "
                    f"{ev.n_steps} steps without ever speaking"
                ],
                f"never spoke, though within sight of another agent for "
                f"{fraction:.0%} of the run",
            )
```

- [ ] **Step 5: Fix the existing test this breaks**

`test_heuristic_social_grounding_is_na_without_conversations` (around line 681)
strips every `chat` but leaves Ada standing beside Bea for 55% of the run — so she
is now *scored*, and the test fails on both its assertions. Its intent (an `n/a`
dimension is excluded from the mean, not counted as zero) is still worth pinning;
give it an agent who genuinely had no one to talk to. Replace it with:

```python
def test_heuristic_social_grounding_is_na_without_conversations():
    replay = make_replay()
    for frame in replay["frames"]:
        for entry in frame.values():
            entry["chat"] = None
        # Out of everyone's sight, too: since #781 a silent agent who stood
        # within vision of someone is scored rather than skipped.
        frame["Ada"]["x"], frame["Ada"]["y"] = 500, 500
    report = audit(replay, judge=HeuristicJudge(), source="fixture")
    entry = report["agents"]["Ada"]["dimensions"]["social_grounding"]
    assert entry["score"] is None
    assert "no conversations" in entry["note"].lower()
    # An n/a dimension is excluded from the means, not counted as zero.
    assert report["agents"]["Ada"]["overall"] >= 7
```

- [ ] **Step 6: Run the tests**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "fix(#781): score a silent agent who stood within sight of someone"
```

---

### Task 5: the run summary names its weakest agent

A run's mean over agents lets a broken pair hide behind a healthy majority. Report
the floor beside the mean.

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py:948-990` (`audit`) and `:1249-1288` (`render_markdown`)
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Produces: `report["summary"]["weakest"]` — `{"name": str, "score": float}`, or `None` when no agent could be scored. Judge-agnostic; the LLM judge gets it too.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_believability_eval.py`:

```python
# ------------------------------------------------------------ run roll-up


def test_summary_names_the_weakest_agent():
    """#781: a run mean lets a broken pair hide behind a healthy majority."""
    report = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    weakest = report["summary"]["weakest"]
    scores = {n: a["overall"] for n, a in report["agents"].items()}

    assert weakest["name"] in scores
    assert weakest["score"] == min(scores.values())
    assert f"Weakest agent | {weakest['name']}" in render_markdown(report)
```

Add `render_markdown` to the import block at the top of the test file (it
currently imports `DIMENSIONS, HeuristicJudge, LlmJudge, audit, build_evidence,
evidence_text, load_replay, main, scramble_replay`).

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py::test_summary_names_the_weakest_agent -v
```

Expected: FAIL with `KeyError: 'weakest'`.

- [ ] **Step 3: Add `weakest` to `audit()`**

In `audit`, replace:

```python
    overall = _mean([a["overall"] for a in agents.values() if a["overall"] is not None])
    return {
        "run": {
            "source": source,
            "steps": len(replay.get("frames", [])),
            "personas": len(evidence),
            "scramble": scramble,
        },
        "judge": judge_info(judge),
        "agents": agents,
        "summary": {"overall": overall, "by_dimension": by_dimension},
    }
```

with:

```python
    scored = {
        name: a["overall"]
        for name, a in agents.items()
        if a["overall"] is not None
    }
    overall = _mean(list(scored.values()))
    # The floor beside the mean: a run mean over agents lets a broken pair hide
    # behind a healthy majority, which is how #760's groundhog-day run outscored
    # the healthiest one (#781).
    weakest = (
        {"name": min(scored, key=lambda n: scored[n]), "score": min(scored.values())}
        if scored
        else None
    )
    return {
        "run": {
            "source": source,
            "steps": len(replay.get("frames", [])),
            "personas": len(evidence),
            "scramble": scramble,
        },
        "judge": judge_info(judge),
        "agents": agents,
        "summary": {
            "overall": overall,
            "weakest": weakest,
            "by_dimension": by_dimension,
        },
    }
```

- [ ] **Step 4: Render it**

In `render_markdown` (line 1277), replace this single line:

```python
    lines.append(f"| **Overall** | **{_fmt_score(report['summary']['overall'])}** |")
```

with:

```python
    lines.append(f"| **Overall** | **{_fmt_score(report['summary']['overall'])}** |")
    weakest = report["summary"].get("weakest")
    if weakest:
        lines.append(
            f"| Weakest agent | {weakest['name']} "
            f"({_fmt_score(weakest['score'])}) |"
        )
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "feat(#781): report the weakest agent beside the run mean"
```

---

### Task 6: flag repeat-conversation loops

The ordering problem is not fully expressible as a score — so name the pathology.
Flag a pair with **≥3 conversations and mean novelty < 0.60**: on batch-1 that is
exactly the two #778 loops (R2 Aiden+Chris 0.44, R3 Hannah+Ravi 0.54) and nothing
else (R4 Casey+Dana 0.72, R1 Diego+Sofia 0.84).

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py` — add two constants beside `SILENT_COLOCATION_FLOOR`; add `_repeat_loops` above the `HeuristicJudge` banner beside `_decisions_in`; call it from `audit`; render it
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `build_evidence`'s output (`dict[str, AgentEvidence]`), `Conversation`, `_content_words`.
- Produces: `_repeat_loops(evidence: dict[str, AgentEvidence]) -> list[dict]`, each `{"participants": list[str], "conversations": int, "mean_novelty": float}`, sorted worst-first. Surfaces as `report["summary"]["loops"]` (always a list, empty when clean).

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_believability_eval.py`:

```python
def test_summary_flags_a_repeat_conversation_loop():
    """#781: the #778 loop is the pathology a single score cannot express --
    three re-runs of one conversation between the same pair."""
    replay = make_replay()
    report = audit(replay, judge=HeuristicJudge(), source="fixture")
    assert report["summary"]["loops"] == []  # one conversation is not a loop

    evidence = build_evidence(replay)
    windows = [
        _convo(1, 2, CHAT),
        _convo(3, 4, CHAT),
        _convo(5, 6, CHAT),
    ]
    for ev in evidence.values():
        ev.conversations = list(windows)
    loops = _repeat_loops(evidence)

    assert len(loops) == 1
    assert loops[0]["participants"] == ["Ada", "Bea"]
    assert loops[0]["conversations"] == 3
    # First window is all-new, the two re-runs add nothing: (1 + 0 + 0) / 3.
    assert loops[0]["mean_novelty"] == 0.33


def test_render_markdown_names_a_flagged_loop():
    report = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    report["summary"]["loops"] = [
        {"participants": ["Ada", "Bea"], "conversations": 8, "mean_novelty": 0.44}
    ]
    rendered = render_markdown(report)

    assert "Repeat-conversation loop" in rendered
    assert "Ada <-> Bea" in rendered
    assert "8 conversations, mean novelty 0.44" in rendered
```

Add `_repeat_loops` to the test file's import block.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -k loop -v
```

Expected: FAIL at import — `cannot import name '_repeat_loops'`.

- [ ] **Step 3: Add the constants**

Beside `SILENT_COLOCATION_FLOOR`, add:

```python
# A pair that met this often and said this little that was new was re-running one
# conversation, not having several (#778, flagged for #781). On the #760 batch-1
# runs these catch both loop pairs (0.44, 0.54) and neither healthy pair
# (0.72, 0.84). A false positive costs a line of report text, not a score.
REPEAT_LOOP_MIN_CONVERSATIONS = 3
REPEAT_LOOP_MAX_NOVELTY = 0.60
```

- [ ] **Step 4: Add `_repeat_loops`**

Immediately after `_decisions_in`:

```python
def _repeat_loops(evidence: dict[str, AgentEvidence]) -> list[dict]:
    """Participant pairs that kept re-running the same conversation.

    The run mean cannot express "two of these five agents were stuck in a
    groundhog-day loop" -- it averages them in with the healthy majority. So
    name the pathology instead of trying to compress it into a score (#781).

    Novelty per window is the fraction of its content words the pair had not
    already used; a pair whose mean falls below
    :data:`REPEAT_LOOP_MAX_NOVELTY` over at least
    :data:`REPEAT_LOOP_MIN_CONVERSATIONS` windows is flagged.
    """
    windows: dict[frozenset[str], dict[tuple[int, int], Conversation]] = {}
    for ev in evidence.values():
        for conv in ev.conversations:
            # Every window appears in each participant's evidence -- key by
            # span so a pair's shared conversation is counted once.
            pair = frozenset(conv.participants)
            windows.setdefault(pair, {})[(conv.start, conv.end)] = conv

    loops: list[dict] = []
    for pair, spans in windows.items():
        ordered = [spans[k] for k in sorted(spans)]
        if len(ordered) < REPEAT_LOOP_MIN_CONVERSATIONS:
            continue
        said_before: set[str] = set()
        novelties = []
        for conv in ordered:
            words = _content_words(
                " ".join(line[1] for line in conv.transcript if len(line) == 2)
            )
            novelties.append(
                len(words - said_before) / len(words) if words else 1.0
            )
            said_before |= words
        mean_novelty = sum(novelties) / len(novelties)
        if mean_novelty < REPEAT_LOOP_MAX_NOVELTY:
            loops.append(
                {
                    "participants": sorted(pair),
                    "conversations": len(ordered),
                    "mean_novelty": round(mean_novelty, 2),
                }
            )
    loops.sort(key=lambda loop: (loop["mean_novelty"], loop["participants"]))
    return loops
```

- [ ] **Step 5: Call it from `audit` and render it**

In `audit`, add to the summary dict (after `"weakest": weakest,`):

```python
            "loops": _repeat_loops(evidence),
```

In `render_markdown`, after the weakest-agent row added in Task 5:

```python
    for loop in report["summary"].get("loops") or []:
        lines += [
            "",
            f"> **Repeat-conversation loop** -- "
            f"{' <-> '.join(loop['participants'])}: "
            f"{loop['conversations']} conversations, mean novelty "
            f"{loop['mean_novelty']:.2f}",
        ]
```

- [ ] **Step 6: Run the tests**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
git commit -m "feat(#781): flag repeat-conversation loops in the run summary"
```

---

### Task 7: re-tighten the scrambled-control acceptance tests

Both controls currently assert `>= 1.0`. After Tasks 1–6 the fixture's real margins
are much wider — pin them so a future change cannot quietly re-saturate a dimension,
which is exactly how the current state arose.

**Files:**
- Modify: `godot-generative-agents/tests/test_believability_eval.py:694-717`

**Interfaces:**
- Consumes: `audit`, `scramble_replay`, `HeuristicJudge`, `make_replay` (all existing).
- Produces: nothing new.

- [ ] **Step 1: Confirm the current margins**

```bash
uv run python -c "
import sys; sys.path.insert(0,'godot-generative-agents'); sys.path.insert(0,'godot-generative-agents/tests')
from test_believability_eval import make_replay
from backend.eval.believability import audit, scramble_replay, HeuristicJudge
j=HeuristicJudge(); i=audit(make_replay(), judge=j)
f=audit(scramble_replay(make_replay(),'frames',seed=7), judge=j)
p=audit(scramble_replay(make_replay(),'plans',seed=0), judge=j)
print('intact', i['summary']['overall'], i['summary']['by_dimension']['plan_coherence'])
print('frames', f['summary']['overall'], '-> overall drop', round(i['summary']['overall']-f['summary']['overall'],2))
print('plans ', p['summary']['by_dimension']['plan_coherence'], '-> plan drop',
      round(i['summary']['by_dimension']['plan_coherence']-p['summary']['by_dimension']['plan_coherence'],2))
"
```

Expected (measured 2026-07-27 with all five changes prototyped): intact overall
**9.50**, plan **10.0**; scrambled frames overall **7.34**, drop **2.16**; swapped
plans `plan_coherence` **5.5**, drop **4.5**.

If your numbers differ from these, stop and reconcile — a mismatch means one of
Tasks 1–6 did not land as specified. Do not simply write down whatever you got.

- [ ] **Step 2: Tighten both assertions**

Replace the two test bodies:

```python
def test_scrambled_frames_score_measurably_worse():
    """The issue's acceptance control: a shuffled run must lose points.

    Pinned tight (#781): the margin was >= 1.0 while `plan_coherence` coverage
    read 100% for everything. Re-saturating a dimension has to fail here.
    """
    replay = make_replay()
    judge = HeuristicJudge()  # deterministic, so the comparison is exact
    intact = audit(replay, judge=judge, source="fixture")
    control = audit(
        scramble_replay(replay, "frames", seed=7), judge=judge, source="control"
    )
    assert intact["summary"]["overall"] - control["summary"]["overall"] >= 2.0


def test_swapped_plans_score_worse_on_plan_coherence():
    replay = make_replay()
    judge = HeuristicJudge()
    intact = audit(replay, judge=judge, source="fixture")
    control = audit(
        scramble_replay(replay, "plans", seed=0), judge=judge, source="control"
    )
    drop = (
        intact["summary"]["by_dimension"]["plan_coherence"]
        - control["summary"]["by_dimension"]["plan_coherence"]
    )
    assert drop >= 4.0  # #781: was >= 1.0 against the saturated coverage term
    assert intact["summary"]["overall"] > control["summary"]["overall"]
```

- [ ] **Step 3: Run the whole suite**

```bash
uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
uv run pytest tests/ -q
```

Expected: all PASS in both.

- [ ] **Step 4: Format check**

```bash
uv run black --check godot-generative-agents/backend/eval/believability.py godot-generative-agents/tests/test_believability_eval.py
```

If it reports changes, run without `--check` and re-run the tests.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tests/test_believability_eval.py
git commit -m "test(#781): pin the scrambled controls to their real margins"
```

---

### Task 8: validate against batch-1 and record the result

The acceptance bar is measured on the #760 batch-1 runs, which live on
`runs/issue-760-live-batch-1`, not `main`.

**Files:**
- Modify: `godot-generative-agents/docs/specs/2026-07-27-believability-progress-metric.md` (add a "Measured result" section)
- Modify: `godot-generative-agents/backend/README.md` (document the two new summary fields)

**Interfaces:**
- Consumes: the finished module.
- Produces: the numbers for the PR body and the #760 comment.

- [ ] **Step 1: Extract the runs**

```bash
mkdir -p /tmp/b1 && git archive runs/issue-760-live-batch-1 \
  godot-generative-agents/runs | tar -x -C /tmp/b1
ls /tmp/b1/godot-generative-agents/runs
```

Expected: the run directories plus `sim.db` (`load_replay` on a run directory needs
`sim.db` beside it). This does not touch your working tree.

- [ ] **Step 2: Audit all five runs with Penn's locations injected**

```bash
cat > /tmp/b1/audit.py <<'PY'
import sys
sys.path.insert(0, "godot-generative-agents")
from backend.eval.believability import load_replay, audit, HeuristicJudge
from backend.penn.penn_world import build_penn_world

LOCS = sorted(l["name"] for l in build_penn_world().locations)
R = "/tmp/b1/godot-generative-agents/runs"
RUNS = [("R1", "run-20260724-193817-d528ec"), ("R2", "run-20260724-194343-78858a"),
        ("R3", "run-20260724-195642-584ead"), ("R4", "run-20260724-201036-e8c405"),
        ("R5", "run-20260724-202121-e51349")]
for tag, rid in RUNS:
    replay = load_replay(f"{R}/{rid}")
    replay["meta"]["locations"] = LOCS  # pre-#780 bake; see spin-off issue 1
    report = audit(replay, judge=HeuristicJudge(), source=tag)
    s = report["summary"]
    print(f"{tag}: overall={s['overall']} weakest={s['weakest']} loops={s['loops']}")
    for name, a in sorted(report["agents"].items(), key=lambda kv: kv[1]["overall"] or 0):
        print(f"    {name:22} {a['overall']}")
PY
uv run python /tmp/b1/audit.py
```

- [ ] **Step 3: Check the acceptance bar**

Every one of these must hold. Record the actual numbers.

1. R2's Aiden Park and Chris Donnelly are the **two lowest** agents in R2 (they
   were 4th and 2nd of 5, at 9.15 and 9.25).
2. R4's Wesley Okafor is no longer the batch's top agent (he was 9.67).
3. R1's overall is **not last** of the five (it was 8.05, 5th).
4. `loops` is non-empty for R2 and R3, and **empty** for R1, R4, R5.
5. R2's flagged pair is `["Aiden Park", "Chris Donnelly"]`; R3's is
   `["Hannah Whitfield", "Ravi Deshmukh"]`.

Reference from the spec's prototype: `R2 8.89 > R1 8.52 > R4 8.39 > R5 7.90 >
R3 7.75`. Small deviations are fine — the five conditions above are the bar, the
ordering is not.

If a condition fails, stop and report which one with its numbers rather than
adjusting a threshold to make it pass.

- [ ] **Step 4: Record the result in the spec**

Append a `## Measured result (implementation)` section to
`godot-generative-agents/docs/specs/2026-07-27-believability-progress-metric.md`
with the before/after run table, the per-agent moves for Aiden, Chris, Wesley and
R1's three, and the flagged pairs — the actual numbers from Step 2, not the
prototype's.

- [ ] **Step 5: Document the new summary fields**

In `godot-generative-agents/backend/README.md`, find the believability section and
add to it:

```markdown
The run summary also carries `weakest` (the lowest-scoring agent, name and score)
and `loops` (participant pairs that kept re-running one conversation: their
conversation count and mean novelty). Both render in the markdown report. A run
mean over agents hides a broken pair behind a healthy majority, so read the floor
and the flags, not just the mean (#781).
```

- [ ] **Step 6: Run the full gate**

```bash
uv run black --check .
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/docs/specs/2026-07-27-believability-progress-metric.md godot-generative-agents/backend/README.md
git commit -m "docs(#781): record the batch-1 validation result"
```

- [ ] **Step 8: Open the PR**

Target `main`. Reviewers are the Godot/geo owners (@aking526 + @0frankie) — the
change is under `godot-generative-agents/`. Use `--body-file`, never
`--body "$(cat <<EOF...)"` (bad substitution).

The body must carry: the before/after run table, the four defects with their
mechanisms, the five acceptance conditions with their measured results, and an
explicit statement that **R1 does not reach #1 and the run-mean ordering is not
the bar** — with the reason (R2's mean is diluted by three healthy agents).

Then comment the same table on #760, and note on #781 which of its bullets this
PR closes.

---

## Follow-ups (do not fold into this PR)

Both filed 2026-07-27; neither belongs in this PR:

- **#813** — `world_grounding` reads `n/a` on every pre-#780 bake, so the dimension
  cannot fire on the runs that motivated it. Attached as a sub-issue of #760.
  Task 8's `meta.locations` injection is the workaround this issue would retire.
- **#814** — score memory *carry*: a later conversation reusing a fact from an
  earlier one. The novelty term in Task 3 is the cheap proxy; true carry detection
  is its own piece of work. Records the measured dead ends (retrieval reach is
  backwards) so they aren't re-derived.
