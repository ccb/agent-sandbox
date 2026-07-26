"""Agent-to-agent conversation (issue #86, NEXT-STEPS Phase E).

When two co-located agents meet, they run a **turn-taking** exchange: one says a
line, the other replies, and so on until someone bows out or a cap is reached.
Every line lands in **both** participants' memory streams as
:class:`~text_adventure_games.memory.MemoryKind.CHAT` -- the speaker remembers
what it said, the listener what it heard. That dual write is the point of the
feature: it is how relationships and information actually propagate through a town
of agents (Park et al., 2023, "Generative Agents").

This module is the loop *around* the dialogue seam (:meth:`~text_adventure_games.
npc.Agent.converse`), exactly as :func:`~text_adventure_games.npc.react_behavior`
is the loop around ``Agent.decide``. It is game-coupled -- it reads
``game.audience_for`` and writes character memory / ``heard`` buffers -- but
imports nothing heavy, talking to the game, characters, and agents by duck typing.

Two deliberate design choices:

* **No precondition gate.** Saying a thing changes no world state, so -- unlike
  ``decide_and_route`` -- the loop does not route utterances through the parser.
* **Reuse the one audibility seam.** Who may be talked to is decided by
  ``Game.audience_for`` (room-based by default; override it for a range/line-of-
  sight world), so a continuous world constrains conversation exactly as it
  constrains who hears a ``Say`` -- there is no second, parallel notion of
  "nearby" to keep in sync.

The loop never *starts* on its own: a caller (the engine turn loop or the
Smallville step loop) decides when two agents meet and calls :func:`converse`. An
agent whose backend can't talk returns ``None`` from ``converse`` and the meeting
simply produces no lines, so wiring this in is safe and additive -- silent until a
conversational brain is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .memory import render_memories
from .prompt_templates import render

# Total lines across both speakers before the loop stops on its own. A meeting is
# a handful of exchanges, not an unbounded dialogue -- this caps cost and keeps one
# pair from monopolizing a turn.
DEFAULT_MAX_EXCHANGES = 6
# Dialogue is moderately memorable -- a little above a mundane observation, below a
# momentous event -- so it surfaces in later retrieval without crowding it.
DEFAULT_CHAT_IMPORTANCE = 4.0
# At most this many place names go into a dialogue observation's grounding
# block (issue #780). Mirrors the decide path's destination-enum cap
# (backend/cognition.py DECIDE_MAX_ENUM) rather than inventing a second rule;
# duplicated as a literal because the engine must not import the backend.
MAX_GROUNDED_PLACES = 20


@dataclass
class Conversation:
    """The record of one meeting: who took part and every line, in order."""

    participants: tuple[str, str]
    lines: list[tuple[str, str]] = field(default_factory=list)  # (speaker, utterance)

    @property
    def happened(self) -> bool:
        """Whether at least one line was actually said."""
        return bool(self.lines)

    def transcript(self) -> str:
        """The dialogue as ``"name: line"`` rows (empty string if nothing said)."""
        return "\n".join(f"{name}: {text}" for name, text in self.lines)

    def last_line(self) -> str | None:
        """The most recent ``"name: line"`` row, or ``None`` if nothing was said."""
        if not self.lines:
            return None
        name, text = self.lines[-1]
        return f"{name}: {text}"


def can_converse(game, a, b) -> bool:
    """Whether *a* can hold a conversation with *b* right now.

    Both must be alive (a dead character may still have an agent attached, but
    the dead don't talk -- issue #755), both need an attached agent (the
    decision-maker that supplies lines), and *b* must be in *a*'s audience under
    the game's audibility seam -- co-located by default, narrowed by any
    ``audience_for`` override. Symmetric in practice (the default audience is
    mutual), but phrased from *a* as the initiator.
    """
    if a is b:
        return False
    if a.get_property("is_dead") or b.get_property("is_dead"):
        return False
    if getattr(a, "agent", None) is None or getattr(b, "agent", None) is None:
        return False
    return b in game.audience_for(a, "", b)


def find_conversation_pairs(game, candidates=None) -> list[tuple]:
    """Return the eligible co-located agent pairs, each unordered pair once.

    Scans ``candidates`` (default: every character in the game) and pairs any two
    that :func:`can_converse`. The earlier-listed character is returned first in
    each pair, so a caller can treat it as the initiator for a deterministic
    order. The caller decides *which* pairs actually talk (e.g. throttling so the
    same two don't re-converse every step) -- this only reports who *could*.
    """
    chars = (
        list(candidates) if candidates is not None else list(game.characters.values())
    )
    pairs = []
    for i, a in enumerate(chars):
        for b in chars[i + 1 :]:
            if can_converse(game, a, b):
                pairs.append((a, b))
    return pairs


def converse(
    game,
    initiator,
    partner,
    *,
    max_exchanges: int = DEFAULT_MAX_EXCHANGES,
    turn: int | None = None,
    importance: float = DEFAULT_CHAT_IMPORTANCE,
) -> Conversation:
    """Run a turn-taking conversation between *initiator* and *partner*.

    The loop alternates speakers: each is asked (via ``agent.converse``) for its
    next line given who it's talking with and the dialogue so far; the line is
    written to both memory streams and delivered to the listener's ``heard``
    buffer; then it's the other's turn. It stops when a speaker says nothing
    (``None``/empty -- a decline or natural end), flags its line as a wrap-up
    (``agent.last_dialogue_done``), or ``max_exchanges`` lines have been said.

    Returns a :class:`Conversation` with the full transcript (empty if the pair
    couldn't talk or the initiator opened with nothing). ``turn`` stamps the
    memories (defaults to ``game.turn``); ``importance`` is the poignancy of each
    chat memory.
    """
    convo = Conversation(participants=(initiator.name, partner.name))
    if not can_converse(game, initiator, partner):
        return convo
    if turn is None:
        turn = getattr(game, "turn", 0)

    speaker, listener = initiator, partner
    for _ in range(max_exchanges):
        if not exchange(
            game, convo, speaker, listener, turn=turn, importance=importance
        ):
            break
        speaker, listener = listener, speaker
    return convo


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
    """Generate and record ONE line of *convo* (issue #371).

    Ask *speaker* (via ``agent.converse``) for its next line given the dialogue
    so far; on a real line, dual-write it to both memory streams and the
    listener's ``heard`` buffer (exactly as the whole-loop ``converse`` does) and
    append it to ``convo.lines``. Emit any cognition-tool trace the line used.

    ``places``/``visited`` are the optional #780 grounding inputs threaded into
    the observation; both ``None`` (the default) reproduces the previous
    observation exactly. ``converse`` deliberately does not forward them --
    the backend's multi-tick caller opts in at its own ``exchange`` call.

    Returns ``True`` if a line was said and the conversation may continue,
    ``False`` if the speaker bowed out (``None``/empty -- a decline or natural
    end) or flagged a wrap-up (``agent.last_dialogue_done``). Does **not** enforce
    ``max_exchanges``: the caller stops when ``len(convo.lines)`` hits its cap.
    This is the one-exchange seam that lets the backend spread a meeting across
    ticks; :func:`converse` is the in-process loop over it. Co-location is
    checked once by the caller (``converse`` / the backend's pair scan), not
    re-checked here -- a multi-tick caller keeps its participants pinned.
    """
    observation = _dialogue_observation(
        speaker, listener, convo, turn, places=places, visited=visited
    )
    utterance = speaker.agent.converse(observation, listener.name)
    _trace_cognition(game, speaker)
    if not utterance or not utterance.strip():
        return False
    utterance = utterance.strip()
    _deliver(speaker, listener, utterance, turn, importance)
    convo.lines.append((speaker.name, utterance))
    return not getattr(speaker.agent, "last_dialogue_done", False)


def _trace_cognition(game, speaker) -> None:
    """Emit any cognition-tool calls the speaker made for its line (issue #358).

    An :class:`~text_adventure_games.npc.LLMAgent` with cognition tools on
    buffers one summary line per ``recall`` / ``read_plan`` call in
    ``last_cognition_trace`` (the dialogue seam has no parser reference); this
    loop -- which does hold the game -- emits them on the private
    AGENT_REASONING channel. Same privacy rule as ``npc._log_decision``: never
    ``command_history``, so one agent's recall can't leak into another's
    observation. A no-op for agents without the buffer (scripted, flag off).
    """
    lines = getattr(getattr(speaker, "agent", None), "last_cognition_trace", None)
    if not lines:
        return
    trace = getattr(getattr(game, "parser", None), "agent_reasoning", None)
    if trace is None:
        return
    for line in lines:
        trace(speaker.name, line)


def _deliver(speaker, listener, utterance: str, turn: int, importance: float) -> None:
    """Write one line into both agents' memories and the listener's heard buffer.

    The two memories are phrased from each agent's point of view ("I said to X"
    vs "X said to me") so retrieval surfaces a first-person record on both sides.
    The listener also ``hear``\\ s the line, mirroring the ``Say`` action, so it
    shows up in the listener's next observation just like any overheard speech.
    """
    _remember(
        speaker,
        f'I said to {listener.name}: "{utterance}"',
        partner=listener.name,
        turn=turn,
        importance=importance,
    )
    _remember(
        listener,
        f'{speaker.name} said to me: "{utterance}"',
        partner=speaker.name,
        turn=turn,
        importance=importance,
    )
    hear = getattr(listener, "hear", None)
    if callable(hear):
        hear(f'{speaker.name} said to you: "{utterance}"')


def _remember(
    character, text: str, *, partner: str, turn: int, importance: float
) -> None:
    """Append a CHAT memory to *character*'s stream, binding its owner lazily
    (as ``decide_and_route`` does) so a never-acted agent still records dialogue."""
    agent = getattr(character, "agent", None)
    memory = getattr(agent, "memory", None)
    if memory is None:
        return
    if not memory.owner:
        memory.owner = character.name
    memory.add_chat(text, turn=turn, partner=partner, importance=importance)


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


def _dialogue_observation(
    speaker, listener, convo: Conversation, turn: int, places=None, visited=None
) -> str:
    """Build the user-message observation for *speaker*'s next line.

    Names the partner, folds in what the speaker remembers about them (a
    read-only retrieval -- ``touch=False`` -- so conversing doesn't perturb
    decision-time recency), and replays the dialogue so far. The persona and
    goals ride on the agent's own system message (see ``LLMAgent``), so they are
    not repeated here. If the caller opts in with ``places``/``visited``, the
    #780 place-grounding block is appended immediately below the first line
    (never above it -- the schedule mock routes on the observation's first
    line); it is absent entirely unless the caller supplies it.
    """
    lines = [f"You are talking with {listener.name}."]
    grounding_block = _place_grounding_block(speaker, places, visited)
    if grounding_block:
        lines.append("")
        lines.append(grounding_block)
    memory = getattr(getattr(speaker, "agent", None), "memory", None)
    if memory is not None:
        try:
            relevant = memory.retrieve(query=listener.name, turn=turn, touch=False)
        except Exception:
            relevant = []
        memory_block = render_memories(relevant)
        if memory_block:
            lines.append("")
            lines.append(memory_block)
    if convo.lines:
        lines.append("")
        lines.append("Conversation so far:")
        lines.extend(f"  {name}: {text}" for name, text in convo.lines)
        lines.append("Say your next line, or a brief goodbye to end the conversation.")
    else:
        lines.append(
            f"You have just met {listener.name}. Greet them or start a conversation."
        )
    return "\n".join(lines)
