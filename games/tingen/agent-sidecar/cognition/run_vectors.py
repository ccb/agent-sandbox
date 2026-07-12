"""Fixture runner — verifies the cognition implementation against test_vectors.json (SPEC.md).
The SAME vectors must pass in the future TypeScript (Yumina) port. Exit non-zero on any failure.

    python3 cognition/run_vectors.py
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import agent_memory as M  # noqa: E402  (vendored agent-sandbox memory framework)
import goals as G  # noqa: E402
import governance as GOV  # noqa: E402

TOL = 1e-6
_passed = 0
_failed = 0


def check(cond: bool, label: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def _record(rid: int, text: str, importance: float, last_accessed: int) -> "M.MemoryRecord":
    return M.MemoryRecord(
        id=rid,
        kind=M.MemoryKind.OBSERVATION,
        text=text,
        created_turn=last_accessed,
        last_accessed_turn=last_accessed,
        importance=importance,
    )


def main() -> int:
    V = json.load(open(os.path.join(_HERE, "test_vectors.json")))

    print("[scoring]")
    for c in V["scoring"]["recency"]:
        rec = _record(0, "x", 1.0, c["last_accessed_turn"])
        got = M.recency_score(rec, c["turn"], c["decay"])
        check(abs(got - c["expected"]) < TOL, f"recency {c['name']} -> {got:.6f}")
    for c in V["scoring"]["importance"]:
        rec = _record(0, "x", c["importance"], 0)
        got = M.importance_score(rec)
        check(abs(got - c["expected"]) < TOL, f"importance {c['name']} -> {got}")
    for c in V["scoring"]["relevance"]:
        got = M.relevance_score(c["query"], c["text"])
        check(abs(got - c["expected"]) < TOL, f"relevance {c['name']} -> {got:.4f}")

    print("[retrieval]")
    for c in V["retrieval"]:
        mem = M.AgentMemory(owner="t")
        for r in c["records"]:
            mem.records.append(_record(r["id"], r["text"], r["importance"], r["last_accessed_turn"]))
        out = mem.retrieve(
            c["query"], c["turn"],
            max_records=c["max_records"], token_budget=c["token_budget"], decay=c["decay"],
        )
        got_order = [r.id for r in out]
        check(got_order == c["expected_order"], f"{c['name']} -> order {got_order}")
        if "expected_scores" in c:
            by_id = {r["id"]: r for r in c["records"]}
            ok = True
            for k, exp in c["expected_scores"].items():
                rec = next(r for r in mem.records if r.id == int(k))
                # recompute the combined score the way retrieve() does (touch already applied,
                # so recompute recency against the PRE-touch last_accessed via the fixture value).
                base = by_id[int(k)]["last_accessed_turn"]
                rec2 = _record(rec.id, rec.text, rec.importance, base)
                s = (M.recency_score(rec2, c["turn"], c["decay"])
                     + M.importance_score(rec2)
                     + M.relevance_score(c["query"], rec.text))
                ok = ok and abs(s - exp) < 1e-4
            check(ok, f"{c['name']} -> combined scores match")
        if "expected_last_accessed_after" in c:
            ok = all(
                next(r for r in mem.records if r.id == int(k)).last_accessed_turn == v
                for k, v in c["expected_last_accessed_after"].items()
            )
            check(ok, f"{c['name']} -> retrieved records touched to turn")

    print("[goals]")
    for c in V["goals"]:
        gs = [G.Goal(g["description"], G.GoalTier(g["tier"]), g["done"], g.get("secret", False))
              for g in c["goals"]]
        for tier, exp in c["expected_active_by_tier"].items():
            got = [g.description for g in G.active_by_tier(gs, tier)]
            check(got == exp, f"active[{tier}] -> {got}")
        got_t = [g.description for g in G.prompt_goals(gs, revealed=True)]
        check(got_t == c["expected_prompt_order_revealed_true"], "prompt order revealed=true")
        got_f = [g.description for g in G.prompt_goals(gs, revealed=False)]
        check(got_f == c["expected_prompt_order_revealed_false"], "prompt order revealed=false (secret dropped)")

    print("[veto]")
    for c in V["veto"]:
        v = GOV.review(c["action"], c["actor"], c["world_state"])
        exp = c["expected"]
        ok = v["decision"] == exp["decision"] and v.get("invariant") == exp.get("invariant")
        if "amended_action" in exp:
            ok = ok and v.get("amended_action") == exp["amended_action"]
        check(ok, f"{c['name']} -> {v['decision']} ({v.get('invariant')})")

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
