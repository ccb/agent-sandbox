"""Offline tests for seeding personas at t=0 (issue #79).

The port folds two upstream bootstrap assets onto the engine's existing seams:
relationships (``agent_history_init_n25.csv``) into each agent's *memory*, and the
partial known-places tree (``spatial_memory.json``) into each character's
*knowledge*. Those assets are git-ignored and absent on a fresh checkout, so these
tests build tiny fixtures in ``tmp_path`` -- mirroring ``synthetic_ville.py`` -- and
never touch ``frontend/``. Everything is deterministic and runs with the mock brain.

Run from ``generative-agents``::

    uv run pytest tests/test_seed_personas.py -v
"""

import csv
import json
import os

import pytest

from backend import seed
from backend.build_world import PERSONAS, build_world
from backend.smallville_agents import attach_agents, observe_and_decide
from text_adventure_games.memory import AgentMemory, MemoryKind
from text_adventure_games.things.characters import Character

# A persona's relationship "whisper": a single ';'-delimited string. Two of the
# three statements name Maria Lopez, so a "Maria" query has a clear best match.
ISABELLA_WHISPER = (
    "Maria Lopez is a regular at your cafe; "
    "You like to chat with Maria Lopez about her studies; "
    "Klaus Mueller stops by for coffee"
)

# A spatial tree keyed by world -> place -> area -> objects, like the upstream
# spatial_memory.json. KLAUS_TREE exercises an empty-object area ("hallway": [])
# and an arealess place ("Johnson Park": {}).
ISABELLA_TREE = {
    "the Ville": {
        "Hobbs Cafe": {"cafe": ["piano", "refrigerator"]},
        "Isabella Rodriguez's apartment": {"main room": ["bed", "desk"]},
    }
}
KLAUS_TREE = {
    "the Ville": {
        "Oak Hill College": {"hallway": [], "library": ["bookshelf"]},
        "Johnson Park": {},
    }
}


def _write_relationships_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Whisper"])
        writer.writerows(rows)


