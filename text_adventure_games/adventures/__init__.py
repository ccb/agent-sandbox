"""Checked-in, runnable game instances built on the engine.

These are concrete adventures (not library code) -- import and run them, or use
them as authoring templates:

    from text_adventure_games.adventures.action_castle import build_game
    game = build_game()
    game.game_loop()

They live inside the installed package so they're importable everywhere
(notebooks, tests, the web app) without any sys.path setup.
"""
