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

# Total lines across both speakers before the loop stops on its own. A meeting is
# a handful of exchanges, not an unbounded dialogue -- this caps cost and keeps one
# pair from monopolizing a turn.
DEFAULT_MAX_EXCHANGES = 6
# Dialogue is moderately memorable -- a little above a mundane observation, below a
# momentous event -- so it surfaces in later retrieval without crowding it.
DEFAULT_CHAT_IMPORTANCE = 4.0


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

    Both need an attached agent (the decision-maker that supplies lines), and *b*
    must be in *a*'s audience under the game's audibility seam -- co-located by
    default, narrowed by any ``audience_for`` override. Symmetric in practice
    (the default audience is mutual), but phrased from *a* as the initiator.
    """
    if a is b:
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
        observation = _dialogue_observation(speaker, listener, convo, turn)
        utterance = speaker.agent.converse(observation, listener.name)
        if not utterance or not utterance.strip():
            break
        utterance = utterance.strip()
        _deliver(speaker, listener, utterance, turn, importance)
        convo.lines.append((speaker.name, utterance))
        if getattr(speaker.agent, "last_dialogue_done", False):
            break
        speaker, listener = listener, speaker
    return convo


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


def _dialogue_observation(speaker, listener, convo: Conversation, turn: int) -> str:
    """Build the user-message observation for *speaker*'s next line.

    Names the partner, folds in what the speaker remembers about them (a
    read-only retrieval -- ``touch=False`` -- so conversing doesn't perturb
    decision-time recency), and replays the dialogue so far. The persona and
    goals ride on the agent's own system message (see ``LLMAgent``), so they are
    not repeated here.
    """
    lines = [f"You are talking with {listener.name}."]
    memory = getattr(getattr(speaker, "agent", None), "memory", None)
    if memory is not None:
        try:
            relevant = memory.retrieve(query=listener.name, turn=turn, touch=False)
        except Exception:
            relevant = []
        block = render_memories(relevant)
        if block:
            lines.append("")
            lines.append(block)
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
