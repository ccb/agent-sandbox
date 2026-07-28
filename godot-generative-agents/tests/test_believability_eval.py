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
    _repeat_loops,
    load_replay,
    main,
    render_markdown,
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
            "locations": ["Cafe", "Gym", "Library"],
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


def test_build_evidence_merges_a_growing_conversation_into_one_window():
    # The live producer (#371) repaints the accumulated transcript onto `chat`
    # every tick, so consecutive frames carry strictly-growing prefixes of the
    # same conversation. build_evidence must not let that read as N windows (#799).
    lines = [["Ada", "Hi."], ["Bea", "Hello."], ["Ada", "Bye."]]
    frames = [
        {
            "Ada": {"x": 0, "y": 0, "act": "chatting", "chat": lines[: i + 1]},
            "Bea": {"x": 0, "y": 0, "act": "chatting", "chat": lines[: i + 1]},
        }
        for i in range(len(lines))
    ]
    replay = {
        "meta": {"personas": [{"name": "Ada"}, {"name": "Bea"}]},
        "frames": frames,
        "memory_streams": {},
    }
    evidence = build_evidence(replay)
    assert len(evidence["Ada"].conversations) == 1
    conv = evidence["Ada"].conversations[0]
    assert conv.transcript == lines
    assert (conv.start, conv.end) == (0, 2)

    # And the user-visible symptom from the issue: social_grounding's count
    # reflects one conversation, not one per tick.
    judge = HeuristicJudge()
    note = judge._social_grounding(evidence["Ada"], evidence).note
    assert note == "1 conversation(s) checked"


def test_build_evidence_collects_decision_frames_with_retrieved_memories():
    evidence = build_evidence(make_replay())
    ada = evidence["Ada"]
    assert len(ada.retrievals) == 1
    r = ada.retrievals[0]
    assert r["step"] == 10
    assert r["act"].startswith("eating breakfast")
    assert r["memories"][0]["text"].startswith("Plan: go to Cafe")


# ------------------------------------------------------------ plan coherence


def _stalled_replay():
    """Ada never leaves the Cafe: one act for the whole run, so she reaches
    stop 1 of her 2-stop schedule instead of both."""
    replay = copy.deepcopy(make_replay())
    for frame in replay["frames"]:
        frame["Ada"] = _at_entry(CAFE, "eating breakfast", "T:Cafe:counter")
    return replay


def test_plan_coherence_penalises_a_day_that_never_advances():
    """#781: standing on one stop all day used to score a perfect 10 --
    coverage asked 'matches some stop', not 'advanced through the stops'."""
    judge = HeuristicJudge()
    intact = judge._plan_coherence(build_evidence(make_replay())["Ada"])
    stalled = judge._plan_coherence(build_evidence(_stalled_replay())["Ada"])

    assert intact.score == 10.0
    assert stalled.score == 5.5
    assert "reached 1 of 2 planned stops" in stalled.note


def test_plan_progress_preserves_later_in_order_visits():
    """An early visit must not hide a later complete in-order sequence."""
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.schedule.append(
        {
            "place": "Gym",
            "activity": "lifting weights",
            "emoji": "s",
            "steps": None,
        }
    )
    judge._match_segments = lambda _ev: [2, 0, 1, 2]

    result = judge._plan_coherence(ev)

    assert result.score == 7.8
    assert "reached 3 of 3 planned stops in order" in result.note


# ------------------------------------------------------------ memory use


def test_memory_use_counts_decisions_not_repainted_frames():
    """#781: the producer repaints (act, memories) every step, so scoring each
    repaint counted one match hundreds of times."""
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    plan = [
        {
            "kind": "plan",
            "importance": 5.0,
            "text": "Plan: go to Cafe and eating breakfast.",
            "created_turn": 0,
        }
    ]
    shelving = [
        {
            "kind": "observation",
            "importance": 2.0,
            "text": "I am shelving books.",
            "created_turn": 40,
        }
    ]
    # 40 repaints of one decision, then two more decisions -- the second of
    # which retrieves a memory unrelated to what it is doing.
    ev.retrievals = [
        {
            "step": s,
            "act": "eating breakfast @ T:Cafe:counter",
            "reasoning": None,
            "memories": plan,
        }
        for s in range(40)
    ] + [
        {
            "step": 40,
            "act": "shelving books @ T:Library:spot",
            "reasoning": None,
            "memories": shelving,
        },
        {
            "step": 41,
            "act": "shelving books @ T:Library:spot",
            "reasoning": None,
            "memories": plan,
        },
    ]

    score = judge._memory_use(ev)
    assert score.note == "2/3 decisions used a relevant memory"


