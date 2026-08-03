"""Tests for the cassette layer and determinism harness (reproducible-runs, #197).

  A.  RecordingClient / ReplayClient round-trip on ``chat`` -- record with a
      MockLlmClient as the wrapped "inner" client, then replay offline.
  A'. The same, on the tool seam (``call_tool`` / ``call_tools``): the paths that
      #354-#359 added AFTER PR #61 -- ToolCallResult must survive the round-trip.
  B.  seed_world -- pinning the engine's only RNG (the rose action).

The headline byte-identical contract lives in the same file, added by Task 2.

Run with pytest::

    uv run pytest tests/test_recording.py -v
"""

import json

import pytest

from text_adventure_games.adventures.react_action_castle import build_llm_game
from text_adventure_games.llm_client import (
    LlmClient,
    MockLlmClient,
    MockReActClient,
    ToolCallResult,
)
from text_adventure_games.recording import (
    CassetteMiss,
    CassetteWriter,
    RecordingClient,
    ReplayClient,
    request_key,
    seed_world,
)
from text_adventure_games.scenario import play, prop

# ----------------------------------------------------------------------
# A tiny deterministic stub that exercises the whole LlmClient Protocol.
# We hand-roll it (rather than lean on MockLlmClient's tool behavior) so the
# tool-seam tests assert an exact, known round-trip.
# ----------------------------------------------------------------------


class _ToolStub:
    """A minimal LlmClient: fixed answers for every call method."""

    def __init__(self):
        self.calls = []

    def chat(self, messages, max_tokens=256, temperature=0.0):
        self.calls.append("chat")
        return "chat-reply"

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append("call_tool")
        return {"location": "Field"}

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        self.calls.append("call_tools")
        return ToolCallResult(
            text="thinking",
            tool_calls=[
                {"id": "t1", "name": "choose_action", "arguments": {"verb": "look"}}
            ],
        )

    def count_tokens(self, text):
        return len(text)

    def preflight(self):
        return None


# ----------------------------------------------------------------------
# Section A: cassette record / replay (chat)  -- verbatim from PR #61,
# request_key calls updated for the method-tagged signature.
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
    assert replay.chat(msgs1) == "one"
    assert replay.chat(msgs2) == "two"
    assert replay.chat(msgs3) == "DONE"


