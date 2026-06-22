"""Tests for the ``flavor_response`` and ``transform_item`` action templates.

These verbs cover the gap between fixed templates (unlock/wear/sit) and the
NPC dispatch verbs. ``flavor_response`` covers the "shake/punch/kick the
vending machine" pattern (verbs the source acknowledges but that do
nothing); ``transform_item`` covers the "open / shake / smash X" pattern
where the source describes a real state change on a target item.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from text_adventure_games.codegen import emit_module, load_spec

FIXTURE = Path(__file__).parent / "fixtures" / "action_castle.spec.json"


def _good_data() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


def _load(tmp_path: Path, src: str):
    path = tmp_path / "g.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location("g", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _add_machine(data: dict):
    """Drop a fake 'vending machine' into the Cottage so the action has a
    target in scope when the player is in the starting room."""
    data["items"].append(
        {
            "name": "machine",
            "description": "a battered vending machine",
            "examine_text": "Out of order.",
            "at": {"location": "Cottage"},
            "properties": {"gettable": False},
            "command_hints": [],
        }
    )


def test_flavor_response_prints_and_passes_turn(tmp_path):
    data = _good_data()
    _add_machine(data)
    data["custom_actions"].append(
        {
            "id": "shake_machine",
            "template": "flavor_response",
            "params": {
                "verb": "shake machine",
                "template_string": "You shake the {item}. It rattles.",
                "requires_in_scope": "machine",
            },
        }
    )
    # The flavor template references {item}, but flavor_response itself does
    # not bind to a specific item. Replace with a literal so the assertion
    # is unambiguous.
    data["custom_actions"][-1]["params"][
        "template_string"
    ] = "You shake the machine. It rattles weakly."
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    ok = game.do_command("shake machine")
    assert ok is True
    # Property of the machine is unchanged (no state change).
    machine = game.locations["Cottage"].items["machine"]
    assert machine.get_property("gettable") is False  # unchanged


def test_flavor_response_fails_when_item_not_in_scope(tmp_path):
    # Use a noun that doesn't contain the substring "in" or any cardinal
    # token, so the player's bare verb doesn't accidentally trigger the
    # parser's go-direction substring fallback. "vendor" is safe.
    data = _good_data()
    data["items"].append(
        {
            "name": "vendor",
            "description": "a battered vendor",
            "examine_text": "Out of order.",
            "at": {"location": "Cottage"},
            "properties": {"gettable": False},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "shake_vendor",
            "template": "flavor_response",
            "params": {
                "verb": "shake vendor",
                "template_string": "rattle.",
                "requires_in_scope": "vendor",
            },
        }
    )
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    # Move the player to a location where vendor is NOT in scope.
    game.do_command("go out")
    ok = game.do_command("shake vendor")
    assert ok is False  # preconditions failed: scope item not present


def test_transform_item_sets_properties_on_success(tmp_path):
    data = _good_data()
    _add_machine(data)
    data["items"].append(
        {
            "name": "soda",
            "description": "a can of soda",
            "examine_text": "warm soda.",
            "at": {"location": "Cottage"},
            "properties": {"is_open": False, "gettable": True},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "open_soda",
            "template": "transform_item",
            "params": {
                "verb": "open soda",
                "item": "soda",
                "template_string": "You open the soda with a hiss.",
                "sets_properties": {"is_open": True},
                "requires_in_inventory": True,
            },
        }
    )
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    # Must be in inventory; pick it up first.
    game.do_command("get soda")
    ok = game.do_command("open soda")
    assert ok is True
    soda = game.player.inventory["soda"]
    assert soda.get_property("is_open") is True


def test_transform_item_requires_inventory_fails_when_not_held(tmp_path):
    data = _good_data()
    _add_machine(data)
    data["items"].append(
        {
            "name": "soda",
            "description": "a can of soda",
            "examine_text": "",
            "at": {"location": "Cottage"},
            "properties": {"is_open": False},
            "command_hints": [],
        }
    )
    data["custom_actions"].append(
        {
            "id": "open_soda",
            "template": "transform_item",
            "params": {
                "verb": "open soda",
                "item": "soda",
                "template_string": "open.",
                "sets_properties": {"is_open": True},
                "requires_in_inventory": True,
            },
        }
    )
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    # Without picking it up first, the precondition fails.
    ok = game.do_command("open soda")
    assert ok is False
    soda = game.locations["Cottage"].items["soda"]
    assert soda.get_property("is_open") is False


def load_spec_from_dict(data: dict):
    """Tiny shim so we can build a GameSpec from a mutated good fixture."""
    from text_adventure_games.codegen.spec import GameSpec

    return GameSpec.from_dict(copy.deepcopy(data))


# --------------------------------------------------------------------------
# New declarative fields on the spec: read_text, use_responses, dialogue,
# greeting. All four route to engine built-ins (Read, Use_On, Talk_To) so the
# LLM can encode these patterns without inventing custom actions.
# --------------------------------------------------------------------------


def test_read_text_on_item_routes_to_engine_read(tmp_path):
    """An item with ``read_text`` becomes readable via the built-in Read."""
    data = _good_data()
    data["items"].append(
        {
            "name": "scroll",
            "description": "a parchment scroll",
            "examine_text": "ROLLED.",
            "at": {"location": "Cottage"},
            "properties": {},
            "command_hints": ["read scroll"],
            "read_text": "Beware the troll on the drawbridge.",
        }
    )
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    ok = game.do_command("read scroll")
    assert ok is True
    history = " ".join(e["content"] for e in game.parser.command_history)
    assert "Beware the troll" in history


def test_use_responses_on_item_route_to_engine_use_on(tmp_path):
    """``use <tool> on <item>`` fires the matching UseResponse."""
    data = _good_data()
    # Replace the lamp's properties with a use_responses entry that turns
    # an unlit-but-flammable candle into a lit one when used on the lamp.
    data["items"].append(
        {
            "name": "tinder",
            "description": "dry tinder",
            "examine_text": "",
            "at": {"location": "Cottage"},
            "properties": {},
            "command_hints": [],
            "use_responses": [
                {
                    "tool": "lamp",
                    "requires_tool_properties": {"is_lit": True},
                    "sets_target_properties": {"is_lit": True},
                    "response_text": "The tinder catches fire.",
                }
            ],
        }
    )
    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    # The player starts with the lamp; light it first, then apply.
    assert game.do_command("light lamp") is True
    ok = game.do_command("use lamp on tinder")
    assert ok is True
    tinder = game.locations["Cottage"].items["tinder"]
    assert tinder.get_property("is_lit") is True


def test_dialogue_greeting_on_character_routes_to_talk_to(tmp_path):
    """``talk to`` returns the greeting; ``ask about`` returns the topic."""
    data = _good_data()
    # The princess already exists in the gold spec; teach her some lines.
    princess = next(c for c in data["characters"] if c["name"] == "princess")
    princess["greeting"] = "Help me, brave traveler!"
    princess["dialogue"] = {"ghost": "The dungeon ghost stole my crown."}

    src = emit_module(load_spec_from_dict(data))
    mod = _load(tmp_path, src)
    game = mod.build_game()
    # Travel to the Tower where the princess is. Reuse the canonical solution
    # up through `go up` to Tower.
    commands = [
        "get pole",
        "go out",
        "go south",
        "catch fish with pole",
        "go north",
        "go north",
        "go east",
        "give fish to troll",
        "go east",
        "attack guard with branch",  # branch in inventory? No -- skip
    ]
    # Simpler: synthesize a co-located NPC test instead of replaying AC.
    # Move the princess into the Cottage so the player can talk to her
    # without traversing the whole castle.
    game = mod.build_game()
    princess_obj = game.characters["princess"]
    princess_obj.location.characters.pop("princess", None)
    cottage = game.locations["Cottage"]
    cottage.add_character(princess_obj)

    assert game.do_command("talk to princess") is True
    history = " ".join(e["content"] for e in game.parser.command_history)
    assert "Help me, brave traveler!" in history
    assert game.do_command("ask princess about ghost") is True
    history = " ".join(e["content"] for e in game.parser.command_history)
    assert "stole my crown" in history


def test_legacy_property_aliases_are_normalized():
    """Legacy keys like ``is_lightable`` map to canonical affordance names."""
    from text_adventure_games.codegen.spec import _normalize_properties

    out = _normalize_properties(
        {"is_lightable": True, "is_food": True, "is_drink": True, "is_lit": False}
    )
    assert out == {
        "flammable": True,
        "edible": True,
        "drinkable": True,
        "is_lit": False,  # state flag stays as-is
    }
