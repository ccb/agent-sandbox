"""LLM-driven GameSpec extraction.

Takes a list of ``ColorTaggedPage`` (from ``pdf_ingest``) plus an LLM client
and returns a validated ``GameSpec``. The LLM is the only stage that may
fail in a way the pipeline can't deterministically recover from; this
module is the only place we tolerate that risk.

Failure handling:
  * LLM returns no content                -> raise ExtractionError
  * LLM returns invalid JSON              -> raise ExtractionError
  * Spec fails validation                 -> one retry with the error list
                                              appended; if still invalid,
                                              raise ExtractionError
  * Validation passes, walkthrough fails  -> one retry with the failing
                                              command and the parser's
                                              fail message appended; if it
                                              still fails, raise
                                              WalkthroughCheckFailed (which
                                              carries the spec so callers
                                              can keep going for debugging)
  * Validation + walkthrough pass         -> return the GameSpec
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .prompts import (
    SOLUTION_OUTLINE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_solution_outline_user_prompt,
    build_user_prompt,
)
from .spec import GameSpec, lint, validate

if TYPE_CHECKING:
    from .pdf_ingest import ColorTaggedPage
    from ..llm_client import LlmClient


class ExtractionError(RuntimeError):
    """Raised when extraction can't produce a valid GameSpec."""


class ExtractionPartial(ExtractionError):
    """Extraction failed, but a usable spec is attached for debugging.

    The CLI catches this so the spec JSON and the emitted Python module are
    still written to disk -- you get to hand-fix whatever the LLM couldn't.
    Subclasses describe the specific failure mode (walkthrough, retry parse,
    retry validation).
    """

    def __init__(
        self,
        message: str,
        spec: GameSpec | None = None,
        raw_response: str | None = None,
    ):
        super().__init__(message)
        self.spec = spec
        self.raw_response = raw_response


class WalkthroughCheckFailed(ExtractionPartial):
    """The retried spec validates, but the walkthrough self-check still
    doesn't reach the win condition. :attr:`spec` is the retry's spec."""


class RetryUnusable(ExtractionPartial):
    """The retry response was unparseable or failed validation, so we fall
    back to the first attempt's spec (attached as :attr:`spec`). Usually
    fired when the LLM returned non-JSON prose or an empty body."""


class WalkthroughFailure(RuntimeError):
    """Raised internally when the post-emit walkthrough fails.

    Carries the failing command (or sentinel ``None``), the parser's last
    fail message, and a short list of (command, success) tuples leading up
    to the failure so the retry prompt can be specific about what went
    wrong.
    """

    def __init__(
        self,
        failing_command: str | None,
        fail_message: str | None,
        trace: list[tuple[str, bool]],
        won: bool,
    ):
        self.failing_command = failing_command
        self.fail_message = fail_message
        self.trace = trace
        self.won = won
        super().__init__(
            f"walkthrough failed at {failing_command!r}: "
            f"{fail_message or 'no message'}"
        )


