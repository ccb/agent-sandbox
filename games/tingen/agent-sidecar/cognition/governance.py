"""Propose-time hard veto — SPEC.md §5. Tingen's contribution: the narrative invariants Yumina's
soft director (nudge/escalate) cannot guarantee. Pure, data-declared, fixture-tested. The same
invariant set is meant to port to Yumina's bridge in TS — only the predicate wiring is per-language.

A Verdict is { decision: approve|amend|veto, reason, invariant, amended_action? }. Invariants are
evaluated in order; the FIRST that fires decides. None fires -> approve."""

from __future__ import annotations

IDLE = {"verb": "idle"}


# NOTE: there is deliberately NO secrecy invariant. Secrecy is PURELY BEHAVIORAL — a character that
# wishes to stay hidden does so because its persona prose tells it to (the LLM decides whether to reveal
# itself), not because a hard veto blocks a "revealing" action. The engine enforces only physics/legality.


def _no_rite_without_site(action: dict, actor: dict, world: dict):
    """The rite only bites at the altar: a perform_ritual_step by an agent with no TASK, or one not
    standing on a rite site, is amended to idle (declares the engine's proximity gate as a portable,
    testable invariant). Eligibility is the agent's own task (data), not a faction."""
    if str(action.get("verb", "")) == "perform_ritual_step":
        if not actor.get("task") or not bool(world.get("actor_at_rite_site", False)):
            return {
                "decision": "amend",
                "invariant": "no_rite_without_site",
                "reason": "the task only advances at its site",
                "amended_action": IDLE,
            }
    return None


# Ordered v1 invariant set. To add governance, append a predicate here (and a fixture).
INVARIANTS = (_no_rite_without_site,)


def review(action: dict, actor: dict, world_state: dict) -> dict:
    """Evaluate the invariants in order; the first match decides the verdict."""
    for invariant in INVARIANTS:
        verdict = invariant(action, actor, world_state)
        if verdict is not None:
            return verdict
    return {"decision": "approve", "invariant": None, "reason": "no invariant fired"}
