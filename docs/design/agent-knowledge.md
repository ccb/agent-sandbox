# Agent Knowledge Design

**Status:** Implemented (issue #45).

*A design for giving each character a private model of what it believes about the
world — possibly incomplete or wrong — that shapes what its agent perceives and
reasons about, without ever bypassing the engine's action precondition gate.*

---

## 1. Why knowledge

Before this feature, an NPC perceived the world fresh every turn through
`Game.describe_for(character)`, which exposed the **omniscient** contents of the
current location: every exit, every item, every other character, plus the agent's
inventory and the available actions. The character had no model of *what it knows*
— no priors, no secrets, and no asymmetry between who-knows-what.

That flattens the simulation. A guard who "knows the tower is locked and holds the
only key" should reason differently from a hungry troll who knows only its bargain
at the bridge. A ghost who knows the runes that can banish it holds a secret no one
else does. You cannot plan to use a key you do not know exists.

Knowledge adds a per-character **belief layer**: facts a character holds about the
world that may be **incomplete** (the troll never learned a key exists) or even
**wrong** (a belief whose text contradicts the world graph). Some beliefs are known
up front; some are learned during play; some are never known. The layer gates what
an agent can plausibly reason about, and it is the substrate for a future dialogue
feature where characters share or withhold what they know.

---

## 2. Design goals

- **Per-character beliefs.** Every `Character` owns a `Knowledge` object. One
  character's beliefs must not leak into another character's observation prompt or
  into the shared command history.
- **Incomplete and fallible by design.** A belief is plain text; it can be partial
  or false. The "uncertain or wrong" axis lives in the wording, not in a numeric
  confidence field.
- **No action shortcuts.** Knowledge changes what command an agent *chooses*, but
  every command still runs through `Parser.parse_command()` and the normal
  `check_preconditions()` -> `apply_effects()` gate.
- **Backward compatible.** Empty knowledge produces a byte-identical observation,
  so existing games, the webapp, and the live-game test suite are unaffected unless
  a character is explicitly seeded.
- **Offline and readable.** `knowledge.py` is pure data with no engine imports, so
  it is trivially unit-testable and easy for a first-year undergraduate to read.

Non-goals for this pass:

- **No confidence scoring.** Beliefs are not weighted; certainty is expressed in
  the text.
- **No automatic perception -> belief learning.** Turning what an agent *saw* into
  a stored record is memory's job (#37), not knowledge's.
- **No exit gating.** Hidden items and characters are gated, but exits stay visible
  (see §5).
- **No LLM-driven belief revision.** Beliefs change only through explicit `add` /
  `learn` calls, never by a model silently rewriting the world-model.

---

## 3. Current repo fit

The repo already had the seams this needs:

- `Game.describe_for(character)` builds a character-specific observation. It is the
  single interception point: beliefs are appended as a section and hidden things
  are filtered there.
- `build_npc_context()` (`npc.py`) wraps `describe_for` plus recent command
  history, and is used by **both** turn modes — sequential `react_behavior()` and
  simultaneous `turns.py gather_intents()` — so knowledge flows into both for free.
- `Character` already serializes structured side-state (`goals`) through
  `to_primitive()` / `from_primitive()`. Knowledge mirrors that pattern exactly.
- `Thing.properties` is a `defaultdict(bool)`, so a `secret_topic` flag defaults to
  falsy and only matters when explicitly set — the basis for perception gating.

Important distinction, echoing memory's:

- **World graph:** the omniscient ground truth (locations, items, characters).
- **Knowledge:** a single character's private *model* of that truth, which may
  disagree with it.

---

## 4. Data model

A new module, `text_adventure_games/knowledge.py`, pure data with no engine
imports:

```python
@dataclass
class Belief:
    text: str                         # the belief in plain language
    topic: str | None = None          # lookup key; also unlocks a matching secret_topic
    learned_turn: int | None = None   # None = known up front; else learned during play


class Knowledge:
    def __init__(self, owner: str = ""):
        self.owner = owner
        self.beliefs: list[Belief] = []

    def add(self, text, topic=None, learned_turn=None) -> Belief: ...  # a prior
    def learn(self, text, turn, topic=None) -> Belief: ...             # stamps the turn
    def knows_about(self, topic) -> bool: ...   # any belief carrying that topic
    def believes(self, substr) -> bool: ...     # case-insensitive text scan
    def render(self) -> str: ...                # "" when empty; else a "What you know:" block
    def to_primitive(self) -> dict: ...
    @classmethod
    def from_primitive(cls, data) -> "Knowledge": ...
```

Design choices that matter:

- **`Belief` has exactly three fields.** Like `Goal`, it resists premature
  structure. There is deliberately no `confidence` or `source`; nothing reads them,
  and the wrong/uncertain axis already lives in the text.
- **One flat list is the single source of truth.** There is no parallel
  `known_secrets` set. The belief that unlocks a secret is itself a renderable
  belief, so it shows up in the observation like any other.
- **`render()` returns `""` for empty knowledge.** This empty-render guard is
  load-bearing: an un-seeded character's observation is identical to before this
  feature existed.

`Character` gains, in `__init__`:

```python
self.knowledge = Knowledge(owner=name)
```

plus an ergonomic helper mirroring `add_goal`:

```python
def add_belief(self, text, topic=None, learned_turn=None) -> Belief:
    return self.knowledge.add(text, topic=topic, learned_turn=learned_turn)
```

---

## 5. Perception gating

Knowledge does more than add a section: it can gate what a character *perceives*.

Flag any `Thing` as hidden:

```python
candle.set_property("secret_topic", "runes")
```

In `describe_for`, the items and characters loops are filtered through one helper:

```python
def _visible_to(thing) -> bool:
    secret = thing.get_property("secret_topic")
    return not secret or character.knowledge.knows_about(secret)
```

So a flagged thing is revealed only to a character for whom
`knowledge.knows_about("runes")` is true; an unflagged thing is always visible.
Because `get_property` defaults to `False`, nothing is hidden in any existing game
unless a `Thing` is explicitly flagged.

**Exits are intentionally not gated.** Exits drive the block / precondition system;
hiding an exit from the observation while the engine still enforces movement through
it would split "what the agent sees" from "what the engine allows." Hidden passages
are better modeled as a block whose condition is a belief, which keeps the world
graph authoritative.

---

## 6. Updating knowledge

Two write paths, both explicit:

- **Priors** seeded before or during world setup, with no turn stamp:

  ```python
  guard.add_belief("The tower door is locked and I hold the only brass key.", topic="door")
  ```

- **Learned beliefs** acquired during play, stamped with the current turn so they
  can be distinguished from priors:

  ```python
  troll.knowledge.learn("The guard never brought the promised food.", turn=game.turn)
  ```

There is deliberately no automatic "I saw X, therefore I now believe X" pipeline.
That inference — converting perception into a stored record — is memory's
responsibility (#37). Keeping knowledge's write path explicit is what keeps the two
layers from overlapping.

---

## 7. Composition with memory (#37)

Knowledge and memory are two different things and must **compose, not overlap**.
Memory (`docs/design/agent-memory.md`) is still a design-only proposal; knowledge
ships **without** depending on `memory.py` existing.

| Layer | What it is | How it's filled | Observation section |
|-------|-----------|-----------------|---------------------|
| **Knowledge** (#45, this doc) | the current *world-model* — "what's true now", possibly wrong | seeded up front or via explicit `learn()` | `What you know:` |
| **Memory** (#37, proposed) | the *episodic log* of what was observed / done | auto-captured from `Game.events`, surfaced by retrieval | `Relevant memories:` |

Both feed `describe_for` (directly today, via retrieval later) in **separate**
sections, so an agent can hold a durable record of *what happened* (memory) and a
revisable model of *what is true* (knowledge) at the same time. A clean future
seam: a salient memory could *inform* a `learn()` call, but memory never writes a
belief on its own.

---

## 8. Demo

`notebooks/knowledge_demo.ipynb` is fully offline and deterministic (no API key).
It reuses the real Action Castle cast via `build_game()` and seeds beliefs **in the
notebook**, leaving the canonical game pristine. It demonstrates:

1. **Asymmetric beliefs** — the guard knows about the brass key and the dungeon
   secret; the troll knows only its bargain (incomplete); the ghost knows the runes
   that banish it (a secret it alone holds); the princess holds a single grieving
   belief.
2. **Divergent observations** — `describe_for(guard)` and `describe_for(troll)`
   carry different `What you know:` sections.
3. **Same rule, different action** — one `ScriptedAgent` rule ("use the key if I
   know of it") yields `unlock door` for the guard and `look` for the troll.
4. **Perception gating** — a candle flagged `secret_topic="runes"` appears in the
   ghost's observation but not the troll's, in the same room.

---

## 9. Save/load

Knowledge serializes through the existing character save path, mirroring `goals`:

- `Character.to_primitive()` adds `thing_data["knowledge"] = self.knowledge.to_primitive()`.
- `Character.from_primitive()` rebuilds it with a `.get` default so save files
  written before this feature still load:

  ```python
  instance.knowledge = Knowledge.from_primitive(
      data.get("knowledge", {"owner": data["name"], "beliefs": []})
  )
  ```

`Knowledge.to_primitive()` emits `{"owner": ..., "beliefs": [{"text", "topic",
"learned_turn"}, ...]}`. Runtime-only fields (the agent, its LLM client) remain
unserialized, exactly as before.

---

## 10. Testing

`tests/test_knowledge.py` covers:

- **Data model:** `Belief` defaults; `add` appends and returns; `learn` stamps the
  turn; `knows_about` / `believes` behavior (including that an empty topic never
  matches).
- **`render()`:** empty knowledge renders `""`; a non-empty render starts with
  `What you know:`, has one bullet per belief, and contains **none** of the
  mock-brain trigger substrings (a real risk because a rendered belief becomes part
  of an NPC's observation).
- **Serialization:** `Knowledge` and `Character` round-trip, including topics and
  learned-turn stamps; a character with no `knowledge` key still loads.
- **Integration / isolation:** a seeded belief appears in that character's
  `describe_for` but not in another character's, and not in
  `parser.command_history` after `build_npc_context`.
- **Perception gating + backward compat:** a `secret_topic` item/character is
  hidden until the viewer's knowledge unlocks the topic; unflagged things are
  always visible; empty knowledge adds no section.

The wider regression surface (`test_react_live_game.py`, `test_time_model.py`,
`test_npc_behaviors.py`) confirms that an unseeded `build_game()` produces an
unchanged observation.

---

## 11. Build order

| Stage | Deliverable |
|-------|-------------|
| 1 | `knowledge.py` with `Belief`, `Knowledge`, deterministic `render`, and serialization. |
| 2 | `Character` integration: `self.knowledge`, `add_belief`, save/load. |
| 3 | `describe_for` injects the beliefs section and gates hidden things. |
| 4 | `tests/test_knowledge.py`: data model, isolation, gating, backward compat. |
| 5 | `notebooks/knowledge_demo.ipynb`: offline asymmetric-knowledge demo. |
| 6 | This design doc, with the knowledge <-> memory composition section. |

Each stage keeps existing no-knowledge games working.

---

## 12. Open questions

- When memory (#37) lands, what is the right seam for a salient memory to *suggest*
  a `learn()` call without memory writing beliefs directly?
- Should beliefs ever be contradicted/retracted (a `forget` or supersede), or is
  append-only plus fallible text enough?
- Should perception gating grow a richer predicate than a single `secret_topic`
  string (e.g. multiple topics, or a callable condition)?
- Should a future dialogue action let one character *transfer* a belief to another,
  and if so, does the recipient mark it `learned_turn` or copy the prior?

---

## 13. Design invariants

- Beliefs are context, not authority. The world graph remains the source of truth;
  a belief may be false, but only actions through the precondition gate mutate the
  world.
- Knowledge is per-character and private. One character's beliefs never appear in
  another's observation or in the shared command history.
- Empty knowledge is invisible. An un-seeded character's observation is identical
  to one produced before this feature existed.
- Knowledge is explicit. Beliefs change only through `add` / `learn`, never by an
  LLM or by automatic perception capture.
- The implementation must be obvious enough that a first- or second-year
  undergraduate can read, test, and extend it.