def extract_spec(
    pages: "list[ColorTaggedPage]",
    game_name: str,
    llm_client: "LlmClient | None" = None,
    max_tokens: int = 12000,
    run_walkthrough: bool = True,
    solution_outline: bool = True,
    max_retries: int = 2,
) -> GameSpec:
    """Run an extraction attempt and iteratively retry while it's not clean.

    A round is "not clean" if any of:
      1. ``validate(spec)`` returns errors,
      2. ``lint(spec)`` returns warnings,
      3. the walkthrough does not reach the win condition (skipped when
         ``run_walkthrough=False``).

    Each retry's user message includes the failures from the *previous*
    round, so the LLM iteratively edits its own spec rather than
    regenerating from scratch. The loop is bounded by ``max_retries``
    (default 2, i.e. up to 3 total attempts). When the budget is
    exhausted with structural problems remaining, an
    :class:`ExtractionPartial` subclass is raised with the latest
    parseable spec attached so callers (the CLI) can still emit it.
    Lint-only failures after the budget are returned, not raised --
    they're advisory.

    ``solution_outline=True`` (default) runs a small pre-pass that asks the
    model to write a short solution outline first; the outline is then
    fed into the main extraction prompt as a constraint. Off for unit
    tests that count LLM calls.
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    if llm_client is None:
        from ..llm_client import client_from_env

        llm_client = client_from_env()
        if llm_client is None:
            raise ExtractionError("no LLM client supplied and LLM_PROVIDER is not set")

    pages_text = _format_pages(pages)

    outline_text: str | None = None
    if solution_outline:
        outline_text = _request_solution_outline(
            llm_client, game_name, pages_text, max_tokens=max_tokens
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(game_name, pages_text, outline_text),
        },
    ]

    # The most recent parseable spec across all rounds. Used as the
    # fallback payload when a later round produces unusable JSON.
    last_good_spec: GameSpec | None = None
    errors: list[str] = []
    warnings: list[str] = []
    walk_fail: WalkthroughFailure | None = None

    for round_num in range(max_retries + 1):
        response = llm_client.chat(messages, max_tokens=max_tokens, temperature=0.0)

        try:
            spec = _parse_to_spec(response, llm_client)
        except ExtractionError as exc:
            # First attempt with no fallback: bubble the bare error so the
            # caller sees the underlying parse / empty-response reason.
            if last_good_spec is None:
                raise
            raise RetryUnusable(
                f"retry {round_num} response could not be parsed ({exc}). "
                "Falling back to the previous round's spec for debugging.",
                spec=last_good_spec,
                raw_response=response,
            ) from exc

        last_good_spec = spec
        errors = validate(spec)
        warnings = [] if errors else lint(spec)
        walk_fail = None
        if not errors and not warnings and run_walkthrough:
            walk_fail = _try_walkthrough(spec)
        if not errors and not warnings and walk_fail is None:
            return spec

        if round_num >= max_retries:
            break

        # Prepare the next round: append this attempt's assistant turn and
        # the iterative-edit retry message that lists what to fix.
        retry_text = _build_retry_message(errors, warnings, walk_fail)
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": retry_text})

    # Budget exhausted with something still wrong. Decide which kind of
    # partial-extraction to raise, attaching the latest spec for debugging.
    assert last_good_spec is not None  # guaranteed: at least one parseable round
    if errors:
        raise RetryUnusable(
            f"spec still has validation errors after {max_retries} "
            f"retr{'y' if max_retries == 1 else 'ies'}:\n  - "
            + "\n  - ".join(errors)
            + "\nFalling back to the latest spec for debugging.",
            spec=last_good_spec,
        )
    if walk_fail is not None:
        trace_repr = "\n      ".join(
            f"{i + 1}. {cmd!r} -> {'OK' if ok else 'FAIL'}"
            for i, (cmd, ok) in enumerate(walk_fail.trace[-8:])
        )
        raise WalkthroughCheckFailed(
            f"walkthrough still fails after {max_retries} "
            f"retr{'y' if max_retries == 1 else 'ies'}. Last commands:\n"
            f"      {trace_repr}\n"
            f"    Last failure: {walk_fail.fail_message!r} on command "
            f"{walk_fail.failing_command!r}.",
            spec=last_good_spec,
        )
    # Lint-only warnings remain. Those are advisory, so return the spec
    # and let the CLI surface the warnings for the user to inspect.
    return last_good_spec


def _try_walkthrough(spec: GameSpec) -> WalkthroughFailure | None:
    """Emit the spec to a temp file, import it, and play the walkthrough.

    Returns ``None`` on success (or when the spec has no walkthrough), or a
    :class:`WalkthroughFailure` describing what went wrong. Catches all
    runtime exceptions from the generated module (we treat them like a
    walkthrough failure -- the LLM has another chance to fix the spec).
    """
    wt = spec.walkthrough
    if wt is None or not wt.commands:
        # No walkthrough provided. Treat as a lint-style failure so the
        # retry prompt asks the LLM to add one; first pass through, it's
        # already been warned.
        return WalkthroughFailure(
            failing_command=None,
            fail_message=(
                "spec has no `walkthrough` field. Add one: "
                '{"commands": [<command-string>, ...]} that wins the game.'
            ),
            trace=[],
            won=False,
        )
    from .emit import emit_module

    try:
        source = emit_module(spec)
    except Exception as exc:  # noqa: BLE001 -- treat emit error as walkthrough failure
        return WalkthroughFailure(
            failing_command=None,
            fail_message=f"emit_module raised {type(exc).__name__}: {exc}",
            trace=[],
            won=False,
        )
    with tempfile.TemporaryDirectory(prefix="codegen_walkthrough_") as tmp:
        path = Path(tmp) / "generated_game.py"
        path.write_text(source)
        try:
            mod_spec = importlib.util.spec_from_file_location("generated_game", path)
            mod = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(mod)
            game = mod.build_game()
        except Exception as exc:  # noqa: BLE001
            return WalkthroughFailure(
                failing_command=None,
                fail_message=f"import/build raised {type(exc).__name__}: {exc}",
                trace=[],
                won=False,
            )
        trace: list[tuple[str, bool]] = []
        last_fail: str | None = None
        for cmd in wt.commands:
            try:
                ok = bool(game.do_command(cmd))
            except Exception as exc:  # noqa: BLE001
                trace.append((cmd, False))
                return WalkthroughFailure(
                    failing_command=cmd,
                    fail_message=(f"do_command raised {type(exc).__name__}: {exc}"),
                    trace=trace,
                    won=False,
                )
            trace.append((cmd, ok))
            if not ok:
                last_fail = getattr(game.parser, "last_fail_message", None)
            if game.is_game_over():
                break
        won = bool(game.is_won())
        if wt.expects_win and not won:
            return WalkthroughFailure(
                failing_command=trace[-1][0] if trace else None,
                fail_message=(
                    last_fail or "walkthrough ran to completion without winning"
                ),
                trace=trace,
                won=won,
            )
        if not wt.expects_win and won:
            return WalkthroughFailure(
                failing_command=None,
                fail_message="walkthrough won but expects_win=false",
                trace=trace,
                won=won,
            )
    return None


def _build_retry_message(
    errors: list[str],
    warnings: list[str],
    walk_fail: "WalkthroughFailure | None" = None,
) -> str:
    lines: list[str] = [
        "MODIFY the JSON spec you just returned. Do NOT regenerate from "
        "scratch -- the prior assistant turn already contains the spec, and "
        "most of it is correct. Make the minimum edits needed to fix the "
        "issues below; preserve every other location, item, character, "
        "block, custom_action, and walkthrough command unchanged.",
        "",
    ]
    if errors:
        lines.append("Validation errors (fix all of these):")
        lines.extend(f"  - {e}" for e in errors)
    if warnings:
        if errors:
            lines.append("")
        lines.append("Lint warnings (likely-broken gameplay; fix them):")
        lines.extend(f"  - {w}" for w in warnings)
    if walk_fail is not None:
        if errors or warnings:
            lines.append("")
        if walk_fail.failing_command is None and not walk_fail.trace:
            lines.append(walk_fail.fail_message or "walkthrough check failed.")
        else:
            lines.append(
                "Walkthrough did NOT reach the win condition when played "
                "against the emitted module:"
            )
            for i, (cmd, ok) in enumerate(walk_fail.trace[-10:]):
                lines.append(f"  {i + 1}. {cmd!r} -> {'OK' if ok else 'FAILED'}")
            if walk_fail.failing_command is not None:
                lines.append(f"  First failing command: {walk_fail.failing_command!r}")
            if walk_fail.fail_message:
                lines.append(f"  Parser said: {walk_fail.fail_message!r}")
            lines.append(
                "Edit ONLY what is needed to make this sequence win. Common "
                "causes: missing custom_action for a verb the walkthrough "
                "uses; wrong direction word on an exit; missing precondition "
                "property on an item/character; the walkthrough itself skips "
                "a step. Patch either `walkthrough.commands` or the spec to "
                "make them consistent -- whichever requires fewer edits."
            )
    lines.append("")
    lines.append(
        "Return the FULL modified JSON spec (the engine re-reads the whole "
        "object). No Markdown fences. No prose outside the JSON."
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _request_solution_outline(
    llm_client, game_name: str, pages_text: str, max_tokens: int
) -> str | None:
    """Pre-pass: ask the LLM for a winning-path outline before extracting.

    The outline is plain markdown the spec-extraction prompt then quotes
    back as a constraint. Soft-fails to ``None`` on any error -- the main
    extraction is still useful without the outline, just slightly worse
    at backfilling missed pieces.
    """
    messages = [
        {"role": "system", "content": SOLUTION_OUTLINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_solution_outline_user_prompt(game_name, pages_text),
        },
    ]
    try:
        # Outline is much smaller than the full spec; cap tokens so a
        # rambling response doesn't eat the whole budget.
        response = llm_client.chat(
            messages, max_tokens=min(2000, max_tokens), temperature=0.0
        )
    except Exception:  # noqa: BLE001 -- outline is opportunistic, never fatal
        return None
    if not response or not response.strip():
        return None
    return response.strip()


def _parse_to_spec(response, llm_client=None) -> GameSpec:
    if not response:
        # Surface whatever the underlying client recorded -- empty content
        # could mean a max_tokens cutoff, a thinking-only response with no
        # text block, a network error, or an auth failure. The user can
        # diagnose only if we tell them which.
        detail = getattr(llm_client, "last_error", None) if llm_client else None
        if detail:
            raise ExtractionError(f"LLM returned no content: {detail}")
        raise ExtractionError(
            "LLM returned no content (the client gave no further detail; "
            "re-run with --verbose or set LLM_VERBOSE=1 to see the cause)"
        )
    text = _strip_markdown_fence(response.strip())
    if not text:
        raise ExtractionError(
            "LLM response was empty after stripping markdown fences. "
            f"Raw response: {_snippet(response)}"
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Some models prepend a prose preamble ("I'll analyze...") before the
        # JSON object. Locate the first `{` and let raw_decode consume only the
        # JSON body, ignoring any trailing prose.
        data = None
        start = text.find("{")
        if start != -1:
            try:
                data, _end = json.JSONDecoder().raw_decode(text[start:])
            except json.JSONDecodeError:
                data = None
        if data is None:
            raise ExtractionError(
                f"LLM response is not valid JSON: {e}. "
                f"Raw response: {_snippet(response)}"
            ) from e
    if not isinstance(data, dict):
        raise ExtractionError(
            f"LLM response JSON is not an object. Raw response: {_snippet(response)}"
        )
    return GameSpec.from_dict(data)


def _snippet(response: str, limit: int = 600) -> str:
    """Truncated, repr-escaped view of the raw LLM response for error
    messages -- enough to see whether the LLM returned prose, half a JSON,
    or nothing at all, without dumping a 4 KB blob into the traceback."""
    if response is None:
        return "None"
    response = str(response)
    if len(response) <= limit:
        return repr(response)
    return repr(response[:limit]) + f" ...[truncated, total {len(response)} chars]"


def _strip_markdown_fence(text: str) -> str:
    """Some models wrap JSON in ```json fences despite instructions; tolerate."""
    if text.startswith("```"):
        # Drop the opening fence (with or without 'json' language tag).
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _format_pages(pages: "list[ColorTaggedPage]") -> str:
    """LLM-friendly rendering of color-tagged pages.

    Uses :func:`pdf_structure.structure_pages` to rebuild the layout
    structure of each page: one location block per room heading, each with
    its description, interactions (verb header + response + rule bullets),
    and exit table. The structured shape makes the verb-to-response and
    direction-to-target pairings explicit so the LLM doesn't have to
    reconstruct them from a flat span stream (which was the root cause of
    rules getting dropped at column or page breaks).

    Anything the structuring heuristic couldn't bucket is emitted under
    ``floating_spans`` so nothing the model might need silently
    disappears.
    """
    from .pdf_structure import structure_pages

    structured = structure_pages(pages)
    blocks: list[str] = []
    for sp in structured:
        page_block: list[str] = [f"[page {sp.page_number}]"]
        for loc in sp.locations:
            page_block.append(f"  location: {loc.name!r}")
            if loc.description:
                page_block.append(f"    description: {loc.description!r}")
            if loc.underlined_nouns:
                page_block.append(f"    underlined_nouns: {loc.underlined_nouns!r}")
            for note in loc.designer_notes:
                page_block.append(f"    designer_note: {note!r}")
            if loc.interactions:
                page_block.append("    interactions:")
                for ix in loc.interactions:
                    page_block.append(f"      - verb: {ix.verb_header!r}")
                    if ix.response:
                        page_block.append(f"        response: {ix.response!r}")
                    for rule in ix.rules:
                        page_block.append(f"        rule: {rule!r}")
                    if ix.underlined_nouns:
                        page_block.append(
                            f"        underlined_nouns: {ix.underlined_nouns!r}"
                        )
            if loc.exits:
                page_block.append("    exits:")
                for ex in loc.exits:
                    page_part = (
                        f" (page {ex.target_page})"
                        if ex.target_page is not None
                        else ""
                    )
                    page_block.append(
                        f"      - direction: {ex.direction!r} -> "
                        f"target: {ex.target_name!r}{page_part}"
                    )
        for floating in sp.floating_spans:
            page_block.append(f"  floating_span: {floating}")
        blocks.append("\n".join(page_block))
    return "\n\n".join(blocks)
