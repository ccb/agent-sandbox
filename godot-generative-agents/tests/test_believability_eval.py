"""The offline believability audit (issue #584).

Pins `backend.eval.believability`: loading a run's artifacts (baked replay
file OR a #304 RunStore run directory), the deterministic scrambler used as
the acceptance control, the per-agent evidence digest, the deterministic
heuristic judge, the LLM judge (scripted, offline) with its ledger ceiling,
and the CLI. Fully offline -- no keys, no network. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_believability_eval.py -v
"""

import copy
import json

from backend.eval.believability import (
    DIMENSIONS,
    HeuristicJudge,
    LlmJudge,
    audit,
    build_evidence,
    evidence_text,
    load_replay,
    main,
    scramble_replay,
)
from backend.run_store import RunStore

# ------------------------------------------------------------ a tiny replay
#
# Two personas, 60 steps, in the exact shape generate_penn_replay.py bakes
# (meta / frames / memory_streams / events). Both eat breakfast at the Cafe
# (where they chat, standing together), then walk to their second stop.

N_STEPS = 60

CAFE = (9, 0)  # where both agents eat breakfast (adjacent tiles)
LIBRARY = (9, 10)  # Ada's afternoon stop
GYM = (30, 0)  # Bea's afternoon stop -- far from the Cafe

CHAT = [
    ["Ada", "This cafe makes a great breakfast."],
    ["Bea", "It does -- best pancakes on campus."],
]


def _persona(name, second_place, second_activity):
    return {
        "name": name,
        "emoji": "X",
        "persona": f"{name} is a busy student.",
        "home": "Home",
        "schedule": [
            {
                "place": "Cafe",
                "activity": "eating breakfast",
                "emoji": "c",
                "steps": 20,
            },
            {
                "place": second_place,
                "activity": second_activity,
                "emoji": "s",
                "steps": None,
            },
        ],
    }


def _walk_entry(place, address, step, start_xy, end_xy, frac):
    x = round(start_xy[0] + (end_xy[0] - start_xy[0]) * frac)
    y = round(start_xy[1] + (end_xy[1] - start_xy[1]) * frac)
    return {
        "x": x,
        "y": y,
        "act": f"walking to {place} @ {address}",
        "e": "🚶",
        "reasoning": None,
        "chat": None,
        "memories": None,
    }


def _at_entry(xy, activity, address, memories=None, chat=None):
    return {
        "x": xy[0],
        "y": xy[1],
        "act": f"{activity} @ {address}",
        "e": "🙂",
        "reasoning": None,
        "chat": chat,
        "memories": memories,
    }


def _agent_frames(name, second_place, second_xy, second_activity):
    """One agent's 60 frames: walk to Cafe (0-9), breakfast (10-29),
    walk to stop two (30-39), afternoon activity (40-59)."""
    cafe_addr = "T:Cafe:counter"
    second_addr = f"T:{second_place}:spot"
    # Ada and Bea stand one tile apart at the Cafe so they can chat.
    cafe_xy = CAFE if name == "Ada" else (CAFE[0] + 1, CAFE[1])
    retrieved = [
        {
            "kind": "plan",
            "importance": 5.0,
            "text": f"Plan: go to Cafe and eating breakfast.",
            "created_turn": 0,
        }
    ]
    frames = []
    for step in range(10):
        frames.append(_walk_entry("Cafe", cafe_addr, step, (0, 0), cafe_xy, step / 9))
    for step in range(10, 30):
        chat = CHAT if 12 <= step <= 20 else None
        memories = retrieved if step == 10 else None
        frames.append(_at_entry(cafe_xy, "eating breakfast", cafe_addr, memories, chat))
    for step in range(30, 40):
        frames.append(
            _walk_entry(
                second_place, second_addr, step, cafe_xy, second_xy, (step - 30) / 9
            )
        )
    for step in range(40, 60):
        frames.append(_at_entry(second_xy, second_activity, second_addr))
    return frames


