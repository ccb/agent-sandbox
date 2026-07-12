"""Tiered goals — SPEC.md §3. Mirrors agent-sandbox's Goal/GoalType (extracted as a tiny
standalone, since characters.py's Goal pulls the whole engine). Adds the public/secret split
and the prompt-render order the spec defines. Pure; fixture-tested by run_vectors.py."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GoalTier(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass
class Goal:
    description: str
    tier: GoalTier
    done: bool = False
    secret: bool = False  # Yumina-parity: secret goals never enter a revealed==False prompt.


# Standing context first (long), immediate push last (short).
_RENDER_ORDER = (GoalTier.LONG, GoalTier.MEDIUM, GoalTier.SHORT)


def _tier(value) -> GoalTier:
    return value if isinstance(value, GoalTier) else GoalTier(value)


def active_by_tier(goals: list[Goal], tier) -> list[Goal]:
    """Active (not done) goals of one tier, in insertion order."""
    t = _tier(tier)
    return [g for g in goals if not g.done and _tier(g.tier) == t]


def prompt_goals(goals: list[Goal], revealed: bool) -> list[Goal]:
    """Active goals to render, long -> medium -> short, insertion order within a tier.
    Secret goals are dropped unless ``revealed`` (the cult's true aim never leaks)."""
    out: list[Goal] = []
    for tier in _RENDER_ORDER:
        for g in goals:
            if g.done or _tier(g.tier) != tier:
                continue
            if g.secret and not revealed:
                continue
            out.append(g)
    return out


def render_block(goals: list[Goal], revealed: bool) -> str:
    """Prompt-ready GOALS block, or '' when there are no active goals to show."""
    chosen = prompt_goals(goals, revealed)
    if not chosen:
        return ""
    lines = [f"- [{g.tier.value}] {g.description}" for g in chosen]
    return "CURRENT GOALS (most important first):\n" + "\n".join(lines)
