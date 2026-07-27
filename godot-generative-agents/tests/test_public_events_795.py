"""World-level public events (issue #795).

An agent can honestly plan around a lecture it was never privately told
about, because a lecture is announced. `events:` is that noticeboard.
"""

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.build_world import load_world_yaml  # noqa: E402
from backend.prompt_templates import render  # noqa: E402


def _world(tmp_path, events, cast_names=("Ana",)):
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    for name in cast_names:
        (personas_dir / f"{name.lower()}.yaml").write_text(
            yaml.safe_dump({"name": name, "home": "Hall", "schedule": []})
        )
    path = tmp_path / "world.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "cast": [n.lower() for n in cast_names],
                "locations": [{"name": "Hall", "address": "W:Hall:lobby"}],
                "events": events,
            }
        )
    )
    return path


def test_a_valid_event_survives_composition(tmp_path):
    path = _world(
        tmp_path, [{"label": "a lecture", "at": "Hall", "when": "this morning"}]
    )
    assert load_world_yaml(path)["events"] == [
        {"label": "a lecture", "at": "Hall", "when": "this morning"}
    ]


def test_an_unknown_place_raises(tmp_path):
    path = _world(tmp_path, [{"label": "a lecture", "at": "Nowhere", "when": "later"}])
    with pytest.raises(ValueError, match="unknown place 'Nowhere'"):
        load_world_yaml(path)


def test_a_missing_required_field_raises(tmp_path):
    path = _world(tmp_path, [{"label": "a lecture", "at": "Hall"}])
    with pytest.raises(ValueError, match="missing required field 'when'"):
        load_world_yaml(path)


def test_a_host_outside_the_active_cast_drops_the_event(tmp_path):
    """Mirrors the meetings rule: no host present, no event."""
    path = _world(
        tmp_path,
        [{"label": "a lecture", "at": "Hall", "when": "later", "host": "Bo"}],
        cast_names=("Ana", "Bo"),
    )
    assert load_world_yaml(path, cast=["ana"])["events"] == []


def test_a_host_who_is_no_persona_at_all_raises(tmp_path):
    """A typo is an authoring bug, not a parked persona -- fail loud."""
    path = _world(
        tmp_path,
        [{"label": "a lecture", "at": "Hall", "when": "later", "host": "Nobody"}],
    )
    with pytest.raises(ValueError, match="unknown host 'Nobody'"):
        load_world_yaml(path)


def test_a_world_with_no_events_key_gets_an_empty_list(tmp_path):
    path = _world(tmp_path, [])
    assert load_world_yaml(path)["events"] == []


def test_public_event_prompty_renders_exactly():
    assert render(
        "public_event",
        label="a guest lecture on gravitational waves",
        at="Irvine Auditorium",
        when="this morning",
        host="Professor Tanaka",
    ) == (
        "There's a guest lecture on gravitational waves at Irvine Auditorium "
        "this morning, hosted by Professor Tanaka. It's open to anyone."
    )


def test_public_event_prompty_without_a_host():
    assert (
        render(
            "public_event",
            label="a farmers market",
            at="College Green",
            when="all morning",
            host="",
        )
        == "There's a farmers market at College Green all morning. It's open to anyone."
    )
