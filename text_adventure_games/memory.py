"""
Per-agent episodic memory (issues #37 / #75).

An :class:`AgentMemory` is an append-only stream of :class:`MemoryRecord`s -- a
private, timestamped log of what one agent *observed*, *reflected* on, or
*planned*. It is the foundation the Generative Agents paper (Park et al., 2023)
builds perception, reflection, and planning on top of.

This is deliberately distinct from knowledge (#45, ``knowledge.py``):

* **Memory** is the episodic *log* -- "on turn 3 the player gave me a fish".
* **Knowledge** is the current *world-model* -- "what's true now".

Memory is context, not authority. A retrieved memory may steer which command an
agent chooses, but the world graph stays the single source of truth and every
command still passes the parser's precondition gate. Memory is also *private*:
one agent's records never leak into another agent's prompt, into
``parser.command_history``, or into ``Game.events``.

Following the same restraint as ``knowledge.py``, this module is pure data with
no engine imports, so it stays easy to unit-test offline and easy for a
first-year student to read. The two engine-shaped methods (:meth:`AgentMemory.
ingest_events`) only *read* from a game/character via duck typing; they never
import or mutate the engine.

Scoring is deterministic by default (recency decay + importance + keyword
relevance), so the whole memory loop works with no network access and with the
mock LLM client. Relevance can optionally upgrade from keyword overlap to
*semantic* similarity by handing :class:`AgentMemory` an ``embedding_client``
(see ``embedding_client.py``); when none is given, retrieval is byte-identical to
before. LLM-backed importance can be layered on the same way; see
``docs/design/agent-memory.md`` (§6) and ``memory-retrieval-embeddings.md``.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from enum import Enum

# --- Retrieval tuning (docs/design/agent-memory.md §6) -----------------------
# Weights for the three retrieval ingredients. Equal by default, like the paper.
ALPHA_RECENCY = 1.0
ALPHA_IMPORTANCE = 1.0
ALPHA_RELEVANCE = 1.0
# Recency decays per turn of non-access. Text-adventure turns are shorter and
# noisier than the paper's sandbox hours, so memories fade a little faster.
DEFAULT_DECAY = 0.95
# How many memories a retrieval may surface, and the rough token ceiling for the
# rendered block (a memory should never crowd out the live observation).
DEFAULT_MAX_RECORDS = 6
DEFAULT_TOKEN_BUDGET = 800

# --- Perception tuning (issue #80) -------------------------------------------
# A "presence" memory ("I see X nearby") is mundane background -- it should
# rarely outweigh an action outcome in retrieval, so it gets the lowest
# importance. PRESENCE_CAP bounds how many presence records one perceive() call
# may add, so a crowded plaza can't flood the stream in a single turn.
PRESENCE_IMPORTANCE = 1.0
PRESENCE_CAP = 12

# A tiny stop-word list so keyword-overlap relevance keys on content words, not
# glue words. Intentionally small and readable rather than exhaustive.
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "here",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "she",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "was",
        "were",
        "with",
        "you",
        "your",
    }
)

# Split on any run of non-alphanumeric characters.
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class MemoryKind(str, Enum):
    """What a memory record represents.

    A ``str`` Enum so members serialize straight to JSON (``kind.value``) and
    read nicely in tests and debug output, mirroring ``GoalType`` in
    ``things/characters.py``.
    """

    OBSERVATION = "observation"  # something the agent perceived or did
    REFLECTION = "reflection"  # a higher-level inference drawn from memories
    PLAN = "plan"  # an intention the agent formed
    CHAT = "chat"  # something said in a conversation (issue #86)


@dataclass
class MemoryRecord:
    """A single timestamped entry in an agent's memory stream.

    Fields follow ``docs/design/agent-memory.md`` §4. The required few carry the
    record (``kind`` / ``text`` / ``created_turn`` / ``importance``); the rest
    are optional provenance the later Phase-B stages fill in (evidence event
    ids, tags, an embedding for semantic relevance, free-form metadata).

    ``importance`` is on the paper's 1-10 "poignancy" scale (1 = mundane, 10 =
    momentous). ``last_accessed_turn`` powers recency decay -- it starts equal to
    ``created_turn`` and is bumped each time the record is retrieved.
    """

    id: int
    kind: MemoryKind
    text: str
    created_turn: int
    last_accessed_turn: int
    importance: float = 1.0
    actor: str | None = None
    source_event_ids: list[int] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)

    def to_primitive(self) -> dict:
        """Serialize to JSON-safe primitives (``tags`` sorted for determinism)."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "text": self.text,
            "created_turn": self.created_turn,
            "last_accessed_turn": self.last_accessed_turn,
            "importance": self.importance,
            "actor": self.actor,
            "source_event_ids": list(self.source_event_ids),
            "tags": sorted(self.tags),
            "embedding": self.embedding,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "MemoryRecord":
        """Reconstruct a record from :meth:`to_primitive` output.

        Tolerant of missing optional keys so older/leaner save files still load
        (mirrors ``Knowledge.from_primitive``)."""
        return cls(
            id=data["id"],
            kind=MemoryKind(data["kind"]),
            text=data["text"],
            created_turn=data["created_turn"],
            last_accessed_turn=data.get("last_accessed_turn", data["created_turn"]),
            importance=data.get("importance", 1.0),
            actor=data.get("actor"),
            source_event_ids=list(data.get("source_event_ids", [])),
            tags=set(data.get("tags", [])),
            embedding=data.get("embedding"),
            metadata=dict(data.get("metadata", {})),
        )


