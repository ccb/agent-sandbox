"""Walkthrough emitter: a sibling test file that plays a winning sequence.

The pipeline writes ``<game>_walkthrough.py`` next to the generated module.
The file is runnable two ways:
  * ``uv run python generated/<game>_walkthrough.py`` -- as a script (asserts).
  * ``uv run pytest generated/<game>_walkthrough.py`` -- as a single test.

The same module is also imported and executed in-process during extraction
(see ``codegen.extract.validate_walkthrough``) so a broken win path fails
the codegen pipeline rather than reaching the user.
"""

from __future__ import annotations

from ._common import q as _q


def emit_walkthrough(spec, module_filename: str) -> str:
    """Render the walkthrough test module for a spec.

    ``module_filename`` is the bare filename of the emitted game module
    (e.g. ``flaming_goat.py``) -- used in an ``importlib.util.spec_from_file_location``
    call relative to the walkthrough file's own directory.
    """
    wt = spec.walkthrough
    if wt is None or not wt.commands:
        raise ValueError("emit_walkthrough requires a non-empty walkthrough")

    commands_repr = "[\n" + "".join(f"    {_q(cmd)},\n" for cmd in wt.commands) + "]"

    module_stem = module_filename.removesuffix(".py")
    expects_win = "True" if wt.expects_win else "False"

    lines = [
        f'"""Auto-generated walkthrough for {spec.game_name!r}.',
        "",
        "Plays a winning command sequence through the generated module and",
        f"asserts that ``game.is_won() == {expects_win}``. This file is the",
        "extractor's own self-test -- if it fails, the LLM spec drifted from",
        "the source rules.",
        "",
        "Run as a script:",
        f"    uv run python <this file>",
        "or via pytest:",
        f"    uv run pytest <this file>",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import importlib.util",
        "from pathlib import Path",
        "",
        f"WALKTHROUGH = {commands_repr}",
        f"EXPECTS_WIN = {expects_win}",
        f"MODULE_FILENAME = {_q(module_filename)}",
        f"MODULE_STEM = {_q(module_stem)}",
        "",
        "",
        "def _load_game_module():",
        "    here = Path(__file__).resolve().parent",
        "    path = here / MODULE_FILENAME",
        "    spec = importlib.util.spec_from_file_location(MODULE_STEM, path)",
        "    mod = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(mod)",
        "    return mod",
        "",
        "",
        "def run_walkthrough():",
        '    """Play the sequence and return (game, per-command results)."""',
        "    mod = _load_game_module()",
        "    game = mod.build_game()",
        "    results = []",
        "    for cmd in WALKTHROUGH:",
        "        ok = game.do_command(cmd)",
        "        results.append((cmd, ok))",
        "        if game.is_game_over():",
        "            break",
        "    return game, results",
        "",
        "",
        "def test_walkthrough_wins():",
        "    game, results = run_walkthrough()",
        "    if EXPECTS_WIN:",
        "        assert game.is_won() is True, (",
        '            f"walkthrough did not win; last command results: {results[-5:]}"',
        "        )",
        "    else:",
        '        assert not game.is_won(), "walkthrough unexpectedly won"',
        "",
        "",
        'if __name__ == "__main__":',
        "    test_walkthrough_wins()",
        '    print("walkthrough OK")',
        "",
    ]
    return "\n".join(lines)