def test_recording_is_transparent_to_the_caller(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    inner = MockLlmClient(["hello"])
    rec = RecordingClient(inner, cassette)
    msgs = [{"role": "user", "content": "hi"}]
    assert rec.chat(msgs) == "hello"
    assert inner.calls[0]["messages"] == msgs  # the call passed through
    rec.close()


def test_recorded_none_round_trips_as_a_hit(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(lambda m, mt, t: None), cassette)
    msgs = [{"role": "user", "content": "fail please"}]
    assert rec.chat(msgs) is None
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    assert replay.chat(msgs) is None  # None is a hit, not a miss


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
    rec.chat(msgs)
    rec.close()

    replay = ReplayClient(cassette)
    assert replay.chat(msgs) == "first"
    assert replay.chat(msgs) == "second"


def test_clients_satisfy_the_llm_protocol(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(MockLlmClient(["x"]), cassette)
    rec.chat([{"role": "user", "content": "a"}])
    # count_tokens now also writes to the cassette (#715), so it must run before
    # close() -- a RecordingClient's writer is only alive up to that point.
    assert rec.count_tokens("hello") == MockLlmClient(["x"]).count_tokens("hello")
    rec.close()
    replay = ReplayClient(cassette)
    assert isinstance(rec, LlmClient)
    assert isinstance(replay, LlmClient)
    assert replay.count_tokens("abcd") == 1


def test_request_key_is_stable_and_param_sensitive():
    msgs = [{"role": "user", "content": "hi"}]
    assert request_key("chat", msgs, 256, 0.0) == request_key("chat", msgs, 256, 0.0)
    assert request_key("chat", msgs, 256, 0.0) != request_key("chat", msgs, 256, 0.7)
    assert request_key("chat", msgs, 256, 0.0) != request_key("chat", msgs, 128, 0.0)


# ----------------------------------------------------------------------
# Section A': the tool seam (call_tool / call_tools) -- the #197 adaptation
# ----------------------------------------------------------------------


def test_request_key_distinguishes_methods_and_tools():
    msgs = [{"role": "user", "content": "hi"}]
    tools = [{"name": "choose_action"}]
    # Same messages + params, different method -> different key.
    assert request_key("chat", msgs, 256, 0.0) != request_key(
        "call_tools", msgs, 256, 0.0, tools=tools
    )
    # Different offered tools / tool_choice -> different key.
    assert request_key(
        "call_tools", msgs, 256, 0.0, tools=tools, tool_choice="auto"
    ) != request_key("call_tools", msgs, 256, 0.0, tools=tools, tool_choice="any")
    assert request_key("call_tools", msgs, 256, 0.0, tools=tools) != request_key(
        "call_tools", msgs, 256, 0.0, tools=[{"name": "other"}]
    )


def test_call_tools_result_round_trips(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    stub = _ToolStub()
    rec = RecordingClient(stub, cassette)
    msgs = [{"role": "user", "content": "act"}]
    tools = [{"name": "choose_action"}]
    recorded = rec.call_tools(msgs, tools, tool_choice="any")
    assert stub.calls == ["call_tools"]  # recording delegated to the inner client
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    served = replay.call_tools(msgs, tools, tool_choice="any")
    # Reconstructed as a real ToolCallResult, value-identical to the recording.
    assert isinstance(served, ToolCallResult)
    assert served.text == recorded.text == "thinking"
    assert served.tool_calls == recorded.tool_calls
    assert served.tool_calls[0]["name"] == "choose_action"


def test_call_tool_dict_round_trips(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    stub = _ToolStub()
    rec = RecordingClient(stub, cassette)
    msgs = [{"role": "user", "content": "where"}]
    tool = {"name": "go"}
    recorded = rec.call_tool(msgs, tool)
    assert stub.calls == ["call_tool"]  # recording delegated to the inner client
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    assert replay.call_tool(msgs, tool) == recorded == {"location": "Field"}


def test_call_tools_recorded_none_round_trips_as_a_hit(tmp_path):
    cassette = str(tmp_path / "run.jsonl")

    class _NullTools(_ToolStub):
        def call_tools(
            self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
        ):
            return None

    rec = RecordingClient(_NullTools(), cassette)
    msgs = [{"role": "user", "content": "act"}]
    tools = [{"name": "choose_action"}]
    assert rec.call_tools(msgs, tools) is None
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    assert replay.call_tools(msgs, tools) is None  # a hit, not a miss


def test_over_consuming_a_tool_key_is_a_miss(tmp_path):
    cassette = str(tmp_path / "run.jsonl")
    rec = RecordingClient(_ToolStub(), cassette)
    msgs = [{"role": "user", "content": "act"}]
    tools = [{"name": "choose_action"}]
    rec.call_tools(msgs, tools)
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    assert isinstance(replay.call_tools(msgs, tools), ToolCallResult)
    with pytest.raises(CassetteMiss):
        replay.call_tools(msgs, tools)


def test_recording_client_proxies_context(tmp_path):
    """run_tool_loop mutates client.context['round']; a wrapped run must expose
    the inner client's context so it behaves like an unwrapped one."""
    cassette = str(tmp_path / "run.jsonl")

    class _WithCtx(_ToolStub):
        def __init__(self):
            super().__init__()
            self.context = {"foo": "bar"}

    inner = _WithCtx()
    rec = RecordingClient(inner, cassette)
    assert rec.context is inner.context  # same object -> mutations land on inner
    rec.close()


def test_recording_client_registers_schedule_on_capable_inner(tmp_path):
    cassette = tmp_path / "run.jsonl"
    schedule = object()

    class _WithSchedules(_ToolStub):
        def __init__(self):
            super().__init__()
            self.schedules = {}

        def register_schedule(self, name, registered_schedule):
            self.schedules[name] = registered_schedule

    inner = _WithSchedules()
    rec = RecordingClient(inner, str(cassette))
    rec.register_schedule("Ada", schedule)
    rec.close()

    assert inner.schedules["Ada"] is schedule
    assert cassette.read_text() == ""  # configuration is not an LLM request


def test_recording_client_ignores_schedule_for_unsupported_inner(tmp_path):
    cassette = tmp_path / "run.jsonl"
    rec = RecordingClient(_ToolStub(), str(cassette))

    rec.register_schedule("Ada", object())  # paid-style clients lack the hook
    rec.close()

    assert cassette.read_text() == ""


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
    assert first and isinstance(first, str)
    assert first == second


# ----------------------------------------------------------------------
# Section C: the headline contract -- record, replay, byte-identical state.
#
# build_llm_game(MockReActClient()) wires the NPCs as LLMAgents whose client has
# call_tools, so react_behavior drives them through the native tool loop
# (npc.py:_use_tool_loop). This run therefore exercises the call_tools cassette
# path end-to-end: a chat-only recording would CassetteMiss here.
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
    """A canonical string for a world snapshot, key-order-independent."""
    return json.dumps(primitive, sort_keys=True)


def test_record_then_replay_is_byte_identical(tmp_path):
    cassette = str(tmp_path / "action_castle.jsonl")

    # Record: a real run through the mock-driven Action Castle, RNG seeded. The
    # NPCs decide via call_tools, so those calls are what land in the cassette.
    seed_world(0)
    client = RecordingClient(MockReActClient(), cassette)
    recorded = build_llm_game(client)
    play(recorded, FEED_TROLL)
    client.close()

    # Replay: same seed, same commands, responses served from the cassette --
    # no MockReActClient in sight, no network, no key.
    seed_world(0)
    replayed = build_llm_game(ReplayClient(cassette, strict=True))
    play(replayed, FEED_TROLL)

    assert _canonical(recorded.to_primitive()) == _canonical(replayed.to_primitive())


# ----------------------------------------------------------------------
# Section D: #715 extensions -- shared writer, count_tokens, lifecycle.
# ----------------------------------------------------------------------


class _CountingStub:
    """A minimal LlmClient whose count_tokens is NOT the len//4 estimate, so a
    replay that ignored the recorded value would visibly disagree."""

    context = None

    def chat(self, messages, max_tokens=256, temperature=0.0):
        return "ok"

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        return {}

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        return None

    def count_tokens(self, text):
        return 999  # deliberately not len(text)//4

    def preflight(self):
        return None


def test_shared_writer_merges_two_clients_into_one_cassette(tmp_path):
    cassette = str(tmp_path / "shared.jsonl")
    writer = CassetteWriter(cassette)
    a = RecordingClient(_CountingStub(), writer=writer)
    b = RecordingClient(_CountingStub(), writer=writer)
    assert a.chat([{"role": "user", "content": "from-a"}]) == "ok"
    assert b.chat([{"role": "user", "content": "from-b"}]) == "ok"
    writer.close()

    replay = ReplayClient(cassette, strict=True)
    # Both clients' calls replay from the one cassette.
    assert replay.chat([{"role": "user", "content": "from-a"}]) == "ok"
    assert replay.chat([{"role": "user", "content": "from-b"}]) == "ok"


def test_count_tokens_is_recorded_and_replayed(tmp_path):
    cassette = str(tmp_path / "counts.jsonl")
    rec = RecordingClient(_CountingStub(), cassette)
    assert rec.count_tokens("anything") == 999
    rec.close()

    replay = ReplayClient(cassette, strict=True)
    # Served from the recording, NOT the len//4 estimate (which would be 2).
    assert replay.count_tokens("anything") == 999
    # A text the recording never measured falls back to the estimate.
    assert replay.count_tokens("xxxxxxxx") == 2


def test_count_tokens_records_each_distinct_text_once(tmp_path):
    # The count never changes for a given text, so a repeated fact is written
    # once, not once per call (#715): otherwise a long parallel-decide day
    # grows the cassette without bound while replay only keeps the last.
    cassette = str(tmp_path / "counts.jsonl")
    rec = RecordingClient(_CountingStub(), cassette)
    for _ in range(3):
        rec.count_tokens("same")
    rec.count_tokens("other")
    rec.close()

    lines = [json.loads(line) for line in open(cassette) if line.strip()]
    counts = [line for line in lines if line.get("method") == "count_tokens"]
    assert len(counts) == 2  # "same" once + "other" once, not four lines


def test_replay_client_is_a_no_op_context_manager(tmp_path):
    cassette = str(tmp_path / "empty.jsonl")
    open(cassette, "w").close()
    with ReplayClient(cassette, strict=True) as client:
        assert client.count_tokens("") == 0
    client.close()  # idempotent, never raises
