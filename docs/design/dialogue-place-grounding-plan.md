# Dialogue Place Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop agents inventing world geography in dialogue and corroborating each other's inventions (#780), by telling a conversing agent which places are real, and by adding a free offline detector that measures whether it worked.

**Architecture:** Two independent halves. (1) *Prevention* — a new `place_grounding.prompty` block appended to the engine's dialogue observation, opt-in via two default-`None` keyword arguments so every existing caller is byte-identical; the generative-agents backend is the only caller that opts in. (2) *Detection* — one additive `meta["locations"]` key in the replay contract plus a `world_grounding` dimension in the offline believability audit.

**Tech Stack:** Python 3.12, `uv`, pytest, Prompty/Jinja templates, Pydantic (contract models), TypeScript (replay type mirror).

**Spec:** `docs/design/dialogue-place-grounding.md` (read it first — this plan implements it and does not restate its reasoning).

## Global Constraints

- **Tests run from the repo root**, no `PYTHONPATH` needed: `uv run pytest tests/ -q` (engine) and `uv run pytest godot-generative-agents/tests/ -q` (backend — a separate pytest root, not collected by the first).
- **Format gate:** `uv run black .` before every commit. CI runs `uv run black --check .`.
- **Never a `set`** for either place collection. The rendered block is part of the LLM request and cassette keys hash the request (`text_adventure_games/recording.py:160-170`), so `PYTHONHASHSEED`-ordered iteration breaks the #197/#715 byte-identical re-run guarantee. Use lists; sort at render time.
- **The grounding block appends BELOW the observation's first line, never above it.** `ScheduleMockClient.call_tool` (`godot-generative-agents/backend/cognition.py:400-448`) routes on `first_line_location(observation)` and lacks the conversing-marker guard its `_decide` sibling has.
- **Frame row key order is contract-pinned** (`backend/contract.py:59`, byte-identity #297). Add to `meta` only; never to `AGENT_FRAME_FIELDS`.
- **Default `None` ⇒ byte-identical.** With `places=None, visited=None` the dialogue observation string must be unchanged, character for character.
- **New prompt content requires three things** (CLAUDE.md): the `.prompty` file, a row in that package's `prompt_templates/README.md` table, and an exact-output pin in the matching test file.
- **Cap:** at most 20 places, mirroring `DECIDE_MAX_ENUM = 20`. Above it, drop the whole block.
- `godot-generative-agents/tests/conftest.py` has an autouse fixture that **fails any test which appends a row to the real shared `RunStore`** — bake subprocesses must pass `--no-persist`.

---

### Task 1: The `place_grounding` prompt template

**Files:**
- Create: `text_adventure_games/prompt_templates/place_grounding.prompty`
- Modify: `text_adventure_games/prompt_templates/README.md` (add one usage-table row)
- Test: `tests/test_prompt_templates.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `prompt_templates.render("place_grounding", places=str, here=str, visited=str) -> str`. All three inputs are **pre-joined, pre-sorted strings**, not lists — sorting and joining happen in the caller (Task 2) so the template stays dumb and the determinism rule lives in one place.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_prompt_templates.py`, following the file's existing banner-comment style:

```python
# ---------------------------------------------------------------------------
# place_grounding -- the #780 dialogue place-grounding block
# ---------------------------------------------------------------------------

_OFF_MAP = (
    "Anywhere else you mention is somewhere from your life outside this world. "
    "You may talk about it, but do not claim to have just been there, and do "
    "not invite anyone to meet you there."
)


def test_place_grounding_full():
    out = prompt_templates.render(
        "place_grounding",
        places="College Hall, Houston Hall, Irvine Auditorium",
        here="Houston Hall",
        visited="College Hall, Houston Hall",
    )
    assert out == (
        "Places in this world you can walk to: "
        "College Hall, Houston Hall, Irvine Auditorium.\n"
        "You are at Houston Hall.\n"
        "You have been to: College Hall, Houston Hall.\n"
        f"{_OFF_MAP}"
    )


def test_place_grounding_drops_empty_lines():
    # Early in a run an agent has been nowhere yet, and a game may not know
    # where the speaker is standing: both sentences vanish rather than
    # rendering blank.
    out = prompt_templates.render(
        "place_grounding",
        places="College Hall, Houston Hall",
        here="",
        visited="",
    )
    assert out == (
        "Places in this world you can walk to: College Hall, Houston Hall.\n"
        f"{_OFF_MAP}"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_prompt_templates.py -k place_grounding -v`
Expected: FAIL — `FileNotFoundError: No prompt template named 'place_grounding'` (the loader raises loudly on an unknown name, listing available templates).

- [ ] **Step 3: Create the template**

Create `text_adventure_games/prompt_templates/place_grounding.prompty`. Match the frontmatter style of `npc_dialogue.prompty` (a `description` explaining what renders it and why, plus typed `inputs` and a `sample`):

```
---
name: place_grounding
description: >
  Appended to the dialogue observation (text_adventure_games/conversation.py,
  _dialogue_observation, issue #780) so a conversing agent knows which places
  are real and reachable, where it is standing, and where it has actually
  been. Off-map places stay sayable -- a varsity rower may talk about her
  boathouse -- but the agent is told not to claim a just-completed visit and
  not to invite anyone to meet there, which are the two moves that turned an
  invention into shared "fact" in run-20260724-201036-e8c405.
  Two rules the caller must honor: this block is appended BELOW the
  observation's first line (ScheduleMockClient.call_tool routes on the first
  line), and both lists arrive already sorted (the rendered text is part of
  the LLM request and cassette keys hash it, so hash-ordered iteration would
  break the #197/#715 byte-identical re-run guarantee).
inputs:
  places:
    type: string
    description: >
      Comma-joined real location names, pre-sorted by the caller. The caller
      omits the whole block when there are none.
  here:
    type: string
    description: >
      The speaker's current location name. The line is dropped when empty.
  visited:
    type: string
    description: >
      Comma-joined places the speaker has actually occupied, pre-sorted and
      excluding the current one. The sentence is dropped when empty.
sample:
  places: College Hall, Houston Hall, Irvine Auditorium
  here: Houston Hall
  visited: College Hall, Houston Hall
---
Places in this world you can walk to: {{ places }}.
{%- if here %}
You are at {{ here }}.
{%- endif %}
{%- if visited %}
You have been to: {{ visited }}.
{%- endif %}
Anywhere else you mention is somewhere from your life outside this world. You may talk about it, but do not claim to have just been there, and do not invite anyone to meet you there.
```

Note the `{%- if %}` / `{%- endif %}` whitespace trimming: this is the same shape `npc_dialogue.prompty` uses to drop an absent Persona line without leaving a blank line behind.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_prompt_templates.py -k place_grounding -v`
Expected: PASS (2 passed).

If the assertion fails on whitespace, print the repr (`python -c` with `render`) and compare — do **not** loosen the assertion. Exact-output pinning is the point of this file.

- [ ] **Step 5: Add the README usage-table row**

In `text_adventure_games/prompt_templates/README.md`, add a row to the usage table matching the existing column layout. It maps the template to the code that renders it:

`place_grounding` | `conversation._place_grounding_block` (via `_dialogue_observation`) | the #780 real-vs-off-map place block for a conversing agent

- [ ] **Step 6: Format and commit**

```bash
uv run black .
git add text_adventure_games/prompt_templates/place_grounding.prompty \
        text_adventure_games/prompt_templates/README.md \
        tests/test_prompt_templates.py
git commit -m "feat(#780): add the place_grounding dialogue prompt template"
```

---

### Task 2: The engine seam — opt-in `places` / `visited`

**Files:**
- Modify: `text_adventure_games/conversation.py` (`exchange` at `:151`, `_dialogue_observation` at `:249`; new module constant and helper)
- Test: `tests/test_conversation.py`

**Interfaces:**
- Consumes: `prompt_templates.render("place_grounding", places=str, here=str, visited=str)` from Task 1.
- Produces:
  - `conversation.MAX_GROUNDED_PLACES = 20` (module constant).
  - `conversation._place_grounding_block(speaker, places, visited) -> str` — returns `""` when there is nothing to say.
  - `conversation.exchange(game, convo, speaker, listener, *, turn, importance=DEFAULT_CHAT_IMPORTANCE, places=None, visited=None) -> bool`
  - `conversation._dialogue_observation(speaker, listener, convo, turn, places=None, visited=None) -> str`

  `places` and `visited` are `Sequence[str] | None`. `_dialogue_observation` deliberately gains **no** `game` parameter, so it stays a pure function of its arguments. `converse()` is deliberately **not** threaded — the backend's `_advance_conversation` calls `exchange` directly, and that single call site is the opt-in.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_conversation.py`. It already has `_talker` and `_two_in_a_room` helpers (`:26-64`) — reuse them.

```python
# --- #780 place grounding ---------------------------------------------------


def _capture_observation():
    """A ScriptedAgent that records the observation it was handed and says one
    line, so a test can assert on the exact prompt the dialogue seam built."""
    seen = {}
    agent = ScriptedAgent(lambda obs: None)

    def rule(observation, partner_name):
        seen["observation"] = observation
        agent.last_dialogue_done = True
        return "Hello."

    agent.converse_rule = rule
    return agent, seen


def test_exchange_without_places_is_byte_identical():
    # The opt-in default must not perturb any existing game's prompt.
    agent, seen = _capture_observation()
    game, alice, bob = _two_in_a_room(agent, _talker(["Hi."]))
    convo.exchange(game, convo.Conversation(participants=("alice", "bob")),
                   alice, bob, turn=1)
    assert seen["observation"] == (
        "You are talking with bob.\n"
        "You have just met bob. Greet them or start a conversation."
    )


def test_exchange_appends_grounding_below_the_first_line():
    # Placement is load-bearing: ScheduleMockClient.call_tool routes on the
    # observation's FIRST line, so the block must never precede it.
    agent, seen = _capture_observation()
    game, alice, bob = _two_in_a_room(agent, _talker(["Hi."]))
    convo.exchange(
        game,
        convo.Conversation(participants=("alice", "bob")),
        alice,
        bob,
        turn=1,
        places=["Plaza", "Field"],
        visited=["Field", "Plaza"],
    )
    lines = seen["observation"].split("\n")
    assert lines[0] == "You are talking with bob."
    # Sorted, not insertion- or hash-ordered.
    assert "Places in this world you can walk to: Field, Plaza." in lines
    # The speaker stands in the Plaza, so it is named as "here", not repeated
    # in the been-to list.
    assert "You are at Plaza." in lines
    assert "You have been to: Field." in lines


def test_grounding_block_dropped_when_no_places_or_over_cap():
    agent, seen = _capture_observation()
    game, alice, bob = _two_in_a_room(agent, _talker(["Hi."]))
    many = [f"Place {i:02d}" for i in range(convo.MAX_GROUNDED_PLACES + 1)]
    for places in ([], many):
        convo.exchange(
            game,
            convo.Conversation(participants=("alice", "bob")),
            alice,
            bob,
            turn=1,
            places=places,
        )
        assert "Places in this world" not in seen["observation"]


def test_grounding_block_is_hashseed_independent():
    # Determinism guard: the rendered block is part of the LLM request and
    # cassette keys hash the request (#197/#715).
    import os
    import subprocess
    import sys

    code = (
        "from text_adventure_games.conversation import _place_grounding_block as b;"
        "print(b(None, ['Zoo', 'Attic', 'Mall'], ['Mall', 'Attic']))"
    )
    outs = set()
    for seed in ("0", "1", "42"):
        # Inherit the environment (so the venv interpreter resolves its
        # imports) and override only the seed.
        outs.add(
            subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
            ).stdout
        )
    assert len(outs) == 1
    assert "Attic, Mall, Zoo" in outs.pop()  # sorted, not as passed in
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_conversation.py -k "grounding or byte_identical" -v`
Expected: FAIL — `TypeError: exchange() got an unexpected keyword argument 'places'` for three of them; `AttributeError: module ... has no attribute 'MAX_GROUNDED_PLACES'` for the cap test. The `byte_identical` test should already PASS (it pins current behavior); if it fails, stop — the baseline string in the test is wrong and must be corrected before proceeding.

- [ ] **Step 3: Add the constant and helper**

In `text_adventure_games/conversation.py`, near the existing module constants (`DEFAULT_MAX_EXCHANGES` at `:43`, `DEFAULT_CHAT_IMPORTANCE` at `:46`):

```python
# At most this many place names go into a dialogue observation's grounding
# block (issue #780). Mirrors the decide path's destination-enum cap
# (backend/cognition.py DECIDE_MAX_ENUM) rather than inventing a second rule;
# duplicated as a literal because the engine must not import the backend.
MAX_GROUNDED_PLACES = 20
```

Then add the helper next to `_dialogue_observation`:

```python
def _place_grounding_block(speaker, places, visited) -> str:
    """Render the #780 real-vs-off-map place block, or ``""`` when there is
    nothing useful to say.

    Dropped entirely when *places* is empty or exceeds
    :data:`MAX_GROUNDED_PLACES`: without the vocabulary the "anywhere else is
    off-map" instruction is meaningless, so a half-block would mislead rather
    than ground. The speaker's current location is named separately and left
    out of the been-to list, which reads as redundant otherwise.

    Both lists are sorted **here**, so callers cannot leak a hash-ordered
    collection into the prompt: the rendered text is part of the LLM request
    and cassette keys hash the request, so ordering instability would break
    the byte-identical re-run guarantee (issues #197, #715).
    """
    names = sorted(places or ())
    if not names or len(names) > MAX_GROUNDED_PLACES:
        return ""
    here = getattr(getattr(speaker, "location", None), "name", "") or ""
    been = sorted({n for n in (visited or ()) if n and n != here})
    return render(
        "place_grounding",
        places=", ".join(names),
        here=here,
        visited=", ".join(been),
    )
```

**The import must be added** — verified: `conversation.py`'s only import from the package is `from .memory import render_memories` (`:38`). Add below it:

```python
from .prompt_templates import render
```

The module docstring at `:15` advertises that it "imports nothing heavy" — `prompt_templates` is already imported by `npc.py` on every dialogue path, so this adds no new dependency to the process, but keep the import at module level (not inside the helper) to match the file's style.

- [ ] **Step 4: Thread the two keyword arguments**

Change `_dialogue_observation`'s signature and insert the block immediately after the first line:

```python
def _dialogue_observation(
    speaker, listener, convo: Conversation, turn: int, places=None, visited=None
) -> str:
```

and, right after `lines = [f"You are talking with {listener.name}."]`:

```python
    block = _place_grounding_block(speaker, places, visited)
    if block:
        lines.append("")
        lines.append(block)
```

Extend `_dialogue_observation`'s docstring with one sentence: that the optional place block is appended below the first line (never above it, because the schedule mock routes on the first line), and that it is absent unless the caller opts in.

Change `exchange`'s signature and its one call:

```python
def exchange(
    game,
    convo: Conversation,
    speaker,
    listener,
    *,
    turn: int,
    importance: float = DEFAULT_CHAT_IMPORTANCE,
    places=None,
    visited=None,
) -> bool:
```

```python
    observation = _dialogue_observation(
        speaker, listener, convo, turn, places=places, visited=visited
    )
```

Add to `exchange`'s docstring: `places`/`visited` are the optional #780 grounding inputs; both `None` (the default) reproduces the previous observation exactly, and `converse` deliberately does not forward them because the backend's multi-tick caller opts in at its own `exchange` call.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_conversation.py -v`
Expected: PASS — the four new tests plus every pre-existing test in the file (the byte-identity guarantee).

- [ ] **Step 6: Run the whole engine suite**

Run: `uv run pytest tests/ -q`
Expected: PASS, no regressions. This is the real byte-identity check: nothing else in the engine passes `places`, so every other dialogue prompt is untouched.

- [ ] **Step 7: Format and commit**

```bash
uv run black .
git add text_adventure_games/conversation.py tests/test_conversation.py
git commit -m "feat(#780): opt-in place grounding on the dialogue observation"
```

---

### Task 3: Backend wiring — accumulate visits and opt in

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py` (`maybe_converse` at `:1912`, `_advance_conversation` at `:1885`)
- Test: `godot-generative-agents/tests/test_dialogue_place_grounding_780.py` (create)

**Interfaces:**
- Consumes: `conversation.exchange(..., places=, visited=)` from Task 2.
- Produces: `state[<name>]["visited"]` — a `list[str]` of place names in first-visit order, maintained by `maybe_converse`. Task 5 does not read it (the audit is replay-only); nothing else depends on it.

Shapes to rely on, confirmed in the current source: `order` is a list of agent names, `chars` is a `name -> Character` dict, and `state[name]` is a per-agent dict (it already carries `"performing"`, `"path"`, `"conversing"`).

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tests/test_dialogue_place_grounding_780.py`:

```python
"""The #780 dialogue place-grounding wiring.

Pins that the sim accumulates each agent's real visit history and hands it,
with the world's place list, to the engine's dialogue seam. Offline -- the
"brain" here is a stub that records the observation it was given.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_dialogue_place_grounding_780.py -v
"""

from text_adventure_games import conversation as convo
from text_adventure_games.games import Game
from text_adventure_games.npc import ScriptedAgent
from text_adventure_games.things import Character, Location

from backend import cognition


def _world():
    """Two agents standing together in the Plaza, with a Field they can reach."""
    plaza = Location("Plaza", "the plaza")
    field = Location("Field", "a field")
    plaza.add_connection("north", field)
    player = Character("player", "you", "")
    plaza.add_character(player)
    seen = {}

    def make(name):
        agent = ScriptedAgent(lambda obs: None)

        def rule(observation, partner_name):
            seen.setdefault(name, []).append(observation)
            agent.last_dialogue_done = True
            return "Hello."

        agent.converse_rule = rule
        ch = Character(name, name, "")
        ch.set_agent(agent)
        plaza.add_character(ch)
        return ch

    a, b = make("alice"), make("bob")
    game = Game(plaza, player, characters=[a, b])
    return game, a, b, seen


def _state(names):
    return {n: {"performing": True, "path": [], "conversing": False} for n in names}


def test_maybe_converse_records_visits_and_grounds_the_prompt():
    game, a, b, seen = _world()
    state = _state(["alice", "bob"])
    chars = {"alice": a, "bob": b}
    frame = {"alice": {}, "bob": {}}

    cognition.maybe_converse(
        game, chars, state, frame, 1, {}, ["alice", "bob"], active={}
    )

    # Visit history accumulated as a LIST (never a set -- cassette keys hash
    # the rendered prompt, so ordering must be stable).
    assert state["alice"]["visited"] == ["Plaza"]
    assert isinstance(state["alice"]["visited"], list)

    # The speaker's observation names the real world and where it stands.
    first = seen["alice"][0]
    assert first.split("\n")[0].startswith("You are talking with")
    assert "Places in this world you can walk to: Field, Plaza." in first
    assert "You are at Plaza." in first


def test_visited_accumulates_across_steps_without_duplicates():
    game, a, b, seen = _world()
    state = _state(["alice", "bob"])
    chars = {"alice": a, "bob": b}
    frame = {"alice": {}, "bob": {}}
    order = ["alice", "bob"]

    cognition.maybe_converse(game, chars, state, frame, 1, {}, order, active={})
    # Walk alice to the Field, then run another step.
    game.locations["Plaza"].remove_character(a)
    game.locations["Field"].add_character(a)
    cognition.maybe_converse(game, chars, state, frame, 2, {}, order, active={})

    assert state["alice"]["visited"] == ["Plaza", "Field"]  # first-visit order
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_dialogue_place_grounding_780.py -v`
Expected: FAIL — `KeyError: 'visited'` (nothing populates it yet) and the grounding assertions fail because `_advance_conversation` does not pass `places`.

- [ ] **Step 3: Accumulate visits in `maybe_converse`**

In `godot-generative-agents/backend/cognition.py`, immediately after `maybe_converse`'s existing two setup lines (`active = active if active is not None else {}` and `completed = 0`), insert:

```python
    # (0) #780: remember every place each resident has actually stood in, so
    # the dialogue seam can tell a conversing agent where it has really been.
    # Nothing in the engine tracks this: Location.has_been_visited is global
    # AND player-only, and Travel marks nothing. A list in first-visit order,
    # never a set -- this reaches the LLM request and cassette keys hash it.
    for nm in order:
        here = getattr(getattr(chars.get(nm), "location", None), "name", None)
        if not here:
            continue
        been = state[nm].setdefault("visited", [])
        if here not in been:
            been.append(here)
```

Add a sentence to `maybe_converse`'s docstring numbered list describing this as step 0.

- [ ] **Step 4: Opt in at the single `exchange` call**

In `_advance_conversation`, replace the `convo.exchange(...)` call at `:1885` with:

```python
    cont = convo.exchange(
        game,
        ac.convo,
        speaker,
        listener,
        turn=step,
        # #780: the opt-in. Only the generative-agents path grounds its
        # dialogue in the world's real geography; Action Castle / hw1_llm keep
        # the unchanged prompt because they never pass these.
        places=sorted(game.locations),
        visited=state[ac.next_speaker].get("visited", ()),
    )
```

Note `ac.next_speaker` is read **before** the alternation below reassigns it — `speaker` was resolved from it three lines up, so the two agree.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_dialogue_place_grounding_780.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the backend suite, including the byte-identity guard**

Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: PASS. `test_bake_is_byte_identical` and `test_replay_contract.py` must both stay green — the bake never reaches this code (`conversation_enabled = llm_client is not None` is False under the mock), so a failure here means the change leaked somewhere it should not have.

- [ ] **Step 7: Format and commit**

```bash
uv run black .
git add godot-generative-agents/backend/cognition.py \
        godot-generative-agents/tests/test_dialogue_place_grounding_780.py
git commit -m "feat(#780): ground live dialogue in the world's real places"
```

---

### Task 4: Carry the world's place list in the replay contract

**Files:**
- Modify: `godot-generative-agents/backend/penn/generate_penn_replay.py` (the `meta` dict at `:312`)
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`PennStepper.meta()` at `:1416`)
- Modify: `godot-generative-agents/backend/contract.py` (module docstring's `meta` block)
- Modify: `godot-generative-agents/backend/contract_models.py` (`Meta` at `:125-139`)
- Modify: `godot-generative-agents/web/src/types/replay.ts` (`ReplayMeta` at `:48-70`)
- Test: `godot-generative-agents/tests/test_replay_contract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (independent of Tasks 1-3; may be done in parallel).
- Produces: `replay["meta"]["locations"] -> list[str]`, sorted, present in both the baked file and the live handshake. Optional on the model (`list[str] | None = None`) so replays baked before this change still validate. Task 5 reads it.

`SCHEMA_VERSION` is **not** bumped: `contract.py` states *"Additive optional fields do NOT bump it"* and *"`meta` key order is deliberately NOT pinned"*.

- [ ] **Step 1: Write the failing tests**

Add to `godot-generative-agents/tests/test_replay_contract.py`:

```python
def test_meta_locations_optional_for_older_replays():
    # Additive field: a replay baked before #780 has no "locations" and must
    # still validate (no SCHEMA_VERSION bump).
    meta = Meta.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "tile_px": 16,
            "width": 245,
            "height": 279,
            "sec_per_step": 10,
            "start": "2023-02-13 08:00:00",
            "vision_r": 8,
            "personas": [],
            "relationships": [],
        }
    )
    assert meta.locations is None


def test_baked_meta_carries_sorted_locations(tmp_path):
    out = _bake_small_replay(tmp_path)
    meta = json.loads(out.read_text())["meta"]
    assert meta["locations"] == sorted(meta["locations"])
    # The six buildings, the outdoor hub, and the named interiors (#780 found
    # the world is 18 locations, not the six the issue counted).
    assert "College Hall" in meta["locations"]
    assert "Penn campus" in meta["locations"]
    assert len(meta["locations"]) >= 18


def test_live_meta_locations_match_the_bake():
    # Baked and live meta must not drift (#297).
    live = PennStepper(num_steps=2, world=build_penn_world()).meta()
    assert live["locations"] == sorted(live["locations"])
    assert Meta.model_validate(live).locations == live["locations"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_replay_contract.py -k locations -v`
Expected: FAIL — `AttributeError: 'Meta' object has no attribute 'locations'`, and `KeyError: 'locations'` from the bake test. The existing `replay.ts` mirror test may also fail once the model gains the field but the TS type has not; that is expected and fixed in Step 4.

- [ ] **Step 3: Add the field to both writers**

Both writers read the **`PennWorld.locations`** spec list, not a `Game`. This is
deliberate and the paths are already verified:

- The bake's `meta` dict has no `Game` in scope — the game is built inside
  `simulate()` and never returned there. `pw.locations` is right there.
- `PennWorld.locations` holds the parsed YAML specs, and `loc["name"]` is the
  established idiom for reading names off it (`serve_penn.py:1110` already does
  exactly this to build the planner's `known_places`).
- These names are identical to `game.locations`' keys by construction:
  `build_world.py:293-306` populates the game from the same list via
  `locations[spec["name"]] = loc`.

In `generate_penn_replay.py`, inside the `meta` dict (after `"relationships": pw.relationships,`):

```python
            # #780: the world's real place names, so the offline believability
            # audit can tell an invented place from a real one without needing
            # the world YAML. Additive + sorted: contract.py's policy is that
            # additive optional meta fields do not bump SCHEMA_VERSION, and a
            # sorted list keeps the bake byte-identical across hash seeds.
            "locations": sorted(loc["name"] for loc in pw.locations),
```

In `serve_penn.py`'s `PennStepper.meta()`, the same expression against the
stepper's world, so baked and live cannot drift (#297):

```python
            # #780: same sorted place list the bake writes, so baked and live
            # meta cannot drift. Reads PennWorld.locations, as the planner's
            # known_places already does.
            "locations": sorted(loc["name"] for loc in self.world.locations),
```

- [ ] **Step 4: Add the field to the model, the TS mirror, and the docstring**

`contract_models.py`, in `Meta`, alongside the other optionals:

```python
    locations: list[str] | None = None  # #780: world place names; absent pre-#780
```

`web/src/types/replay.ts`, in `ReplayMeta` (the file header says edit the Python side first, and `test_replay_contract.py` asserts the two stay field-for-field):

```typescript
  /** The world's real place names, sorted. Absent in replays baked before #780. */
  locations?: string[];
```

`contract.py`, in the module docstring's `meta` block, add a line next to `"relationships"`:

```
        "locations",                     # world place names, sorted (#780) --
                                         #   additive, absent pre-#780
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_replay_contract.py -q`
Expected: PASS, including the pre-existing `replay.ts` mirror test and `test_meta_defaults_cover_both_surfaces`.

- [ ] **Step 6: Confirm the bake is still byte-identical**

Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: PASS. `test_bake_is_byte_identical` runs the bake under three `PYTHONHASHSEED` values; a sorted list is stable, so this passes. If it fails, the new value is being derived from an unsorted set somewhere — sort at the writer, not at the reader.

- [ ] **Step 7: Format and commit**

```bash
uv run black .
git add godot-generative-agents/backend/penn/generate_penn_replay.py \
        godot-generative-agents/backend/penn/serve_penn.py \
        godot-generative-agents/backend/contract.py \
        godot-generative-agents/backend/contract_models.py \
        godot-generative-agents/web/src/types/replay.ts \
        godot-generative-agents/tests/test_replay_contract.py
git commit -m "feat(#780): carry the world's place list in replay meta"
```

---

### Task 5: The `world_grounding` believability dimension

**Files:**
- Modify: `godot-generative-agents/backend/eval/believability.py` (`DIMENSIONS` at `:297`, `AgentEvidence` at `:151`, `build_evidence` at `:245`, `HeuristicJudge.score_agent` at `:402`, `evidence_text` at `:783`)
- Modify: `godot-generative-agents/backend/prompt_templates/believability_rubric.prompty`
- Modify: `godot-generative-agents/backend/prompt_templates/README.md` (the rubric row's test pointer, if its wording names the four dimensions)
- Test: `godot-generative-agents/tests/test_believability_eval.py`

**Interfaces:**
- Consumes: `replay["meta"]["locations"]` from Task 4.
- Produces:
  - `DIMENSIONS` gains `"world_grounding"` — which automatically extends `BELIEVABILITY_TOOL`'s properties and `required` (`:760`), `summary.by_dimension` (`:699`), and the markdown report order.
  - `AgentEvidence.world_places: list[str]` (new field, defaulted so existing constructions keep working).
  - `_merge_growth_windows(conversations) -> list[Conversation]` (module-level helper).
  - `_PLACE_NOUNS` and `_EXPERIENCE_CUES` (module-level frozensets/tuples).
  - `HeuristicJudge._world_grounding(ev) -> DimScore`.

- [ ] **Step 1: Write the failing tests**

Add to `godot-generative-agents/tests/test_believability_eval.py`. First extend the fixture's `meta` in `make_replay()` so the world has real places (the fixture's two stops are `Cafe`, `Library`, `Gym`):

```python
            "locations": ["Cafe", "Gym", "Library"],
```

Then the new tests:

```python
# ------------------------------------------------------------ world grounding


def _convo(start, end, transcript, participants=("Ada", "Bea")):
    from backend.eval.believability import Conversation

    return Conversation(
        start=start, end=end, participants=list(participants), transcript=transcript
    )


def test_world_grounding_is_a_rubric_dimension():
    from backend.eval.believability import BELIEVABILITY_TOOL

    assert "world_grounding" in DIMENSIONS
    props = BELIEVABILITY_TOOL["parameters"]["properties"]
    assert "world_grounding" in props
    assert "world_grounding" in BELIEVABILITY_TOOL["parameters"]["required"]


def test_merge_growth_windows_collapses_an_accumulating_transcript():
    # The live producer (#371) appends one line per tick, so _conversations_in
    # keys every growth as its own window: one meeting looked like 23.
    from backend.eval.believability import _merge_growth_windows

    a = [["Ada", "Hi."]]
    b = [["Ada", "Hi."], ["Bea", "Hello."]]
    c = [["Ada", "Hi."], ["Bea", "Hello."], ["Ada", "Bye."]]
    merged = _merge_growth_windows([_convo(1, 1, a), _convo(2, 2, b), _convo(3, 3, c)])
    assert len(merged) == 1
    assert merged[0].transcript == c
    assert (merged[0].start, merged[0].end) == (1, 3)


def test_world_grounding_flags_an_invented_place_with_an_invitation():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(1, 1, [["Ada", "It's right down by the river, a ten-minute "
                             "walk through the athletic complex -- come by!"]])
    ]
    score = judge._world_grounding(ev)
    assert score.score is not None and score.score < 5
    assert any("river" in e or "complex" in e for e in score.evidence)


def test_world_grounding_allows_bare_off_map_backstory():
    # A rower may talk about her boathouse; §1 of the spec permits it. Only a
    # first-hand claim or an invitation is a defect.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(1, 1, [["Ada", "I row, so I'm always rushing in from the boathouse."]])
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_does_not_flag_real_places():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(1, 1, [["Ada", "I went to the Library and then the Gym."]])
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_catches_a_cue_with_no_place_noun_in_its_window():
    # The Casey case: "Oh yeah, I totally went!" names no place, but the window
    # names the boathouse, so the claim is attributable.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "Did you ever make it down to the boathouse?"],
                ["Ada", "Oh yeah, I totally went! The light was perfect down there."],
            ],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score is not None and score.score < 10
    assert any("Ada" in e for e in score.evidence)


def test_world_grounding_is_none_without_conversations():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = []
    assert judge._world_grounding(ev).score is None


def test_evidence_text_lists_the_worlds_places():
    evidence = build_evidence(make_replay())
    text = evidence_text(evidence["Ada"], evidence)
    assert "Places that exist in this world: Cafe, Gym, Library" in text
```

Also update the existing `test_rubric_prompt_renders_exactly` (`:432`) to include the new bullet and the changed closing line — write the expected string to match the template you produce in Step 5.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_believability_eval.py -q`
Expected: FAIL — `ImportError` for `_merge_growth_windows`, `AttributeError: '_world_grounding'`, `"world_grounding" not in DIMENSIONS`, and the rubric pin mismatching.

- [ ] **Step 3: Add the dimension, the vocabulary, and the window merge**

In `godot-generative-agents/backend/eval/believability.py`:

```python
DIMENSIONS = (
    "plan_coherence",
    "temporal_sanity",
    "social_grounding",
    "world_grounding",
    "memory_use",
)
```

Add the two word lists next to `_STOPWORDS`:

```python
# Common nouns for places a campus agent might invent (issue #780). Case is
# useless here: the real confabulations -- "boathouse", "the river", "athletic
# complex" -- were all lowercase. A hit is only a candidate: it is discarded
# when it falls inside a real location name, so "Kamin Gallery" and "Reception
# Hall" don't false-positive.
# ponytail: naive gazetteer; the LLM judge is the backstop when it misses.
_PLACE_NOUNS = frozenset(
    """annex arena bar boathouse bridge cafe center centre complex courtyard
    dorm field garden gallery gym lab market museum park pool quad rink
    restaurant shop stadium station store studio theater theatre track""".split()
)

# Phrases that turn naming a place into a checkable claim: having been there,
# or inviting someone to go. Taken from the actual #780 transcript rather than
# invented. Bare mentions are allowed -- see the spec's non-goal.
_EXPERIENCE_CUES = (
    "been there",
    "check it out",
    "come by",
    "down there",
    "i went",
    "made it down",
    "make it down",
    "meet me",
    "minute walk",
    "shots of",
    "show me",
    "swing by",
    "totally went",
    "walk if you",
    "went to",
)
```

Add the merge helper next to `_conversations_in`:

```python
def _merge_growth_windows(conversations: list[Conversation]) -> list[Conversation]:
    """Collapse one live conversation's per-tick growth into a single window.

    ``_conversations_in`` groups frames by *identical* chat payload, and warns
    in its own docstring that a producer accumulating lines per frame "would
    key each growth as a new window and overcount". The multi-tick producer
    (#371) does exactly that -- one Dana/Casey meeting registered as 23
    windows -- which both fragments window context and would score the same
    line many times over.

    Same participants and starting no later than one step after the current
    window's end means the same meeting; the longest transcript wins.

    Deliberately local to this dimension rather than a fix to
    ``_conversations_in``, which also feeds ``social_grounding``: correcting it
    there would move already-published scores. Filed separately.
    """
    merged: list[Conversation] = []
    for conv in sorted(conversations, key=lambda c: (c.start, c.end)):
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev.participants == conv.participants
            and conv.start <= prev.end + 1
        ):
            prev.end = max(prev.end, conv.end)
            if len(conv.transcript) > len(prev.transcript):
                prev.transcript = conv.transcript
            continue
        merged.append(
            Conversation(
                start=conv.start,
                end=conv.end,
                participants=list(conv.participants),
                transcript=list(conv.transcript),
            )
        )
    return merged
```

- [ ] **Step 4: Carry the place list on the evidence, and add the judge method**

Add the field to `AgentEvidence` (at the end, with a default so nothing else breaks):

```python
    world_places: list[str] = field(default_factory=list)  # meta.locations (#780)
```

In `build_evidence`, read it once before the persona loop and pass it in:

```python
    world_places = sorted(meta.get("locations") or [])
```

```python
            world_places=world_places,
```

Wire the dimension into `score_agent`, in `DIMENSIONS` order:

```python
            "world_grounding": self._world_grounding(ev),
```

Add the method after `_social_grounding`:

```python
    # -- dimension 4: world grounding -----------------------------------------

    def _world_grounding(self, ev: AgentEvidence) -> DimScore:
        """Does the agent talk about places that actually exist (issue #780)?

        Naming an off-map place is allowed -- a rower may talk about her
        boathouse. What is not allowed is claiming first-hand experience of it
        or inviting someone to meet there, so only cue-carrying lines score.

        Cues are matched **per window, not per line**: the worst line in the
        run that motivated this ("Oh yeah, I totally went! The light was
        perfect down there") names no place at all, and is only attributable
        because the partner named the boathouse earlier in the same window.
        """
        if not ev.conversations:
            return DimScore(None, note="no conversations observed for this agent")
        if not ev.world_places:
            return DimScore(
                None, note="replay carries no meta.locations (baked before #780)"
            )
        real = " | ".join(ev.world_places).lower()
        scores: list[float] = []
        evidence: list[str] = []
        for conv in _merge_growth_windows(ev.conversations):
            lines = [line for line in conv.transcript if len(line) == 2]
            # Which off-map places does this window name at all?
            invented = sorted(
                {
                    word
                    for _, text in lines
                    for word in re.findall(r"[a-z]+", text.lower())
                    if word in _PLACE_NOUNS and word not in real
                }
            )
            mine = [(sp, tx) for sp, tx in lines if sp == ev.name]
            if not mine:
                continue
            claimed = [
                (sp, tx)
                for sp, tx in mine
                if invented and any(cue in tx.lower() for cue in _EXPERIENCE_CUES)
            ]
            scores.append(1.0 - len(claimed) / len(mine))
            for sp, tx in claimed[:3]:
                evidence.append(
                    f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                    f"{sp} claims experience of {', '.join(invented)} -- not in "
                    f"this world -- in '{tx[:80]}'"
                )
            if invented and not claimed:
                evidence.append(
                    f"steps {conv.start}-{conv.end}: mentions {', '.join(invented)} "
                    f"(not in this world) without claiming to have been there -- "
                    f"allowed, not scored"
                )
        if not scores:
            return DimScore(None, note="this agent said nothing in any window")
        return DimScore(
            _scale(sum(scores) / len(scores)),
            evidence,
            f"{len(scores)} conversation window(s) checked against "
            f"{len(ev.world_places)} real place(s)",
        )
```

Confirm `re` and `field` are already imported at the top of the module (they are — `re` for `_content_words`, `field` for `DimScore`).

- [ ] **Step 5: Give the LLM judge the place list and the rubric bullet**

In `evidence_text`, right after the `Sim day starts ...` block and before the `Schedule` section:

```python
    if ev.world_places:
        lines.append(
            "Places that exist in this world: " + ", ".join(ev.world_places) + "."
        )
```

In `believability_rubric.prompty`, add a bullet between `social_grounding` and `memory_use` (keeping the file's ~66-column wrap and two-space continuation indent):

```
- world_grounding: places the agent discusses exist in this world, and it
  never claims first-hand experience of a place its timeline shows it
  never visited.
```

and change the closing line, because it names the count:

```
Call grade_believability once, with all five dimensions.
```

Check `godot-generative-agents/backend/prompt_templates/README.md`'s row for `believability_rubric`; if its description names four dimensions, update it to five.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_believability_eval.py -q`
Expected: PASS, including the re-pinned rubric render and the pre-existing scramble-control test (`overall` still degrades through the other four dimensions even though `world_grounding` is scramble-invariant — see the spec's §3.4).

- [ ] **Step 7: Run both suites**

Run: `uv run pytest tests/ -q && uv run pytest godot-generative-agents/tests/ -q`
Expected: PASS.

- [ ] **Step 8: Format and commit**

```bash
uv run black .
git add godot-generative-agents/backend/eval/believability.py \
        godot-generative-agents/backend/prompt_templates/believability_rubric.prompty \
        godot-generative-agents/backend/prompt_templates/README.md \
        godot-generative-agents/tests/test_believability_eval.py
git commit -m "feat(#780): add the world_grounding believability dimension"
```

---

### Task 6: Verify against the real run, then finish

**Files:**
- No source changes. Produces a PR comment and one new issue.

**Interfaces:**
- Consumes: everything above.
- Produces: the audit numbers that become #780's regression baseline.

- [ ] **Step 1: Audit the run that surfaced the bug**

The run store is git-ignored and per-checkout, so this run lives in the **main checkout**, not the worktree:

```bash
uv run python -m backend.eval.believability \
  /Users/alistairking/Projects/purm-2026/agent-sandbox/godot-generative-agents/runs/run-20260724-201036-e8c405
```

Expected: a markdown report whose `world_grounding` row is low for Dana Ellsworth and Casey Nguyen, with evidence citing the boathouse window near step 979 and the follow-up near step 1074.

If `world_grounding` reports `n/a` with "replay carries no meta.locations", that is correct and expected — this run was recorded *before* Task 4. Re-run with the world list injected to get real numbers:

```bash
uv run python - <<'EOF'
import json
from backend.eval.believability import audit, build_evidence, HeuristicJudge, load_replay, render_markdown
p = "/Users/alistairking/Projects/purm-2026/agent-sandbox/godot-generative-agents/runs/run-20260724-201036-e8c405"
replay = load_replay(p)
import yaml
w = yaml.safe_load(open("godot-generative-agents/backend/penn/world_data_upenn.yaml"))
replay["meta"]["locations"] = sorted(l["name"] for l in w["locations"])
print(render_markdown(audit(replay, HeuristicJudge(), source=p, scramble=None)))
EOF
```

Record the resulting `world_grounding` scores — they are the baseline the next live batch (#760) is compared against.

- [ ] **Step 2: Note the re-run limitation in the PR**

Do **not** try to A/B this run by replaying its cassette. It ships `cassette.jsonl` and is normally re-runnable offline (#715), but the grounding block changes the prompt and cassette keys hash the request, so a post-fix re-run will `CassetteMiss`. Verification is an audit over the existing frames only.

- [ ] **Step 3: File the `_conversations_in` overcount as its own issue**

This is a pre-existing defect found while doing this work, so per CLAUDE.md it gets its own issue attached as a sub-issue of #760:

```bash
gh issue create --repo ccb/agent-sandbox \
  --title "believability audit overcounts live conversations (_conversations_in keys each per-tick growth as a new window)" \
  --label generative-agents \
  --body-file <(cat <<'EOF'
`_conversations_in` groups frames by *identical* `chat` payload. Its own docstring warns that a producer which accumulates lines per frame "would key each growth as a new window and overcount -- if that contract ever changes, this grouping must change with it."

The multi-tick conversation producer (#371) does exactly that: it appends one line per tick. In `run-20260724-201036-e8c405` a single Dana/Casey meeting registers as **23 separate conversations**, and `social_grounding` reports "23 conversation(s) checked" for what was about three.

Effects: `social_grounding` means over prefix windows rather than conversations, its evidence list is duplicated, and short prefixes have artificially few substantive lines.

#780 works around this with a local `_merge_growth_windows` helper inside the new `world_grounding` dimension rather than fixing it centrally, because a central fix moves already-published `social_grounding` scores and deserves its own review.

Found while implementing #780.
EOF
)
```

Then attach it (the API takes the database id, not the issue number):

```bash
gh api --method POST /repos/ccb/agent-sandbox/issues/760/sub_issues \
  -F sub_issue_id="$(gh api /repos/ccb/agent-sandbox/issues/<n> --jq .id)"
```

- [ ] **Step 4: Post the verification results and mark the PR ready**

```bash
gh pr comment 798 --repo ccb/agent-sandbox --body-file <results file>
gh pr ready 798 --repo ccb/agent-sandbox
```

`gh pr merge` fails on a draft PR, so `gh pr ready` must come first. Do **not** merge — that is the user's call.

---

## Self-review

**Spec coverage.** §2.1 → Task 1. §2.2 → Task 2 (Steps 3-4). §2.3 (placement) → Task 2, `test_exchange_appends_grounding_below_the_first_line`. §2.4 (visited source, no sets) → Task 3 Step 3 plus Task 2's hash-seed test. §2.5 (scope, cap) → Task 2 Step 3 and `test_grounding_block_dropped_when_no_places_or_over_cap`; Task 3 Step 4 is the opt-in. §2.6 (bake unaffected) → Task 3 Step 6. §3.1 → Task 4. §3.2 → Task 5 Steps 3-5. §3.3 (cue scoring, window-scoped) → Task 5, `test_world_grounding_allows_bare_off_map_backstory` and `test_world_grounding_catches_a_cue_with_no_place_noun_in_its_window`. §3.3a (growth windows) → Task 5, `test_merge_growth_windows_collapses_an_accumulating_transcript`. §3.4 (scramble invariance) → documented in the docstring; Task 5 Step 6 confirms the existing control test still passes. §4 files → all covered. §5 tests → all present. §6 verification → Task 6.

**Type consistency.** `places`/`visited` are `Sequence[str] | None` everywhere and sorted only inside `_place_grounding_block`. `MAX_GROUNDED_PLACES` is used in Task 2's helper and its test. `state[nm]["visited"]` is written in Task 3 Step 3 and read in Step 4 via `.get("visited", ())`. `meta["locations"]` is written in Task 4 and read in Task 5 via `meta.get("locations")` → `AgentEvidence.world_places`. `_merge_growth_windows` returns `list[Conversation]`, the same dataclass `_conversations_in` produces.

**One known gap, deliberate.** The heuristic's `invented` set only detects off-map places whose head noun is in `_PLACE_NOUNS`; a proper-noun invention ("the Ferguson Annex" is caught via "annex", but "Ferguson Hall" is not, since "hall" is not in the gazetteer — it appears in real names). The LLM judge covers that case, and the spec's §7 records the ceiling.