# ------------------------------------------------------------ social grounding


FIRST_CHAT = [
    ["Ada", "The pancakes here are excellent."],
    ["Bea", "The pancakes really are excellent."],
]
SECOND_CHAT = [
    ["Ada", "My shelving rota starts at noon."],
    ["Bea", "My weights session starts at noon."],
]


def _social_score(second_transcript):
    """Ada's social grounding when her pair's second conversation carries
    *second_transcript*. Both windows fall while Ada and Bea walk together, so
    co-location, grounding and speaker validity are identical either way and
    only novelty moves."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    windows = [_convo(1, 2, FIRST_CHAT), _convo(3, 4, second_transcript)]
    for ev in evidence.values():
        ev.conversations = list(windows)
    return judge._social_grounding(evidence["Ada"], evidence)


def test_social_grounding_penalises_a_rerun_conversation():
    """#781: the #778 loop pairs re-ran one conversation and scored 10/10."""
    fresh = _social_score(SECOND_CHAT)
    rerun = _social_score(FIRST_CHAT)

    assert fresh.score - rerun.score >= 1.0
    assert any("new to this pair" in line for line in rerun.evidence)


def test_social_grounding_scores_a_silent_agent_who_had_the_chance():
    """#781: never speaking used to mean n/a, which drops out of the mean --
    R4's silent Wesley Okafor was the top-scoring agent in the batch."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    for ev in evidence.values():
        ev.conversations = []

    score = judge._social_grounding(evidence["Ada"], evidence)
    assert score.score == 1.0
    assert "never spoke" in score.note
    assert "55%" in score.note  # Ada is within sight of Bea for 33 of 60 steps


def test_social_grounding_stays_na_for_an_agent_who_was_never_near_anyone():
    """The floor only penalises a missed opportunity, not solitude."""
    judge = HeuristicJudge()
    evidence = build_evidence(make_replay())
    for ev in evidence.values():
        ev.conversations = []
    evidence["Ada"].positions = [(500, 500)] * evidence["Ada"].n_steps

    assert judge._social_grounding(evidence["Ada"], evidence).score is None


# ------------------------------------------------------------ world grounding


def _convo(start, end, transcript, participants=("Ada", "Bea")):
    from backend.eval.believability import Conversation

    return Conversation(
        start=start, end=end, participants=list(participants), transcript=transcript
    )


def test_world_grounding_is_a_rubric_dimension():
    from backend.eval.believability import BELIEVABILITY_TOOL

    assert "world_grounding" in DIMENSIONS
    props = BELIEVABILITY_TOOL["parameters"]["properties"]
    assert "world_grounding" in props
    assert "world_grounding" in BELIEVABILITY_TOOL["parameters"]["required"]


def test_merge_growth_windows_collapses_an_accumulating_transcript():
    # The live producer (#371) appends one line per tick, so _conversations_in
    # keys every growth as its own window: one meeting looked like 23.
    from backend.eval.believability import _merge_growth_windows

    a = [["Ada", "Hi."]]
    b = [["Ada", "Hi."], ["Bea", "Hello."]]
    c = [["Ada", "Hi."], ["Bea", "Hello."], ["Ada", "Bye."]]
    merged = _merge_growth_windows([_convo(1, 1, a), _convo(2, 2, b), _convo(3, 3, c)])
    assert len(merged) == 1
    assert merged[0].transcript == c
    assert (merged[0].start, merged[0].end) == (1, 3)


def test_merge_growth_windows_collapses_two_conversations_running_at_once():
    # The producer keys `active` by pair frozenset, so two pairs can talk at the
    # same time -- fifteen personas on a campus makes that common. Their growth
    # windows then interleave in (start, end) order, so a merge that only looks
    # at the PREVIOUS window sees the other pair's fragment every time, fails
    # the participants check, and appends everything unmerged: the #799
    # overcount, back again exactly when conversations overlap.
    from backend.eval.believability import _merge_growth_windows

    ab = [["Ada", "Hi."]], [["Ada", "Hi."], ["Bea", "Hello."]]
    cd = [["Cy", "Yo."]], [["Cy", "Yo."], ["Di", "Hey."]]
    merged = _merge_growth_windows(
        [
            _convo(1, 1, ab[0], ("Ada", "Bea")),
            _convo(1, 1, cd[0], ("Cy", "Di")),
            _convo(2, 2, ab[1], ("Ada", "Bea")),
            _convo(2, 2, cd[1], ("Cy", "Di")),
        ]
    )
    assert len(merged) == 2
    by_pair = {frozenset(c.participants): c for c in merged}
    assert by_pair[frozenset(("Ada", "Bea"))].transcript == ab[1]
    assert by_pair[frozenset(("Cy", "Di"))].transcript == cd[1]
    assert all((c.start, c.end) == (1, 2) for c in merged)


def test_merge_growth_windows_keeps_a_pairs_second_meeting_separate():
    # The guard the per-pair keying must not lose: the same pair meeting AGAIN
    # later is two windows, not one grown window -- even though the key matches.
    from backend.eval.believability import _merge_growth_windows

    morning = [["Ada", "Morning."]]
    evening = [["Ada", "Evening."]]
    merged = _merge_growth_windows([_convo(1, 3, morning), _convo(400, 402, evening)])
    assert len(merged) == 2
    assert [c.transcript for c in merged] == [morning, evening]


def test_world_grounding_flags_an_invented_place_with_an_invitation():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            1,
            [
                [
                    "Ada",
                    "It's right down by the river, a ten-minute "
                    "walk through the athletic complex -- come by!",
                ]
            ],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score is not None and score.score < 5
    # Two separate assertions, each pinned to one word: the evidence lines
    # this dimension emits are built from the classified word lists
    # (`invented`/`seen`), never from the raw transcript text, so each check
    # only passes when the gazetteer actually recognized that word -- if
    # `_PLACE_NOUNS` regresses and silently drops one of them, that half
    # fails loudly instead of being masked by the other.
    assert any("river" in e for e in score.evidence)
    assert any("complex" in e for e in score.evidence)


def test_world_grounding_allows_bare_off_map_backstory():
    # A rower may talk about her boathouse; §1 of the spec permits it. Only a
    # first-hand claim or an invitation is a defect.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(1, 1, [["Ada", "I row, so I'm always rushing in from the boathouse."]])
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_does_not_flag_real_places():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(1, 1, [["Ada", "I went to the Library and then the Gym."]])
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_catches_a_cue_with_no_place_noun_in_its_window():
    # The Casey case: "Oh yeah, I totally went!" names no place, but the window
    # names the boathouse, so the claim is attributable.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "Did you ever make it down to the boathouse?"],
                ["Ada", "Oh yeah, I totally went! The light was perfect down there."],
            ],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score is not None and score.score < 10
    assert any("Ada" in e for e in score.evidence)


def test_world_grounding_evidence_distinguishes_two_claims_in_one_window():
    # Two first-hand claims about the same off-map place in one window used to
    # emit byte-identical evidence lines (the cue phrase now distinguishes
    # them), and a flagged window also got a redundant "place words seen"
    # trailer on top of its per-line findings (now suppressed).
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            1,
            [
                ["Ada", "I went to the boathouse yesterday, it was great."],
                ["Ada", "Yeah, come by the boathouse sometime!"],
            ],
        )
    ]
    ev_lines = judge._world_grounding(ev).evidence
    claims = [e for e in ev_lines if "claims first-hand experience" in e]
    assert len(claims) == 2
    assert len(set(claims)) == 2  # distinct, not duplicated
    # The cue phrase is what distinguishes them, and it never leaks a place
    # noun into the evidence: "boathouse" appears only via the classified list.
    assert "i went" in claims[0] and "come by" in claims[1]
    # A flagged window gets no redundant summary trailer.
    assert not any("place words seen" in e for e in ev_lines)


def test_world_grounding_is_none_without_conversations():
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = []
    assert judge._world_grounding(ev).score is None


def test_world_grounding_is_none_on_a_replay_baked_before_780():
    # Task 4's meta.locations is optional: a replay baked before it exists
    # must still audit, just without this one dimension.
    judge = HeuristicJudge()
    replay = make_replay()
    del replay["meta"]["locations"]
    ev = build_evidence(replay)["Ada"]
    score = judge._world_grounding(ev)
    assert score.score is None
    assert "meta.locations" in score.note


def test_world_grounding_exempts_a_real_place_invitation_beside_off_map_backstory():
    # Issue #807. Window-scoped cue matching made my partner's *allowed* boathouse
    # backstory attach to my invitation to a place that exists here. My line
    # grounds itself, so it is not a claim about her boathouse.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "I row out of the boathouse most mornings."],
                ["Ada", "Nice -- meet me at the Cafe after?"],
            ],
        )
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_evidence_reports_an_exempted_line_truthfully():
    # Issue #809. An exempted line (#807) leaves `claimed` empty, which used to
    # take the "without claiming to have been there" summary branch -- in a
    # window where the agent said "I totally went". The score is the accepted
    # #807 ceiling and must not move; the evidence has to stop asserting the
    # opposite of what happened.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "Did you ever make it down to the boathouse?"],
                ["Ada", "Oh yeah, I totally went -- way nicer than the Library."],
            ],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score == 10.0  # the #807 ceiling, unchanged
    assert not any("without claiming to have been there" in e for e in score.evidence)
    assert len(score.evidence) == 1
    exempt = score.evidence[0]
    # The cue, the off-map place the window scoping attached it to, and why the
    # line was not scored. "boathouse" comes from the classified `invented`
    # list, never the raw transcript (#780 I2), so this fails loudly if the
    # gazetteer stops recognizing it.
    assert "totally went" in exempt
    assert "boathouse" in exempt
    assert "not scored: the line names a real place and no off-map one" in exempt


def test_world_grounding_evidence_for_a_scored_claim_is_unchanged_by_809():
    # The other half of #809's acceptance: the same window with no real place in
    # Ada's line does not trip the exemption, so it stays on the path this
    # dimension exists for -- one per-line finding, no summary trailer.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "Did you ever make it down to the boathouse?"],
                ["Ada", "Oh yeah, I totally went! The light was perfect down there."],
            ],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score == 1.0
    assert score.evidence == [
        'steps 1-2 (08:01): Ada claims first-hand experience ("down there, '
        'totally went") in a window that names boathouse -- not in this world'
    ]


def test_world_grounding_exempts_a_real_place_the_verbatim_check_cannot_cover():
    # Issue #807 mutation gap: "meet me at the Cafe" (the test above) satisfies
    # BOTH halves of `_names_only_real_places` at once -- the gazetteer noun
    # "cafe" AND the verbatim meta.locations name "Cafe" -- so it doesn't pin the
    # gazetteer half alone; deleting `bool(words) or` from the predicate leaves
    # every existing test green. This case isolates it: the shipped Penn world's
    # 18 location names are proper nouns, and `_PLACE_NOUNS` carries exactly one
    # of them ("gallery", via Van Pelt -- Kamin Gallery), so "meet me at the
    # gallery" is exempt only because the gazetteer noun resolves real -- no
    # meta.locations name appears verbatim in that line.
    judge = HeuristicJudge()
    replay = make_replay()
    replay["meta"]["locations"] = ["Van Pelt — Kamin Gallery", "Houston Hall"]
    ev = build_evidence(replay)["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "I row out of the boathouse most mornings."],
                ["Ada", "Nice -- meet me at the gallery after?"],
            ],
        )
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_exempts_a_real_place_the_gazetteer_does_not_carry():
    # The half that matters on the shipped Penn world: its 18 location names are
    # proper nouns, and `_PLACE_NOUNS` carries exactly one of them ("gallery", via
    # Van Pelt -- Kamin Gallery). Exempting only gazetteer nouns would exempt
    # almost nothing there, so the line is also checked against meta.locations.
    from backend.eval.believability import _PLACE_NOUNS

    assert "library" not in _PLACE_NOUNS  # pins what makes this case distinct
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            2,
            [
                ["Bea", "I row out of the boathouse most mornings."],
                ["Ada", "Nice -- meet me at the Library after?"],
            ],
        )
    ]
    assert judge._world_grounding(ev).score == 10.0


def test_world_grounding_still_flags_a_real_and_an_invented_place_in_one_line():
    # The exemption is "names a real place AND no off-map one". Naming both is
    # still a first-hand claim about the off-map one, so it stays scored.
    judge = HeuristicJudge()
    ev = build_evidence(make_replay())["Ada"]
    ev.conversations = [
        _convo(
            1,
            1,
            [["Ada", "Meet me at the Library, then we'll walk to the boathouse!"]],
        )
    ]
    score = judge._world_grounding(ev)
    assert score.score is not None and score.score < 10
    assert any("boathouse" in e for e in score.evidence)


def test_evidence_text_lists_the_worlds_places():
    evidence = build_evidence(make_replay())
    text = evidence_text(evidence["Ada"], evidence)
    assert "Places that exist in this world: Cafe, Gym, Library" in text


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
        # Out of everyone's sight, too: since #781 a silent agent who stood
        # within vision of someone is scored rather than skipped.
        frame["Ada"]["x"], frame["Ada"]["y"] = 500, 500
    report = audit(replay, judge=HeuristicJudge(), source="fixture")
    entry = report["agents"]["Ada"]["dimensions"]["social_grounding"]
    assert entry["score"] is None
    assert "no conversations" in entry["note"].lower()
    # An n/a dimension is excluded from the means, not counted as zero.
    assert report["agents"]["Ada"]["overall"] >= 7


# ------------------------------------------------------------ run roll-up


def test_summary_names_the_weakest_agent():
    """#781: a run mean lets a broken pair hide behind a healthy majority."""
    report = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    weakest = report["summary"]["weakest"]
    scores = {n: a["overall"] for n, a in report["agents"].items()}

    assert weakest["name"] in scores
    assert weakest["score"] == min(scores.values())
    assert f"Weakest agent | {weakest['name']}" in render_markdown(report)


