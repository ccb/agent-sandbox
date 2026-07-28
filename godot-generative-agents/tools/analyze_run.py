#!/usr/bin/env python3
"""Summarise one persisted live-LLM run: what the agents did, and what it cost (#760).

Batch 1 built this table by hand for five runs and lost the scratch script; batch 2
commits it. Reads only what a run already persists -- ``runs/<id>/frames.jsonl`` and
the ``memories``/``runs`` tables of ``runs/sim.db`` -- plus the ``usage.json`` the
driver captured before shutdown (tokens and by_tool/by_role live in the in-process
ledger and never reach the database).

Three counting rules are worth stating, because each produces wrong numbers if you
take the obvious route:

* **Conversations (#781).** A frame's ``chat`` is the whole transcript so far, not the
  new line, and it is repainted across the playback window. Counting non-empty
  ``chat`` frames, or counting distinct transcripts, double-counts badly -- a 20-line
  exchange looks like 20 conversations. A conversation is a maximal run of frames
  whose chat each extends the previous as a prefix; ``--self-check`` pins this.
* **Verbs.** There are two different "talk_to share" numbers and they disagree by 4x.
  A frame's ``trace`` holds the action *currently running*, repainted every frame, so
  counting it measures share of agent-*time* -- long actions dominate. Batch 1 quoted
  share of *decisions*: one count per ``call_tools`` reply in the cassette, which is
  what "are the agents stuck in a talk loop" actually asks. Both are reported;
  ``decisions`` is the headline and the one comparable to batch 1's write-ups.
* **Co-settled pair-steps (#795).** Whether two agents were ever actually together
  (not just in the same building while one walks through) is what "was conversation
  even possible" asks. The backend counts this itself now and writes it to
  ``run.yaml``'s ``result:`` block -- authoritative, and this tool prefers it. For a
  run saved before that counter existed there is no such record, so it falls back to
  approximating from frames alone; the only available signal there is "not walking",
  which also counts a merely-*idle* agent as settled and so can over-report. The
  output always states which of the two it used -- never silently blended.

Stdlib only, no repo imports: it must stay runnable against an archived run directory
long after the code that wrote it has moved on.

usage:
  analyze_run.py <run-id> [--runs-dir DIR] [--usage usage.json] [--json]
  analyze_run.py --self-check
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import sqlite3
import sys
import tempfile

# #779 tags every seeded edge memory; #778 renders every kept commitment through
# prompt_templates/commitment_memory.prompty, whose body starts "I agreed with".
RELATIONSHIP_TAG = "relationship"
COMMITMENT_PREFIX = "I agreed with "


def count_conversations(chats: list[list | None]) -> int:
    """Number of distinct conversations in one agent's per-frame ``chat`` series.

    ``chats`` is that agent's ``chat`` value at each frame, in order: None when not
    talking, otherwise the transcript-so-far as a list of ``[speaker, text]`` lines.
    A new conversation starts whenever a transcript is *not* an extension of the one
    in the previous frame -- which is what makes the repainting harmless.
    """
    count = 0
    prev: list | None = None
    for chat in chats:
        if not chat:
            prev = None
            continue
        if prev is None or chat[: len(prev)] != prev:
            count += 1
        prev = chat
    return count


def read_frames(path: pathlib.Path) -> tuple[list[dict], int]:
    frames = [json.loads(line) for line in path.open() if line.strip()]
    return frames, len(frames)


def count_decisions(cassette: pathlib.Path) -> collections.Counter:
    """Verbs the model actually *chose*, one per decide reply, from the cassette.

    Only ``call_tools`` -- the decide path. ``call_tool`` is the single-tool route
    used by scoring and the like, which is a cost line, not an action.
    """
    verbs: collections.Counter = collections.Counter()
    if not cassette.exists():
        return verbs
    for line in cassette.open():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("method") != "call_tools":
            continue
        for call in (rec.get("response") or {}).get("tool_calls") or []:
            if call.get("name"):
                verbs[call["name"]] += 1
    return verbs


def _co_settled_from_frames(frames: list[dict]) -> tuple[int, dict]:
    """Co-settled pair-steps approximated from replay frames alone.

    APPROXIMATE, and the tool says so in its output. From frames the only
    available signal is "act does not start with 'walking to '", which counts
    an *idle* agent as settled and so can over-report. The backend counter
    (#795) is authoritative; this exists only for runs saved before it landed.
    """
    total, by_pair = 0, {}
    for frame in frames:
        settled = [
            (name, a.get("loc"))
            for name, a in sorted(frame.items())
            if not str(a.get("act") or "").startswith("walking to ") and a.get("loc")
        ]
        for i, (a_name, a_loc) in enumerate(settled):
            for b_name, b_loc in settled[i + 1 :]:
                if a_loc == b_loc:
                    total += 1
                    key = f"{a_name} + {b_name}"
                    by_pair[key] = by_pair.get(key, 0) + 1
    return total, by_pair


def _load_run_record(run_id: str, runs_dir: pathlib.Path) -> dict:
    """Read a run.yaml's `result:` block without a yaml dependency.

    Only the scalars (plus one nested map, `by_pair`) under `result:` are
    needed, so a small indent-tracking scanner beats adding a dependency to
    a stdlib-only tool. `result.save()` writes block-style YAML at a fixed
    2/4-space indent (verified against `RunRecord.save`'s `yaml.safe_dump`),
    which is all this relies on -- it is not a general YAML parser.

    One flow-style case is unavoidable even in block-style output: PyYAML
    always renders an EMPTY collection as `{}`/`[]`, never as an empty
    block (there is no block spelling of "nothing here"). `by_pair: {}` is
    exactly the zero-co-settled run #795 is about, so it must parse to an
    empty dict, not the literal string `"{}"`. Anything flow-style beyond
    that -- a non-empty `{...}`/`[...]` -- is a shape this scanner does not
    understand, and *guessing* at it risks a wrong number labelled
    authoritative. So it fails safe instead: abandon the whole record and
    let the caller fall back to the frame proxy.
    """
    path = runs_dir / run_id / "run.yaml"
    if not path.is_file():
        return {}
    result: dict = {}
    in_result = False
    nested_key: str | None = None  # result-level key currently being filled
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith(" "):
            in_result = line.strip() == "result:"
            nested_key = None
            continue
        if not in_result or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        value = value.strip()
        if indent == 2:
            if value == "":
                nested_key = key
                result[key] = {}
            elif value == "{}":
                nested_key = None
                result[key] = {}
            elif value[:1] in "{[":
                # Any other flow-style collection -- including an empty `[]`,
                # which render() would then call .items() on. Unreachable today
                # (_by_pair_json always writes a mapping), fail-safe anyway.
                return {}  # can't confirm the shape
            else:
                nested_key = None
                result[key] = int(value) if value.lstrip("-").isdigit() else value
        elif indent == 4 and nested_key:
            if value[:1] in "{[":
                return {}  # same fail-safe, one level down
            result[nested_key][key] = (
                int(value) if value.lstrip("-").isdigit() else value
            )
    return {"result": result} if result else {}


_WALK_ACT = re.compile(r"^walking to (.+?) @ (.*)$")


def _walk_target(act: str) -> tuple[str, str] | None:
    """``(display name, building)`` for a walk-in-progress act, else ``None``.

    A leg in progress paints ``walking to <display name> @
    <world>:<building>:<place>``. Classifying a turn-around needs the
    *building*, and the address is the only reliable source for it: a
    sub-place's display name drops its building's qualifier, so ``Van Pelt --
    Moelis Reading Room`` (address ``UPenn:Van Pelt Library:Moelis Family
    Grand Reading Room``) shares no prefix with its own building's display
    name, ``Van Pelt Library``. Reducing display names and comparing those is
    what scored two of #826's baseline library-to-its-own-reading-room hops as
    cross-campus retargets, and published the wrong number.

    The addressless campus hub paints ``walking to Penn campus @ None`` -- it
    is nowhere in particular, so its building is ``""``, which
    ``_same_place`` treats as matching anything.
    """
    m = _WALK_ACT.match(act)
    if not m:
        return None
    place, address = m.group(1), m.group(2)
    parts = address.split(":")
    return place, (parts[1] if address != "None" and len(parts) >= 3 else "")


def _same_place(a: str, b: str) -> bool:
    """Two walk targets naming one building. ``""`` -- the hub -- matches all."""
    return not a or not b or a == b


def _turnarounds(frames: list, sec_per_step: int = 10, start: str = "") -> list[dict]:
    """Every arrival that departed again, split by kind (#850).

    The #826 signature: `run_simulation.step` only asks an agent to decide once
    its tile path is empty, so a destination change always sits on an arrival
    boundary -- and a walk segment followed *immediately* by another walk
    segment means the agent got there and turned straight around. Reading
    frames alone is enough: the act line is "walking to <place> @ <address>"
    for the whole leg, so a change of act between two walking frames is a new
    leg.

    Combining the two kinds into one count (what this did before #850) makes a
    number no fix can be judged by -- #760 batch 5 measured 17 of the
    baseline's 20 as one agent oscillating inside a single building (#849),
    while the cross-building retargeting #826 is about sat flat at 3:

    * ``same_place`` -- the two destinations share a building, or one is the
      campus hub. #849.
    * ``retarget`` -- the agent abandoned a leg to a genuinely different
      building. #826. ``abandoned_minutes`` is how long it had been walking the
      leg it gave up on, which is the cost of the event and #826's acceptance
      measure.

    Known under-count, and #850 asked for a second look at it: a zero-tile
    travel to the place the agent already stands sets `desc`/`act` to the same
    "walking to <place> @ <address>" string (`run_simulation.step`'s travel
    branch builds it whether or not `path` comes back empty), so the agent
    re-decides every tick with an UNCHANGED `act` and this reads as one
    continuous leg, scoring 0. The split narrows the blast radius rather than
    fixing it: a zero-tile travel targets the place the agent is standing in,
    so an invisible one can only ever be a ``same_place`` hit -- the
    ``retarget`` count #826 now rests on is not exposed to it. Detecting them
    at all needs the cassette's travel decisions, not frames. And the old
    warning still holds for the combined number: a run with thrash near 0 and
    `walking_share` near 100% is this failure mode, not a fix.

    frames.jsonl carries no clock, so ``sec_per_step``/``start`` (from
    manifest.json) are what turn steps into sim-minutes and wall-clock.
    """
    started = datetime.datetime.fromisoformat(start) if start else None
    events: list[dict] = []
    previous: dict = {}  # agent -> (its act, the step that act began)
    for step, frame in enumerate(frames):
        for name, a in frame.items():
            act = str((a or {}).get("act") or "")
            was_act, began = previous.get(name, ("", step))
            if act == was_act:
                continue
            previous[name] = (act, step)
            old, new = _walk_target(was_act), _walk_target(act)
            if not (old and new):
                continue  # not two back-to-back legs: an arrival came between
            events.append(
                {
                    "agent": name,
                    "step": step,
                    "clock": (
                        (
                            started + datetime.timedelta(seconds=step * sec_per_step)
                        ).strftime("%H:%M")
                        if started
                        else ""
                    ),
                    "kind": "same_place" if _same_place(old[1], new[1]) else "retarget",
                    "from": old[0],
                    "to": new[0],
                    "abandoned_minutes": (step - began) * sec_per_step // 60,
                }
            )
    return events


def _load_manifest(run_dir: pathlib.Path) -> dict:
    """The run's manifest.json, or ``{}``.

    frames.jsonl has no clock, so this is the only record of how much sim-time
    a step is worth. The exporter writes ``sec_per_step`` and ``start`` into
    it (#580). Without it the tool falls back to the exporter's own default of
    10 s/step and *says* which it used, rather than printing minutes derived
    from a guess as if they were measured.
    """
    path = run_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def summarise(run_id: str, runs_dir: pathlib.Path, usage: dict | None) -> dict:
    run_dir = runs_dir / run_id
    frames, steps = read_frames(run_dir / "frames.jsonl")

    verbs: collections.Counter = collections.Counter()
    walking = 0
    agent_frames = 0
    chats_by_agent: dict[str, list] = collections.defaultdict(list)
    for frame in frames:
        for name, a in frame.items():
            agent_frames += 1
            if str(a.get("act") or "").startswith("walking to "):
                walking += 1
            for entry in a.get("trace") or []:
                if entry.get("kind") == "action" and entry.get("tool"):
                    verbs[entry["tool"]] += 1
            chats_by_agent[name].append(a.get("chat"))

    conversations = sum(count_conversations(c) for c in chats_by_agent.values())
    total_verbs = sum(verbs.values())
    decisions = count_decisions(run_dir / "cassette.jsonl")
    total_decisions = sum(decisions.values())

    # #795: prefer the backend's own count (RunRecord.result) and fall back to
    # the frame proxy only for runs saved before it existed -- see
    # _co_settled_from_frames for why the fallback can over-report.
    record = _load_run_record(run_id, runs_dir)  # returns {} when absent
    recorded = (record.get("result") or {}).get("co_settled_pair_steps")
    if recorded is not None:
        co_settled, by_pair = recorded, (record["result"].get("by_pair") or {})
        co_settled_source = "run record"
    else:
        co_settled, by_pair = _co_settled_from_frames(frames)
        co_settled_source = "frames (approximate: idle counts as settled)"

    manifest = _load_manifest(run_dir)
    spm = manifest.get("sec_per_step")
    spm_ok = isinstance(spm, int) and not isinstance(spm, bool) and spm > 0
    sec_per_step = spm if spm_ok else 10
    turnarounds = _turnarounds(frames, sec_per_step, str(manifest.get("start") or ""))
    thrash = dict(sorted(collections.Counter(e["agent"] for e in turnarounds).items()))

    out = {
        "run_id": run_id,
        "steps": steps,
        "agents": sorted(chats_by_agent),
        # Share of decisions -- batch 1's measure, the comparable one.
        "decisions": dict(decisions.most_common()),
        "decision_count": total_decisions,
        "distinct_verbs": len(decisions),
        "talk_to_share": (
            round(decisions.get("talk_to", 0) / total_decisions, 4)
            if total_decisions
            else 0.0
        ),
        # Share of agent-time -- the same verbs weighted by how long each ran.
        "time_verbs": dict(verbs.most_common()),
        "time_verb_frames": total_verbs,
        "talk_to_time_share": (
            round(verbs.get("talk_to", 0) / total_verbs, 4) if total_verbs else 0.0
        ),
        "walking_share": round(walking / agent_frames, 4) if agent_frames else 0.0,
        "sec_per_step": sec_per_step,
        "sec_per_step_source": "manifest.json" if spm_ok else "default (no manifest)",
        # #826: arrivals that immediately departed again -- a walk segment
        # followed by another walk with no arrival between. 20 across #760
        # batch 4 (Priya 4, Mateo 16); expect ~0 once the decide seam tells an
        # agent what it just did and what a walk costs.
        "arrived_then_departed": thrash,
        "arrived_then_departed_total": sum(thrash.values()),
        # Halved: each conversation is seen once per participant.
        "conversations": conversations // 2 if conversations > 1 else conversations,
        "conversations_agent_sided": conversations,
        "co_settled": co_settled,
        "co_settled_source": co_settled_source,
        "by_pair": by_pair,
    }

    db = runs_dir / "sim.db"
    if db.exists():
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT status, cost, steps, model FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row:
            out["persisted"] = {
                "status": row["status"],
                "cost": row["cost"],
                "steps": row["steps"],
                "model": row["model"],
            }
        seeded: collections.Counter = collections.Counter()
        commitments: collections.Counter = collections.Counter()
        for m in con.execute(
            "SELECT agent, kind, text, extra FROM memories WHERE run_id = ?", (run_id,)
        ):
            if RELATIONSHIP_TAG in (m["extra"] or ""):
                seeded[m["agent"]] += 1
            elif m["text"].startswith(COMMITMENT_PREFIX):
                commitments[m["agent"]] += 1
        out["relationship_memories"] = dict(sorted(seeded.items()))  # #779
        out["relationship_memories_total"] = sum(seeded.values())
        out["commitment_memories"] = dict(sorted(commitments.items()))  # #778
        out["commitment_memories_total"] = sum(commitments.values())
        con.close()

    if usage:
        out["cost"] = usage.get("total_cost_usd")
        out["calls"] = usage.get("calls")
        out["failed_calls"] = usage.get("failed_calls")
        out["input_tokens"] = usage.get("input_tokens")
        out["output_tokens"] = usage.get("output_tokens")
        out["cache_read_input_tokens"] = usage.get("cache_read_input_tokens")
        out["by_role"] = usage.get("by_role")
        out["by_tool"] = usage.get("by_tool")
        out["over_budget"] = usage.get("over_budget")
    return out


def render(s: dict) -> str:
    lines = [
        f"run {s['run_id']}  {s['steps']} steps  {len(s['agents'])} agents",
        f"  agents      {', '.join(s['agents'])}",
    ]
    if "cost" in s:
        lines.append(
            f"  cost        ${s['cost']:.4f}  {s['calls']} calls"
            f"  ({s['input_tokens']:,} in / {s['output_tokens']:,} out,"
            f" cache_read {s['cache_read_input_tokens']:,})"
            + ("  BUDGET TRIPPED" if s.get("over_budget") else "")
        )
        if s.get("failed_calls"):
            lines.append(f"  failed      {s['failed_calls']} calls errored (#745)")
    if "persisted" in s:
        p = s["persisted"]
        lines.append(
            f"  persisted   status={p['status']} cost=${p['cost']:.4f} steps={p['steps']}"
        )
    lines += [
        f"  walking     {s['walking_share']:.1%} of agent-frames"
        f"   ({s['sec_per_step']}s per step, {s['sec_per_step_source']})",
        f"  thrash      {s['arrived_then_departed_total']} arrivals departed again"
        + (
            "  "
            + ", ".join(
                f"{name}×{n}"
                for name, n in sorted(
                    s["arrived_then_departed"].items(), key=lambda kv: -kv[1]
                )
            )
            if s["arrived_then_departed"]
            else ""
        ),
        f"  talk_to     {s['talk_to_share']:.1%} of {s['decision_count']} decisions"
        f"   ({s['talk_to_time_share']:.1%} of agent-time)",
        f"  verbs       {s['distinct_verbs']} distinct: "
        + ", ".join(f"{v}×{n}" for v, n in s["decisions"].items()),
        f"  convos      {s['conversations']}",
        f"  co-settled  {s['co_settled']} pair-steps  [{s['co_settled_source']}]",
        *(
            f"    {pair:<28} {n}"
            for pair, n in sorted(s["by_pair"].items(), key=lambda kv: -kv[1])
        ),
    ]
    if "relationship_memories_total" in s:
        lines.append(
            f"  #779 seeds  {s['relationship_memories_total']} relationship memories "
            + (
                str(s["relationship_memories"])
                if s["relationship_memories"]
                else "(NONE)"
            )
        )
        lines.append(
            f"  #778 commit {s['commitment_memories_total']} commitment memories "
            + (str(s["commitment_memories"]) if s["commitment_memories"] else "(none)")
        )
    if s.get("by_role"):
        lines.append(
            "  by_role     "
            + ", ".join(
                f"{r} ${c:.4f}"
                for r, c in sorted(s["by_role"].items(), key=lambda kv: -kv[1])
            )
        )
    return "\n".join(lines)


def self_check() -> None:
    """The counting rule that batch 1 got wrong (#781), pinned."""
    a, b, c = ["A", "hi"], ["B", "yo"], ["A", "bye"]
    # One exchange, repainted across five frames, is ONE conversation.
    assert count_conversations([[a], [a, b], [a, b], [a, b, c], [a, b, c]]) == 1
    # A gap ends it; the next transcript starts a second.
    assert count_conversations([[a], [a, b], None, [a], [a, b]]) == 2
    # Back-to-back without a gap: not a prefix-extension, so still two.
    assert count_conversations([[a], [a, b], [c], [c, b]]) == 2
    assert count_conversations([None, None]) == 0
    assert count_conversations([]) == 0
    # The naive counts this rule replaces would have said 5 and 4.

    # #795: the frame-proxy fallback. A walking agent never counts as settled
    # even when co-located; two settled agents in the same room do, once.
    frames = [
        {
            "A": {"act": "reading @ x", "loc": "Hall"},
            "B": {"act": "reading @ x", "loc": "Hall"},
        },
        {
            "A": {"act": "walking to Hall @ x", "loc": "Hall"},
            "B": {"act": "reading @ x", "loc": "Hall"},
        },
        {
            "A": {"act": "reading @ x", "loc": "Hall"},
            "B": {"act": "reading @ x", "loc": "Green"},
        },
    ]
    total, by_pair = _co_settled_from_frames(frames)
    assert total == 1, total
    assert by_pair == {"A + B": 1}, by_pair

    # #795: the authoritative run-record reader, including the one nested
    # map (`by_pair`) run.yaml carries -- exercised against real
    # `yaml.safe_dump` block-style output, not a hand-typed guess at it.
    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = pathlib.Path(tmp)
        run_dir = runs_dir / "run1"
        run_dir.mkdir()
        (run_dir / "run.yaml").write_text(
            "game: penn\n"
            "seed: 42\n"
            "result:\n"
            "  steps: 1200\n"
            "  cost_usd: 0.5\n"
            "  co_settled_pair_steps: 399\n"
            "  by_pair:\n"
            "    Diego Torres + Sofia Ramirez: 248\n"
            "    Tanaka + Sofia Ramirez: 90\n"
            "  conversations: 12\n"
            "steps: []\n",
            encoding="utf-8",
        )
        record = _load_run_record("run1", runs_dir)
        assert record["result"]["co_settled_pair_steps"] == 399, record
        assert record["result"]["by_pair"] == {
            "Diego Torres + Sofia Ramirez": 248,
            "Tanaka + Sofia Ramirez": 90,
        }, record
        assert _load_run_record("missing", runs_dir) == {}

    # #795 CRITICAL regression: PyYAML always renders an EMPTY dict as flow
    # style (`by_pair: {}`) even under block-style dump -- there is no block
    # spelling of "nothing here". That is exactly the zero-co-settled run
    # this tool exists to surface, and the naive parser above stored the
    # literal string "{}" for it, which crashed render()'s `.items()` call.
    # This exact YAML text is real `yaml.safe_dump(..., sort_keys=False)`
    # output for that shape (checked in a throwaway probe, not re-derived
    # here) -- a hand-typed guess is how the original bug hid.
    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = pathlib.Path(tmp)
        run_dir = runs_dir / "run-zero"
        run_dir.mkdir()
        (run_dir / "frames.jsonl").write_text(
            '{"A": {"act": "reading @ x", "loc": "Hall"}}\n'
            '{"A": {"act": "walking to Green @ x", "loc": "Green"}}\n',
            encoding="utf-8",
        )
        (run_dir / "run.yaml").write_text(
            "game: penn\n"
            "seed: 42\n"
            "cassette:\n"
            "  path: cassette.jsonl\n"
            "  sha256: abc123\n"
            "engine_version: deadbeef\n"
            "result:\n"
            "  steps: 1200\n"
            "  cost_usd: 0.234\n"
            "  co_settled_pair_steps: 0\n"
            "  by_pair: {}\n"
            "  conversations: 0\n"
            "steps_list: []\n",
            encoding="utf-8",
        )
        record = _load_run_record("run-zero", runs_dir)
        assert record["result"]["co_settled_pair_steps"] == 0, record
        assert record["result"]["by_pair"] == {}, record
        # The bug was in render(), not the parser -- a parser-only assert
        # would have missed it. Run the real summarise() -> render() path.
        s = summarise("run-zero", runs_dir, usage=None)
        assert s["co_settled"] == 0, s
        assert s["co_settled_source"] == "run record", s
        assert s["by_pair"] == {}, s
        out = render(s)
        assert "co-settled  0 pair-steps  [run record]" in out, out

    # Fail-safe: a flow-style value this scanner does not understand (a
    # non-empty `{...}`, or ANY `[...]` -- render() calls .items() on by_pair)
    # must abandon the whole record, not guess at it -- never a wrong number
    # labelled authoritative. Caller falls back to the frame proxy for such a
    # run, same as if run.yaml were absent.
    for weird in ("{a: 1, b: 2}", "[]", "[1, 2]"):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = pathlib.Path(tmp)
            run_dir = runs_dir / "run-weird"
            run_dir.mkdir()
            (run_dir / "run.yaml").write_text(
                f"result:\n  co_settled_pair_steps: 7\n  by_pair: {weird}\n",
                encoding="utf-8",
            )
            assert _load_run_record("run-weird", runs_dir) == {}, weird

    # #826: an arrival that departed again is a walk segment followed by another
    # walk segment. Ada walks, arrives and settles (not a turn-around); Bo walks,
    # then walks somewhere else with no frame between (one turn-around).
    frames = [
        {
            "Ada": {"act": "walking to Cafe @ T:Cafe:counter"},
            "Bo": {"act": "walking to Cafe @ T:Cafe:counter"},
        },
        {
            "Ada": {"act": "walking to Cafe @ T:Cafe:counter"},
            "Bo": {"act": "walking to Library @ T:Library:desks"},
        },
        {
            "Ada": {"act": "reading @ T:Cafe:counter"},
            "Bo": {"act": "walking to Library @ T:Library:desks"},
        },
        {
            "Ada": {"act": "walking to Library @ T:Library:desks"},
            "Bo": {"act": "reading @ T:Library:desks"},
        },
    ]
    got = _turnarounds(frames)
    assert [(e["agent"], e["kind"]) for e in got] == [("Bo", "retarget")], got
    # An agent who never walks contributes nothing, and a missing agent entry is
    # tolerated (frames from a run that added a resident mid-way).
    assert _turnarounds([{"Cy": {"act": "reading @ x"}}, {}]) == []

    # #850: the classifier primitive. Every comparison is on the ADDRESS -- see
    # _walk_target for why display names cannot be reduced and compared, which
    # is how the published batch-5 split was wrong the first time.
    vp_room = (
        "walking to Van Pelt — Moelis Reading Room @ "
        "UPenn:Van Pelt Library:Moelis Family Grand Reading Room"
    )
    assert _walk_target(vp_room) == (
        "Van Pelt — Moelis Reading Room",
        "Van Pelt Library",
    ), _walk_target(vp_room)
    # THE TRAP: these two display names share no prefix, but they are one
    # building. Reducing "Van Pelt — Moelis Reading Room" to "Van Pelt" and
    # comparing it to "Van Pelt Library" scores this as a cross-campus retarget.
    vp = "walking to Van Pelt Library @ UPenn:Van Pelt Library:lobby"
    assert _walk_target(vp) == ("Van Pelt Library", "Van Pelt Library")
    assert _same_place(_walk_target(vp_room)[1], _walk_target(vp)[1])
    # The addressless campus hub is nowhere in particular: it matches anything.
    hub = "walking to Penn campus @ None"
    assert _walk_target(hub) == ("Penn campus", "")
    assert _same_place("", "Houston Hall") and _same_place("Houston Hall", "")
    # Two genuinely different buildings do not match.
    assert not _same_place("Van Pelt Library", "Houston Hall")
    # Not a walk at all, and an address this scanner does not recognise (fewer
    # than three segments) -- the latter compares as "unknown", never as a
    # match, so an unfamiliar world over-reports retargets rather than hiding
    # oscillation.
    assert _walk_target("reading @ UPenn:Van Pelt Library:lobby") is None
    assert _walk_target("walking to Elsewhere @ flat-address") == (
        "Elsewhere",
        "",
    ), _walk_target("walking to Elsewhere @ flat-address")

    # #850: the two kinds, on the real act strings the Penn runs emit.
    hh = "walking to Houston Hall @ UPenn:Houston Hall:lobby"
    hh_pool = (
        "walking to Houston Hall — Billiard Room @ UPenn:Houston Hall:Billiard Room"
    )
    ch = "walking to College Hall @ UPenn:College Hall:lobby"
    sat = "reading @ UPenn:Van Pelt Library:lobby"

    def frame(**acts):
        return {name: {"act": act} for name, act in acts.items()}

    # 60 s/step keeps the arithmetic readable: one frame is one sim-minute.
    split = [
        frame(Osc=hh, Trap=vp_room, Hub=hub, Real=vp, Arrives=vp, Sits=sat),
        frame(Osc=hh, Trap=vp_room, Hub=hub, Real=vp, Arrives=vp, Sits=sat),
        frame(Osc=hh, Trap=vp_room, Hub=hub, Real=vp, Arrives=sat, Sits=sat),
        frame(Osc=hh_pool, Trap=vp, Hub=ch, Real=hh, Arrives=hh, Sits=sat),
    ]
    events = _turnarounds(split, sec_per_step=60, start="2023-02-13 08:00:00")
    by_agent = {e["agent"]: e for e in events}
    assert len(events) == 4, events
    # Same building via its own sub-place; via the em-dash display name that
    # does NOT prefix-match its building; and via the addressless hub.
    assert by_agent["Osc"]["kind"] == "same_place", by_agent["Osc"]
    assert by_agent["Trap"]["kind"] == "same_place", by_agent["Trap"]
    assert by_agent["Hub"]["kind"] == "same_place", by_agent["Hub"]
    # A genuinely different building, and only that one.
    assert by_agent["Real"]["kind"] == "retarget", by_agent["Real"]
    assert by_agent["Real"]["from"] == "Van Pelt Library", by_agent["Real"]
    assert by_agent["Real"]["to"] == "Houston Hall", by_agent["Real"]
    # The leg ran steps 0-3, so three minutes were thrown away; the clock is
    # the moment it was abandoned, 08:00 + 3 steps of 60 s.
    assert by_agent["Real"]["abandoned_minutes"] == 3, by_agent["Real"]
    assert by_agent["Real"]["clock"] == "08:03", by_agent["Real"]
    # An agent that ARRIVED between its two legs is not a turn-around, and one
    # that never walks contributes nothing.
    assert "Arrives" not in by_agent and "Sits" not in by_agent, by_agent
    # No start -> no clock string, and the 10 s/step default floors the same
    # 3-step leg to 0 min rather than fabricating 3.
    assert _turnarounds(split)[0]["clock"] == ""
    assert {e["abandoned_minutes"] for e in _turnarounds(split)} == {0}

    # #850: manifest.json is the only record of sim-time per step. Absent or
    # unreadable falls back to 10 and is labelled as a fallback, never printed
    # as if measured.
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = pathlib.Path(tmp)
        assert _load_manifest(run_dir) == {}
        (run_dir / "manifest.json").write_text("{ not json", encoding="utf-8")
        assert _load_manifest(run_dir) == {}
        (run_dir / "manifest.json").write_text(
            '{"sec_per_step": 10, "start": "2023-02-13 08:00:00"}', encoding="utf-8"
        )
        assert _load_manifest(run_dir)["sec_per_step"] == 10

    print("self-check OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarise one persisted live-LLM run.")
    ap.add_argument("run_id", nargs="?")
    # tools/ -> godot-generative-agents/ -> runs/, i.e. run_store.DEFAULT_RUNS_DIR.
    # (Not imported: this file is deliberately stdlib-only. The `/ "runs"` was
    # lost when the script was promoted out of runs/issue-760-batch-2/, where
    # parents[1] already WAS the runs dir.)
    ap.add_argument(
        "--runs-dir", default=str(pathlib.Path(__file__).resolve().parents[1] / "runs")
    )
    ap.add_argument("--usage", help="usage.json captured before /shutdown")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return 0
    if not args.run_id:
        ap.error("run_id is required (or pass --self-check)")

    usage = json.loads(pathlib.Path(args.usage).read_text()) if args.usage else None
    s = summarise(args.run_id, pathlib.Path(args.runs_dir), usage)
    print(json.dumps(s, indent=2) if args.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
