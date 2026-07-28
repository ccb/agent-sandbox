#!/usr/bin/env python3
"""Classify arrived_then_departed hits: real retarget vs same-place oscillation."""

import json, pathlib, re, sys, collections


def dest(act):
    m = re.match(r"walking to (.+?) @ ", act)
    return m.group(1) if m else None


def base(place):  # "Houston Hall — Reception Hall" -> "Houston Hall"
    return place.split(" — ")[0] if place else place


def same_place(a, b):
    """Two destinations naming the same building.

    NOT `base(a) == base(b)`: a sub-place drops its building's qualifier, so
    "Van Pelt — Moelis Reading Room" reduces to "Van Pelt" and never matches the
    building's own name, "Van Pelt Library". That miss scored two of the
    baseline's library-to-its-own-reading-room hops as genuine retargets.
    """
    if not a or not b:
        return False
    if "Penn campus" in (a, b) or a == b:
        return True
    x, y = base(a), base(b)
    return x.startswith(y) or y.startswith(x)


def run(path, label):
    prev = {}
    hits = []
    for step, line in enumerate(pathlib.Path(path).open()):
        for name, a in json.loads(line).items():
            act = str((a or {}).get("act") or "")
            w = act.startswith("walking to ")
            pact, pw = prev.get(name, ("", False))
            if w and act != pact and pw:
                hits.append((name, step, dest(pact), dest(act)))
            prev[name] = (act, w)
    same, real = [], []
    for h in hits:
        _, _, d0, d1 = h
        # same-place: one destination is the other's parent building, or the
        # addressless campus hub, or literally identical
        if same_place(d0, d1):
            same.append(h)
        else:
            real.append(h)
    print(
        f"=== {label}: {len(hits)} turn-arounds — {len(same)} same-place oscillation, {len(real)} genuine retarget"
    )
    # episodes: cluster hits within 120 steps (20 sim-min) per agent
    eps = collections.defaultdict(list)
    for name, step, d0, d1 in hits:
        b = eps[name]
        if b and step - b[-1][-1] <= 120:
            b[-1][-1] = step
        else:
            b.append([step, step])
    for name, spans in sorted(eps.items()):
        n = sum(1 for h in hits if h[0] == name)
        print(
            f"  {name:20s} {n:3d} hits in {len(spans)} episode(s): "
            + ", ".join(f"step {a}-{b}" for a, b in spans)
        )
    for name, step, d0, d1 in real:
        print(f"    GENUINE  {name} step {step}: {d0!r} -> {d1!r}")
    pairs = collections.Counter((base(d0), base(d1)) for _, _, d0, d1 in same)
    for (x, y), n in pairs.most_common(5):
        print(f"    osc x{n}: {x} <-> {y}")


B = "/Users/alistairking/Projects/purm-2026/agent-sandbox/.claude/worktrees/issue-760-batch-4-sonnet/godot-generative-agents/runs/run-20260727-190111-f15134/frames.jsonl"
N = sys.argv[1]
run(B, "BASELINE run-20260727-190111-f15134 (batch 4)")
print()
run(N, "BATCH 5 (main + #826/#831/#837/#838)")