def make_replay():
    ada = _agent_frames("Ada", "Library", LIBRARY, "shelving books")
    bea = _agent_frames("Bea", "Gym", GYM, "lifting weights")
    frames = [{"Ada": ada[i], "Bea": bea[i]} for i in range(N_STEPS)]
    streams = {
        "Ada": [
            {
                "kind": "plan",
                "importance": 5.0,
                "text": "Plan: go to Cafe and eating breakfast. "
                "Today's stops: Cafe, Library.",
                "created_turn": 0,
            },
            {
                "kind": "observation",
                "importance": 3.0,
                "text": "I traveled to Cafe.",
                "created_turn": 10,
            },
            {
                "kind": "observation",
                "importance": 2.0,
                "text": "I am eating breakfast.",
                "created_turn": 11,
            },
        ],
        "Bea": [
            {
                "kind": "plan",
                "importance": 5.0,
                "text": "Plan: go to Cafe and eating breakfast. "
                "Today's stops: Cafe, Gym.",
                "created_turn": 0,
            },
            {
                "kind": "observation",
                "importance": 3.0,
                "text": "I traveled to Cafe for breakfast.",
                "created_turn": 10,
            },
        ],
    }
    return {
        "meta": {
            "schema_version": 1,
            "tile_px": 32,
            "width": 40,
            "height": 40,
            "steps": N_STEPS,
            "sec_per_step": 60,
            "start": "2023-02-13 08:00:00",
            "vision_r": 8,
            "personas": [
                _persona("Ada", "Library", "shelving books"),
                _persona("Bea", "Gym", "lifting weights"),
            ],
            "relationships": [],
        },
        "frames": frames,
        "memory_streams": streams,
        "events": [
            {
                "turn": 10,
                "actor": "Ada",
                "action": "travel",
                "summary": "Ada arrived at the Cafe",
                "payload": {},
            }
        ],
    }


# ------------------------------------------------------------ loading


def test_load_replay_reads_a_baked_json_file(tmp_path):
    replay = make_replay()
    path = tmp_path / "penn_replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    loaded = load_replay(path)
    assert list(loaded) == ["meta", "frames", "memory_streams", "events"]
    assert loaded == replay


def test_load_replay_reads_a_run_store_directory(tmp_path):
    replay = make_replay()
    store = RunStore(tmp_path / "runs")
    run_id = store.create_run(replay["meta"], run_id="run-x")
    for step, frame in enumerate(replay["frames"]):
        store.append_frame(run_id, step, frame)
    for i, (name, stream) in enumerate(replay["memory_streams"].items()):
        store.record_memories(
            run_id,
            name,
            [
                dict(rec, id=j, last_accessed_turn=rec["created_turn"])
                for j, rec in enumerate(stream)
            ],
        )
    store.append_events(run_id, replay["events"])
    loaded = load_replay(tmp_path / "runs" / run_id)
    assert loaded["meta"]["personas"] == replay["meta"]["personas"]
    assert loaded["frames"] == replay["frames"]
    assert loaded["memory_streams"] == replay["memory_streams"]
    assert loaded["events"] == replay["events"]


# ------------------------------------------------------------ the scrambler


def test_scramble_frames_is_deterministic_and_does_not_mutate():
    replay = make_replay()
    before = copy.deepcopy(replay)
    a = scramble_replay(replay, "frames", seed=7)
    b = scramble_replay(replay, "frames", seed=7)
    assert replay == before  # input untouched
    assert a["frames"] == b["frames"]  # same seed, same shuffle
    assert a["frames"] != replay["frames"]  # actually scrambled
    # Only the frame ORDER changes -- same multiset of frames.
    key = lambda f: json.dumps(f, sort_keys=True)
    assert sorted(map(key, a["frames"])) == sorted(map(key, replay["frames"]))


def test_scramble_plans_swaps_schedules_between_agents():
    replay = make_replay()
    swapped = scramble_replay(replay, "plans", seed=0)
    schedules = {p["name"]: p["schedule"] for p in swapped["meta"]["personas"]}
    original = {p["name"]: p["schedule"] for p in replay["meta"]["personas"]}
    # Every agent now carries some OTHER agent's schedule.
    assert schedules["Ada"] == original["Bea"]
    assert schedules["Bea"] == original["Ada"]


# ------------------------------------------------------------ evidence


def test_build_evidence_collapses_frames_into_act_segments():
    evidence = build_evidence(make_replay())
    assert set(evidence) == {"Ada", "Bea"}
    ada = evidence["Ada"]
    acts = [(s.start, s.end, s.act) for s in ada.segments]
    assert acts == [
        (0, 9, "walking to Cafe @ T:Cafe:counter"),
        (10, 29, "eating breakfast @ T:Cafe:counter"),
        (30, 39, "walking to Library @ T:Library:spot"),
        (40, 59, "shelving books @ T:Library:spot"),
    ]


def test_build_evidence_finds_the_shared_conversation():
    evidence = build_evidence(make_replay())
    ada = evidence["Ada"]
    assert len(ada.conversations) == 1
    conv = ada.conversations[0]
    assert conv.start == 12 and conv.end == 20
    assert sorted(conv.participants) == ["Ada", "Bea"]
    assert conv.transcript == CHAT
    # The same conversation shows up on Bea's side too.
    assert evidence["Bea"].conversations == ada.conversations


