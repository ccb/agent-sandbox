"""Direction auto-reverse heuristics for the PDF -> spec porting pipeline.

The core engine believes in *cardinal* opposites only: ``add_connection``
(see ``things/locations.py``) reads :data:`text_adventure_games.enums.OPPOSITES`
to wire ``north``<->``south``, ``in``<->``out`` and friends automatically.

Parsely PDFs lean on a few *verb-prefix* exit pairs too -- ``enter moat`` /
``exit moat``, ``climb up rope`` / ``climb down rope`` -- whose noun tail
carries through unchanged. Those are a porting convention, not engine truth, so
they live here in ``codegen`` rather than in the core enum module. ``spec`` uses
:func:`canonical_opposite` to compute the effective exit graph (for
``validate``) and to flag redundant hand-written reverse exits (for ``lint``).
"""

from __future__ import annotations

from ..enums import OPPOSITES

# Verb-prefix opposites: paired movement templates whose noun tail (if any)
# carries through unchanged. Common Parsely patterns like "enter moat" /
# "exit moat" and "climb up rope" / "climb down rope" follow this shape, so
# the porting pipeline can derive the reverse automatically without forcing
# every spec to spell out `reverse_direction`.
#
# Matching order is "longest source prefix wins" inside ``canonical_opposite``
# so "climb up" beats a hypothetical bare "climb" rule. Each entry is checked
# both as the bare verb (``"enter"`` -> ``"exit"``) and as a prefix on a noun
# tail (``"enter moat"`` -> ``"exit moat"``).
_VERB_PREFIX_OPPOSITES: tuple[tuple[str, str], ...] = (
    ("climb up", "climb down"),
    ("climb down", "climb up"),
    ("enter", "exit"),
    ("exit", "enter"),
)


def canonical_opposite(direction: str) -> str | None:
    """Return the auto-reverse for ``direction``, if any.

    Checks the cardinal :data:`OPPOSITES` table first (the same table the
    engine uses for real reverse-exit wiring), then the verb-prefix templates
    in ``_VERB_PREFIX_OPPOSITES``. Returns ``None`` when there is no
    auto-reverse (the caller should either install no reverse -- one-way exits
    like ``jump`` -- or pass an explicit ``reverse_direction`` on the
    ``Exit``/``add_connection`` call).
    """
    direction = str(direction).lower().strip()
    if not direction:
        return None
    if direction in OPPOSITES:
        return str(OPPOSITES[direction])
    # Verb-prefix templates. Longest-first so ``"climb up"`` is matched
    # before any future bare-``"climb"`` rule.
    for src, dst in sorted(_VERB_PREFIX_OPPOSITES, key=lambda p: -len(p[0])):
        if direction == src:
            return dst
        if direction.startswith(src + " "):
            return dst + direction[len(src) :]
    return None
