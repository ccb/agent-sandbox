"""Co-settled pair-steps (issue #795).

The metric that makes a socially dead run visible. A co-settled pair-step
is one step in which two agents are both settled -- `performing and not
path` -- and share a location. Counted BEFORE the cooldown/busy filters:
this measures opportunity, not eligibility, which is what makes the
issue's 399-vs-0 comparison meaningful.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.run_simulation import count_co_settled  # noqa: E402


class FakeChar:
    def __init__(self, location):
        self.location = location


def _state(**kw):
    base = {"performing": False, "path": [], "conversing": False}
    base.update(kw)
    return base


def test_two_settled_agents_in_one_room_count():
    hall = object()
    chars = {"A": FakeChar(hall), "B": FakeChar(hall)}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(chars, state, ["A", "B"]) == [("A", "B")]


def test_a_walking_agent_does_not_count():
    hall = object()
    chars = {"A": FakeChar(hall), "B": FakeChar(hall)}
    state = {
        "A": _state(performing=True),
        "B": _state(performing=True, path=[(1, 1)]),
    }
    assert count_co_settled(chars, state, ["A", "B"]) == []


def test_different_rooms_do_not_count():
    chars = {"A": FakeChar(object()), "B": FakeChar(object())}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(chars, state, ["A", "B"]) == []


def test_a_conversing_pair_still_counts():
    """Opportunity, not eligibility -- a pair mid-conversation is co-settled."""
    hall = object()
    chars = {"A": FakeChar(hall), "B": FakeChar(hall)}
    state = {
        "A": _state(performing=True, conversing=True),
        "B": _state(performing=True, conversing=True),
    }
    assert count_co_settled(chars, state, ["A", "B"]) == [("A", "B")]


def test_a_locationless_agent_never_pairs():
    """char.location can be None; two Nones are not 'the same room'."""
    chars = {"A": FakeChar(None), "B": FakeChar(None)}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(chars, state, ["A", "B"]) == []


def test_pairs_come_back_in_order_order():
    hall = object()
    names = ["C", "A", "B"]
    chars = {n: FakeChar(hall) for n in names}
    state = {n: _state(performing=True) for n in names}
    assert count_co_settled(chars, state, names) == [("C", "A"), ("C", "B"), ("A", "B")]
