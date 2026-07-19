"""Offline smoke for the #595 experiment harness: it runs end-to-end under the
scripted brain (no key), the outcome classifier is exercised, and a report is
produced. The research CLAIM (rate above control) is a manual, keyed run -- not
asserted here. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.cognition import attach_agents  # noqa: E402
from backend.penn.experiments.boil_from_memory import (  # noqa: E402
    _AVERSION,
    _RETRIEVAL,
    _configure,
    classify_outcome,
    run_arm,
)
from backend.penn.scripted_brain import build_scripted_brains  # noqa: E402
from penn_world import WORLD_DATA_BOIL, build_penn_world  # noqa: E402


class _C:
    def __init__(self, **props):
        self._p = props

    def get_property(self, k):
        return self._p.get(k, False)


def test_classify_outcome_reads_the_authoritative_flags():
    assert classify_outcome(_C(drank_safe=1, drank_unboiled=0)) == "boiled_then_drank"
    assert classify_outcome(_C(drank_unboiled=1)) == "drank_raw"
    assert classify_outcome(_C()) == "neither"


def test_run_arm_smoke_with_scripted_brain():
    # A single scripted trial runs the whole harness plumbing offline.
    result = run_arm(
        seeded=True,
        trials=1,
        steps=20,
        make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
    )
    assert set(result) >= {"boiled_then_drank", "drank_raw", "neither", "rate"}
    assert result["boiled_then_drank"] + result["drank_raw"] + result["neither"] == 1


def test_seeded_aversion_is_retrieved_at_the_water_decision():
    # The #595 prerequisite: the seeded memory must actually reach the decide
    # prompt near the water, or the live brain can't reason from it.
    from backend.run_simulation import simulate
    from penn_world import WORLD_DATA_BOIL, build_penn_world

    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    personas = _configure(pw.personas, seeded=True)
    captured = {}

    def build_capture(world_map):
        game, chars = pw.build_world_fn(world_map)
        captured.update(chars)
        return game, chars

    simulate(
        pw.world_map,
        40,
        personas=personas,
        build_world_fn=build_capture,
        llm_client=build_scripted_brains()[0],
    )
    agent = captured[personas[0]["name"]].agent
    # By the end of a Houston-centred run the aversion has surfaced at least once.
    assert any(
        "violently ill" in r.text for r in agent.last_retrieved
    ), "seeded aversion never retrieved -- raise its importance or tag it"


def test_importance_forward_retrieval_rescues_a_buried_seed_633():
    """As the memory stream grows (a frequently-deciding live brain), the
    default recency-heavy profile buries the importance-5 aversion; the
    experiment's importance-forward `_RETRIEVAL` surfaces it. Pinned against the
    real Houston decide observation so it tracks the actual query, not a proxy.
    """
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    game, chars = pw.build_world_fn(pw.world_map)
    personas = _configure(pw.personas, seeded=True)
    attach_agents(chars, personas)
    ch = chars[personas[0]["name"]]
    mem = ch.agent.memory
    # A dense stream of fresh same-place memories, as a live brain deciding
    # often would accrue over the run.
    for t in range(1, 81):
        mem.add_observation(
            "settling in at the union before dinner at Houston Hall",
            turn=t,
            importance=2.0,
        )
    game.turn = 80
    query = game.describe_for(ch)  # the exact string observe_and_decide retrieves on

    def surfaced(**kw):
        recs = mem.retrieve(query, turn=80, touch=False, **kw)
        return any(_AVERSION[:25] in r.text for r in recs)

    assert not surfaced(), "default retrieval should bury the seed at this density"
    assert surfaced(
        max_records=_RETRIEVAL.max_records,
        decay=_RETRIEVAL.recency_decay,
        alpha_recency=_RETRIEVAL.alpha_recency,
        alpha_importance=_RETRIEVAL.alpha_importance,
        alpha_relevance=_RETRIEVAL.alpha_relevance,
    ), "importance-forward retrieval should surface the seed"


def test_stop_when_ends_the_run_early_676():
    """simulate() breaks as soon as the stop_when predicate is truthy, so the
    boil experiment stops paying for idle live decides once the outcome latches.
    The deciding step's frame is still recorded."""
    from backend.run_simulation import simulate

    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    personas = _configure(pw.personas, seeded=False)
    captured = {}

    def cap(wm):
        game, chars = pw.build_world_fn(wm)
        captured.update(chars)
        return game, chars

    calls = {"n": 0}

    def stop_after_third(_game):
        calls["n"] += 1
        return calls["n"] >= 3

    frames = simulate(
        pw.world_map,
        50,
        personas=personas,
        build_world_fn=cap,
        llm_client=build_scripted_brains()[0],
        stop_when=stop_after_third,
    )
    assert len(frames) == 3  # stopped at the third step, not all 50
