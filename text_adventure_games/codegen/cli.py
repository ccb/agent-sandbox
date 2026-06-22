"""Command-line entry for the codegen pipeline.

Two workflows:

1. **Extract from a PDF** (live LLM)::

    uv run python -m text_adventure_games.codegen <pdf> \\
        --game "Action Castle" \\
        --out generated/action_castle.py \\
        --spec generated/action_castle.spec.json \\
        [--page-range 15-28] \\
        [--no-walkthrough] \\
        [--max-retries N]

   Reads the PDF, ingests the requested page range, extracts a
   ``GameSpec`` via the configured LLM, validates it, and emits a
   runnable Python module. Always pass ``--spec`` so the final spec is
   preserved for re-emission (workflow #2 below).

2. **Re-emit from a saved spec** (no LLM)::

    uv run python -m text_adventure_games.codegen \\
        --game "Action Castle" \\
        --out generated/action_castle.py \\
        --mock generated/action_castle.spec.json

   The positional ``pdf`` is optional when ``--mock`` is supplied. The
   pipeline reads the spec JSON, validates and lints it, then emits the
   Python module. Use this to regenerate ``.py`` after hand-editing a
   spec, or after bumping the engine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .emit import emit_module_to_file
from .extract import ExtractionPartial, extract_spec
from .pdf_ingest import game_page_ranges, ingest_pdf
from .spec import dump_spec, lint, validate


def _parse_page_range(s: str) -> tuple[int, int]:
    if "-" not in s:
        raise argparse.ArgumentTypeError("page-range must be START-END (e.g. 15-28)")
    a, b = s.split("-", 1)
    return int(a), int(b)


def _resolve_range(
    pdf_path: Path, game: str, override: tuple[int, int] | None
) -> tuple[int, int]:
    if override is not None:
        return override
    ranges = game_page_ranges(pdf_path)
    if game not in ranges:
        raise SystemExit(
            f"game {game!r} not found in PDF TOC; available: "
            f"{sorted(ranges.keys())}"
        )
    return ranges[game]


def _build_llm_client(mock_spec_path: Path | None):
    from ..llm_client import MockLlmClient, client_from_env

    if mock_spec_path is not None:
        text = Path(mock_spec_path).read_text()
        # Sanity: load to confirm it parses.
        json.loads(text)
        # Callable form: every chat() call returns the same JSON. A list
        # would be drained on the first call, leaving the validation/
        # walkthrough retry with an empty response and an opaque
        # "LLM returned no content" error.
        return MockLlmClient(responses=lambda *_a, **_k: text)
    client = client_from_env()
    if client is None:
        raise SystemExit(
            "no LLM client available -- set LLM_PROVIDER (anthropic|openai|mock) "
            "or pass --mock <path-to-spec.json>"
        )
    return client


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m text_adventure_games.codegen")
    ap.add_argument(
        "pdf",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Path to the Parsely PDF. Required for live-LLM extraction; "
            "optional (and ignored) when --mock is used to re-emit from a "
            "saved spec."
        ),
    )
    ap.add_argument(
        "--game",
        required=True,
        help="Game name as it appears in the PDF TOC (e.g. 'Action Castle').",
    )
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the generated Python module.",
    )
    ap.add_argument(
        "--spec",
        type=Path,
        default=None,
        help="Optional: also write the extracted GameSpec JSON here.",
    )
    ap.add_argument(
        "--page-range",
        type=_parse_page_range,
        default=None,
        help="Override the TOC's page range (e.g. 15-28).",
    )
    ap.add_argument(
        "--mock",
        type=Path,
        default=None,
        help=(
            "Use a MockLlmClient that returns the JSON at this path "
            "(skips the real LLM). Handy for offline demos."
        ),
    )
    ap.add_argument(
        "--dump-spec-only",
        action="store_true",
        help=(
            "Extract and write --spec, then stop. Skips Python emission. "
            "Useful for debugging extractor drift without overwriting a "
            "previous generated module."
        ),
    )
    ap.add_argument(
        "--no-walkthrough",
        action="store_true",
        help=(
            "Skip the post-emit walkthrough self-check. The LLM still "
            "produces a walkthrough field, but the pipeline does not import "
            "the emitted module and play it; lint warnings + structural "
            "validation are the only feedback signals. Use this when the "
            "model is struggling to commit to a winning path and you want "
            "to ship the structural spec for manual debugging."
        ),
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=12000,
        help=(
            "Max output tokens for the main extraction call. Bump this for "
            "large games (e.g. AC3 needs ~24000) when the LLM truncates the "
            "JSON mid-spec. Default 12000."
        ),
    )
    ap.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help=(
            "Maximum LLM retries when the spec has validation errors, lint "
            "warnings, or a failing walkthrough. Each retry feeds the prior "
            "failures back to the model with 'MODIFY your spec' framing, so "
            "the LLM iteratively edits its own output. Default 2 (3 total "
            "attempts)."
        ),
    )
    args = ap.parse_args(argv)

    # --mock re-emits from a saved spec; the PDF isn't read in that
    # path, so it's optional. For live-LLM extraction the PDF is required.
    if args.mock is None:
        if args.pdf is None:
            raise SystemExit(
                "pdf is required for live-LLM extraction. Pass a PDF path, "
                "or use --mock <spec.json> to re-emit from a saved spec."
            )
        pdf_path: Path = args.pdf
        if not pdf_path.exists():
            raise SystemExit(f"PDF not found: {pdf_path}")

        pages_range = _resolve_range(pdf_path, args.game, args.page_range)
        print(
            f"[codegen] ingesting {args.game!r} pages "
            f"{pages_range[0]}-{pages_range[1]} ..."
        )
        pages = ingest_pdf(pdf_path, pages_range)
        print(f"[codegen] {len(pages)} pages ingested")
    else:
        # The mock returns the saved spec text regardless of input, so the
        # pages list can be empty -- _format_pages() handles that fine.
        pages = []
        print(f"[codegen] --mock mode: re-emitting from {args.mock} " "(no PDF ingest)")

    client = _build_llm_client(args.mock)
    # When --mock is supplied, the user has already vetted the spec they
    # handed us, so skip the post-emit walkthrough self-check; it would
    # otherwise fail (and force a retry) whenever the mocked spec lacks a
    # walkthrough field. The explicit --no-walkthrough flag overrides for
    # live LLM runs where the walkthrough is the bottleneck.
    run_walkthrough = args.mock is None and not args.no_walkthrough
    if args.mock is not None:
        args.max_retries = 0

    print(
        f"[codegen] extracting via {type(client).__name__} "
        f"(walkthrough check: {'on' if run_walkthrough else 'off'}, "
        f"max_retries: {args.max_retries}) ..."
    )
    extraction_partial: ExtractionPartial | None = None
    try:
        spec = extract_spec(
            pages,
            args.game,
            llm_client=client,
            run_walkthrough=run_walkthrough,
            max_retries=args.max_retries,
            max_tokens=args.max_tokens,
        )
    except ExtractionPartial as exc:
        # The retried spec passed structural validation but the walkthrough
        # didn't win -- OR the retry response was unparseable / didn't
        # validate, in which case we fell back to the first attempt's spec.
        # Either way, keep the spec so we still write the spec JSON + the
        # generated module: those artifacts are exactly what the user needs
        # to debug the failure by hand.
        spec = exc.spec
        extraction_partial = exc
        print(
            "[codegen] WARNING: extraction did not produce a fully verified "
            "spec. Writing the spec and module anyway for manual debugging.",
            file=sys.stderr,
        )
        print(f"[codegen]   {exc}", file=sys.stderr)
    print(
        f"[codegen] extracted spec: "
        f"{len(spec.locations)} locations, "
        f"{len(spec.items)} items, "
        f"{len(spec.characters)} characters, "
        f"{len(spec.custom_actions)} actions, "
        f"{len(spec.blocks)} blocks"
    )

    if args.spec:
        args.spec.parent.mkdir(parents=True, exist_ok=True)
        # Always write a *parseable* spec to args.spec so the file stays a
        # reproducible source: a downstream `--mock args.spec` run can
        # re-emit the .py without touching the LLM. The raw LLM payload
        # (when it was unparseable) goes to a sibling .raw.txt for
        # forensic debugging, not into the .spec.json itself.
        dump_spec(spec, args.spec)
        print(f"[codegen] wrote spec to {args.spec}")
        raw = getattr(extraction_partial, "raw_response", None)
        if raw is not None:
            raw_path = args.spec.with_suffix(args.spec.suffix + ".raw.txt")
            raw_path.write_text(raw)
            print(
                f"[codegen] wrote raw LLM response to {raw_path} "
                "(unparseable JSON; spec.json is the fallback)",
                file=sys.stderr,
            )

    warnings = lint(spec)
    if warnings:
        print(f"[codegen] {len(warnings)} lint warning(s):")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("[codegen] lint clean")

    if args.dump_spec_only:
        print("[codegen] --dump-spec-only set; skipping module emission")
        return 0

    # Emission may itself raise when the spec is structurally rough (a
    # RetryUnusable fallback returns the latest attempt, which may have
    # validation errors). The user explicitly wants the spec JSON on disk
    # for debugging in that case, so print the error and keep going rather
    # than crashing with no module written. We only skip validation when
    # `validate(spec)` would actually fail: WalkthroughCheckFailed carries
    # a structurally valid spec and should go through the normal gate.
    spec_validation_errors = validate(spec)
    skip_validation = bool(extraction_partial) and bool(spec_validation_errors)
    try:
        out_path = emit_module_to_file(spec, args.out, skip_validation=skip_validation)
        print(f"[codegen] wrote module to {out_path}")
    except Exception as exc:  # noqa: BLE001
        if extraction_partial is None:
            raise
        print(
            f"[codegen] WARNING: emit_module_to_file failed ({type(exc).__name__}: "
            f"{exc}). Spec JSON is still on disk for debugging.",
            file=sys.stderr,
        )
        return 1
    if extraction_partial is not None:
        # Non-zero exit so scripts that chain `codegen && pytest ...` notice
        # the failure -- but the files on disk are intact for debugging.
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
