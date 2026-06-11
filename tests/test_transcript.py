"""Tests for the run transcript and provenance records (reproducible-runs).

Two parts:

  A. The data records -- ``StepRecord`` / ``RunRecord`` round-trip through their
     primitive form and save/load as JSON and YAML (the human-readable run file).
  B. Capture -- attaching a ``TranscriptRecorder`` to a game makes the ReAct loop
     record one ``StepRecord`` per agent attempt, with the route outcome.

Run with pytest::

    pytest tests/test_transcript.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import LLMAgent, ScriptedAgent, react_behavior
from text_adventure_games.transcript import (
    RunRecord,
    StepRecord,
    TranscriptRecorder,
    file_sha256,
    git_sha,
    record_step,
)


@pytest.fixture
def tiny_game():
    """A small, isolated 2-room world: Field --north--> Forest, with a troll."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def _step(**overrides):
    """A fully-populated StepRecord for round-trip tests."""
    fields = dict(
        turn=2,
        actor="troll",
        observation="You are on a drawbridge...",
        system_prompt="You are an NPC...",
        raw_response="Reasoning: hungry\nAction: eat fish",
        reasoning="hungry",
        command="eat fish",
        route_ok=True,
        fail_reason=None,
        world_delta={},
    )
    fields.update(overrides)
    return StepRecord(**fields)


# ----------------------------------------------------------------------
# Section A: the records
# ----------------------------------------------------------------------


def test_steprecord_round_trips():
    step = _step()
    assert StepRecord.from_primitive(step.to_primitive()) == step


def test_runrecord_round_trips():
    run = RunRecord(
        game="action_castle.build_game",
        seed=0,
        cassette={"path": "run.jsonl", "sha256": "abc123"},
        engine_version="deadbee",
        steps=[_step(turn=1, route_ok=False, fail_reason="no weapon"), _step(turn=2)],
        result={"goal": "troll_fed", "success": True},
    )
    assert RunRecord.from_primitive(run.to_primitive()) == run


def test_runrecord_save_load_json(tmp_path):
    path = str(tmp_path / "run.json")
    run = RunRecord(game="g", seed=7, engine_version="v1", steps=[_step()])
    run.save(path)
    assert RunRecord.load(path) == run


def test_runrecord_save_load_yaml(tmp_path):
    pytest.importorskip("yaml")
    path = str(tmp_path / "run.yaml")
    run = RunRecord(game="g", seed=7, engine_version="v1", steps=[_step()])
    run.save(path)
    loaded = RunRecord.load(path)
    assert loaded == run
    # ... and it's the readable YAML a student can open.
    text = open(path, encoding="utf-8").read()
    assert "seed: 7" in text
    assert "eat fish" in text


def test_file_sha256_and_git_sha(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text("hello\n", encoding="utf-8")
    h = file_sha256(str(f))
    assert isinstance(h, str) and len(h) == 64
    assert file_sha256(str(f)) == h  # stable
    assert isinstance(git_sha(), str)  # best-effort, never raises


# ----------------------------------------------------------------------
# Section B: capture in the ReAct loop
# ----------------------------------------------------------------------


def test_record_step_is_a_noop_without_a_recorder():
    class Bare:  # no `transcript` attribute
        pass

    record_step(Bare(), turn=0, actor="x")  # must not raise


def test_no_recorder_attached_by_default(tiny_game):
    assert tiny_game.transcript is None


def test_transcript_captures_a_successful_step(tiny_game):
    game = tiny_game
    game.transcript = TranscriptRecorder()
    troll = game.characters["troll"]
    react_behavior(troll, game, ScriptedAgent(lambda obs: "look"))

    assert len(game.transcript.steps) == 1
    step = game.transcript.steps[0]
    assert step.actor == "troll"
    assert step.turn == game.turn
    assert step.command == "look"
    assert step.route_ok is True
    assert step.fail_reason is None
    assert step.raw_response == "look"  # ScriptedAgent has no separate raw reply
    assert "FIELD" in step.observation  # the observation the agent saw


def test_transcript_captures_failure_then_retry(tiny_game):
    game = tiny_game
    game.transcript = TranscriptRecorder()
    troll = game.characters["troll"]

    # "go south" has no exit from the Field -> precondition fails; the reflect
    # observation contains 'failed', so the retry picks a valid command.
    def rule(obs):
        return "look" if "failed" in obs else "go south"

    react_behavior(troll, game, ScriptedAgent(rule), max_retries=1)

    steps = game.transcript.steps
    assert len(steps) == 2
    assert steps[0].command == "go south"
    assert steps[0].route_ok is False
    assert steps[0].fail_reason  # a reason was captured
    assert steps[1].command == "look"
    assert steps[1].route_ok is True


def test_transcript_records_prompt_and_reasoning_for_llm_agent(tiny_game):
    game = tiny_game
    game.transcript = TranscriptRecorder()
    troll = game.characters["troll"]
    client = MockLlmClient(["Reasoning: I keep watch.\nAction: look"])
    react_behavior(troll, game, LLMAgent(client, persona="a watchful troll"))

    step = game.transcript.steps[0]
    assert "You are an NPC" in step.system_prompt
    assert "a watchful troll" in step.system_prompt
    assert step.reasoning == "I keep watch."
    assert step.command == "look"
    assert step.raw_response == "Reasoning: I keep watch.\nAction: look"
