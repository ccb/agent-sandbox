"""The #941 carry-forward frame codec: slim on write, fatten on read.

The invariant that matters is the round-trip law — ``fatten(slim(x)) == x``
for any emitter-shaped input (every ``AGENT_FRAME_FIELDS`` key present on
every entry, the shape ``replay_frame_entry`` always produces). The viewer
renders the *fattened* frames, so this law is exactly the "the fix must not
change the simulation being viewed" requirement in test form.
"""

import copy
import json

from backend.contract import AGENT_FRAME_FIELDS
from backend.replay_codec import fatten_frames, slim_frames


def _entry(
    x=1,
    y=2,
    act="reading",
    e="📖",
    reasoning=None,
    chat=None,
    memories=None,
    trace=None,
):
    """An emitter-shaped agent entry (all 8 keys, pinned order)."""
    return {
        "x": x,
        "y": y,
        "act": act,
        "e": e,
        "reasoning": reasoning,
        "chat": chat,
        "memories": memories if memories is not None else [],
        "trace": trace if trace is not None else [],
    }


def _mem(text, importance=1.0, kind="event", created_turn=0):
    return {
        "kind": kind,
        "importance": importance,
        "text": text,
        "created_turn": created_turn,
    }


def test_round_trip_is_exact():
    """chat: null -> lines -> same lines -> explicit null -> SAME lines again.

    The re-appearance after the explicit null must survive the round trip —
    the viewer's speech-bubble trigger diffs against last-seen chat, so a
    codec that collapsed it would silently drop a conversation.
    """
    lines = [["Ada", "hello"], ["Bob", "hi"]]
    mems_a = [_mem("saw Bob", importance=1.0)]
    mems_b = [_mem("saw Bob", importance=5.0)]  # importance drift: same text, re-scored
    frames = [
        {"Ada": _entry(chat=None, memories=mems_a)},
        {"Ada": _entry(x=2, chat=lines, memories=mems_a)},
        {"Ada": _entry(x=3, chat=lines, memories=mems_a)},
        {"Ada": _entry(x=4, chat=None, memories=mems_b)},
        {"Ada": _entry(x=5, chat=lines, memories=mems_b)},
    ]
    assert fatten_frames(slim_frames(frames)) == frames


def test_fatten_is_identity_on_fat_frames():
    frames = [
        {"Ada": _entry(), "Bob": _entry(x=9)},
        {"Ada": _entry(x=2), "Bob": _entry(x=9, reasoning="hmm")},
    ]
    assert fatten_frames(frames) == frames


def test_slim_drops_unchanged_carry_fields_only():
    mems = [_mem("a")]
    frames = [
        {"Ada": _entry(memories=mems, trace=[{"d": 1}], reasoning="r", chat=None)},
        {"Ada": _entry(x=2, memories=mems, trace=[{"d": 1}], reasoning="r", chat=None)},
    ]
    slim = slim_frames(frames)
    # Frame 0 is verbatim; frame 1 keeps only the always-on fields.
    assert slim[0] == frames[0]
    assert set(slim[1]["Ada"]) == {"x", "y", "act", "e"}
    assert slim[1]["Ada"]["x"] == 2


def test_slim_preserves_pinned_key_order():
    frames = [
        {"Ada": _entry(chat=[["Ada", "hi"]])},
        {"Ada": _entry(x=2, chat=None)},  # chat changed -> emitted
    ]
    for frame in slim_frames(frames):
        keys = list(frame["Ada"].keys())
        pinned = [k for k in AGENT_FRAME_FIELDS if k in keys]
        assert keys == pinned


def test_fatten_rebuilds_pinned_key_order():
    frames = [
        {"Ada": _entry(chat=[["Ada", "hi"]])},
        {"Ada": _entry(x=2, chat=[["Ada", "hi"]])},
    ]
    for frame in fatten_frames(slim_frames(frames)):
        assert list(frame["Ada"].keys()) == list(AGENT_FRAME_FIELDS)


def test_codec_does_not_mutate_input():
    frames = [
        {"Ada": _entry(chat=[["Ada", "hi"]], memories=[_mem("m")])},
        {"Ada": _entry(x=2, chat=[["Ada", "hi"]], memories=[_mem("m")])},
    ]
    snapshot = copy.deepcopy(frames)
    slim = slim_frames(frames)
    fatten_frames(slim)
    assert frames == snapshot