def test_build_evidence_collects_decision_frames_with_retrieved_memories():
    evidence = build_evidence(make_replay())
    ada = evidence["Ada"]
    assert len(ada.retrievals) == 1
    r = ada.retrievals[0]
    assert r["step"] == 10
    assert r["act"].startswith("eating breakfast")
    assert r["memories"][0]["text"].startswith("Plan: go to Cafe")


# ------------------------------------------------------------ heuristic judge


def test_heuristic_scores_the_coherent_fixture_high():
    report = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    ada = report["agents"]["Ada"]
    for dim in DIMENSIONS:
        entry = ada["dimensions"][dim]
        assert entry["score"] >= 7, f"{dim} scored {entry['score']}"
        # Every dimension cites at least one concrete step example.
        assert entry["evidence"], f"{dim} cited no evidence"
        assert any("step" in line for line in entry["evidence"])
    assert report["agents"]["Ada"]["overall"] >= 7
    assert report["summary"]["overall"] >= 7


def test_heuristic_social_grounding_is_na_without_conversations():
    replay = make_replay()
    for frame in replay["frames"]:
        for entry in frame.values():
            entry["chat"] = None
    report = audit(replay, judge=HeuristicJudge(), source="fixture")
    entry = report["agents"]["Ada"]["dimensions"]["social_grounding"]
    assert entry["score"] is None
    assert "no conversations" in entry["note"].lower()
    # An n/a dimension is excluded from the means, not counted as zero.
    assert report["agents"]["Ada"]["overall"] >= 7


def test_scrambled_frames_score_measurably_worse():
    """The issue's acceptance control: a shuffled run must lose points."""
    replay = make_replay()
    judge = HeuristicJudge()  # deterministic, so the comparison is exact
    intact = audit(replay, judge=judge, source="fixture")
    control = audit(
        scramble_replay(replay, "frames", seed=7), judge=judge, source="control"
    )
    assert intact["summary"]["overall"] - control["summary"]["overall"] >= 1.0


def test_swapped_plans_score_worse_on_plan_coherence():
    replay = make_replay()
    judge = HeuristicJudge()
    intact = audit(replay, judge=judge, source="fixture")
    control = audit(
        scramble_replay(replay, "plans", seed=0), judge=judge, source="control"
    )
    drop = (
        intact["summary"]["by_dimension"]["plan_coherence"]
        - control["summary"]["by_dimension"]["plan_coherence"]
    )
    assert drop >= 1.0
    assert intact["summary"]["overall"] > control["summary"]["overall"]


# ------------------------------------------------------------ the LLM judge

GRADE = {
    "plan_coherence": {
        "score": 9,
        "evidence": ["steps 10-29: breakfast at the Cafe, exactly as planned"],
        "note": "clean plan",
    },
    "temporal_sanity": {"score": 8, "evidence": ["steps 40-59: afternoon stop"]},
    "social_grounding": {"score": 7, "evidence": ["steps 12-20: cafe chat"]},
    "memory_use": {"score": 6, "evidence": ["step 10: plan memory retrieved"]},
}


def _scripted_client(reply=GRADE):
    from text_adventure_games.llm_client import MockLlmClient

    return MockLlmClient(tool_responses=lambda messages, tool, mt, temp: reply)


def test_llm_judge_scores_from_the_model_and_bills_the_ledger():
    client = _scripted_client()
    client.ledger.max_cost_usd = 0.50  # the spend ceiling (acceptance c)
    judge = LlmJudge(client)
    report = audit(make_replay(), judge=judge, source="fixture")
    ada = report["agents"]["Ada"]["dimensions"]
    assert ada["plan_coherence"]["score"] == 9.0
    assert ada["plan_coherence"]["evidence"] == GRADE["plan_coherence"]["evidence"]
    assert ada["plan_coherence"]["note"] == "clean plan"
    assert ada["memory_use"]["score"] == 6.0
    # One judge call per agent, every one recorded in the ledger.
    assert len(client.tool_calls) == 2
    assert report["judge"]["kind"] == "llm"
    assert report["judge"]["calls"] == 2
    assert report["judge"]["cost_usd"] == 0.0  # the mock is free
    assert report["judge"]["max_cost_usd"] == 0.50
    # The judge call asks for the pinned rubric tool.
    assert client.tool_calls[0]["tool"]["name"] == "grade_believability"


def test_llm_judge_falls_back_to_the_heuristic_on_a_malformed_reply():
    client = _scripted_client(reply=None)  # model declined / malformed
    report = audit(make_replay(), judge=LlmJudge(client), source="fixture")
    baseline = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    ada = report["agents"]["Ada"]["dimensions"]
    for dim in DIMENSIONS:
        assert (
            ada[dim]["score"] == baseline["agents"]["Ada"]["dimensions"][dim]["score"]
        )
        assert "heuristic" in ada[dim]["note"]


