"""Simultaneous turn mode: the gather -> resolve round (issue #25, #42).

The default game loop is sequential: the player acts, then each NPC observes
the world *as changed by everyone before it* and acts. For richer simulations
(and the future 2D JRPG front end) we instead want characters to decide
**simultaneously**. This module implements that as an opt-in mode
(``Game(..., turn_mode="simultaneous")``) with the four-phase round from
``docs/design/multi-character-play.md`` (section 3):

1. **gather**  — collect one intended command per acting NPC. Every agent
   decides against the same turn-start snapshot, *before* the player's
   command has resolved — no one gets to peek at what anyone else does
   this turn.
2. **resolve** — the player's command resolves first (design-doc rule), then
   each gathered command routes through the parser's precondition gate, in
   resolve order (``resolve_order`` below). Same-turn **contention** is settled
   here deliberately (issue #42): a lightweight claim on each command's target
   means that when two characters reach for the same thing, the higher-priority
   one wins it and the loser is told *why* — it gets a ranked fallback or an
   informed retry, and the conflict is recorded as a first-class ``conflict``
   event rather than a bare failure.
3. **react**   — triggers fire, exactly as in sequential mode.
4. **advance** — the turn counter increments once per round.

Characters with a legacy ``behavior`` (and no agent) still work: they act at
their resolve slot via ``take_turn()``, observing the mid-resolve world — the
same semantics they had in the sequential loop.

The ordering and contention machinery is the **Orchestration** layer designed in
``docs/design/implemented/simultaneous-actions.md``; it is opt-in and additive — with no
phase map, no fallbacks, and no contention it reduces to PR #30's behavior.
"""

from dataclasses import dataclass, field

from .npc import (
    build_npc_context,
    format_observation_with_memories,
    route_first_workable,
    route_with_retry,
)


@dataclass
class Intent:
    """One gathered intention for the resolve phase.

    ``character`` wants to run ``command`` (chosen by ``agent`` during gather; a
    legacy behavior-only character carries ``agent=None, command=None`` and is
    resolved via ``take_turn()`` instead). The remaining fields support fair
    resolution (issue #42): ``gather_index`` is a stable tiebreak (the order the
    intent was gathered), ``action_name`` feeds the phase ordering, ``target`` is
    the resource the command claims (for contention detection), and ``fallbacks``
    are ranked backups the agent pre-chose for a lost contest.
    """

    character: "Character"
    agent: "Agent | None"
    command: "str | None"
    gather_index: int = 0
    action_name: "str | None" = None
    target: "Thing | None" = None
    fallbacks: list = field(default_factory=list)


# Default coarse action phases, lowest rank resolves first (design §4.1):
# communication can't be "missed" by being late, movement settles where everyone
# is, manipulation happens among the settled positions, and combat resolves last
# against a fully-arranged board. Opt in per game with ``game.phases``; with no
# map every action ties at one bucket and the order is PR #30's initiative sort.
DEFAULT_PHASES = {
    "say": 0,  # communicate
    "go": 1,  # move
    "get": 2,  # manipulate
    "drop": 2,
    "give": 2,
    "unlock door": 2,
    "attack": 3,  # fight
}


def _is_acting(game, character) -> bool:
    """Whether a character takes part in this round — the same skip rules as
    the sequential loop (Game.end_turn): not the player, not dead, not
    unconscious, and actually somewhere in the world."""
    if character is game.player:
        return False
    if character.get_property("is_dead") or character.get_property("is_unconscious"):
        return False
    if character.location is None:
        return False
    return True


def _as_command_list(decision) -> list:
    """Normalize what ``Agent.decide`` returned — a ``str`` (today), a ranked
    ``list[str]`` (issue #42 fallbacks), or ``None`` — into a list of non-empty
    command strings. The head is the primary command; the tail are fallbacks."""
    if decision is None:
        return []
    if isinstance(decision, str):
        decision = [decision]
    return [command for command in decision if command]


def gather_intents(game) -> list:
    """Phase 1 (gather): one intended command per acting NPC, in gather order
    (the insertion order of ``game.characters``).

    Agents decide here, against the turn-start world — but nothing is routed
    or traced yet; execution and its narration happen in resolve order. An
    agent that returns no command is simply sitting this round out. For each
    intent we also record, against the same snapshot, the command's action name
    and the resource it claims (via ``peek_action``, which constructs the action
    without running it) so the resolve phase can settle contention (issue #42).
    """
    intents = []
    for character in list(game.characters.values()):
        if not _is_acting(game, character):
            continue
        agent = character.agent
        if agent is not None:
            # Same persona lazy-adoption as make_react_behavior: an agent
            # attached without a persona takes on its character's.
            if not agent.persona:
                agent.persona = character.persona or ""
            # Re-read the character's goals each round, exactly as the
            # sequential factories do, so in-game add_goal()/complete_goal()
            # reaches the next decision prompt (issue #23 tiered goals).
            agent.goals = character.goals
            agent.action_names = list(game.parser.actions)
            # Perceive the nearby world and fold relevant memories into the
            # prompt, the same Observe step react_behavior runs (issues #75/#80).
            # Bind the memory owner first: gather never reaches decide_and_route,
            # which is where the sequential path binds it lazily.
            if not agent.memory.owner:
                agent.memory.owner = character.name
            agent.memory.perceive(game, character)
            base = build_npc_context(character, game)
            relevant = agent.memory.retrieve(query=base, turn=getattr(game, "turn", 0))
            observation = format_observation_with_memories(base, relevant)
            commands = _as_command_list(agent.decide(observation))
            if not commands:
                continue
            command, fallbacks = commands[0], commands[1:]
            # Peek the action (built, not run) to read its name and claimed
            # resource against the snapshot the agent decided on.
            action = game.parser.peek_action(command, actor=character)
            intents.append(
                Intent(
                    character,
                    agent,
                    command,
                    gather_index=len(intents),
                    action_name=action.action_name() if action is not None else None,
                    target=action.claimed_resource() if action is not None else None,
                    fallbacks=fallbacks,
                )
            )
        elif character.behavior is not None:
            # Legacy behavior: no command to gather; it runs whole at its
            # resolve slot and claims nothing.
            intents.append(Intent(character, None, None, gather_index=len(intents)))
    return intents


