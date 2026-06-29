"""A Smallville ``Game`` whose "nearby" means tile distance, not room hops.

Issue #80 gave the engine a single visibility seam --
``Game.perceivable_locations(character)`` -- that decides which locations a
character can perceive each turn (its agents/objects/events are then folded into
memory by ``AgentMemory.perceive``). The engine's default walks the room
*connection* graph out to ``character.vision_r`` hops.

That graph is the wrong notion of distance for Smallville: ``build_world`` wires
each arena to the hub with a one-way ``to <name>`` exit (no reverse), so from any
arena the room graph goes nowhere -- the default would only ever return the
current arena. Smallville's real proximity lives on the 140x100 tile map
(``world_map.py``). This is exactly the case the seam was built to be overridden
for (issue #82): :class:`TiledGame` answers "what's nearby" with **tile
distance**, so two residents standing near each other *on the map* perceive each
other in the sim.

This is the canonical worked example of the engine's design note about its two
"nearby" seams. :class:`TiledGame` overrides *both*, by the same tile distance:
``perceivable_locations`` (sight -- what an agent sees and remembers) and
``audience_for`` (hearing -- who an agent can talk with). So perception and
conversation share one notion of proximity: a resident converses with whoever is
close enough *on the map* to perceive, not only with whoever happens to share its
arena (issues #82, #86).
"""

from text_adventure_games import games


class TiledGame(games.Game):
    """A ``Game`` that perceives by tile distance over a :class:`WorldMap`.

    Identical to the engine ``Game`` except it carries a ``world_map`` and
    overrides :meth:`perceivable_locations` (sight) and :meth:`audience_for`
    (hearing) to measure "nearby" by tile distance. With no ``world_map`` both
    fall back to the current room, so it is a safe drop-in even before a map is
    loaded.
    """

    def __init__(self, *args, world_map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.world_map = world_map

    def perceivable_locations(self, character):
        """Locations within ``character.vision_r`` *tiles* of its current arena.

        Each engine ``Location`` carries a ``tile_address`` (e.g.
        ``"the Ville:Hobbs Cafe:cafe"``); we keep every location whose footprint
        is within the radius of the viewer's, measured by
        :meth:`WorldMap.tile_gap`. Falls back to just the current room when there
        is no map, the room has no tile address (e.g. the hub), or vision is 0 --
        matching the engine default's radius-0 behavior.
        """
        loc = character.location
        if loc is None:
            return []
        radius = getattr(character, "vision_r", 0)
        origin = getattr(loc, "tile_address", None)
        if self.world_map is None or origin is None or radius <= 0:
            return [loc]
        # Perf note (#106): this scans every location once per call, and the step
        # loop calls it once per acting agent per tick -- so perception is
        # O(agents x locations) per tick. Totally fine at Smallville's scale
        # (~25 agents, ~20 arenas); `tile_gap` is O(1) on precomputed bounding
        # boxes. If a future map ever has thousands of locations, index the
        # arenas spatially (e.g. a tile grid / bucket by region) instead of this
        # linear scan -- future-you, this is the line to revisit.
        near = [
            other
            for other in self.locations.values()
            if getattr(other, "tile_address", None) is not None
            and self.world_map.tile_gap(origin, other.tile_address) <= radius
        ]
        # `origin == origin` -> gap 0, so the current room is always included;
        # `or [loc]` is a belt-and-braces guard for an odd address mapping.
        return near or [loc]

    def audience_for(self, speaker, message, target=None):
        """Characters within ``speaker.vision_r`` *tiles* who hear the message.

        The hearing counterpart to :meth:`perceivable_locations`, and the seam
        that gates Smallville conversations by proximity: an agent should only
        converse with someone it could perceive, so we reuse the very same
        tile-distance query and return everyone standing in an in-range location
        (the speaker aside). Two residents thus talk when they're close *on the
        map*, not only when they happen to share one arena (issue #86).

        Falls back to the engine's room-based audience for free: with no
        ``world_map`` (or ``vision_r <= 0``) ``perceivable_locations`` yields just
        the speaker's own room, so the audience is everyone co-located with them.
        """
        audience = []
        for loc in self.perceivable_locations(speaker):
            audience.extend(c for c in loc.characters.values() if c is not speaker)
        return audience
