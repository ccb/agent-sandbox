# Dialogue place grounding: real geography vs. off-map backstory

**Status:** design spec, not yet implemented. Addresses
[#780](https://github.com/ccb/agent-sandbox/issues/780).

Agents invent world geography while talking, and a second agent then claims to
have *visited* the invention. In run `run-20260724-201036-e8c405` Dana placed a
boathouse "right down by the river — maybe a ten-minute walk if you cut through
the athletic complex", and ninety-five steps later Casey reported the trip with
sensory detail ("the light was actually perfect down there"). No boathouse, no
river, no athletic complex exists, and Casey never occupied a fourth location.
Both halves landed in both agents' `chat` memory streams, indistinguishable from
a real observation, and were still being discussed a hundred steps later.

The root cause is structural, not a model failure: **the dialogue prompt carries
no world context at all.** `_dialogue_observation`
(`text_adventure_games/conversation.py:249`) passes exactly three things — the
partner's name, memories retrieved by partner-name, and the transcript so far.
No current location, no place list, no beliefs, no visit history. The *decide*
path gets all of it (`game.describe_for()` plus a `destination` enum capped at
20, `godot-generative-agents/backend/cognition.py:824`). So agents discuss
geography with zero grounding by construction, and nothing downstream checks
what they said against the world.

This design fixes it on the input side and adds a free offline detector so the
fix is measurable.

---

## 1. Goals and non-goals

**Goals**

- An agent talking about places is *told* which places are real and reachable,
  where it is, and where it has actually been.
- Zero change to dialogue text. Nothing new appears in the Godot chat bubbles,
  the replay, or either agent's memory stream.
- Zero change to any game that doesn't opt in. Action Castle, `hw1_llm`, and the
  byte-identical mock bake are untouched.
- The failure is detectable offline, for free, from a finished replay — so the
  fix can be verified against the run that surfaced it rather than by re-reading
  a live-Haiku transcript by hand.

**Explicit non-goal: we do not ban off-map talk.** Dana's persona *is* a varsity
rower. Her mentioning a boathouse is in character and should stay possible. What
she must not do is give walking directions to it or invite someone to meet her
there, and what Casey must not do is claim she went. The distinction we enforce
is **epistemic status**, not vocabulary.

**Rejected alternative: tokens in the dialogue text.** An earlier proposal had
the model append `(real)` / `(not-in-map)` after each place it names. Two
problems. First, to tag correctly the model needs the real-place list anyway —
and once it has that, the tag is derivable mechanically, so the output field
earns nothing. Second, dialogue text is not a private channel: `_publish_chat`
(`cognition.py:1781`) paints the raw utterance onto the frame, the exporter
writes it verbatim, the Godot viewer renders it, and `_remember`
(`conversation.py:235`) stores it as `I said to Casey: "…"` in both memory
streams. Tokens would surface in all four places unless a stripping pass were
added to each.

---

## 2. Part 1 — the grounding block (prevention)

### 2.1 The template

New `text_adventure_games/prompt_templates/place_grounding.prompty`, vars
`places`, `here`, `visited`. CLAUDE.md requires new LLM prompt content to live
in a `.prompty`, be rendered via `prompt_templates.render()`, be listed in
`prompt_templates/README.md`, and have its exact output pinned in
`tests/test_prompt_templates.py`. `_dialogue_observation` hand-builds its string
in Python today, but new prompt text follows the documented rule rather than the
local precedent.

It renders to:

```
Places in this world you can walk to:
  College Hall, Houston Hall, Houston Hall — Billiard Room, …
You are at Houston Hall. You have been to: College Hall, Houston Hall,
Irvine Auditorium.

Anywhere else you mention is somewhere from your life outside this world.
You may talk about it, but do not claim to have just been there, and do not
invite anyone to meet you there.
```

The last two clauses target the two specific sentences in #780: Casey's *"Oh
yeah, I totally went!"* and Dana's *"you should come by sometime and check it
out!"*

### 2.2 The engine seam

`exchange()` (`conversation.py:151`) gains two keyword-only arguments,
`places=None` and `visited=None`, threaded into `_dialogue_observation`
(`:249`). Both `None` ⇒ the block is absent ⇒ today's observation string
byte-for-byte.

`_dialogue_observation` takes the same two arguments but deliberately does *not*
gain a `game` parameter, even though its only caller has one in scope. The
caller supplies the two collections instead. This keeps it a pure function of its
arguments, unit-testable without building a world, and keeps the engine from
growing an opinion about what a "real place" is.

Two edge cases, specified so they can't be guessed at:

- **Empty `places`** (or more than `DECIDE_MAX_ENUM` of them) ⇒ the *entire*
  block is omitted, not just the list line. The instruction sentence is
  meaningless without the vocabulary it refers to.
- **Empty `visited`**, or `visited` containing only the current location ⇒ the
  `You have been to: …` sentence is omitted; the `You are at X.` sentence still
  renders. This is the normal state early in a run.

The same observation string is reused verbatim across all three converse routes
— cognition-tools, structured, and free-text (`npc.py:802-808`); only the system
message differs. So one change covers every path, and the block must read
correctly in all three.

### 2.3 Block placement is load-bearing

**The block appends *below* the first line, never above it.**

`ScheduleMockClient.call_tool` (`cognition.py:400-448`) lacks the
conversing-marker check that its `_decide` sibling has (`:409-417`) and routes on
`first_line_location(observation)` (`:264-274`) — "first non-empty line,
lowercased". A line inserted above `"You are talking with X."` that happened to
match the current destination would consume a queued authored command and
increment `_commands_used`, a stateful side effect corrupting later decides.
Appending below the first line is inert. This gets its own test so a future
refactor can't quietly reorder it.

### 2.4 Where `visited` comes from

Nothing in the engine or backend tracks which locations a character has
occupied:

- `Character` holds `location` (current only) and does not serialize history
  (`things/characters.py:74-137`, `178-207`).
- `Location.has_been_visited` exists (`things/locations.py:60`) but is **global
  and player-only** — the only NPC-reachable writer, `actions/locations.py:117`,
  sits behind `if is_main_player:`. It is unusable here.
- The backend `Travel` action marks nothing (`backend/actions.py:66-73`).

Rather than scrape it back out of the memory stream, the sim accumulates it.
`maybe_converse` (`cognition.py:1912`) already receives the persistent per-agent
`state` dict; at the top of each call it appends every character's current
`location.name` to `state[<name>]["visited"]`, held as a **list in first-visit
order** (not a set — see below). `_advance_conversation` (`:1885`) then passes
that list and `sorted(game.locations)` into `exchange`.

**Neither collection is ever a `set`, and both are rendered sorted.** Iteration
order of a Python `set` of strings varies with `PYTHONHASHSEED`. The rendered
block is part of the LLM request, and cassette keys hash the request
(`text_adventure_games/recording.py:160-170`), so a hash-ordered collection would
break the byte-identical re-run guarantee from #197 / #715. A list keeps `state`
JSON-serializable as well. Sorting at render time is not cosmetic here — it is
what makes the prompt reproducible.

### 2.5 Scope and the cap

Opt-in lives at the single backend call site, so only the generative-agents path
is affected. Action Castle (14 locations) and `hw1_llm` keep today's behavior,
and no dungeon geography leaks to an NPC in a game whose point is discovering
it.

`world_data_upenn.yaml` holds **18 locations** — `Penn campus` (the outdoor
hub), six buildings, and eleven named interiors (seven Van Pelt rooms, three
Houston Hall rooms, one Williams Hall classroom). Note the issue's own framing
("six campus buildings") undercounts, because it grepped for buildings. Above
`DECIDE_MAX_ENUM = 20` the block is dropped, mirroring what `action_tools_for`
already does to the `destination` enum rather than inventing a second rule; the
world YAML already documents 18 of 20 slots in use.

Cost is roughly 90 tokens per dialogue line, small next to the memory block
already in the observation.

### 2.6 Why the bake cannot be affected

`conversation_enabled = llm_client is not None` (`run_simulation.py:971`) is
False under the mock bake, and `maybe_converse` is gated on it (`:729`). So
`exchange` — and therefore `_dialogue_observation` — is never called during a
bake. `test_bake_is_byte_identical` is unreachable from this change even before
the opt-in default is considered.

No test anywhere pins a dialogue observation string, so there is nothing else to
update.

---

## 3. Part 2 — the detector

### 3.1 One additive meta key

The replay does **not** carry per-agent location: the frame row is
`AGENT_FRAME_FIELDS = ("x","y","act","e","reasoning","chat","memories","trace")`
(`backend/contract.py:59`), emitted by `replay_frame_entry`
(`penn_world.py:795`). Frame row key order *is* pinned for byte-identity, so
frames are left alone.

`meta`, however, is explicitly extensible: *"Additive optional fields do NOT
bump [SCHEMA_VERSION]"* and *"`meta` key order is deliberately NOT pinned"*
(`contract.py:94-105`). So `meta["locations"] = sorted(game.locations)` is added
in **both** writers — `generate_penn_replay.py:312` and
`serve_penn.PennStepper.meta():1421` — because those comments insist baked and
live meta stay in lock-step (#297). Exact precedent: `relationships` is already
a world-level fact carried in meta purely for an analysis consumer.

Mirrors to update: the `contract.py` docstring, `contract_models.Meta`, and
`web/src/types/replay.ts`.

### 3.2 The `world_grounding` dimension

Added to `DIMENSIONS` (`backend/eval/believability.py:297`), which alone extends
`BELIEVABILITY_TOOL`'s properties and required list (`:760`),
`summary.by_dimension` (`:699`), and the markdown report order. Then a
`_world_grounding` method on `HeuristicJudge` wired into `score_agent`
(`:405-410`), and a rubric bullet in `believability_rubric.prompty`. Three
edits — the path the file already documents.

The two judges split by what each is actually good at:

| Judge | Does |
|---|---|
| `HeuristicJudge` (free, no LLM) | The mechanical half: scans conversation transcripts for place-ish nouns not accounted for by `meta["locations"]`, then scores the subset carrying an experience cue (§3.3). |
| `LlmJudge` | The semantic half: grades whether a conversation asserts experience the agent's own timeline contradicts. |

**Heuristic.** A ~30-word gazetteer (`boathouse, river, gym, quad, dorm, cafe,
complex, annex, courtyard, …`) finds candidate place nouns. Capitalization is
useless here: Dana's "boathouse", "the river", and "athletic complex" are all
lowercase. Each hit is then checked as a case-insensitive substring against the
real names, so "Kamin Gallery" and "Reception Hall" do not false-positive.

**LLM judge.** `evidence_text` (`:783`) already ships conversation transcripts
*and* the collapsed `act` timeline — and `act` embeds the address
(`@ UPenn:College Hall`), which is exactly what the issue's own `jq` used to
prove Casey never left three buildings. The judge therefore gets the timeline
and the real-place list and needs no address parsing on our side. One added
evidence line lists `meta["locations"]`.

### 3.3 Scoring must match the rule we enforce

§1 deliberately *permits* off-map backstory. A metric that penalized every
off-world mention would measure something we allow and would score Dana's
persona as a defect.

So the heuristic scores only off-world places carrying a first-hand or
invitation cue — `went`, `been there`, `come by`, `meet me`, `minute walk`,
`check it out` — and reports bare mentions as unscored context in the evidence
list. That targets the two actual #780 sentences and leaves the rower alone.
`_scale` maps the clean-line fraction to 1–10 as the other dimensions do.

### 3.4 Known limitation: scramble invariance

`scramble_replay` (`:91-120`) is the control that must score *worse*. But
`world_grounding` reads conversation text, which scrambling `frames` or `plans`
does not alter — so this dimension is scramble-invariant. `overall` is a mean,
so the control still degrades through the other four dimensions. This is
documented next to the dimension rather than papered over with a fake signal.

---

## 4. Files touched

Source only; the test files are listed in §5.

| File | Change |
|---|---|
| `text_adventure_games/prompt_templates/place_grounding.prompty` | new template |
| `text_adventure_games/prompt_templates/README.md` | usage-table row |
| `text_adventure_games/conversation.py` | `exchange` + `_dialogue_observation` gain `places` / `visited`, default `None` |
| `godot-generative-agents/backend/cognition.py` | accumulate visited in `maybe_converse`; pass both from `_advance_conversation` |
| `godot-generative-agents/backend/penn/generate_penn_replay.py` | `meta["locations"]` |
| `godot-generative-agents/backend/penn/serve_penn.py` | `meta["locations"]` (lock-step) |
| `godot-generative-agents/backend/contract.py` | docstring: document the new meta key |
| `godot-generative-agents/backend/contract_models.py` | `Meta.locations` |
| `godot-generative-agents/web/src/types/replay.ts` | TS mirror |
| `godot-generative-agents/backend/eval/believability.py` | `world_grounding` dimension |
| `godot-generative-agents/backend/prompt_templates/believability_rubric.prompty` | rubric bullet |

---

## 5. Testing

- `tests/test_prompt_templates.py` — pin `place_grounding` rendered output
  exactly, per CLAUDE.md.
- `tests/test_conversation.py` — with `places=None, visited=None` the
  observation is unchanged (the byte-identity guarantee); with both supplied the
  block appears, and **appears below the first line** (§2.3).
- Determinism — the rendered block is identical across `PYTHONHASHSEED` values
  (§2.4).
- `godot-generative-agents/tests/test_replay_contract.py` — `meta["locations"]`
  present, sorted, and identical between the bake and the live handshake.
- `godot-generative-agents/tests/test_believability_eval.py` — `world_grounding`
  appears in `DIMENSIONS`, the tool schema, and the markdown; the heuristic
  flags a cue-carrying off-world mention and does *not* flag a bare one or a
  real interior room; the rubric render is re-pinned (`:435`).

## 6. Verification

Run the audit against `run-20260724-201036-e8c405` and confirm it flags Dana at
step 979 and Casey at step 1074. That score is then the regression test: it
should move on the next live batch (#760) with the grounding block in place.

## 7. Deliberate ceilings

- The place-noun gazetteer and the cue list are naive word lists. They exist to
  make the heuristic judge useful offline for free; the LLM judge is the
  fallback when they miss.
- The block is dropped above 20 places rather than truncated or summarized.
- `visited` accumulates only while conversation is enabled — the whole run in
  live mode, which is the only mode where it matters.
