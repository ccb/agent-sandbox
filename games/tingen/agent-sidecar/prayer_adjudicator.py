#!/usr/bin/env python3
"""
Prayer adjudication reference (deterministic).
==============================================
The offline judgment the sidecar uses for player prayers, mirrored EXACTLY by the Godot
MockSidecar (tingen/src/MockSidecar.gd). The engine test feeds a battery of prayers through
both and asserts identical (outcome, severity); the real LLM replaces this later behind the
same contract. Keep the marker lists, thresholds, and decision order in lockstep with the
GDScript side.

Pure stdlib. Reads the focused pantheon from tingen/data/gods.json (one source of truth with
the engine), so a god's domain/register/wrath cannot drift between the two languages.
"""
from __future__ import annotations

import json
from pathlib import Path

GODS_PATH = Path(__file__).resolve().parent.parent / "tingen" / "data" / "gods.json"

RESPECT = [
    "please", "humbly", "beseech", "guide", "protect", "mercy",
    "grant", "thank", "praise", "honor", "i offer", "i beg",
]
DISRESPECT = [
    "demand", "command", "obey", "serve me", "worthless",
    "weak", "kneel", "i curse", "mock", "useless",
]
GRANT_THRESHOLD = 3
CRYPTIC_THRESHOLD = 1
OUTCOME_ZH = {"granted": "应允", "cryptic": "神秘应答", "ignored": "无应", "punished": "惩罚"}


def load_gods() -> dict:
    with open(GODS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _count(text: str, markers: list) -> int:
    return sum(1 for m in markers if m in text)


def _clampi(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def adjudicate_prayer(request: dict, gods: dict) -> dict:
    god_id = request.get("god", "")
    text = str(request.get("prayer", "")).lower()
    standing = float(request.get("standing", 0.0))
    god = gods.get(god_id, {})

    respect = _count(text, RESPECT)
    disrespect = _count(text, DISRESPECT)
    domain = [str(k).lower() for k in god.get("domain", [])]
    domain_hit = any(kw in text for kw in domain)

    score = respect * 2 - disrespect * 5
    score += 1 if domain_hit else 0
    score += int(max(-3.0, min(3.0, standing)))

    register = god.get("register", "")
    wrath = float(god.get("wrath", 0.5))

    if disrespect > 0:
        outcome = "punished"
        severity = _clampi(disrespect + int(round(wrath * 2.0)), 1, 3)
    elif register == "tarot":
        outcome, severity = "cryptic", 1
    elif score >= GRANT_THRESHOLD:
        outcome = "granted"
        severity = 2 if god_id == "outer_god" else 1
    elif score >= CRYPTIC_THRESHOLD:
        outcome, severity = "cryptic", 1
    else:
        outcome, severity = "ignored", 0

    return {
        "god": god_id, "outcome": outcome,
        "outcome_zh": OUTCOME_ZH.get(outcome, ""),
        "severity": severity, "score": score,
    }
