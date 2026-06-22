import re
from text_adventure_games.codegen.pdf_ingest import ingest_pdf, game_page_ranges

PDF = "parsely_pdfs/Parsely_r31_final.pdf"
SKIP = {"Hello", "Readme", "Index"}

# Each pattern is matched case-insensitively against each game's rule_text.
# Patterns target the verb form (the Parsely book writes rules as
# "WEAR X:", "USE X ON Y:", etc.) but allow lowercase too.
MECHANICS = {
    "WEAR": r"\bwear\b",
    "USE X ON Y": r"\buse\b[^.]*\bon\b",
    "READ": r"\bread\b",
    "OPEN": r"\bopen\b",
    "TALK TO": r"\btalk\s+to\b",
    "ASK X ABOUT Y": r"\bask\b[^.]*\babout\b",
    "SEARCH": r"\bsearch\b",
    "SHOW": r"\bshow\b",
    "KNOCK": r"\bknock\b",
    "LISTEN": r"\blisten\b",
    "SAY YES/NO": r"\bsay\s+(yes|no)\b",
    "Score / points": r"\b\d+\s+points?\b|\bepilogue",
    "Follow / party": r"\bfollow\b|\bjoin\s+the\s+party\b|\binvite\b",
    "Make / cook / brew": r"\b(make|cook|brew|combine|build\s+fire)\b",
    "Sleep / rest": r"\b(sleep|rest)\b",
}

ranges = game_page_ranges(PDF)
games = [(n, r) for n, r in ranges.items() if n not in SKIP]

# Header
print(f"{'Mechanic':<22}", *[n[:6] for n, _ in games], sep=" | ")
print("-" * (22 + len(games) * 9))

totals = {}
for label, pattern in MECHANICS.items():
    rx = re.compile(pattern, re.IGNORECASE)
    row, hits = [], 0
    for name, r in games:
        text = " ".join(p.rule_text() for p in ingest_pdf(PDF, r))
        present = bool(rx.search(text))
        row.append("  ✓   " if present else "  -   ")
        hits += present
    totals[label] = hits
    print(f"{label:<22}", *row, sep=" | ")

print()
print("Hits / 12 (sorted):")
for label, n in sorted(totals.items(), key=lambda kv: -kv[1]):
    print(f"  {n:2d}/12  {label}")
