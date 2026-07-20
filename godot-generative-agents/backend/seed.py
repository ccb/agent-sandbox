"""Seed generative-agents personas with their t=0 social structure and world knowledge.

The upstream ``the_ville_n25`` data ships two bootstrap files per resident that the
port folds onto the engine's existing agent seams (issue #79):

* ``agent_history_init_n25.csv`` -- the pre-seeded *relationships* ("where social
  structure lives at t=0"): one ``;``-delimited list of statements per persona.
  Each statement becomes one entry in that agent's :class:`AgentMemory`
  (``text_adventure_games/memory.py``), so retrieval can surface "Rajiv Patel is
  my housemate" the moment the agent reasons about Rajiv.
* ``spatial_memory.json`` -- the persona's *partial* known-places tree
  (world -> place -> area -> objects). The places (and their areas) become
  :class:`Belief`s in that character's :class:`Knowledge`
  (``text_adventure_games/knowledge.py``), rendered into the "What you know:"
  section of the observation. Knowledge is partial by design: an agent only
  believes in the places its own tree lists.

This module is the port's *wiring*: it composes those engine APIs and never
modifies them. The loaders tolerate missing files -- the ~38MB upstream assets are
git-ignored and only present after ``./setup.sh`` -- so seeding is a no-op on a
fresh checkout or in CI, and callers stay byte-identical when the data is absent.
"""

from __future__ import annotations

import csv
import json
import os

from .prompt_templates import render

# Importance (the paper's 1-10 poignancy scale) for a seeded relationship memory.
# Above a mundane perceived event (1.0) but below the day's plan (5.0): social
# priors are notable background, not the agent's active intention. Tunable.
RELATIONSHIP_IMPORTANCE = 3.0


def load_relationships(csv_path: str) -> dict[str, list[str]]:
    """Parse the relationships CSV into ``{persona name: [statement, ...]}``.

    The file has two columns, ``Name`` and ``Whisper``; each whisper is a single
    ``;``-delimited string of relationship statements. We split it into separate
    statements (stripped, empties dropped) so each becomes its own memory --
    matching the paper, and giving retrieval one fact to surface per query rather
    than one undifferentiated blob. Returns ``{}`` if the file is missing.
    """
    if not os.path.isfile(csv_path):
        return {}
    relationships: dict[str, list[str]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("Name") or "").strip()
            whisper = row.get("Whisper") or ""
            statements = [s.strip() for s in whisper.split(";") if s.strip()]
            if name:
                relationships[name] = statements
    return relationships


def load_spatial_memory(personas_dir: str, name: str) -> dict:
    """Load one persona's ``spatial_memory.json`` known-places tree.

    Looks under ``{personas_dir}/{name}/bootstrap_memory/spatial_memory.json`` and
    returns the parsed ``{world: {place: {area: [objects]}}}`` tree, or ``{}`` when
    the file is missing (so a caller seeds whatever is present and skips the rest).
    """
    path = os.path.join(personas_dir, name, "bootstrap_memory", "spatial_memory.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_relationships(
    memory,
    statements: list[str],
    turn: int = 0,
    importance: float = RELATIONSHIP_IMPORTANCE,
) -> int:
    """Seed an agent's *memory* with its relationship statements at ``turn``.

    Each statement becomes one observation -- the kind for "something the agent
    knows from experience" -- tagged ``seed``/``relationship`` for provenance.
    Returns how many were added.
    """
    for statement in statements:
        memory.add_observation(
            statement,
            turn=turn,
            importance=importance,
            tags={"seed", "relationship"},
        )
    return len(statements)


def seed_spatial_knowledge(character, tree: dict) -> int:
    """Seed a *character's* knowledge with the places it knows (place + areas).

    For each place in the persona's spatial tree we add one belief naming the place
    and its areas, e.g. "You know Oak Hill College -- its hallway, library,
    classroom." The objects within an area are intentionally left out to keep the
    "What you know:" section readable. Beliefs are seeded as priors
    (``learned_turn=None``): this is what the agent knows up front. Knowledge stays
    *partial* -- only the places in this persona's tree are added. Returns how many
    beliefs were added.
    """
    if not tree:
        return 0
    # The tree is keyed by world ("the Ville"); take that one subtree, falling back
    # to the first (only) top-level key so a renamed world still works.
    world = tree.get("the Ville")
    if world is None:
        world = next(iter(tree.values()), {})

    added = 0
    for place, areas in world.items():
        area_names = list(areas.keys()) if isinstance(areas, dict) else []
        text = render("spatial_knowledge", place=place, areas=", ".join(area_names))
        character.add_belief(text)
        added += 1
    return added
