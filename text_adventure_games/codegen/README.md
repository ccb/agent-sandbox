# `text_adventure_games.codegen`

A structured, color-tagged **reader** for Parsely PDFs, to skim slice by slice
while hand-porting a game to the engine.

This package used to be a full PDF → GameSpec JSON → Python `build_game()`
pipeline. That spec-extraction and module-emission half has been **removed**: in
practice a good prompt with Claude Code working directly against the PDF produces
a substantially better port than the template-driven emitter did. The emitter had
to commit to a fixed spec schema and template catalogue, so anything the schema
didn't model — a 100-point scoring table, a posed "are you sure you want to go
home?", a trigger tied to NPC inventory state — got dropped or shoved into a
generic `flavor_response`. Claude Code, prompted against the same PDF, notices
those beats and reaches for the right engine primitive each time.

What remains is the genuinely useful part: the **PDF ingest + structured view**.

- `pdf_ingest` tags spans by color (cyan rule vs. black flavor) and exposes
  underlined nouns — the most useful structured view of a Parsely PDF you can get
  without an LLM. Hand-porting goes faster with `ingest_pdf(path, page_range)`
  open in a notebook.
- `render_source` renders a scoped slice (by game, page range, or room) as
  compact markdown to read against the engine as you port.

## How to port a Parsely game

1. Pull the source one slice at a time with `render_source` / the `source` CLI:

   ```bash
   uv run python -m text_adventure_games.codegen.source \
       --pdf parsely_pdfs/<book>.pdf --game "Action Castle II"
   uv run python -m text_adventure_games.codegen.source \
       --pdf parsely_pdfs/<book>.pdf --pages 51-58
   ```

   Or from Python: `from text_adventure_games.codegen import render_source`. For
   the raw tagged spans, `from text_adventure_games.codegen.pdf_ingest import
   ingest_pdf` and skim the rule_text / item_nouns per page.
2. Open `text_adventure_games/adventures/action_castle.py` (or
   `action_castle_2.py` / `action_castle_3.py`) as your worked example.
3. Ask Claude Code to port the game, pointing it at both. Tell it which engine
   primitives to lean on (`Prompt`, `Recipe`, `following`, `refuses_follow`,
   `Darkness`, lethal `Block`, `award()` if scoring) and which adventure to
   mirror in structure.
4. Iterate on the failing parts of the walkthrough.

See `docs/converting-parsely-games.md` for the full guide.

## Layout

| Module | Responsibility |
| --- | --- |
| `pdf_ingest` | PyMuPDF span/color/underline parser. Pure, no LLM. |
| `pdf_structure` | Group ingested spans into per-location blocks. |
| `source_view` | `render_source`: a scoped PDF slice as compact markdown. |
| `source` | `python -m text_adventure_games.codegen.source` CLI. |

The base engine never imports this package; PyMuPDF stays optional.