def phase_rank(intent, game) -> int:
    """Which phase an intent's action resolves in (design §4.1). Reads the
    game's optional ``phases`` map; with no map (or an action not in it) every
    intent lands in one bucket, so the phase component never breaks ties and the
    order collapses to PR #30's initiative sort."""
    phases = getattr(game, "phases", None) or {}
    return phases.get(intent.action_name, len(phases))


def _resolve_key(intent, game):
    """The default resolution key (design §4): a tuple sorted lexicographically
    — first *what kind* of action (phase), then *which character* is faster
    (initiative, PR #30's field), then *who decided first* (gather order)."""
    return (
        phase_rank(intent, game),
        -int(intent.character.get_property("initiative")),
        intent.gather_index,
    )


def resolve_order(intents, game) -> list:
    """Phase 2 ordering: return the intents in the order they resolve.

    The default policy is :func:`_resolve_key` (phase, then initiative, then
    gather order). A game may express *situational* priority — "the defender
    acts before the attacker this turn" — by defining its own
    ``resolve_order(self, intents)`` method on a ``Game`` subclass (design §4.2);
    we honor that override here, falling back to the default policy otherwise.
    """
    override = getattr(game, "resolve_order", None)
    if callable(override):
        return override(intents)
    return sorted(intents, key=lambda intent: _resolve_key(intent, game))


def _handle_contention(game, intent, winner) -> None:
    """Resolve a lost contest (issue #42): tell the loser *why*, surface the
    conflict, then hand it a pre-chosen fallback or an informed retry.

    The loser's gathered command is known to be doomed (``winner`` already took
    the resource this round), so it is never routed blindly — that is what turns
    a bare ``"I don't see it."`` failure into a legible "someone beat me to it."
    """
    character = intent.character
    reason = f"{winner.character.name} got the {intent.target.name} first this turn."
    # Surface contention as a first-class signal: a CONFLICT line for the
    # renderer (the story) and a `conflict` event for the log (the paper trail).
    game.parser.conflict(character.name, reason)
    game.log_event(
        character.name,
        "conflict",
        summary=reason,
        payload={"command": intent.command, "winner": winner.character.name},
    )
    if intent.fallbacks:
        # Cheap arm: a backup the agent pre-chose at gather — no second decide().
        route_first_workable(character, game, intent.agent, intent.fallbacks)
    else:
        # Informed arm: reflect on the true reason and re-decide.
        route_with_retry(
            character, game, intent.agent, intent.command, conflict_reason=reason
        )


def run_simultaneous_round(game, player_command: str) -> bool:
    """Run one full gather -> resolve -> react -> advance round.

    The simultaneous-mode counterpart of ``Game.do_command`` +
    ``Game.end_turn``. Returns whether the *player's* command succeeded; on
    failure the turn does not advance and the gathered intents are discarded,
    matching the sequential rule that a failed player command costs no turn.
    (For LLM-backed agents the gather decisions are already spent — that is
    the accepted price of deciding against the turn-start snapshot.)
    """
    # 1. gather — before the player's command touches the world.
    game._round_event_start = len(game.events)  # this round begins here
    intents = gather_intents(game)

    # 2. resolve — the player goes first (explicit actor, as in do_command).
    if not game.parser.parse_command(player_command, actor=game.player):
        return False

    # 4. advance — the counter moves once per round, before NPC resolution,
    # mirroring end_turn().
    game.turn += 1

    # 2b. resolve the NPC intents in priority order, settling contention as we
    # go. ``secured`` maps each contested resource to the intent that actually
    # took it this round; because we resolve highest-priority first, the first
    # intent to *win* a resource holds it, and any later intent reaching for the
    # SAME object is the loser of a genuine contest (issue #42). Gating on a
    # resource truly secured — not merely claimed — keeps the loser's reason
    # honest: if the winner's own command failed (e.g. the player took the thing
    # first), nothing is secured and the later intent fails plainly instead.
    secured = {}
    for intent in resolve_order(intents, game):
        character = intent.character
        # Re-check: the world has moved since gather — a character may have
        # died, been knocked out, or been removed by an earlier resolution,
        # and a dead character's gathered command must not run.
        if not _is_acting(game, character):
            continue
        if intent.agent is None:
            # Legacy behavior: runs whole at its resolve slot.
            character.take_turn(game)
        elif intent.target is not None and intent.target in secured:
            # A higher-priority character already took this exact resource.
            _handle_contention(game, intent, winner=secured[intent.target])
        elif route_with_retry(character, game, intent.agent, intent.command):
            # Uncontested, or the first to reach the resource: record what it
            # secured so a later claimant on the same object is seen as a loser.
            if intent.target is not None:
                secured[intent.target] = intent
        else:
            # A plain failure with no contender behind it (e.g. the player took
            # the thing first): the #30 signal, unchanged.
            reason = getattr(game.parser, "last_fail_message", None) or "action failed"
            game.log_event(
                character.name,
                "action_failed",
                summary=reason,
                payload={"command": intent.command},
            )
        if game.is_game_over():
            break

    # 3. react — triggers, exactly as the sequential loop does it.
    if not game.is_game_over():
        game._run_triggers()
    return True
