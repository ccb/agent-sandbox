"""Simultaneous turn mode: the gather -> resolve round (issue #25).

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
   ``initiative`` order (higher first; ties keep gather order). Contention is
   settled here implicitly: if two characters grabbed for the same thing, the
   later one's preconditions fail and the failure reason is fed back so its
   agent may retry (see :func:`npc.route_with_retry`).
3. **react**   — triggers fire, exactly as in sequential mode.
4. **advance** — the turn counter increments once per round.

Characters with a legacy ``behavior`` (and no agent) still work: they act at
their resolve slot via ``take_turn()``, observing the mid-resolve world — the
same semantics they had in the sequential loop.
"""

from collections import namedtuple

from .npc import build_npc_context, route_with_retry

# One gathered intention: which character wants to run which command, and the
# agent that chose it. Legacy behavior-only characters carry
# ``agent=None, command=None`` and are resolved via take_turn() instead.
Intent = namedtuple("Intent", ["character", "agent", "command"])


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


def gather_intents(game) -> list:
    """Phase 1 (gather): one intended command per acting NPC, in gather order
    (the insertion order of ``game.characters``).

    Agents decide here, against the turn-start world — but nothing is routed
    or traced yet; execution and its narration happen in resolve order. An
    agent that returns no command is simply sitting this round out.
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
            observation = build_npc_context(character, game)
            command = agent.decide(observation)
            if command:
                intents.append(Intent(character, agent, command))
        elif character.behavior is not None:
            # Legacy behavior: no command to gather; it runs whole at its
            # resolve slot.
            intents.append(Intent(character, None, None))
    return intents


def resolve_order(intents) -> list:
    """Phase 2 ordering: higher ``initiative`` resolves first; characters
    without one (get_property returns False, i.e. 0) keep gather order among
    themselves, because Python's sort is stable."""
    return sorted(
        intents, key=lambda intent: -int(intent.character.get_property("initiative"))
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
    intents = gather_intents(game)

    # 2. resolve — the player goes first (explicit actor, as in do_command).
    if not game.parser.parse_command(player_command, actor=game.player):
        return False

    # 4. advance — the counter moves once per round, before NPC resolution,
    # mirroring end_turn().
    game.turn += 1

    for intent in resolve_order(intents):
        character = intent.character
        # Re-check: the world has moved since gather — a character may have
        # died, been knocked out, or been removed by an earlier resolution,
        # and a dead character's gathered command must not run.
        if not _is_acting(game, character):
            continue
        if intent.agent is not None:
            succeeded = route_with_retry(character, game, intent.agent, intent.command)
            if not succeeded:
                # The conflict signal (design doc section 8): record what was
                # attempted and why it failed, e.g. losing a contested item.
                reason = (
                    getattr(game.parser, "last_fail_message", None) or "action failed"
                )
                game.log_event(
                    character.name,
                    "action_failed",
                    summary=reason,
                    payload={"command": intent.command},
                )
        else:
            character.take_turn(game)
        if game.is_game_over():
            break

    # 3. react — triggers, exactly as the sequential loop does it.
    if not game.is_game_over():
        game._run_triggers()
    return True
