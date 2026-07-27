"""Co-settled pair-steps (issue #795).

The metric that makes a socially dead run visible. A co-settled pair-step is
one step in which two agents are both settled -- `performing and not path` --
AND within earshot of each other under the game's `audience_for` seam, i.e.
`conversation.can_converse`: the exact predicate `find_conversation_pairs`
uses. Counted BEFORE the cooldown/busy filters: this measures opportunity, not
eligibility, which is what makes the issue's 399-vs-0 comparison meaningful.

The earshot half is not decoration. "Penn campus" is a single outdoor hub
Location spanning the whole map, so a `location is location` test would score
two agents idling hundreds of tiles apart as co-settled -- a still-dead run
reporting healthy opportunity. `penn_world` overrides `audience_for` with
`perceivable_locations` + `can_perceive`; the hub test below pins that
`count_co_settled` honours such an override rather than going around it.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.run_simulation import count_co_settled  # noqa: E402


class FakeChar:
    def __init__(self, location, name="", tile=(0, 0)):
        self.name = name
        self.location = location
        self.tile = tile
        self.agent = object()  # can_converse needs a decision-maker on both
        if location is not None:
            location.characters[name] = self

    def get_property(self, key):
        return False  # not dead


class FakeLocation:
    """A room. Characters register themselves into `characters` on construction."""

    def __init__(self):
        self.characters = {}


class RoomGame:
    """The engine's default audibility: everyone in the speaker's room."""

    @staticmethod
    def audience_for(speaker, message, target=None):
        loc = speaker.location
        if loc is None:
            return []
        return [c for c in loc.characters.values() if c is not speaker]


class ProximityGame:
    """`penn_world`'s shape: same room AND within `vision_r` Chebyshev tiles."""

    vision_r = 8

    @classmethod
    def audience_for(cls, speaker, message, target=None):
        loc = speaker.location
        if loc is None:
            return []
        return [
            c
            for c in loc.characters.values()
            if c is not speaker and cls._gap(speaker, c) <= cls.vision_r
        ]

    @staticmethod
    def _gap(a, b):
        return max(abs(a.tile[0] - b.tile[0]), abs(a.tile[1] - b.tile[1]))


def _state(**kw):
    base = {"performing": False, "path": [], "conversing": False}
    base.update(kw)
    return base


def test_two_settled_agents_in_one_room_count():
    hall = FakeLocation()
    chars = {"A": FakeChar(hall, "A"), "B": FakeChar(hall, "B")}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(RoomGame, chars, state, ["A", "B"]) == [("A", "B")]


def test_a_walking_agent_does_not_count():
    hall = FakeLocation()
    chars = {"A": FakeChar(hall, "A"), "B": FakeChar(hall, "B")}
    state = {
        "A": _state(performing=True),
        "B": _state(performing=True, path=[(1, 1)]),
    }
    assert count_co_settled(RoomGame, chars, state, ["A", "B"]) == []


def test_different_rooms_do_not_count():
    chars = {"A": FakeChar(FakeLocation(), "A"), "B": FakeChar(FakeLocation(), "B")}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(RoomGame, chars, state, ["A", "B"]) == []


def test_a_conversing_pair_still_counts():
    """Opportunity, not eligibility -- a pair mid-conversation is co-settled."""
    hall = FakeLocation()
    chars = {"A": FakeChar(hall, "A"), "B": FakeChar(hall, "B")}
    state = {
        "A": _state(performing=True, conversing=True),
        "B": _state(performing=True, conversing=True),
    }
    assert count_co_settled(RoomGame, chars, state, ["A", "B"]) == [("A", "B")]


def test_a_locationless_agent_never_pairs():
    """char.location can be None; two Nones are not 'the same room'."""
    chars = {"A": FakeChar(None, "A"), "B": FakeChar(None, "B")}
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(RoomGame, chars, state, ["A", "B"]) == []


def test_pairs_come_back_in_order_order():
    hall = FakeLocation()
    names = ["C", "A", "B"]
    chars = {n: FakeChar(hall, n) for n in names}
    state = {n: _state(performing=True) for n in names}
    assert count_co_settled(RoomGame, chars, state, names) == [
        ("C", "A"),
        ("C", "B"),
        ("A", "B"),
    ]


def test_opposite_ends_of_one_hub_do_not_count():
    """The Penn case: one huge outdoor hub, two agents that can never converse.

    Same Location, both settled -- but 200 tiles apart, far outside vision_r.
    `maybe_converse` would never pair them, so neither may this."""
    campus = FakeLocation()
    chars = {
        "A": FakeChar(campus, "A", tile=(10, 10)),
        "B": FakeChar(campus, "B", tile=(210, 10)),
    }
    state = {"A": _state(performing=True), "B": _state(performing=True)}
    assert count_co_settled(ProximityGame, chars, state, ["A", "B"]) == []
    # ...and the same pair, same hub, standing together, does count -- so the
    # test above is proving the range gate, not a broken fixture.
    chars["B"].tile = (14, 10)
    assert count_co_settled(ProximityGame, chars, state, ["A", "B"]) == [("A", "B")]