def test_llm_judge_stops_calling_once_the_ledger_ceiling_is_hit():
    client = _scripted_client()
    client.ledger.max_cost_usd = 0.0  # already over budget: spend nothing
    report = audit(make_replay(), judge=LlmJudge(client), source="fixture")
    assert client.tool_calls == []  # no model calls fired at all
    ada = report["agents"]["Ada"]["dimensions"]
    for dim in DIMENSIONS:
        assert ada[dim]["score"] is not None  # heuristic still scored it
        assert "budget" in ada[dim]["note"]


def test_llm_judge_clamps_scores_and_repairs_partial_replies():
    reply = dict(GRADE, plan_coherence={"score": 99, "evidence": ["steps 0-9"]})
    del reply["memory_use"]  # one dimension missing entirely
    report = audit(
        make_replay(), judge=LlmJudge(_scripted_client(reply)), source="fixture"
    )
    ada = report["agents"]["Ada"]["dimensions"]
    assert ada["plan_coherence"]["score"] == 10.0  # clamped into 1-10
    assert ada["memory_use"]["score"] is not None  # heuristic filled the gap
    assert "heuristic" in ada["memory_use"]["note"]


# ------------------------------------------------------------ the judge prompt


def test_rubric_prompt_renders_exactly():
    from backend.prompt_templates import render

    text = render("believability_rubric", evidence="AGENT DIGEST HERE")
    assert text == (
        "You are auditing one simulated agent's recorded day for believability.\n"
        "Judge only what the record shows; be strict.\n"
        "\n"
        "AGENT DIGEST HERE\n"
        "\n"
        "Grade each dimension from 1 (broken) to 10 (fully believable), citing\n"
        "step ranges from the timeline as evidence:\n"
        "\n"
        "- plan_coherence: the agent's actions matched its plan, or deviated for\n"
        "  a reason visible in the timeline or memories.\n"
        "- temporal_sanity: activities suit the sim clock and the schedule's\n"
        "  timing.\n"
        "- social_grounding: conversation lines reference real shared context\n"
        "  from both participants' memory streams, not confabulation.\n"
        "- memory_use: the memories retrieved for each decision were relevant\n"
        "  to the decision made.\n"
        "\n"
        "Call grade_believability once, with all four dimensions."
    )


def test_evidence_text_digests_the_run_for_the_judge():
    evidence = build_evidence(make_replay())
    text = evidence_text(evidence["Ada"], evidence)
    assert "Agent: Ada" in text
    assert "eating breakfast" in text  # schedule + timeline
    assert "steps 10-29" in text  # collapsed segments, step-cited
    assert "This cafe makes a great breakfast." in text  # the transcript
    assert "Plan: go to Cafe" in text  # plan memories + retrievals


# ------------------------------------------------------------ the CLI


def test_cli_writes_a_markdown_report(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)  # heuristic-only path
    replay_path = tmp_path / "penn_replay.json"
    replay_path.write_text(json.dumps(make_replay()), encoding="utf-8")
    out = tmp_path / "report.md"
    assert main([str(replay_path), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "# Believability audit" in text
    assert "## Ada" in text and "## Bea" in text  # per-agent sections
    assert "Plan coherence" in text
    assert "Run summary" in text


def test_cli_scramble_flag_and_json_format(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    replay_path = tmp_path / "penn_replay.json"
    replay_path.write_text(json.dumps(make_replay()), encoding="utf-8")
    out = tmp_path / "report.json"
    code = main(
        [
            str(replay_path),
            "--out",
            str(out),
            "--format",
            "json",
            "--scramble",
            "frames",
            "--seed",
            "7",
        ]
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["run"]["scramble"] == "frames"
    assert set(report["agents"]) == {"Ada", "Bea"}
    # The scrambled control scores worse than the intact run (acceptance b).
    intact = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    assert report["summary"]["overall"] < intact["summary"]["overall"]


def test_cli_uses_the_mock_provider_offline(tmp_path, monkeypatch):
    # LLM_PROVIDER=mock: real client plumbing, zero spend, no keys -- the
    # mock declines the tool call, so every agent falls back to heuristic,
    # and the judge spend block still lands in the report from the ledger.
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    replay_path = tmp_path / "penn_replay.json"
    replay_path.write_text(json.dumps(make_replay()), encoding="utf-8")
    out = tmp_path / "report.json"
    assert main([str(replay_path), "--out", str(out), "--format", "json"]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["judge"]["kind"] == "llm"
    assert report["judge"]["provider"] == "mock"  # named even without a config
    assert report["judge"]["cost_usd"] == 0.0
    assert report["judge"]["max_cost_usd"] == 1.0  # the default ceiling
    assert report["summary"]["overall"] is not None
