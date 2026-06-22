# `text_adventure_games.codegen`

PDF → GameSpec JSON → Python `build_game()` module. The pipeline ingests a
Parsely PDF, extracts a typed `GameSpec` via an LLM, validates it, and emits a
Python module that imports only from `text_adventure_games`.

## When to reach for codegen

Honestly: **not often.** This package exists as a reference for the
PDF-to-game pipeline, but in practice a good prompt with Claude Code working
directly against the PDF produces a substantially better port than this
pipeline does.

Two implementations of Action Castle II and III on this repo make the
contrast concrete:

- `text_adventure_games/adventures/action_castle_2.py` and
  `action_castle_3.py` were written by Claude Code from the PDF with
  hand-guidance. They honor the PDF's scoring tables, multi-ending epilogues,
  posed yes/no dialogs, and prescribed death paths. They use the engine's
  modern primitives (`Recipe`, `Prompt`, `Character.following`,
  `refuses_follow`, `blocks.Darkness`).
- Their codegen-generated counterparts (now removed from the tree) covered
  the puzzle mechanics correctly but flattened the narrative layer: no
  scoring, single endings, no posed prompts, several PDF-prescribed death
  conditions missing, and a habit of solving things with hand-rolled blocks
  where an engine primitive would do.

The reason is straightforward. The codegen pipeline has to commit to a fixed
spec schema and template catalogue. Anything the schema doesn't model — a
100-point scoring table, a posed "are you sure you want to go home?", a
trigger tied to NPC inventory state — gets dropped on the floor or shoved
into a generic `flavor_response`. Claude Code, prompted against the same PDF,
notices those beats and reaches for the right engine primitive each time.

## So why is this package still here?

- It's a working example of a PDF → typed-spec → emitted-Python pipeline,
  useful if you want to study the layering.
- The `pdf_ingest` module on its own is genuinely useful: it tags spans by
  color (cyan rule vs. black flavor) and exposes underlined nouns, which is
  the most useful structured view of a Parsely PDF you can get without an
  LLM. Hand-porting goes faster with `ingest_pdf(path, page_range)` open in
  a notebook.
- `spec.validate()` and `spec.lint()` are useful as a sanity checklist for
  hand-written game modules too (every connection target exists, no prefix
  collisions on `ACTION_NAME`, etc.).

## How to actually port a Parsely game

1. Open the PDF page range for the game in a notebook with
   `from text_adventure_games.codegen.pdf_ingest import ingest_pdf` and skim
   the rule_text / item_nouns per page.
2. Open `text_adventure_games/adventures/action_castle.py` (or
   `action_castle_2.py` / `action_castle_3.py`) in another buffer as your
   worked example.
3. Ask Claude Code to port the game, pointing it at both. Tell it which
   engine primitives to lean on (`Prompt`, `Recipe`, `following`,
   `refuses_follow`, `Darkness`, lethal `Block`, `award()` if scoring) and
   which adventure to mirror in structure.
4. Iterate on the failing parts of the walkthrough — this is where the
   model is most useful and the pipeline is most brittle.

If you do want to run the pipeline anyway:

```bash
uv sync --extra codegen
uv run python -m text_adventure_games.codegen \
    parsely_pdfs/Parsely_r31_final.pdf \
    --game "Action Castle" \
    --out generated/action_castle.py \
    --spec generated/action_castle.spec.json
```

Expect to hand-edit the result before it's playable end-to-end.

## Layout

| Module | Responsibility |
| --- | --- |
| `pdf_ingest` | PyMuPDF span/color/underline parser. Pure, no LLM. |
| `extract` | LLM-driven GameSpec extractor (two-stage; mock fallback). |
| `spec` | `GameSpec` dataclasses, JSON I/O, `validate`, `lint`. |
| `templates/` | Per-template emitters for actions and blocks. |
| `emit` | `GameSpec` → Python source string. |
| `prompts` | LLM prompt strings used by `extract`. |
| `cli` | `python -m text_adventure_games.codegen` entry point. |

The base engine never imports this package; PyMuPDF stays optional.
