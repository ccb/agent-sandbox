"""Tests for the cassette layer and determinism harness (reproducible-runs).

Three things are exercised here:

  A. ``RecordingClient`` / ``ReplayClient`` round-trip -- recording with a
     ``MockLlmClient`` as the wrapped "inner" client, then replaying offline.
  B. ``seed_world`` -- pinning the engine's only RNG (the rose action).
  C. The headline contract: record a real Action Castle run, replay it, and get
     a byte-identical final world state.

Run with pytest::

    pytest tests/test_recording.py -v
"""

import json

import pytest

from notebooks.hw1_llm import build_llm_game
from text_adventure_games.llm_client import LlmClient, MockLlmClient, MockReActClient
from text_adventure_games.recording import (
    CassetteMiss,
    RecordingClient,
    ReplayClient,
    request_key,
    seed_world,
)
from text_adventure_games.scenario import play, prop

# ----------------------------------------------------------------------
# Section A: cassette record / replay
# ----------------------------------------------------------------------


def test_record_then_replay_serves_same_responses(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    inner = MockLlmClient(["one", "two"], default="DONE")
    rec = RecordingClient(inner, cassette)
    msgs1 = [{"role": "user", "content": "a"}]
    msgs2 = [{"role": "user", "content": "b"}]
    msgs3 = [{"role": "user", "content": "c"}]
    assert rec.chat(msgs1) == "one"
    assert rec.chat(msgs2) == "two"
    assert rec.chat(msgs3) == "DONE"
    rec.close()

    replay = ReplayClient(cassette)
    # Same requests -> same recorded responses, in order, with no inner client.
    assert replay.chat(msgs1) == "one"
    assert replay.chat(msgs2) == "two"
    assert replay.chat(msgs3) == "DONE"


def test_recording_is_transparent_to_the_caller(tmp_path):
    """A RecordingClient returns exactly what the wrapped client returns, and
    the call still reaches the inner client (recorded in its ``calls``)."""
    cassette = str(tmp_path / "run.jsonl")
    inner = MockLlmClient(["hello"])
    rec = RecordingClient(inner, cassette)
    msgs = [{"role": "user", "content": "hi"}]
    assert rec.chat(msgs) == "hello"
    assert inner.calls[0]["messages"] == msgs  # the call passed through
    rec.close()


def test_recorded_none_round_trips_as_a_hit(tmp_path):
    """A model failure (``None``) is a real recorded answer, not a cassette miss."""
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(lambda m, mt, t: None), cassette)
    msgs = [{"role": "user", "content": "fail please"}]
    assert rec.chat(msgs) is None
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    # Strict, yet this does NOT raise: None is a hit, served straight back.
    assert replay.chat(msgs) is None


def test_strict_miss_raises_and_lenient_returns_none(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(["x"]), cassette)
    rec.chat([{"role": "user", "content": "recorded"}])
    rec.close()

    unseen = [{"role": "user", "content": "never recorded"}]
    assert ReplayClient(cassette, strict=False).chat(unseen) is None
    with pytest.raises(CassetteMiss):
        ReplayClient(cassette, strict=True).chat(unseen)


def test_over_consuming_a_key_is_a_miss(tmp_path):
    """A request recorded once can be served once; a second identical request
    is over-consumption -- the replayed run diverged -- so it's a miss."""
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(["only-once"]), cassette)
    msgs = [{"role": "user", "content": "same"}]
    rec.chat(msgs)
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    assert replay.chat(msgs) == "only-once"
    with pytest.raises(CassetteMiss):
        replay.chat(msgs)


def test_identical_requests_replay_in_recorded_order(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    inner = MockLlmClient(["first", "second"])
    rec = RecordingClient(inner, cassette)
    msgs = [{"role": "user", "content": "same"}]
    rec.chat(msgs)
    rec.chat(msgs)  # identical request, different recorded response
    rec.close()

    replay = ReplayClient(cassette)
    assert replay.chat(msgs) == "first"
    assert replay.chat(msgs) == "second"


def test_clients_satisfy_the_llm_protocol(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(["x"]), cassette)
    rec.chat([{"role": "user", "content": "a"}])
    rec.close()
    replay = ReplayClient(cassette)
    assert isinstance(rec, LlmClient)
    assert isinstance(replay, LlmClient)
    # count_tokens: RecordingClient delegates; ReplayClient uses a heuristic.
    assert rec.count_tokens("hello") == MockLlmClient(["x"]).count_tokens("hello")
    assert replay.count_tokens("abcd") == 1


def test_request_key_is_stable_and_param_sensitive():
    msgs = [{"role": "user", "content": "hi"}]
    assert request_key(msgs, 256, 0.0) == request_key(msgs, 256, 0.0)
    assert request_key(msgs, 256, 0.0) != request_key(msgs, 256, 0.7)
    assert request_key(msgs, 256, 0.0) != request_key(msgs, 128, 0.0)


# ----------------------------------------------------------------------
# Section B: engine determinism (seed_world)
# ----------------------------------------------------------------------


def _smell_the_rose_scent():
    """Build Action Castle, pick and smell the rose, return its random scent."""
    game = build_llm_game(MockReActClient())
    play(game, ["go out", "pick rose", "smell rose"])
    return prop(game, "rose", "scent")


def test_seed_world_makes_rose_scent_reproducible():
    seed_world(0)
    first = _smell_the_rose_scent()
    seed_world(0)
    second = _smell_the_rose_scent()
    assert first and isinstance(first, str)  # a scent was chosen
    assert first == second  # ... and seeding reproduces it exactly


# ----------------------------------------------------------------------
# Section C: the headline contract -- record, replay, byte-identical state
# ----------------------------------------------------------------------

FEED_TROLL = [
    "get pole",
    "go out",
    "go south",
    "catch fish with pole",
    "go north",
    "go north",
    "go east",
    "give fish to troll",
]


def _canonical(primitive):
    """A canonical string for a world snapshot, order-independent."""
    return json.dumps(primitive, sort_keys=True)


def test_record_then_replay_is_byte_identical(tmp_path):
    cassette = str(tmp_path / "action_castle.jsonl")

    # Record: a real run through the mock-driven Action Castle, RNG seeded.
    seed_world(0)
    client = RecordingClient(MockReActClient(), cassette)
    recorded = build_llm_game(client)
    play(recorded, FEED_TROLL)
    client.close()

    # Replay: same seed, same commands, responses served from the cassette --
    # no MockReActClient in sight.
    seed_world(0)
    replayed = build_llm_game(ReplayClient(cassette, strict=True))
    play(replayed, FEED_TROLL)

    assert _canonical(recorded.to_primitive()) == _canonical(replayed.to_primitive())
