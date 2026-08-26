"""Per-run verb histogram + one-verb-ate-the-run warning (issue #811).

#795's fix made co-settlement possible -- and `talk_to` promptly became 59% of
one run's decisions while `social.co_settled_pair_steps` and
`social.conversations` both went UP. No metric flagged it: the verb mix only
existed in `tools/analyze_run.py`'s offline output. This pins the live
counterparts, plumbed exactly like the #795 social block:

* `step()` reports each decision's verb through `decide_info` (the out-param
  that already carries `deciders`/`timeouts`);
* the stepper accumulates them and `run_usage()` serves a `verbs` block beside
  `social`, so GET /usage and the frame feed carry the histogram;
* `run.yaml`'s result records it at finish;
* `_finish_run()` warns -- once, real-brain only, never on a resume -- when one
  verb took more than `VERB_MIX_WARN_SHARE` of at least
  `VERB_MIX_MIN_DECISIONS` decisions.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_verb_mix_811.py -v
"""

import sys
from pathlib import Path

from text_adventure_games.transcript import RunRecord

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); import them off the sim directory, like test_penn_live.py.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import SCRIPTED, PennStepper  # noqa: E402
from backend.run_store import RunStore  # noqa: E402

# The two-run A/B on the #760 log that opened #811: R9's mix (the degenerate
# run the warning exists to catch) and R1's (the healthy full-day baseline it
# must stay quiet on). Real numbers, so the thresholds are tested against the
# evidence they were chosen from.
R9_MIX = {"talk_to": 17, "travel": 6, "perform": 6}  # 58.6% of 29 -- warns
R1_MIX = {"talk_to": 23, "perform": 12, "travel": 10, "get": 2}  # 48.9% of 47
R7_MIX = {"perform": 10, "travel": 7, "talk_to": 1}  # 55.6% of 18 -- under floor

WARNING_PHRASE = "one verb ate the run"


def _scripted_stepper(**kwargs):
    """A stepper with a real-shaped (but free, key-free) brain: the #811
    warning is gated on `llm_client is not None`, same as #795's."""
    return PennStepper(
        num_steps=50,
        world=build_penn_world(),
        llm=SCRIPTED,
        decide_workers=0,
        **kwargs,
    )


# ------------------------------------------------------------- run_usage()


def test_run_usage_verbs_block_starts_at_zero():
    verbs = PennStepper(num_steps=2, world=build_penn_world()).run_usage()["verbs"]
    assert verbs == {"decisions": 0, "by_verb": {}, "resumed": False}


def test_run_usage_reports_the_verb_histogram():
    stepper = _scripted_stepper()
    # Drive the accumulator directly: this test is about the reporting shape
    # (total + busiest-verb-first ordering), not the counting -- exactly like
    # its #795 sibling test_run_usage_reports_the_social_block.
    stepper._verb_counts = {"travel": 6, "talk_to": 17, "perform": 6}
    verbs = stepper.run_usage()["verbs"]
    assert verbs["decisions"] == 29
    assert list(verbs["by_verb"].items()) == [
        ("talk_to", 17),
        ("travel", 6),
        ("perform", 6),
    ]


# ------------------------------------------------- counting, wire by wire


def test_tick_wires_chosen_verbs_into_the_histogram(monkeypatch):
    # Replace step() itself and check what tick() does with what step()
    # reports back -- the seam test that catches a deleted accumulator line
    # while every shape test above still passes (the #795 review lesson).
    stepper = _scripted_stepper()

    def fake_step(*args, **kwargs):
        kwargs["decide_info"]["verbs"] = ["talk_to", "travel"]
        raw = {
            name: {"movement": (0, 0), "description": "", "pronunciatio": ""}
            for name in stepper.order
        }
        return raw, 0

    monkeypatch.setattr(serve_penn, "step", fake_step)
    stepper.tick()
    stepper.tick()
    assert stepper._verb_counts == {"talk_to": 2, "travel": 2}


def test_a_mock_run_counts_real_decision_verbs():
    # End to end through the REAL step(): the free mock brain's first tick has
    # every agent decide (travel to its first stop / perform), and each of
    # those decisions must land in the histogram -- counting is bookkeeping,
    # so it runs under every brain, like the #825 co-settle counter.
    stepper = PennStepper(num_steps=4, world=build_penn_world())
    for _ in range(4):
        stepper.tick()
    assert sum(stepper._verb_counts.values()) > 0
    # Command verbs, not sentence fragments: every key is a registered verb.
    assert all(" " not in verb for verb in stepper._verb_counts)


# ------------------------------------------------------------- run.yaml


def test_run_yaml_records_the_verb_histogram(tmp_path):
    stepper = _scripted_stepper(run_store=RunStore(tmp_path / "runs"), seed=0)
    stepper._verb_counts = dict(R9_MIX)
    stepper._finish_run()
    record = RunRecord.load(str(tmp_path / "runs" / stepper._run_id / "run.yaml"))
    assert record.result["verbs"] == {"talk_to": 17, "travel": 6, "perform": 6}


# ------------------------------------------------------- the finish warning


def test_a_one_verb_run_warns_at_finish_once(capsys):
    stepper = _scripted_stepper()
    stepper._verb_counts = dict(R9_MIX)  # talk_to = 58.6% of 29
    stepper._step_idx = 1200
    stepper._co_settled_total = 862  # R9 was social -- #795 stays quiet
    stepper._finish_run()
    stepper._finish_run()  # the live loop keeps ticking a finished day
    out = capsys.readouterr().out
    assert out.count(WARNING_PHRASE) == 1
    assert "talk_to" in out


def test_a_balanced_run_does_not_warn(capsys):
    stepper = _scripted_stepper()
    stepper._verb_counts = dict(R1_MIX)  # top verb 48.9% of 47
    stepper._step_idx = 1200
    stepper._co_settled_total = 399
    stepper._finish_run()
    assert WARNING_PHRASE not in capsys.readouterr().out


def test_a_quiet_run_stays_under_the_decision_floor(capsys):
    # R7's day: 18 decisions, perform at 55.6% -- but that is three agents
    # following a schedule, not a verb eating a run. Under
    # VERB_MIX_MIN_DECISIONS the share is schedule-following noise, and R7's
    # actual failure (a silent day) is #795's warning, not this one.
    stepper = _scripted_stepper()
    stepper._verb_counts = dict(R7_MIX)
    stepper._step_idx = 1200
    stepper._co_settled_total = 12  # keep #795 out of the captured output
    stepper._finish_run()
    assert WARNING_PHRASE not in capsys.readouterr().out


def test_a_mock_run_never_warns_about_verb_mix(capsys):
    # The histogram counts under every brain, but the warning is real-brain
    # only (llm_client is not None), like #795's: a mock bake's day IS mostly
    # perform, and warning on it every bake would just be noise.
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.llm_client is None
    stepper._verb_counts = {"perform": 100, "travel": 2}
    stepper._step_idx = 1200
    stepper._finish_run()
    assert WARNING_PHRASE not in capsys.readouterr().out


def test_a_resumed_run_does_not_verb_false_alarm(capsys):
    # Same caveat as the social block: a resume restarts the accumulators at
    # 0 for this process, so the counts describe a slice of the day, not the
    # day -- a share computed over the slice could false-alarm.
    stepper = _scripted_stepper()
    stepper._verb_counts = dict(R9_MIX)
    stepper._step_idx = 1200
    stepper._co_settled_total = 862
    stepper._resumed = True
    stepper._finish_run()
    assert WARNING_PHRASE not in capsys.readouterr().out
