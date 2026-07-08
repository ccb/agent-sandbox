"""The Infocom trio (SAVE/RESTORE/SCRIPT) over (seed, journal) saves.

Builds on tests/test_journal_replay.py's determinism guarantees: here we test
the player-facing commands, the stores, the staged-restore contract
(``pending_restore``), and the version-drift guard.
"""

from text_adventure_games import saves
from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game(seed=5):
    game = tomb.build_game(seed=seed)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.save_store = saves.MemorySaveStore()
    return game, cap


def _fingerprint(game):
    return (
        game.player.location.name,
        game.turn,
        game.score,
        sorted(w.name for w in game.player.wounds),
        sorted(game.player.carried_items().keys()),
    )


def test_save_is_free_and_unjournaled():
    game, _ = _game()
    game.do_command("look")
    turn, journal = game.turn, list(game.journal)
    game.do_command("save 1")
    assert game.turn == turn  # writing the log down costs no turn
    assert game.journal == journal  # and is not itself part of the log
    assert game.save_store.read("1")["commands"] == journal


def test_bare_save_lists_slots():
    game, cap = _game()
    game.do_command("save 2")
    game.do_command("save")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "2:" in out and "(empty)" in out


def test_save_rejects_unknown_slot():
    game, cap = _game()
    game.do_command("save 9")
    assert game.save_store.read("9") is None
    assert any("No such position" in t for t in cap.texts(Channel.BLOCKED))


def test_no_store_fails_politely():
    game, cap = _game()
    game.save_store = None
    game.do_command("save 1")
    assert any("nowhere here" in t for t in cap.texts(Channel.BLOCKED))


def test_restore_stages_the_blob_for_the_owning_loop():
    game, cap = _game()
    game.do_command("go north")
    game.do_command("save 1")
    blob = game.save_store.read("1")
    game.do_command("restore 1")
    assert game.pending_restore == blob  # staged, not performed in-place
    assert any("Restoring position 1" in t for t in cap.texts(Channel.NARRATION))


def test_restore_empty_slot_fails():
    game, cap = _game()
    game.do_command("restore 3")
    assert any("empty" in t for t in cap.texts(Channel.BLOCKED))
    assert getattr(game, "pending_restore", None) is None


def test_save_then_restore_round_trip():
    """The full contract: play, save, play on (and get hurt), then rebuild
    from the blob -- the restored game matches the save point exactly."""
    game, _ = _game(seed=7041)
    for cmd in tomb.WIN_WALKTHROUGH[:20]:
        game.do_command(cmd)
    game.do_command("save 1")
    at_save = _fingerprint(game)
    for cmd in tomb.WIN_WALKTHROUGH[20:26]:
        game.do_command(cmd)  # the world moves on past the save point
    assert _fingerprint(game) != at_save

    restored, drift = saves.restore(tomb.build_game, game.save_store.read("1"))
    assert not drift
    assert _fingerprint(restored) == at_save


def test_drift_guard_flags_a_stale_save():
    """A save whose fingerprint no longer matches the replay is flagged, not
    silently resumed (the honest failure when game content changes)."""
    game, _ = _game(seed=9)
    game.do_command("look")
    blob = saves.snapshot(game)
    blob["meta"]["room"] = "A Room Renamed Since"
    _, drift = saves.restore(tomb.build_game, blob)
    assert drift


def test_script_prints_the_expedition_log():
    game, cap = _game()
    game.do_command("look")
    game.do_command("go north")
    game.do_command("script")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "> look" in out and "> go north" in out
    assert game.journal == ["look", "go north"]  # SCRIPT itself unjournaled


def test_file_save_store_round_trips(tmp_path):
    store = saves.FileSaveStore(str(tmp_path / "slots.json"))
    game, _ = _game()
    game.save_store = store
    game.do_command("look")
    game.do_command("save 2")
    assert store.read("2")["commands"] == ["look"]
    assert "2" in store.list()
    fresh = saves.FileSaveStore(str(tmp_path / "slots.json"))
    assert fresh.read("2") == store.read("2")
