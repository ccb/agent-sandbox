"""Test script for NPC behaviors. Runs the game with scripted commands
and verifies NPC actions fire correctly."""

from homeworks.hw1_solution import action_castle
from text_adventure_games.webapp.web_parser import WebParser


def make_test_game():
    """Create a game with WebParser so we can inspect messages."""
    game = action_castle.build_game()
    game.set_parser(WebParser(game))
    game.parser.parse_command("look")
    game.parser.get_messages()  # drain initial messages
    return game


def run_commands(game, commands):
    """Run a list of commands, returning all messages produced by each."""
    results = []
    for cmd in commands:
        game.do_command(cmd)
        msgs = game.parser.get_messages()
        results.append({"command": cmd, "messages": msgs})
    return results


def print_results(results):
    for r in results:
        print(f"> {r['command']}")
        for msg in r["messages"]:
            tag = msg["type"]
            print(f"  [{tag}] {msg['text'][:120]}")
        print()


def test_troll_escalation():
    print("=" * 60)
    print("TEST: Troll escalation (growl → snarl → pound → attack)")
    print("=" * 60)
    game = make_test_game()
    results = run_commands(game, [
        "go out", "go north", "go east",  # navigate to drawbridge
        "wait", "wait", "wait",            # 3 escalation turns
        "wait",                            # troll attacks
    ])
    print_results(results)

    npc_msgs = [
        msg["text"]
        for r in results for msg in r["messages"]
        if msg["type"] == "npc_action"
    ]
    assert any("growl" in m.lower() for m in npc_msgs), "Missing growl"
    assert any("snarl" in m.lower() for m in npc_msgs), "Missing snarl"
    assert any("pound" in m.lower() for m in npc_msgs), "Missing pound fists"

    attack_msgs = [
        msg["text"]
        for r in results for msg in r["messages"]
        if msg["type"] == "output" and "attacked" in msg["text"]
    ]
    assert len(attack_msgs) > 0, "Troll never attacked"
    assert game.player.get_property("is_unconscious"), "Player should be unconscious"
    print("PASSED\n")


def test_troll_no_action_on_failed_command():
    print("=" * 60)
    print("TEST: NPCs don't act after failed commands")
    print("=" * 60)
    game = make_test_game()
    run_commands(game, ["go out", "go north", "go east"])
    game.parser.get_messages()  # drain

    # Type gibberish - should not trigger NPC
    game.do_command("xyzzy")
    msgs = game.parser.get_messages()
    npc_msgs = [m for m in msgs if m["type"] == "npc_action"]
    assert len(npc_msgs) == 0, f"NPC acted on failed command: {npc_msgs}"
    print("PASSED\n")


def test_troll_resets_on_leave():
    print("=" * 60)
    print("TEST: Troll resets counter when player leaves")
    print("=" * 60)
    game = make_test_game()
    run_commands(game, [
        "go out", "go north", "go east",  # at drawbridge
        "wait",                            # turn 1: growl
        "go west",                         # leave
        "go east",                         # return
        "wait",                            # should be growl again (reset)
    ])
    msgs = game.parser.get_messages()  # get all remaining

    # Count total results
    results = run_commands(game, [])
    # Let's just re-check by doing it from scratch
    game = make_test_game()
    results = run_commands(game, [
        "go out", "go north", "go east",  # at drawbridge
        "wait",                            # growl
    ])
    npc1 = [m for r in results for m in r["messages"] if m["type"] == "npc_action"]

    results2 = run_commands(game, ["go west", "go east", "wait"])
    npc2 = [m for r in results2 for m in r["messages"] if m["type"] == "npc_action"]

    # Both should be growls (counter reset)
    assert any("growl" in m["text"].lower() for m in npc1), "First visit: expected growl"
    assert any("growl" in m["text"].lower() for m in npc2), "Second visit: expected growl (reset)"
    print_results(results + results2)
    print("PASSED\n")


def test_troll_stops_when_fed():
    print("=" * 60)
    print("TEST: Troll stops acting after being fed")
    print("=" * 60)
    game = make_test_game()
    results = run_commands(game, [
        "get pole", "go out", "go south",
        "catch fish with pole",
        "go north", "go north", "go east",  # at drawbridge
        "give fish to troll",                # feed troll
        "wait",                              # should be no troll action
    ])
    print_results(results)

    # After feeding, wait should produce no NPC messages
    last = results[-1]
    npc_msgs = [m for m in last["messages"] if m["type"] == "npc_action"]
    assert len(npc_msgs) == 0, f"Troll acted after being fed: {npc_msgs}"
    assert not game.characters["troll"].get_property("is_hungry"), "Troll should not be hungry"
    print("PASSED\n")


def test_guard_escalation():
    print("=" * 60)
    print("TEST: Guard escalation (warn → threaten → threaten → attack)")
    print("=" * 60)
    game = make_test_game()
    results = run_commands(game, [
        "get pole", "go out", "go south",
        "catch fish with pole",
        "go north", "go north", "go east",
        "give fish to troll",
        "go east",                          # courtyard with guard
        "wait", "wait", "wait",             # 3 warnings
        "wait",                             # guard attacks
    ])
    print_results(results)

    npc_msgs = [
        m["text"]
        for r in results for m in r["messages"]
        if m["type"] == "npc_action"
    ]
    assert any("warn" in m.lower() for m in npc_msgs), "Missing warn"
    assert any("threaten" in m.lower() for m in npc_msgs), "Missing threaten"
    assert game.player.get_property("is_unconscious"), "Player should be unconscious"
    print("PASSED\n")


def test_ghost_two_turn_kill():
    print("=" * 60)
    print("TEST: Ghost threatens then kills in two turns")
    print("=" * 60)
    game = make_test_game()

    # Teleport to dungeon
    game.player.location.remove_character(game.player)
    dungeon = game.locations["Dungeon"]
    dungeon.add_character(game.player)
    game.player.location = dungeon

    results = run_commands(game, ["look", "wait"])
    print_results(results)

    npc_msgs = [
        m["text"]
        for r in results for m in r["messages"]
        if m["type"] == "npc_action"
    ]
    assert any("hollow eyes" in m.lower() or "haunt" in m.lower() for m in npc_msgs), "Missing haunt"
    assert any("plunge" in m.lower() or "icy hand" in m.lower() for m in npc_msgs), "Missing ghost touch"
    assert game.player.get_property("is_dead"), "Player should be dead"
    print("PASSED\n")


def test_describe_for_npc():
    print("=" * 60)
    print("TEST: game.describe_for() works for NPCs")
    print("=" * 60)
    game = make_test_game()

    troll = game.characters["troll"]
    desc = game.describe_for(troll)
    print(desc)
    print()

    assert "DRAWBRIDGE" in desc
    assert "club" in desc.lower(), "Should list troll's inventory"
    assert "Available actions:" in desc
    assert "growl" in desc, "Should list growl action"
    assert "Turn:" in desc
    print("PASSED\n")


if __name__ == "__main__":
    test_troll_escalation()
    test_troll_no_action_on_failed_command()
    test_troll_resets_on_leave()
    test_troll_stops_when_fed()
    test_guard_escalation()
    test_ghost_two_turn_kill()
    test_describe_for_npc()
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
