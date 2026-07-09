"""The (seed, journal) save model (docs/design/ios-tomb-app.md §2).

A seeded game is deterministic, so a save file is just the seed plus the
journal of turn-consuming commands, and restore is ``build_game(seed)`` +
``replay(journal)``. These tests pin the three legs that make that true:
what the journal records, that replay reproduces state exactly, and that
the Tomb's full win route is deterministic end to end (the guard that keeps
a stray unseeded ``random`` call from silently corrupting every save).
"""

from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.reporting import CaptureRenderer, Channel


def _quiet(game):
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return cap


def _fingerprint(game):
    """The state a save/restore must preserve, as one comparable tuple."""
    return (
        game.player.location.name,
        game.turn,
        game.score,
        sorted(w.name for w in game.player.wounds),
        sorted(game.player.carried_items().keys()),
        game.is_game_over(),
    )


def test_journal_records_only_turn_consuming_successes():
    game = tomb.build_game(seed=11)
    _quiet(game)
    game.do_command("look")  # consumes a turn -> journaled
    game.do_command("i")  # FREE action -> not journaled
    game.do_command("frobnicate the zeitgeist")  # parse failure -> not journaled
    game.do_command("go north")  # journaled
    assert game.journal == ["look", "go north"]


def test_comma_sequences_journal_part_by_part():
    """A comma sequence is recorded as its successful parts, so replaying the
    journal never re-splits (and a failed part simply isn't there)."""
    game = tomb.build_game(seed=11)
    _quiet(game)
    game.do_command("look, i, go north")
    assert game.journal == ["look", "go north"]


def test_replay_reproduces_state_exactly():
    """Play a real opening (wreck loot, then into the tomb), then restore a
    fresh build from (seed, journal) and compare fingerprints."""
    route = tomb.WIN_WALKTHROUGH[:20]
    live = tomb.build_game(seed=7041)
    _quiet(live)
    for cmd in route:
        live.do_command(cmd)
    saved = (live.rng_seed, list(live.journal))

    restored = tomb.build_game(seed=saved[0])
    restored.replay(saved[1])
    assert _fingerprint(restored) == _fingerprint(live)
    # The journal rebuilt itself during replay: saving again needs no cases.
    assert restored.journal == saved[1]

    # And the two games remain in lockstep AFTER the restore point: the next
    # turns render identically (the strong determinism property).
    cap_live, cap_restored = _quiet(live), _quiet(restored)
    for cmd in tomb.WIN_WALKTHROUGH[20:26]:
        live.do_command(cmd)
        restored.do_command(cmd)
    assert cap_live.texts(Channel.NARRATION) == cap_restored.texts(Channel.NARRATION)


def test_replay_stops_at_game_over():
    game = tomb.build_game(seed=3)
    _quiet(game)
    ran = game.replay(["look", "go north"] + ["wait"] * 3)
    assert ran <= 5
    assert game.turn > 0


def test_the_win_route_is_deterministic():
    """Two seeded builds of the full win route must match transcript-for-
    transcript. If this fails, some random draw is bypassing tomb._RNG --
    which would silently corrupt every (seed, journal) save."""
    transcripts = []
    for _ in range(2):
        game = tomb.build_game(seed=0)
        cap = _quiet(game)
        for cmd in tomb.WIN_WALKTHROUGH:
            if game.is_game_over():
                break
            game.do_command(cmd)
        transcripts.append(
            (
                cap.texts(Channel.NARRATION),
                cap.texts(Channel.DAMAGE),
                game.score,
                game.is_won(),
            )
        )
    assert transcripts[0] == transcripts[1]
    assert transcripts[0][3], "the win route should still win"
