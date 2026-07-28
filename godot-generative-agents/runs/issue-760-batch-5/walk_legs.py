#!/usr/bin/env python3
"""Did agents actually arrive? Longest continuous walking stretch + settled share."""

import json, pathlib, sys, collections


def clock(s):
    m = 8 * 60 + s * 10 // 60
    return f"{m//60%24:02d}:{m%60:02d}"


def run(path, label):
    walking_run = collections.defaultdict(int)
    longest = collections.defaultdict(lambda: (0, 0))
    total = collections.Counter()
    walk = collections.Counter()
    tail = {}
    for step, line in enumerate(pathlib.Path(path).open()):
        for name, a in json.loads(line).items():
            act = str((a or {}).get("act") or "")
            w = act.startswith("walking to ")
            total[name] += 1
            walk[name] += w
            if w:
                walking_run[name] += 1
                if walking_run[name] > longest[name][0]:
                    longest[name] = (walking_run[name], step)
            else:
                walking_run[name] = 0
            tail[name] = walking_run[name]
    print(f"=== {label}")
    for name in sorted(total):
        n, end = longest[name]
        print(
            f"  {name:20s} walk {100*walk[name]/total[name]:4.1f}%   "
            f"longest unbroken walk {n*10//60:3d} min (ends {clock(end)})   "
            f"still walking at end: {tail[name]*10//60} min"
        )


B = "/Users/alistairking/Projects/purm-2026/agent-sandbox/.claude/worktrees/issue-760-batch-4-sonnet/godot-generative-agents/runs/run-20260727-190111-f15134/frames.jsonl"
run(B, "BASELINE (batch 4)")
print()
run(sys.argv[1], "BATCH 5")