def test_summary_flags_a_repeat_conversation_loop():
    """#781: the #778 loop is the pathology a single score cannot express --
    three re-runs of one conversation between the same pair."""
    replay = make_replay()
    report = audit(replay, judge=HeuristicJudge(), source="fixture")
    assert report["summary"]["loops"] == []  # one conversation is not a loop

    evidence = build_evidence(replay)
    windows = [_convo(1, 2, CHAT), _convo(3, 4, CHAT), _convo(5, 6, CHAT)]
    for ev in evidence.values():
        ev.conversations = list(windows)
    loops = _repeat_loops(evidence)

    assert len(loops) == 1
    assert loops[0]["participants"] == ["Ada", "Bea"]
    assert loops[0]["conversations"] == 3
    # First window is all-new, the two re-runs add nothing: (1 + 0 + 0) / 3.
    assert loops[0]["mean_novelty"] == 0.33


def test_render_markdown_names_a_flagged_loop():
    report = audit(make_replay(), judge=HeuristicJudge(), source="fixture")
    report["summary"]["loops"] = [
        {"participants": ["Ada", "Bea"], "conversations": 8, "mean_novelty": 0.44}
    ]
    rendered = render_markdown(report)

    assert "Repeat-conversation loop" in rendered
    assert "Ada <-> Bea" in rendered
    assert "8 conversations, mean novelty 0.44" in rendered


