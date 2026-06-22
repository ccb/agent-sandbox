"""Unit tests for GameSpec validation.

These tests poke holes in a known-good spec and assert the right error
surfaces. They run without ever invoking the emitter or the engine, so
failures here pinpoint the validator in ``codegen/spec.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from text_adventure_games.codegen.spec import GameSpec, lint, validate

FIXTURE = Path(__file__).parent / "fixtures" / "action_castle.spec.json"


def _good_data() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


def _spec(data: dict) -> GameSpec:
    return GameSpec.from_dict(data)


def test_gold_spec_has_no_validation_errors():
    assert validate(_spec(_good_data())) == []


def test_unknown_start_at_location():
    data = _good_data()
    data["start_at"] = "Atlantis"
    errors = validate(_spec(data))
    assert any("start_at" in e and "Atlantis" in e for e in errors)


def test_exit_to_unknown_location():
    data = _good_data()
    data["locations"][0]["exits"].append({"direction": "north", "to": "Mordor"})
    errors = validate(_spec(data))
    assert any("Mordor" in e for e in errors)


def test_same_location_synonym_exits_to_same_target_is_fatal():
    # Both ``up`` and ``in`` declared on Tower Stairs going to Tower.
    # Door-block is on ``up``, so ``in`` walks through the locked door.
    data = _good_data()
    for loc in data["locations"]:
        if loc["name"] == "Tower Stairs":
            loc["exits"].append({"direction": "in", "to": "Tower"})
            break
    errors = validate(_spec(data))
    assert any(
        "Tower Stairs" in e and "Tower" in e and "multiple" in e for e in errors
    ), errors


def test_flavor_response_with_movement_verb_lint_warns():
    """A flavor_response whose verb starts with a movement keyword
    (climb / enter / jump / dive / crawl / swim / walk / ride / leap /
    fly / exit) is almost always a misplaced exit -- the LLM saw a verb
    that describes how the player traverses between locations and reached
    for the wrong template. Lint must flag it so the retry prompt nudges
    the model toward an Exit on the source location."""
    data = _good_data()
    data["custom_actions"].append(
        {
            "id": "climb_tree",
            "template": "flavor_response",
            "params": {
                "verb": "climb tree",
                "template_string": "You climb the tree.",
                "at_location": "Winding Path",
            },
        }
    )
    spec = _spec(data)
    warnings = lint(spec)
    assert any(
        "climb tree" in w and "movement" in w.lower() for w in warnings
    ), warnings


def test_flavor_response_with_non_movement_verb_does_not_warn():
    """Sanity: legit flavor verbs (shake/punch/kick) are not movement and
    must NOT trip the new lint."""
    data = _good_data()
    data["items"].append(
        {
            "name": "machine",
            "description": "a vending machine",
            "examine_text": "",
            "at": {"location": "Cottage"},
            "properties": {"gettable": False},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "shake_machine",
            "template": "flavor_response",
            "params": {
                "verb": "shake machine",
                "template_string": "It rattles.",
                "requires_in_scope": "machine",
            },
        }
    )
    spec = _spec(data)
    warnings = lint(spec)
    assert not any("shake" in w and "movement" in w.lower() for w in warnings)


def test_multi_word_lock_item_warns():
    # Rename "door" -> "tower door" (item + block + action all updated).
    # ACTION_NAME becomes "unlock tower door", but "unlock door" fails to
    # match -- exactly the bug the user hit.
    data = _good_data()
    for item in data["items"]:
        if item["name"] == "door":
            item["name"] = "tower door"
    for block in data["blocks"]:
        if block.get("obstacle", {}).get("name") == "door":
            block["obstacle"]["name"] = "tower door"
    for action in data["custom_actions"]:
        if action["params"].get("lock_item") == "door":
            action["params"]["lock_item"] = "tower door"
    spec = _spec(data)
    assert validate(spec) == []  # structurally valid
    warnings = lint(spec)
    assert any("lock_item" in w and "tower door" in w for w in warnings), warnings


def test_cross_side_auto_reverse_duplicate_is_fatal():
    # Stairs declares ``up -> Tower``; Tower declares ``out -> Stairs``.
    # Engine auto-reverse turns this into Stairs.{up, in} -> Tower, which
    # bypasses any block on ``up``. Must be caught.
    data = _good_data()
    for loc in data["locations"]:
        if loc["name"] == "Tower":
            loc["exits"].append({"direction": "out", "to": "Tower Stairs"})
            break
    errors = validate(_spec(data))
    assert any(
        "Tower Stairs" in e and "Tower" in e and "multiple" in e for e in errors
    ), errors


def test_duplicate_location_name():
    data = _good_data()
    data["locations"].append({"name": "Cottage", "description": "another", "exits": []})
    errors = validate(_spec(data))
    assert any("duplicate location name" in e for e in errors)


def test_item_with_unknown_owner():
    data = _good_data()
    data["items"][0]["at"] = {"owner": "nobody"}
    errors = validate(_spec(data))
    assert any("nobody" in e for e in errors)


def test_item_with_neither_owner_nor_location():
    data = _good_data()
    data["items"][0]["at"] = {}
    errors = validate(_spec(data))
    assert any("at.location or at.owner required" in e for e in errors)


def test_character_inventory_references_undefined_item():
    data = _good_data()
    data["characters"][0]["inventory"].append("phantom")
    errors = validate(_spec(data))
    assert any("phantom" in e and "not defined in items" in e for e in errors)


def test_character_at_unknown_location():
    data = _good_data()
    data["characters"][0]["at"] = "Atlantis"
    errors = validate(_spec(data))
    assert any("Atlantis" in e for e in errors)


def test_block_with_unknown_template():
    data = _good_data()
    data["blocks"][0]["template"] = "wishful_thinking"
    errors = validate(_spec(data))
    assert any("wishful_thinking" in e for e in errors)


def test_property_block_missing_obstacle():
    data = _good_data()
    data["blocks"][0]["obstacle"] = None
    # The dataclass converts None obstacle field; provide as missing.
    del data["blocks"][0]["obstacle"]
    errors = validate(_spec(data))
    assert any("requires 'obstacle'" in e for e in errors)


def test_property_block_obstacle_references_unknown_character():
    data = _good_data()
    data["blocks"][0]["obstacle"] = {"kind": "character", "name": "phantom"}
    errors = validate(_spec(data))
    assert any("phantom" in e for e in errors)


def test_darkness_block_missing_unblocked_property():
    data = _good_data()
    for b in data["blocks"]:
        if b["template"] == "darkness_block":
            b.pop("unblocked_if_inventory_has_property", None)
    errors = validate(_spec(data))
    assert any("darkness_block requires" in e for e in errors)


def test_unknown_action_template():
    data = _good_data()
    data["custom_actions"][0]["template"] = "wish_for_it"
    errors = validate(_spec(data))
    assert any("wish_for_it" in e for e in errors)


def test_action_param_references_unknown_item():
    data = _good_data()
    for a in data["custom_actions"]:
        if a["template"] == "unlock_with_key":
            a["params"]["lock_item"] = "vapor"
    errors = validate(_spec(data))
    assert any("vapor" in e and "not a defined item" in e for e in errors)


def test_duplicate_action_name():
    data = _good_data()
    # Add a second wear_item with the same target -> same ACTION_NAME.
    data["items"].append(
        {
            "name": "crown",  # already exists; this is intentional for test
            "description": "duplicate",
            "examine_text": "",
            "at": {"location": "Cottage"},
            "properties": {},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "wear_crown_two",
            "template": "wear_item",
            "params": {
                "item": "crown",
                "required_actor_property": "is_royal",
                "set_actor_property": "is_crowned",
            },
        }
    )
    errors = validate(_spec(data))
    assert any("duplicate action name" in e for e in errors)


def test_flavor_response_requires_verb_and_template():
    data = _good_data()
    data["custom_actions"].append(
        {"id": "shake_it", "template": "flavor_response", "params": {}}
    )
    errors = validate(_spec(data))
    assert any("shake_it" in e and "verb" in e for e in errors), errors
    assert any("shake_it" in e and "template_string" in e for e in errors), errors


def test_flavor_response_unknown_in_scope_item_errors():
    data = _good_data()
    data["custom_actions"].append(
        {
            "id": "shake_vapor",
            "template": "flavor_response",
            "params": {
                "verb": "shake vapor",
                "template_string": "nothing happens.",
                "requires_in_scope": "vapor",
            },
        }
    )
    errors = validate(_spec(data))
    assert any("shake_vapor" in e and "vapor" in e for e in errors), errors


def test_transform_item_requires_item_and_sets_properties():
    data = _good_data()
    data["custom_actions"].append(
        {
            "id": "smash_it",
            "template": "transform_item",
            "params": {"verb": "smash it", "template_string": "smashed."},
        }
    )
    errors = validate(_spec(data))
    assert any("smash_it" in e and "item" in e for e in errors), errors
    assert any("smash_it" in e and "sets_properties" in e for e in errors), errors


def test_reserved_verb_collision_warns():
    # A custom verb starting with the reserved "drink" head: the engine's
    # built-in DRINK shadows it, so the custom action never fires. Lint
    # catches this before the live game does.
    data = _good_data()
    data["items"].append(
        {
            "name": "soda",
            "description": "a soda",
            "examine_text": "",
            "at": {"location": "Cottage"},
            "properties": {},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "drink_soda",
            "template": "flavor_response",
            "params": {
                "verb": "drink soda",
                "template_string": "You drink the soda.",
            },
        }
    )
    spec = _spec(data)
    assert validate(spec) == []  # structurally fine
    warnings = lint(spec)
    assert any("drink_soda" in w and "reserved" in w for w in warnings), warnings


def test_walkthrough_round_trips_through_spec():
    data = _good_data()
    spec = _spec(data)
    assert spec.walkthrough is not None
    assert spec.walkthrough.commands  # non-empty
    assert spec.walkthrough.expects_win is True


def test_win_condition_unknown_kind():
    data = _good_data()
    data["win_condition"] = {"kind": "vibes"}
    errors = validate(_spec(data))
    assert any("vibes" in e for e in errors)


def test_win_condition_player_at_unknown_location():
    data = _good_data()
    data["win_condition"] = {
        "kind": "player_at_location",
        "location": "Atlantis",
    }
    errors = validate(_spec(data))
    assert any("Atlantis" in e for e in errors)
