"""Offline tests for using semantic memory retrieval in the sim (issue #102).

Two port-side pieces sit on top of the engine's embedding seam (#76):

* ``run_simulation.resolve_embedding_client`` -- turns the ``--embeddings`` flag
  (and the ``EMBEDDING_PROVIDER`` env var) into a client, degrading to ``None``
  (keyword overlap) so the default run stays free, offline, and CI-safe.
* ``gen_agents.compare_retrieval`` -- the manual probe that accrues real resident
  memories, then measures keyword-overlap vs semantic retrieval directly.

Everything here uses the deterministic ``MockEmbeddingClient`` (or no client at
all), so it needs no model download, no network, and no maze assets. Run from
``generative-agents``::

    uv run pytest tests/test_embeddings_in_sim.py -v
"""

import pytest

from gen_agents.build_world import PERSONAS, build_world
from gen_agents.compare_retrieval import accrue_memories, compare, make_embedding_client
from gen_agents.run_simulation import resolve_embedding_client
from gen_agents.smallville_agents import attach_agents
from text_adventure_games.embedding_client import MockEmbeddingClient

# --------------------------------------------------------------------------
# resolve_embedding_client: flag wins, env is the fallback, degrade to None
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_embedding_env(monkeypatch):
    """No EMBEDDING_* vars leak in from the runner's environment."""
    for var in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_returns_none_without_flag_or_env():
    # The default sim run: no flag, no env -> keyword overlap (None).
    assert resolve_embedding_client(None) is None


def test_resolve_flag_selects_backend():
    assert isinstance(resolve_embedding_client("mock"), MockEmbeddingClient)


def test_resolve_reads_env_when_flag_absent(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    assert isinstance(resolve_embedding_client(None), MockEmbeddingClient)


def test_resolve_flag_overrides_env(monkeypatch):
    # The explicit flag wins over the environment. Using "mock" for both the
    # winner and a deliberately broken env value keeps the test offline while
    # still proving precedence (the env value is never consulted).
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bogus-never-used")
    assert isinstance(resolve_embedding_client("mock"), MockEmbeddingClient)


def test_resolve_unknown_provider_degrades_to_none():
    # An unknown provider must not crash the run -- it degrades to keyword
    # overlap, the same graceful pattern as embedding_client_from_env.
    assert resolve_embedding_client("no-such-provider") is None


# --------------------------------------------------------------------------
# compare_retrieval: the probe runs offline and is read-only
# --------------------------------------------------------------------------


def _accrued_world(num_steps=12):
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    accrue_memories(game, chars, num_steps)
    return game, chars


def test_make_embedding_client_falls_back_to_mock():
    # The probe always needs *some* client (keyword-vs-keyword is a no-op), so an
    # unknown/uninstalled backend falls back to the mock rather than returning None.
    assert isinstance(make_embedding_client("no-such-provider"), MockEmbeddingClient)


def test_accrue_memories_builds_a_stream():
    # After a short run, residents at a hub have accrued more than a lone plan:
    # their own travel/perform plus perceptions of co-located neighbors.
    _, chars = _accrued_world()
    isabella = chars["Isabella Rodriguez"]  # Hobbs Cafe, a 7-resident hub
    texts = [r.text for r in isabella.agent.memory.records]
    assert "I traveled to Hobbs Cafe." in texts
    assert any("arrived from" in t for t in texts)  # perceived a neighbor arriving
    assert len(isabella.agent.memory.records) > 4


def test_compare_returns_wellformed_results():
    game, chars = _accrued_world()
    results = compare(game, chars, MockEmbeddingClient(), query=None, top_k=4, turn=12)
    assert results  # at least one resident accrued more than top_k memories
    for r in results:
        assert len(r["keyword"]) <= 4 and len(r["semantic"]) <= 4
        kw_ids = {x.id for x in r["keyword"]}
        sem_ids = {x.id for x in r["semantic"]}
        assert r["same_set"] == (kw_ids == sem_ids)
        # same_order implies same_set (identical lists share their membership).
        assert not (r["same_order"] and not r["same_set"])


def test_compare_resident_filter_limits_to_one():
    game, chars = _accrued_world()
    results = compare(
        game,
        chars,
        MockEmbeddingClient(),
        query=None,
        top_k=4,
        turn=12,
        only="Isabella Rodriguez",
    )
    assert [r["name"] for r in results] == ["Isabella Rodriguez"]


def test_compare_is_read_only():
    # The comparison must not disturb the stream it inspects: read-only retrieval
    # (touch=False) leaves last_accessed_turn untouched, and the swapped-in
    # embedding client is restored, so a later real retrieval is unaffected.
    game, chars = _accrued_world()
    memory = chars["Isabella Rodriguez"].agent.memory
    before = {r.id: r.last_accessed_turn for r in memory.records}
    compare(game, chars, MockEmbeddingClient(), query=None, top_k=4, turn=999)
    after = {r.id: r.last_accessed_turn for r in memory.records}
    assert after == before
    assert memory.embedding_client is None  # restored (was None during accrual)
