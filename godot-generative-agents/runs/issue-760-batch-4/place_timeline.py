#!/usr/bin/env python3
"""Where was each agent, and when? (#760 batch 4)

analyze_run.py answers "how much" -- decisions, cost, co-settled totals. This
answers "where", which is what you need to explain a co-settled number rather
than just report it. Batch 4's headline finding (#821) came out of reading two
of these side by side: every agent intended to be at the 10:00 lecture, and the
timeline showed each of them arriving after it ended.

Frames carry no explicit place field -- the location is inside the `act` string
as "... @ UPenn:<Place>:<sub-place>" -- so parse it out and collapse runs.

    ./place_timeline.py <run-dir> [--runs-dir DIR] [--agent NAME]

Stdlib only, like analyze_run.py, so it runs against any checkout.
"""

import argparse
import json
import pathlib
import re

SEC_PER_STEP = 10
SIM_START_MIN = 8 * 60  # 08:00


def clock(step: int) -> str:
    m = SIM_START_MIN + step * SEC_PER_STEP // 60
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def timeline(frames: pathlib.Path, only=None):
    seqs: dict[str, list] = {}
    for step, line in enumerate(frames.open()):
        for name, a in json.loads(line).items():
            if only and only.lower() not in name.lower():
                continue
            act = (a or {}).get("act") or ""
            m = re.search(r"@ UPenn:([^:]+)", act)
            key = (m.group(1) if m else "(none)", act.startswith("walking to"))
            run = seqs.setdefault(name, [])
            if run and run[-1][0] == key:
                run[-1][2] = step
            else:
                run.append([key, step, step])
    return seqs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_id")
    ap.add_argument(
        "--runs-dir", default=str(pathlib.Path(__file__).resolve().parents[1])
    )
    ap.add_argument("--agent", default=None, help="substring filter on agent name")
    args = ap.parse_args()

    frames = pathlib.Path(args.runs_dir) / args.run_id / "frames.jsonl"
    if not frames.exists():
        raise SystemExit(f"no frames.jsonl at {frames}")

    for name, spans in timeline(frames, args.agent).items():
        print(f"--- {name} ---")
        for (place, moving), a, b in spans:
            # Drop one-or-two-step walk blips; they are path recalculation, not
            # a leg of a journey, and they bury the real stops in noise.
            if moving and b - a < 2:
                continue
            print(
                f"  {a:5d}-{b:5d}  {clock(a)}-{clock(b)}  "
                f"{'walk ' if moving else 'AT   '}{place}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