def test_never_seen_keys_stay_absent():
    """Fatten is conservative: a key an agent never carried is NOT invented.

    Pre-#359 replays have no ``trace`` on any frame; fattening one must not
    change its content (readers ``.get()`` absent keys already). Once a key
    appears, it carries forward from there."""
    frames = [
        {"Ada": {"x": 1, "y": 2, "act": "idle", "e": "🙂"}},
        {"Ada": {"x": 2, "y": 2, "act": "idle", "e": "🙂", "chat": [["Ada", "hi"]]}},
        {"Ada": {"x": 3, "y": 2, "act": "idle", "e": "🙂"}},
    ]
    fat = fatten_frames(frames)
    assert "chat" not in fat[0]["Ada"] and "trace" not in fat[0]["Ada"]
    assert fat[1]["Ada"]["chat"] == [["Ada", "hi"]]
    assert fat[2]["Ada"]["chat"] == [["Ada", "hi"]]  # carried once seen
    assert "trace" not in fat[2]["Ada"]


def test_explicit_null_after_absent_key_round_trips():
    """A carry key's FIRST appearance as an explicit null must stay explicit.

    slim must not treat "previous frame had no chat key" as equal to
    ``chat: None`` — fatten never invents a value for a never-seen key, so
    dropping the null here would break the round-trip law on mixed-vintage
    frames (a run whose early rows predate a field)."""
    frames = [
        {"Ada": {"x": 1, "y": 2, "act": "idle", "e": "🙂"}},
        {"Ada": {"x": 2, "y": 2, "act": "idle", "e": "🙂", "chat": None}},
    ]
    slim = slim_frames(frames)
    assert "chat" in slim[1]["Ada"]  # explicit null survives slimming
    assert fatten_frames(slim) == frames


def test_non_dict_frame_rows_pass_through():
    """A version-skewed row degrades to pass-through (#638), never a crash —
    mirroring the gd/ts readers, which skip such rows."""
    frames = [None, {"Ada": _entry()}, "junk", {"Ada": _entry(x=2)}]
    assert slim_frames(frames)[0] is None
    assert slim_frames(frames)[2] == "junk"
    assert fatten_frames(slim_frames(frames)) == frames


def test_new_agent_mid_run_is_verbatim():
    frames = [
        {"Ada": _entry()},
        {"Ada": _entry(), "Bob": _entry(x=9, chat=[["Bob", "yo"]])},
        {"Ada": _entry(), "Bob": _entry(x=9, chat=[["Bob", "yo"]])},
    ]
    slim = slim_frames(frames)
    assert slim[1]["Bob"]["chat"] == [["Bob", "yo"]]  # first appearance: explicit
    assert "chat" not in slim[2]["Bob"]  # then carried
    assert fatten_frames(slim) == frames


def test_slim_output_validates_against_contract():
    """Slim entries (optional fields absent) still satisfy AgentFrame."""
    from backend.contract_models import AgentFrame

    frames = [
        {"Ada": _entry(chat=[["Ada", "hi"]], memories=[_mem("m")])},
        {"Ada": _entry(x=2, chat=[["Ada", "hi"]], memories=[_mem("m")])},
    ]
    for frame in slim_frames(frames):
        for entry in frame.values():
            AgentFrame.model_validate(entry)


def test_slim_size_grows_linearly_not_quadratically():
    """#941's regression guard: the fat encoding is O(steps * memories-so-far)
    because every frame re-snapshots the whole list; the slim encoding must
    scale with the number of *changes*. Doubling the step count with the same
    change cadence must not blow past ~2.5x the bytes."""

    def build(steps):
        # Model what frames actually carry: a bounded retrieval subset (the
        # ranked top-k, ~6 records in real runs), re-ranked every 10 steps —
        # NOT the whole ever-growing stream.
        frames, mems = [], []
        for i in range(steps):
            if i % 10 == 0:
                mems = ([_mem(f"memory {i}", created_turn=i)] + mems)[:6]
            frames.append({"Ada": _entry(x=i, memories=mems)})
        return frames

    small = len(json.dumps(slim_frames(build(200))))
    big = len(json.dumps(slim_frames(build(400))))
    fat_big = len(json.dumps(build(400)))
    assert big < 2.5 * small, f"slim grew superlinearly: {small} -> {big}"
    assert (
        big < fat_big / 5
    ), f"slim not materially smaller than fat: {big} vs {fat_big}"