def test_scrambled_frames_score_measurably_worse():
    """The issue's acceptance control: a shuffled run must lose points.

    Pinned tight (#781): the margin was >= 1.0 while `plan_coherence` coverage
    read 100% for everything. Re-saturating a dimension has to fail here.
    """
    replay = make_replay()
    judge = HeuristicJudge()  # deterministic, so the comparison is exact
    intact = audit(replay, judge=judge, source="fixture")
    control = audit(
        scramble_replay(replay, "frames", seed=7), judge=judge, source="control"
    )
    assert intact["summary"]["overall"] - control["summary"]["overall"] >= 2.0


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
    assert drop >= 4.0  # #781: was >= 1.0 against the saturated coverage term
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
    "world_grounding": {"score": 10, "evidence": ["no off-map places mentioned"]},
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
        # Deliberately the SAME rule the heuristic and the place_grounding
        # prompt enforce -- off-map is sayable, just not visitable. A stricter
        # judge bullet (an earlier draft also policed real-but-never-visited
        # places) would make every judge-vs-heuristic delta on this dimension
        # partly a measure of rule mismatch rather than of the run.
        "- world_grounding: the agent may mention places outside this world, but\n"
        "  never claims to have just been to one, and never invites anyone to\n"
        "  meet there.\n"
        "- memory_use: the memories retrieved for each decision were relevant\n"
        "  to the decision made.\n"
        "\n"
        "Call grade_believability once, with all five dimensions."
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


def test_cli_json_stdout_is_pure_json(tmp_path, monkeypatch, capsys):
    # The no-provider notice must land on stderr, not stdout, so a
    # `--format json | jq`-style consumer can parse stdout as-is.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    replay_path = tmp_path / "penn_replay.json"
    replay_path.write_text(json.dumps(make_replay()), encoding="utf-8")
    assert main([str(replay_path), "--format", "json"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)  # parses only if stdout is pure JSON
    assert set(report["agents"]) == {"Ada", "Bea"}
    assert "No LLM judge" in captured.err


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