def _write_spatial(personas_dir, name, tree):
    bootstrap = os.path.join(personas_dir, name, "bootstrap_memory")
    os.makedirs(bootstrap, exist_ok=True)
    with open(
        os.path.join(bootstrap, "spatial_memory.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(tree, f)


@pytest.fixture
def seed_assets(tmp_path):
    """Write a tiny relationships CSV + a couple of spatial trees; return paths.

    Isabella and Maria get relationships; Isabella and Klaus get spatial trees.
    Everyone else is intentionally left unseeded so the *partial* cases (a persona
    with no row / no spatial file) can be asserted.
    """
    csv_path = tmp_path / "agent_history_init_n25.csv"
    _write_relationships_csv(
        csv_path,
        [
            ("Isabella Rodriguez", ISABELLA_WHISPER),
            ("Maria Lopez", "Isabella Rodriguez owns the cafe you visit"),
        ],
    )
    personas_dir = tmp_path / "personas"
    _write_spatial(personas_dir, "Isabella Rodriguez", ISABELLA_TREE)
    _write_spatial(personas_dir, "Klaus Mueller", KLAUS_TREE)
    return str(csv_path), str(personas_dir)


def _observation_seen_by(char):
    """The last observation string the agent's mock client was handed."""
    return char.agent.llm_client.tool_calls[-1]["messages"][-1]["content"]


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------


def test_load_relationships_splits_on_semicolons(tmp_path):
    csv_path = tmp_path / "rel.csv"
    _write_relationships_csv(
        csv_path, [("Isabella Rodriguez", ISABELLA_WHISPER), ("Maria Lopez", "")]
    )
    rel = seed.load_relationships(str(csv_path))

    assert rel["Isabella Rodriguez"] == [
        "Maria Lopez is a regular at your cafe",
        "You like to chat with Maria Lopez about her studies",
        "Klaus Mueller stops by for coffee",
    ]
    # An empty whisper yields no statements (not one empty string).
    assert rel["Maria Lopez"] == []


def test_load_relationships_missing_file_is_empty():
    assert seed.load_relationships("/no/such/file.csv") == {}


def test_load_spatial_memory_reads_tree(tmp_path):
    personas_dir = tmp_path / "personas"
    _write_spatial(personas_dir, "Klaus Mueller", KLAUS_TREE)
    assert seed.load_spatial_memory(str(personas_dir), "Klaus Mueller") == KLAUS_TREE
    # A persona with no bootstrap file gets an empty tree, not an error.
    assert seed.load_spatial_memory(str(personas_dir), "Nobody") == {}


# --------------------------------------------------------------------------
# Seeders (pure, no game)
# --------------------------------------------------------------------------


def test_seed_relationships_adds_observations_at_turn_0():
    mem = AgentMemory(owner="Isabella Rodriguez")
    added = seed.seed_relationships(
        mem,
        [
            "Maria Lopez is a regular at your cafe",
            "Klaus Mueller stops by for coffee",
        ],
    )
    assert added == 2
    assert len(mem.records) == 2
    for rec in mem.records:
        assert rec.kind == MemoryKind.OBSERVATION
        assert rec.created_turn == 0
        assert rec.importance == seed.RELATIONSHIP_IMPORTANCE
        assert {"seed", "relationship"} <= rec.tags

    # Retrieval surfaces the Maria fact for a Maria query (relevance does the work).
    top = mem.retrieve(query="Maria Lopez", turn=0)
    assert top, "expected at least one retrieved memory"
    assert "Maria Lopez" in top[0].text


def test_seed_spatial_knowledge_adds_place_beliefs():
    char = Character("Isabella Rodriguez", "the cafe owner", "I am Isabella.")
    added = seed.seed_spatial_knowledge(char, ISABELLA_TREE)

    assert added == 2
    texts = [b.text for b in char.knowledge.beliefs]
    assert "You know Hobbs Cafe — its cafe." in texts
    assert "You know Isabella Rodriguez's apartment — its main room." in texts
    # Seeded as priors (known up front), not learned during play.
    assert all(b.learned_turn is None for b in char.knowledge.beliefs)
    # And it renders into the observation's "What you know:" section.
    rendered = char.knowledge.render()
    assert rendered.startswith("What you know:")
    assert "Hobbs Cafe" in rendered


def test_seed_spatial_knowledge_handles_empty_and_arealess_places():
    char = Character("Klaus Mueller", "the student", "I am Klaus.")
    added = seed.seed_spatial_knowledge(char, KLAUS_TREE)

    assert added == 2
    texts = [b.text for b in char.knowledge.beliefs]
    # An empty-object area ("hallway": []) is still a known area and is listed.
    assert "You know Oak Hill College — its hallway, library." in texts
    # A place with no areas at all renders without the "-- its ..." clause.
    assert "You know Johnson Park." in texts


def test_seed_spatial_knowledge_empty_tree_is_noop():
    char = Character("Nobody", "nobody", "I am nobody.")
    assert seed.seed_spatial_knowledge(char, {}) == 0
    assert char.knowledge.render() == ""


# --------------------------------------------------------------------------
# Wiring through attach_agents
# --------------------------------------------------------------------------


def test_attach_seeds_relationships_into_memory(seed_assets):
    csv_path, _ = seed_assets
    _, chars = build_world()
    attach_agents(chars, PERSONAS, relationships_csv=csv_path)

    isabella = chars["Isabella Rodriguez"]
    rel = [
        r
        for r in isabella.agent.memory.records
        if r.kind == MemoryKind.OBSERVATION and "relationship" in r.tags
    ]
    assert len(rel) == 3  # Isabella's whisper has three statements
    # The day-plan memory is still there alongside the relationships.
    assert any(r.kind == MemoryKind.PLAN for r in isabella.agent.memory.records)

    # A persona with no CSV row gets only its plan -- no relationship memories.
    john = chars["John Lin"]
    assert not any("relationship" in r.tags for r in john.agent.memory.records)


def test_attach_seeds_spatial_into_knowledge(seed_assets):
    _, personas_dir = seed_assets
    _, chars = build_world()
    attach_agents(chars, PERSONAS, base_personas_dir=personas_dir)

    isabella = chars["Isabella Rodriguez"]
    assert isabella.knowledge.believes("Hobbs Cafe")
    assert "What you know:" in isabella.knowledge.render()

    # Knowledge is partial: a persona with no spatial file knows no places.
    john = chars["John Lin"]
    assert john.knowledge.render() == ""


def test_seeding_is_decision_neutral(seed_assets):
    csv_path, personas_dir = seed_assets

    # Without seeding.
    plain_game, plain_chars = build_world()
    attach_agents(plain_chars, PERSONAS)
    plain_game.turn = 0
    plain_cmd = observe_and_decide(plain_game, plain_chars["Isabella Rodriguez"], 0)

    # With seeding.
    game, chars = build_world()
    attach_agents(
        chars,
        PERSONAS,
        relationships_csv=csv_path,
        base_personas_dir=personas_dir,
    )
    game.turn = 0
    isabella = chars["Isabella Rodriguez"]
    cmd = observe_and_decide(game, isabella, 0)

    # The seed data is surfaced into the prompt the agent reasons over...
    observation = _observation_seen_by(isabella)
    assert "What you know:" in observation  # spatial knowledge
    assert "Relevant memories:" in observation  # retrieved relationships
    # ...but memory/knowledge is context, not authority: the mock reads only the
    # location off the first line, so the decision is byte-identical either way.
    assert cmd == plain_cmd == "travel to Hobbs Cafe"


def test_missing_assets_skip_silently():
    _, chars = build_world()
    # Bad paths (and the default of no paths) must not raise, and must not seed.
    attach_agents(
        chars,
        PERSONAS,
        relationships_csv="/no/such/file.csv",
        base_personas_dir="/no/such/dir",
    )
    isabella = chars["Isabella Rodriguez"]
    assert not any("relationship" in r.tags for r in isabella.agent.memory.records)
    assert isabella.knowledge.render() == ""
    # Only the day-plan memory remains.
    assert [r.kind for r in isabella.agent.memory.records] == [MemoryKind.PLAN]


# --------------------------------------------------------------------------
# Real upstream assets (skipped unless ./setup.sh has populated frontend/)
# --------------------------------------------------------------------------


def _real_asset_paths():
    from backend.run_simulation import (
        DEFAULT_BASE_SIM,
        DEFAULT_STORAGE,
        DEFAULT_VILLE_DIR,
    )

    csv_path = os.path.join(DEFAULT_VILLE_DIR, "agent_history_init_n25.csv")
    base_personas = os.path.join(DEFAULT_STORAGE, DEFAULT_BASE_SIM, "personas")
    return csv_path, base_personas


@pytest.mark.skipif(
    not os.path.isfile(_real_asset_paths()[0]),
    reason="upstream the_ville assets absent (run ./setup.sh)",
)
def test_real_assets_seed_every_persona():
    csv_path, base_personas = _real_asset_paths()
    _, chars = build_world()
    attach_agents(
        chars, PERSONAS, relationships_csv=csv_path, base_personas_dir=base_personas
    )
    for spec in PERSONAS:
        char = chars[spec["name"]]
        # Every resident has at least one relationship memory and one known place.
        assert any("relationship" in r.tags for r in char.agent.memory.records)
        assert char.knowledge.beliefs
