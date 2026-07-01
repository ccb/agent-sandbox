"""Perception: how well a character perceives a location (design: docs/design/perception.md).

Layer 1 -- sight. A :class:`Veil` is to *describing* what a
:class:`~text_adventure_games.blocks.Block` is to *movement*: a small, composable,
subclassable condition attached to a location that limits how well an observer can
see it. Games opt in (``location.obscure(Darkness())``); a location with no veils
and a non-blind observer resolves to :data:`Sight.CLEAR`, so ``describe`` renders
exactly as before -- the feature is zero-cost until used.

Senses beyond sight (touch/hearing/smell) and the structured ``Scene``/narrator
split are later layers; this module is deliberately just the sight gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .enums import Property


class Sight(IntEnum):
    """How well an observer sees a location. Ordered so "most restrictive wins":
    a resolver takes the minimum across all veils."""

    NONE = 0   # can't see -- render only the "can't see" blurb
    DIM = 1    # partial -- the room's gist + exits, but not items/characters
    CLEAR = 2  # full: description + exits + items + characters


def carries_light(character) -> bool:
    """True if *character* holds a lit item anywhere it would shed light -- in
    hand, worn, wielded, or inside an open carried container. Mirrors the
    ``Darkness`` movement block's check so sight and travel agree about light."""
    if character is None:
        return False
    slots = (
        getattr(character, "inventory", {}),
        getattr(character, "worn", {}),
        getattr(character, "wielded", {}),
    )
    for slot in slots:
        for item in slot.values():
            if item.get_property(Property.IS_LIT):
                return True
            for inner in item.accessible_contents().values():
                if inner.get_property(Property.IS_LIT):
                    return True
    return False


class Veil:
    """A location-attached, observer-aware perception condition -- the perception
    counterpart to :class:`~text_adventure_games.blocks.Block`. Subclass and
    override :meth:`sight` (and optionally :meth:`blurb`). Attach with
    ``location.obscure(MyVeil())``."""

    def sight(self, observer, location) -> Sight:
        """How well *observer* can see *location* through this veil."""
        return Sight.CLEAR

    def blurb(self, location) -> str:
        """What to narrate in place of the room when this veil blinds the view."""
        return "You can't make anything out here."


class Darkness(Veil):
    """Pitch dark: nothing is seen unless the observer carries a lit light."""

    def sight(self, observer, location) -> Sight:
        return Sight.CLEAR if carries_light(observer) else Sight.NONE

    def blurb(self, location) -> str:
        return "It's pitch dark -- you can see nothing without a light."


class Fog(Veil):
    """A dim haze: the room's shape and exits show, but not its contents."""

    def sight(self, observer, location) -> Sight:
        return Sight.DIM

    def blurb(self, location) -> str:
        return "A thick haze blurs everything more than a few feet off."


def sight_for(observer, location) -> tuple[Sight, str]:
    """Resolve how well *observer* perceives *location*: the most restrictive of
    the observer's own conditions (blindness) and every veil on the location.

    Returns ``(Sight, blurb)``. With no veils and a non-blind observer this is
    ``(Sight.CLEAR, "")`` immediately -- the zero-cost default."""
    if observer is not None and observer.get_property("blind"):
        return Sight.NONE, "You see nothing -- you're blind."
    level, blurb = Sight.CLEAR, ""
    for veil in getattr(location, "veils", ()):
        s = veil.sight(observer, location)
        if s < level:
            level, blurb = s, veil.blurb(location)
    return level, blurb


@dataclass(frozen=True)
class Scene:
    """An observer's perception of their location -- the shared result that both
    the human ``describe`` and the agent ``describe_for`` renderers consume, so
    the two always perceive the same world.

    Layer 1 carries the sight resolution and the text to show in place of the
    room description (the room's own text when seen, a veil's blurb when not).
    Later layers grow this into the structured anchor a pluggable narrator
    rewrites from -- the perceived exits/items/characters, plus what was heard
    or smelled rather than seen.
    """

    sight: Sight
    description: str

