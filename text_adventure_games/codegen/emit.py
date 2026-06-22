"""GameSpec -> Python source emitter.

Validates the spec, dispatches each ``custom_actions`` and ``blocks`` entry
through the template registry in ``codegen/templates``, and assembles the
final module via ``templates/module.py``. Refuses to emit a spec that fails
``codegen.spec.validate``.

If ``black`` is importable the emitted source is formatted before return; a
``compile(...)`` smoke check is always run so syntax errors raise here rather
than at downstream import time.

A walkthrough sibling file is also emitted when ``spec.walkthrough`` is set:
``emit_module_to_file(spec, "generated/game.py")`` will produce both
``generated/game.py`` and ``generated/game_walkthrough.py`` (the latter is the
LLM's own self-test).
"""

from __future__ import annotations

from pathlib import Path

from .spec import GameSpec, validate
from .templates.module import emit_module as _emit_module
from .templates.walkthrough import emit_walkthrough as _emit_walkthrough


class SpecValidationError(ValueError):
    """Raised when ``emit_module`` is called on an invalid GameSpec."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("GameSpec failed validation:\n  - " + "\n  - ".join(errors))


def emit_module(spec: GameSpec, skip_validation: bool = False) -> str:
    """Return the Python source for a build_game() module.

    Raises ``SpecValidationError`` if the spec doesn't pass ``validate``,
    and ``SyntaxError`` (via ``compile``) if the emitter happens to produce
    invalid Python (a codegen bug, not a spec bug).
    """
    if not skip_validation:
        errors = validate(spec)
        if errors:
            raise SpecValidationError(errors)

    source = _emit_module(spec)

    # Run black if available -- improves diffs and catches some bugs by
    # forcing a parse. Failing to format is non-fatal; the smoke compile
    # below is the real correctness gate.
    try:
        import black

        mode = black.Mode(line_length=88)
        source = black.format_str(source, mode=mode)
    except (ImportError, Exception):  # noqa: BLE001 -- format is best-effort
        pass

    # Compile-check: a syntax error here means the emitter produced bad
    # Python from a valid spec, which is a codegen bug we want loud.
    compile(source, "<generated>", "exec")
    return source


def emit_module_to_file(
    spec: GameSpec, path: str | Path, skip_validation: bool = False
) -> Path:
    """Emit the game module to ``path``; if the spec has a walkthrough,
    also emit a sibling ``<stem>_walkthrough.py`` next to it. Returns the
    game module path written.
    """
    source = emit_module(spec, skip_validation=skip_validation)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source)
    if spec.walkthrough and spec.walkthrough.commands:
        wt_source = _emit_walkthrough(spec, p.name)
        wt_path = p.with_name(f"{p.stem}_walkthrough.py")
        wt_path.write_text(wt_source)
    return p


def emit_walkthrough_module(spec: GameSpec, module_filename: str) -> str:
    """Render the walkthrough sibling module as a string.

    ``module_filename`` is the bare filename of the emitted game module
    (e.g. ``flaming_goat.py``). Used by extract.py for the in-process
    walkthrough check.
    """
    return _emit_walkthrough(spec, module_filename)