# --- Deterministic scoring helpers (docs/design/agent-memory.md §6) ----------


def _tokenize(text: str) -> set[str]:
    """Lower-case content words of *text* with stop-words and empties dropped."""
    return {
        tok for tok in _TOKEN_RE.split(text.lower()) if tok and tok not in _STOP_WORDS
    }


def recency_score(
    record: MemoryRecord, turn: int, decay: float = DEFAULT_DECAY
) -> float:
    """Exponential decay over turns since the record was last accessed (0-1)."""
    return decay ** max(0, turn - record.last_accessed_turn)


def importance_score(record: MemoryRecord) -> float:
    """Normalize the 1-10 importance onto 0-1, clamping out-of-range values."""
    return max(0.0, min(record.importance, 10.0)) / 10.0


def relevance_score(query: str, text: str) -> float:
    """Keyword overlap between *query* and *text* as a 0-1 fraction.

    The share of the query's content words that also appear in the memory. A
    query with no content words (only stop-words) scores 0 -- there is nothing
    to be relevant *to*. A deterministic stand-in for the paper's embedding
    similarity that needs no model and no network."""
    q = _tokenize(query)
    if not q:
        return 0.0
    return len(q & _tokenize(text)) / len(q)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors, in ``[-1, 1]``.

    Returns 0.0 when either vector is all zeros (no direction to compare),
    mirroring how keyword relevance scores 0 when there's nothing to match.
    Hand-rolled in pure Python so this module keeps its no-dependency footprint
    (a handful of short memory vectors per retrieval -- numpy would be overkill)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class AgentMemory:
    """One agent's private, append-only memory stream.

    Records are only ever appended (never edited or deleted), which keeps memory
    an honest log of what happened. The ``owner`` name scopes the stream to a
    single character so retrieval can never surface another agent's thoughts; it
    is filled in lazily by the ReAct loop the first time the agent acts.

    Pass an ``embedding_client`` (see ``embedding_client.py``) to score relevance
    by semantic similarity instead of keyword overlap. It's optional and off by
    default: with no client, retrieval uses keyword relevance and behaves exactly
    as before (issue #76).
    """

    def __init__(self, owner: str = "", embedding_client=None):
        self.owner = owner
        self.records: list[MemoryRecord] = []
        # Optional semantic-relevance backend (issue #76). None -> keyword
        # overlap, the deterministic, dependency-free default.
        self.embedding_client = embedding_client
        # How far into Game.events we've already perceived (issue #75 stage 3).
        self.last_seen_event_index = 0
        # Which agents/objects were in view last turn (issue #80), keyed
        # "char:<name>@<room>" / "item:<name>@<room>". We log a presence memory
        # only when something *new* enters view, so standing next to the same
        # neighbor every turn doesn't re-log it. Cleared keys drop out when a
        # thing leaves view, so re-entering a room re-notices it.
        self._perceived: set[str] = set()
        # Importance accrued since the last reflection; reflection (a later
        # stage) fires when this crosses a threshold, then resets it.
        self.importance_since_reflection = 0.0
        self._next_id = 0

    # --- writers (append-only) ----------------------------------------------

    def _add(
        self,
        kind: MemoryKind,
        text: str,
        turn: int,
        importance: float,
        actor: str | None,
        source_event_ids,
        tags,
    ) -> MemoryRecord:
        """Append one record, assigning it the next id. The single mutation
        point: every public writer funnels through here."""
        record = MemoryRecord(
            id=self._next_id,
            kind=kind,
            text=text,
            created_turn=turn,
            last_accessed_turn=turn,
            importance=importance,
            actor=actor,
            source_event_ids=list(source_event_ids) if source_event_ids else [],
            tags=set(tags) if tags else set(),
        )
        self._next_id += 1
        self.records.append(record)
        self.importance_since_reflection += importance
        return record

    def add_observation(
        self,
        text: str,
        turn: int,
        importance: float = 1.0,
        actor: str | None = None,
        source_event_ids=None,
        tags=None,
    ) -> MemoryRecord:
        """Record something the agent perceived or did."""
        return self._add(
            MemoryKind.OBSERVATION,
            text,
            turn,
            importance,
            actor,
            source_event_ids,
            tags,
        )

    def add_reflection(
        self,
        text: str,
        turn: int,
        evidence_ids=None,
        importance: float = 5.0,
        tags=None,
    ) -> MemoryRecord:
        """Record a higher-level inference, citing the memories it rests on."""
        return self._add(
            MemoryKind.REFLECTION, text, turn, importance, None, evidence_ids, tags
        )

    def add_plan(
        self, text: str, turn: int, importance: float = 5.0, tags=None
    ) -> MemoryRecord:
        """Record an intention the agent formed."""
        return self._add(MemoryKind.PLAN, text, turn, importance, None, None, tags)

    def add_chat(
        self,
        text: str,
        turn: int,
        partner: str | None = None,
        importance: float = 4.0,
        tags=None,
    ) -> MemoryRecord:
        """Record a line said in a conversation (issue #86).

        Written into *both* conversants' streams by ``conversation.converse`` --
        the speaker remembers what it said, the listener what it heard -- so a
        meeting durably shapes both agents' memories (the channel relationships
        and information actually propagate through). ``partner`` is the other
        party (stored as ``actor``); dialogue is moderately memorable, so the
        default importance sits a little above a mundane observation.
        """
        return self._add(MemoryKind.CHAT, text, turn, importance, partner, None, tags)

    # --- perception: fold the visible world into memory ---------------------

    def perceive(self, game, character) -> list[MemoryRecord]:
        """Perceive the nearby world this turn and store it (issue #80).

        The single perception entry point, shared by every turn mode (the
        sequential ReAct loop, the simultaneous gather phase, and the Smallville
        port). It folds two things into memory, both scoped to what *character*
        can see -- the locations returned by ``game.perceivable_locations``:

        1. **Events** -- new entries in ``game.events`` whose actor is in view or
           whose payload names this agent (see :meth:`_ingest_events`).
        2. **Presence** -- the other agents and objects standing in view, but
           only those *newly* in view since last turn, so a stable neighbor
           isn't re-logged every turn (see :meth:`_perceive_presence`).

        Presence is a vision-radius feature: with ``vision_r == 0`` (the default)
        a character sees only its own room and we record **no** presence, so the
        memory stream is byte-identical to before #80. Widen ``vision_r`` and the
        agent starts noticing who and what is around it.

        Reads the game/character by duck typing only (plus the optional
        ``game.perceivable_locations`` seam) -- no engine import, no mutation.
        """
        locations = self._perceivable_locations(game, character)
        added = self._ingest_events(game, character, locations)
        if getattr(character, "vision_r", 0) > 0:
            added.extend(self._perceive_presence(character, locations, game))
        return added

    @staticmethod
    def _perceivable_locations(game, character) -> list:
        """The rooms *character* can see into, via the engine's visibility seam.

        Falls back to just the current room when the game predates the seam, so
        this module keeps working against any duck-typed game object."""
        if hasattr(game, "perceivable_locations"):
            return game.perceivable_locations(character)
        return [character.location]

    def ingest_events(self, game, character) -> list[MemoryRecord]:
        """Perceive new ``game.events`` in the *current room* and store them.

        The radius-0 case of :meth:`perceive`, kept as a named method for the
        callers and tests that only want event perception. Equivalent to
        ``perceive`` for a character with ``vision_r == 0`` and no presence.
        """
        return self._ingest_events(game, character, [character.location])

    def _ingest_events(self, game, character, locations) -> list[MemoryRecord]:
        """Walk new ``game.events`` and store the ones this character perceives.

        Walks the log from :attr:`last_seen_event_index` forward; for each event
        :meth:`_perceive_event` returns either a ``(sentence, importance)`` pair
        or ``None`` (not perceived). The index then advances past everything
        examined, so a second call with no new events is a no-op. The single
        index advance lives here, so no caller can double-count.
        """
        new_events = game.events[self.last_seen_event_index :]
        added: list[MemoryRecord] = []
        for offset, event in enumerate(new_events):
            index = self.last_seen_event_index + offset
            perceived = self._perceive_event(event, game, character, locations)
            if perceived is None:
                continue
            text, importance = perceived
            added.append(
                self.add_observation(
                    text,
                    turn=getattr(game, "turn", 0),
                    importance=importance,
                    actor=event.actor if isinstance(event.actor, str) else None,
                    source_event_ids=[index],
                )
            )
        self.last_seen_event_index = len(game.events)
        return added

    def _perceive_event(self, event, game, character, sight_rooms):
        """How *character* perceives *event*: a ``(sentence, importance)`` pair,
        or ``None`` if it's neither seen nor heard (docs/design/agent-memory.md).

        Visibility is keyed on *where the action happened* (its origin), not where
        the actor is now -- so a departure (a GO whose origin you can see) and an
        actor who acts in your room then moves on are both witnessed; an arrival
        (its destination in view) still counts too. Failing sight, a *loud* event
        (``heard_radius`` hops away) is heard, muffled and directional. The
        agent's own actions are skipped -- the ReAct loop records them as richer
        outcomes. Legacy events with no origin fall back to the actor's room.
        """
        actor = event.actor
        if actor == self.owner:  # own action -> recorded as an outcome instead
            return None
        payload = event.payload or {}
        if self.owner and self.owner in (str(v) for v in payload.values()):
            return (self._event_to_sentence(event), 1.0)

        sight_names = {getattr(loc, "name", loc) for loc in sight_rooms}
        origin = payload.get("location")
        dest = payload.get("dest")

        # SEEN: the action happened in -- or moved into -- a room in view.
        seen = False
        if origin is not None:
            seen = origin in sight_names or (dest is not None and dest in sight_names)
        if not seen and origin is None and isinstance(actor, str):
            # Legacy event (no logged origin): fall back to the actor's room.
            other = game.characters.get(actor)
            seen = other is not None and getattr(other, "location", None) in sight_rooms
        if seen:
            return (self._render_seen(event, character, origin, dest), 1.0)

        # HEARD: a loud event from beyond sight -- muffled, directional, fainter.
        radius = int(payload.get("heard_radius") or 0)
        if radius > 0 and origin is not None and hasattr(game, "audible_rooms"):
            here = getattr(getattr(character, "location", None), "name", None)
            heard = game.audible_rooms(origin, radius)
            if here in heard:
                return (self._render_heard(event, heard[here]), 0.5)
        return None

    def _render_seen(self, event, character, origin, dest) -> str:
        """A sentence for a fully-witnessed event. Movement (origin != dest) reads
        as a departure or an arrival from the viewer's vantage; anything else
        falls to :meth:`_event_to_sentence`."""
        if origin is not None and dest is not None and dest != origin:
            here = getattr(getattr(character, "location", None), "name", None)
            direction = (event.payload or {}).get("dir")
            if here == origin:
                whither = f" to the {direction}" if direction else f" toward {dest}"
                return f"{event.actor} left{whither}".strip()
            if here == dest:
                return f"{event.actor} arrived from {origin}".strip()
        return self._event_to_sentence(event)

    @staticmethod
    def _render_heard(event, direction) -> str:
        """A muffled, directional line for a sound from out of sight."""
        where = f"the {direction}" if direction else "somewhere nearby"
        sound = (event.payload or {}).get("sound") or "a commotion"
        return f"From {where}: {sound}".strip()

    def _perceive_presence(self, character, locations, game) -> list[MemoryRecord]:
        """Notice the agents and objects standing in view, storing the new ones.

        Builds the set of things currently in view (keyed by kind, name, and
        room, so the same name in two rooms is two distinct sightings), then
        stores a low-importance observation for each key not seen last turn.
        ``self._perceived`` is then replaced with the current set, so a thing
        that leaves view drops out and is re-noticed if it returns. Capped at
        :data:`PRESENCE_CAP` records per call so a crowd can't flood the stream.
        """
        turn = getattr(game, "turn", 0)
        current: dict[str, str] = {}  # key -> sentence
        for loc in locations:
            room = getattr(loc, "name", "")
            for name in getattr(loc, "characters", {}):
                if name == self.owner:
                    continue  # the agent doesn't "see itself" nearby
                current[f"char:{name}@{room}"] = f"I see {name} nearby."
            for name in getattr(loc, "items", {}):
                current[f"item:{name}@{room}"] = f"I see {name} nearby."

        fresh = [key for key in current if key not in self._perceived]
        added: list[MemoryRecord] = []
        for key in fresh[:PRESENCE_CAP]:
            added.append(
                self.add_observation(
                    current[key],
                    turn=turn,
                    importance=PRESENCE_IMPORTANCE,
                    tags={"presence"},
                )
            )
        if len(fresh) > PRESENCE_CAP:
            added.append(
                self.add_observation(
                    "There are several others nearby.",
                    turn=turn,
                    importance=PRESENCE_IMPORTANCE,
                    tags={"presence"},
                )
            )
        # Replace (don't union): things no longer in view drop out, so leaving
        # and re-entering a room re-notices it, and the set stays bounded.
        self._perceived = set(current)
        return added

    @staticmethod
    def _event_to_sentence(event) -> str:
        """One short sentence for an event, built from its structured fields.

        Phrased from ``event.summary`` (the command text, e.g. "give fish to
        troll") rather than any narration string -- private memory must never
        echo the third-person prose the mock brain keys on, or a remembered
        line could spoof another agent's decision.
        """
        # A non-string actor marks an engine event (today only fired triggers).
        if not isinstance(event.actor, str):
            return f"Something happened: {event.summary or event.action}".strip()
        detail = event.summary or event.action
        return f"{event.actor} did: {detail}".strip()

    # --- retrieval ----------------------------------------------------------

    def retrieve(
        self,
        query: str,
        turn: int,
        max_records: int = DEFAULT_MAX_RECORDS,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        decay: float = DEFAULT_DECAY,
        alpha_recency: float = ALPHA_RECENCY,
        alpha_importance: float = ALPHA_IMPORTANCE,
        alpha_relevance: float = ALPHA_RELEVANCE,
        touch: bool = True,
    ) -> list[MemoryRecord]:
        """Return the most useful memories for *query* at *turn*.

        Scores every record by the paper's three ingredients (recency,
        importance, relevance), takes the top ``max_records``, then trims to
        ``token_budget`` so the rendered block can't crowd out the live
        observation. Retrieved records have their ``last_accessed_turn`` bumped
        to *turn* (so attending to a memory keeps it fresh). Ties break by newer
        id, giving a stable, deterministic order.

        Relevance is keyword overlap by default; with an ``embedding_client`` it
        is semantic similarity instead (see :meth:`_relevance_by_id`). All three
        ingredients stay on a 0-1 scale, so the weights combine the same way
        either path. ``alpha_recency`` / ``alpha_importance`` /
        ``alpha_relevance`` weight the three ingredients; they default to the
        module's ``ALPHA_*`` constants (equal weights, like the paper), so
        omitting them reproduces the historical scoring exactly. A simulation can
        override them to, say, favor relevance over recency (see
        ``generative-agents`` ``RetrievalConfig``).

        Set ``touch=False`` for a *read-only* retrieval that does not bump
        ``last_accessed_turn`` -- for inspecting or comparing what would surface
        without disturbing recency (e.g. scoring the same stream under two
        relevance modes). The default ``touch=True`` is the decision-time path.
        """
        relevance = self._relevance_by_id(query)
        scored = []
        for record in self.records:
            score = (
                alpha_recency * recency_score(record, turn, decay)
                + alpha_importance * importance_score(record)
                + alpha_relevance * relevance[record.id]
            )
            scored.append((score, record))
        scored.sort(key=lambda pair: (pair[0], pair[1].id), reverse=True)

        chosen: list[MemoryRecord] = []
        spent = 0
        for _, record in scored[:max_records]:
            cost = self._estimate_tokens(record)
            if chosen and spent + cost > token_budget:
                break
            chosen.append(record)
            spent += cost
        if touch:
            for record in chosen:
                record.last_accessed_turn = turn
        return chosen

    def _relevance_by_id(self, query: str) -> dict[int, float]:
        """Relevance of every record to *query*, keyed by record id (0-1).

        Keyword overlap by default. With an ``embedding_client`` set, scores by
        cosine similarity instead: the query is embedded once and each record's
        embedding is computed lazily and cached on the record (so repeated
        retrievals don't re-embed), then cosine in [-1, 1] is rescaled to [0, 1]
        to share the keyword path's scale.
        """
        if self.embedding_client is None:
            return {r.id: relevance_score(query, r.text) for r in self.records}

        # Embed any records we haven't embedded yet, in one batched call.
        missing = [r for r in self.records if r.embedding is None]
        if missing:
            for record, vector in zip(
                missing, self.embedding_client.embed([r.text for r in missing])
            ):
                record.embedding = vector
        (query_vector,) = self.embedding_client.embed([query])
        return {
            r.id: (1.0 + cosine_similarity(query_vector, r.embedding)) / 2.0
            for r in self.records
        }

    @staticmethod
    def _estimate_tokens(record: MemoryRecord) -> int:
        """Cheap, offline token estimate for one rendered bullet (~4 chars/token)."""
        return max(1, len(_format_bullet(record)) // 4)

    # --- rendering ----------------------------------------------------------

    def render(self, records=None) -> str:
        """Render memories as an observation block, or ``""`` when there are none.

        The empty-render guard is load-bearing (as in ``Knowledge.render``): an
        agent with nothing to recall gets a byte-identical observation to before
        memory existed, so existing games are unaffected. Pass the retrieved
        subset; ``None`` renders the whole stream (handy for debugging/tests).
        """
        return render_memories(self.records if records is None else records)

    # --- save/load ----------------------------------------------------------

    def to_primitive(self) -> dict:
        """Serialize the whole stream to JSON-safe primitives."""
        return {
            "owner": self.owner,
            "last_seen_event_index": self.last_seen_event_index,
            "perceived": sorted(self._perceived),
            "importance_since_reflection": self.importance_since_reflection,
            "next_id": self._next_id,
            "records": [r.to_primitive() for r in self.records],
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "AgentMemory":
        """Reconstruct an AgentMemory from :meth:`to_primitive` output."""
        instance = cls(owner=data.get("owner", ""))
        instance.records = [
            MemoryRecord.from_primitive(r) for r in data.get("records", [])
        ]
        instance.last_seen_event_index = data.get("last_seen_event_index", 0)
        # .get default keeps pre-#80 save files loadable (no presence state ->
        # an empty set means the first perceive after load re-notices the room).
        instance._perceived = set(data.get("perceived", []))
        instance.importance_since_reflection = data.get(
            "importance_since_reflection", 0.0
        )
        # Restore the id counter so future ids stay unique; recompute as a
        # fallback if an older save didn't store it.
        instance._next_id = data.get(
            "next_id", (max((r.id for r in instance.records), default=-1) + 1)
        )
        return instance


def _format_bullet(record: MemoryRecord) -> str:
    """One rendered memory line, e.g. ``- [observation, turn 3] ...`` (§6)."""
    return f" - [{record.kind.value}, turn {record.created_turn}] {record.text}"


def render_memories(records) -> str:
    """Render *records* as a "Relevant memories:" block, or ``""`` when empty.

    The empty-render guard is load-bearing (as in ``Knowledge.render``): with no
    records to show, callers get an empty string and leave the observation
    byte-identical to before memory existed.
    """
    if not records:
        return ""
    lines = ["Relevant memories:"]
    lines.extend(_format_bullet(r) for r in records)
    return "\n".join(lines)
