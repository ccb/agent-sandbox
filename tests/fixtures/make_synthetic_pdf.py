"""Regenerate ``tests/fixtures/synthetic.pdf``.

The synthetic PDF exercises ``codegen.pdf_ingest`` against a known layout
without depending on the gitignored Parsely PDF. All content here is
placeholder text -- not copied from any book.

Run it directly to rewrite the fixture::

    uv run python tests/fixtures/make_synthetic_pdf.py
"""

from pathlib import Path

import pymupdf

BLACK = (35 / 255, 31 / 255, 32 / 255)  # matches Parsely flavor color
CYAN = (0 / 255, 174 / 255, 239 / 255)  # matches Parsely rule color
WHITE = (1.0, 1.0, 1.0)


def _emit_page(doc, title: str, flavor: str, rule: str, item_to_underline: str):
    page = doc.new_page(width=425, height=648)
    # Title (largest font, near the top).
    page.insert_text((40, 60), title, fontsize=22, color=BLACK)
    # Flavor body (black).
    page.insert_text((40, 110), flavor, fontsize=11, color=BLACK)
    # Underlined item: emit the text in flavor color, then draw a short
    # horizontal stroke just below its baseline.
    item_y = 150
    page.insert_text((40, item_y), item_to_underline, fontsize=11, color=BLACK)
    # Estimate the item's width for the underline stroke.
    text_width = pymupdf.get_text_length(item_to_underline, fontsize=11)
    page.draw_line(
        (40, item_y + 2),
        (40 + text_width, item_y + 2),
        color=BLACK,
        width=0.6,
    )
    # Rule body (cyan).
    page.insert_text((40, 200), rule, fontsize=11, color=CYAN)


def _emit_partial_underline_page(doc, title: str, prefix: str, noun: str, suffix: str):
    """Page where only one word inside a longer flavor span is underlined.

    Exercises the underline-detection fix: with the whole sentence on one
    line, the underline must credit only ``noun`` (not the whole span).
    """
    page = doc.new_page(width=425, height=648)
    page.insert_text((40, 60), title, fontsize=22, color=BLACK)
    text_y = 110
    # Write the prefix.
    page.insert_text((40, text_y), prefix, fontsize=11, color=BLACK)
    prefix_w = pymupdf.get_text_length(prefix, fontsize=11)
    # Write the noun (will be underlined).
    page.insert_text((40 + prefix_w, text_y), noun, fontsize=11, color=BLACK)
    noun_w = pymupdf.get_text_length(noun, fontsize=11)
    # Write the suffix.
    page.insert_text((40 + prefix_w + noun_w, text_y), suffix, fontsize=11, color=BLACK)
    # Draw the underline ONLY below the noun's x-range.
    page.draw_line(
        (40 + prefix_w, text_y + 2),
        (40 + prefix_w + noun_w, text_y + 2),
        color=BLACK,
        width=0.6,
    )
    # A tiny cyan rule so the page is well-formed.
    page.insert_text(
        (40, 200), "Examining gives a description.", fontsize=11, color=CYAN
    )


def main():
    here = Path(__file__).resolve().parent
    out = here / "synthetic.pdf"
    doc = pymupdf.open()
    _emit_page(
        doc,
        title="Cabin",
        flavor="You are inside a small cabin.",
        rule="The lantern only works after being lit.",
        item_to_underline="lantern",
    )
    _emit_page(
        doc,
        title="Forest",
        flavor="You stand at the edge of a quiet forest.",
        rule="The wolf will not move unless distracted by food.",
        item_to_underline="branch",
    )
    _emit_page(
        doc,
        title="Cliff",
        flavor="A windy cliff overlooks the sea.",
        rule="Jumping ends the adventure.",
        item_to_underline="rope",
    )
    # Page 4: only "soda" is underlined inside a longer sentence.
    _emit_partial_underline_page(
        doc,
        title="Vending",
        prefix="A can of ",
        noun="soda",
        suffix=" drops out of the machine.",
    )
    doc.save(out)
    doc.close()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
