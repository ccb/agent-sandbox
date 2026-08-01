"""Export a persisted run back into ``penn_replay.json`` (issue #307).

The live->replay bridge: ``serve_penn --persist`` (or a persisted bake)
records a run into the #304 RunStore; this module reads it back out as the
exact five-key replay the bake writes -- ``{meta, frames, memory_streams,
events, wishes}``, every shape pinned by the #305 contract -- so a recorded
live run re-opens in the Godot viewer ("Open a local replay file" in the
landing menu) with bubbles, memory streams, timeline markers, and demand
records (#622) intact.

    uv run python -m backend.penn.export_replay              # newest run
    uv run python -m backend.penn.export_replay <run_id> --out replay.json

Read-side only: no simulation, no store writes. (``backend/exporter.py`` is
NOT this writer -- it emits the legacy Django folder format.)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.contract import SCHEMA_VERSION
from backend.replay_codec import fatten_frames, slim_frames
from backend.run_store import DEFAULT_RUNS_DIR, RunStore


def build_replay(store: RunStore, run_id: str) -> dict:
    """Assemble the #305 ``Replay`` dict for *run_id* from the store.

    ``meta`` is the run's manifest with ``steps`` filled from the frame
    count when absent -- a live manifest doesn't know it up front, while a
    bake's already does and must pass through untouched (the round-trip
    test pins exported == baked file). Raises ``ValueError`` on an unknown
    run id.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"unknown run id: {run_id}")
    meta = run["manifest"]
    # Stores hold fat frames today, but fatten anyway (#941): it's the
    # identity on fat rows, and it means in-process consumers (the
    # believability eval routes run dirs through here) always see full rows
    # whatever a future store holds. The slim encoding is applied only when
    # main() writes the file.
    frames = fatten_frames(store.read_frames(run_id))
    meta.setdefault("steps", len(frames))
    return {
        "meta": meta,
        "frames": frames,
        "memory_streams": {
            p["name"]: store.memories_for(run_id, p["name"]) for p in meta["personas"]
        },
        "events": store.read_events(run_id),
        "wishes": store.read_wishes(run_id),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export a persisted run (#304 RunStore) to penn_replay.json."
    )
    ap.add_argument("run_id", nargs="?", default=None, help="default: the newest run")
    ap.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="RunStore root (default: godot-generative-agents/runs/)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="output path (default: <runs-dir>/<run_id>/penn_replay.json)",
    )
    args = ap.parse_args()

    store = RunStore(args.runs_dir)
    run_id = args.run_id
    if run_id is None:
        runs = store.list_runs()
        if not runs:
            print(f"No runs in {store.root} -- record one with --persist first.")
            return 2
        run_id = runs[0]["id"]
    try:
        replay = build_replay(store, run_id)
    except ValueError as exc:
        print(exc)
        return 2

    # Written files are slim (#941), same as the bake's writer — the WASM
    # viewer can't parse a showcase-scale fat file. build_replay stays fat
    # for in-process callers. The file's schema_version must describe the
    # encoding *this writer* used, not whatever version the run was recorded
    # under, so stamp the current one (a dict() copy keeps the manifest's key
    # order — schema_version is replaced in place).
    replay = dict(replay)
    replay["meta"] = dict(replay["meta"], schema_version=SCHEMA_VERSION)
    replay["frames"] = slim_frames(replay["frames"])

    out = Path(args.out) if args.out else store.root / run_id / "penn_replay.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(replay, fh, ensure_ascii=False)
    print(
        f"Wrote {out.resolve()} ({len(replay['frames'])} steps, "
        f"{len(replay['meta']['personas'])} personas, "
        f"{len(replay['events'])} events, {len(replay['wishes'])} wishes). "
        'Open it in the viewer via "Open a local replay file".'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
