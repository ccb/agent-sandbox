"""Roundtrip test: handwritten GameSpec -> emitted Python -> playable scenario.

This is the critical gate for the codegen pipeline. It isolates codegen
correctness from LLM-extraction correctness by hand-feeding the emitter the
gold Action Castle spec in ``tests/fixtures/action_castle.spec.json`` and
asserting that the resulting module passes the canonical winning solution.

If this test fails, the bug is in:
  * an action template emitter,
  * a block template emitter,
  * the module scaffolding, or
  * the gold spec itself (cross-check against
    ``notebooks/hw1_solution/action_castle.py``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from text_adventure_games.codegen import emit_module, load_spec
from text_adventure_games.scenario import at, blocked, has_item, play, prop

FIXTURE = Path(__file__).parent / "fixtures" / "action_castle.spec.json"


def _load_module_from_source(tmp_path: Path, source: str, name: str = "ac_gen"):
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The canonical Action Castle solution. Mirrors
# ``tests/test_scenarios.py::FEED_TROLL_COMMANDS`` and continues through the
# tower, the dungeon, and back to the throne room. Each command is a player
# turn; the NPCs act on each successful turn (sequential mode).
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

WIN_REMAINDER = [
    # Detour: branch (Top of Tree -> useful for breaking the guard)
    "go west",  # Winding Path
    "go up",  # Top of Tall Tree
    "get branch",
    "go down",  # Winding Path
    # Rose from the garden, smell it to set the scent
    "go south",  # Garden Path
    "pick rose",
    "smell rose",
    "go north",  # Winding Path
    "go east",  # Drawbridge (troll fed -- passable)
    "go east",  # Courtyard (guard here, blocks east)
    "attack guard with branch",  # branch breaks, guard drops key + sword
    "get key",
    "get sword",
    "go east",  # Great Feasting Hall
    "get candle",
    "go west",  # Courtyard
    "go up",  # Tower Stairs (door blocks up)
    "unlock door",
    "go up",  # Tower
    "give rose to princess",  # auto-smell -> princess is happy
    "propose princess",  # both married, player gains is_royal
    "go down",  # Tower Stairs
    "go down",  # Courtyard
    "light candle",
    "go down",  # Dungeon Stairs
    "go down",  # Dungeon (darkness unblocked by lit candle)
    "read runes",  # ghost banished, drops crown
    "get crown",
    "wear crown",  # player is_crowned (requires is_royal)
    "go up",  # Dungeon Stairs
    "go up",  # Courtyard
    "go east",  # Great Feasting Hall
    "go east",  # Throne Room
    "sit on throne",  # player is_reigning -> game won
]


def test_roundtrip_initial_state(tmp_path):
    """Pre-state assertions match the spec."""
    spec = load_spec(FIXTURE)
    src = emit_module(spec)
    mod = _load_module_from_source(tmp_path, src)
    game = mod.build_game()

    assert at(game, "The player", "Cottage")
    assert "lamp" in game.player.inventory
    assert blocked(game, "Drawbridge", "east")
    assert blocked(game, "Courtyard", "east")
    assert blocked(game, "Tower Stairs", "up")
    assert blocked(game, "Dungeon Stairs", "down")
    assert prop(game, "troll", "is_hungry")
    assert prop(game, "guard", "emotional_state") == "suspicious"
    assert not prop(game, "ghost", "is_banished")


def test_roundtrip_feed_troll_unblocks_drawbridge(tmp_path):
    """The motivating Action Castle scenario, on the regenerated module."""
    spec = load_spec(FIXTURE)
    src = emit_module(spec)
    mod = _load_module_from_source(tmp_path, src)
    game = mod.build_game()

    play(game, FEED_TROLL)
    assert not prop(game, "troll", "is_hungry")
    assert not blocked(game, "Drawbridge", "east")


def test_npc_only_actions_are_hidden_from_player_typing(tmp_path):
    """NPC escalation verbs (ghost touch, troll kills, etc.) must not route
    when the player types them, must not appear in `help`, but must still
    be dispatchable by the NPC turn loop (which passes an explicit actor).
    """
    spec = load_spec(FIXTURE)
    source = emit_module(spec)
    mod = _load_module_from_source(tmp_path, source)
    game = mod.build_game()

    # 1. The parser refuses to route NPC verbs typed by the player.
    npc_verbs = ["ghost touch", "troll kills", "wraith touch", "ogre attack"]
    for verb in npc_verbs:
        action_cls = game.parser.actions.get(verb)
        if action_cls is None:
            continue  # not in this game's spec; nothing to test
        assert getattr(
            action_cls, "NPC_ONLY", False
        ), f"{verb!r} should be tagged NPC_ONLY"
        # Player-typed dispatch returns None: the substring loop skips it.
        intent = game.parser.determine_intent(verb, actor=game.player)
        assert intent != verb, f"player-typed {verb!r} unexpectedly routes to itself"

    # 2. `help` output does not advertise any NPC_ONLY action.
    help_messages: list[str] = []
    original_ok = game.parser.ok
    game.parser.ok = lambda msg: help_messages.append(msg)
    try:
        game.parser.actions["help"](game, "help", actor=game.player).apply_effects()
    finally:
        game.parser.ok = original_ok
    help_text = "\n".join(help_messages)
    for verb in npc_verbs:
        if verb in game.parser.actions:
            assert (
                verb not in help_text
            ), f"`help` should not list NPC-only verb {verb!r}, got:\n{help_text}"

    # 3. NPC turn dispatch still works: pass an explicit non-player actor.
    if "ghost touch" in game.parser.actions:
        ghost = game.characters.get("ghost")
        if ghost is not None:
            intent = game.parser.determine_intent("ghost touch the player", actor=ghost)
            assert (
                intent == "ghost touch"
            ), "NPC turn dispatch should still see NPC_ONLY actions"


def test_roundtrip_full_canonical_solution_wins(tmp_path):
    """The full canonical solution drives is_won() to True."""
    spec = load_spec(FIXTURE)
    src = emit_module(spec)
    mod = _load_module_from_source(tmp_path, src)
    game = mod.build_game()

    play(game, FEED_TROLL + WIN_REMAINDER)
    assert game.is_won() is True


def test_emit_writes_walkthrough_sibling(tmp_path):
    """``emit_module_to_file`` writes both the module and the walkthrough."""
    from text_adventure_games.codegen import emit_module_to_file

    spec = load_spec(FIXTURE)
    out = tmp_path / "ac.py"
    emit_module_to_file(spec, out)
    wt = tmp_path / "ac_walkthrough.py"
    assert out.exists(), "module not emitted"
    assert wt.exists(), "walkthrough sibling not emitted"
    text = wt.read_text()
    # The walkthrough file references the game module by filename and
    # contains the run_walkthrough / test_walkthrough_wins entry points.
    assert "ac.py" in text
    assert "def run_walkthrough" in text
    assert "def test_walkthrough_wins" in text


def test_walkthrough_module_runs_and_wins(tmp_path):
    """Importing the emitted walkthrough module and calling it should win."""
    from text_adventure_games.codegen import emit_module_to_file

    spec = load_spec(FIXTURE)
    out = tmp_path / "ac.py"
    emit_module_to_file(spec, out)
    wt = tmp_path / "ac_walkthrough.py"
    wt_spec = importlib.util.spec_from_file_location("ac_walkthrough", wt)
    wt_mod = importlib.util.module_from_spec(wt_spec)
    wt_spec.loader.exec_module(wt_mod)
    game, _ = wt_mod.run_walkthrough()
    assert game.is_won() is True
