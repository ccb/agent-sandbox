"""Tests for the embedding client layer (issue #76).

The mock backend is deterministic and dependency-free, so these run offline with
no API key and no model download -- the same contract as the mock LLM client.
The one test that touches the real local model (model2vec) skips itself when the
package or its model download isn't available.
"""

import pytest

from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    MockEmbeddingClient,
    LocalEmbeddingClient,
    create_embedding_client,
    embedding_client_from_env,
)
from text_adventure_games.memory import cosine_similarity

# --- MockEmbeddingClient: deterministic, offline -----------------------------


def test_mock_embedding_is_deterministic():
    """Same text -> identical vector, across calls and across instances (it
    hashes with hashlib, not the per-process-salted built-in ``hash``)."""
    a = MockEmbeddingClient().embed(["the troll guards the bridge"])[0]
    b = MockEmbeddingClient().embed(["the troll guards the bridge"])[0]
    assert a == b


def test_mock_embedding_batch_shape():
    """One vector per input, in order, each of the client's dimensionality."""
    client = MockEmbeddingClient(dim=32)
    vectors = client.embed(["alpha", "beta", "gamma"])
    assert len(vectors) == 3
    assert all(len(v) == 32 for v in vectors)


def test_mock_related_text_scores_higher():
    """Texts that share words embed closer than unrelated ones -- enough signal
    to exercise the embedding retrieval path without a real model."""
    client = MockEmbeddingClient()
    query = client.embed(["the troll guards the bridge"])[0]
    related = client.embed(["a troll blocks the bridge"])[0]
    unrelated = client.embed(["the princess sings in the tower"])[0]
    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_empty_text_embeds_to_zero_vector():
    """No content -> the zero vector, which cosine_similarity treats as 0."""
    vec = MockEmbeddingClient().embed([""])[0]
    assert all(x == 0.0 for x in vec)
    assert cosine_similarity(vec, MockEmbeddingClient().embed(["anything"])[0]) == 0.0


# --- factory + environment helper --------------------------------------------


def test_create_embedding_client_mock():
    client = create_embedding_client(EmbeddingConfig(provider="mock"))
    assert isinstance(client, MockEmbeddingClient)


def test_create_embedding_client_unknown_provider_raises():
    with pytest.raises(ValueError):
        create_embedding_client(EmbeddingConfig(provider="not-a-provider"))


def test_from_env_unset_returns_none(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert embedding_client_from_env() is None


def test_from_env_mock_returns_client(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    assert isinstance(embedding_client_from_env(), MockEmbeddingClient)


def test_from_env_bad_provider_returns_none(monkeypatch):
    """An unusable provider degrades to None (keyword fallback), never raises."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "not-a-provider")
    assert embedding_client_from_env() is None


# --- real local backend (skipped offline) ------------------------------------


def test_local_embedding_client_smoke():
    """LocalEmbeddingClient embeds real text when model2vec + its model are
    available. Skips cleanly otherwise (no package, or no network to download
    the model) so the offline suite stays green."""
    pytest.importorskip("model2vec")
    try:
        client = LocalEmbeddingClient()
        vectors = client.embed(["the troll is hungry", "the troll is hungry"])
    except Exception as exc:  # download/network/model errors -> not a failure
        pytest.skip(f"model2vec model unavailable offline: {exc}")
    assert len(vectors) == 2
    assert len(vectors[0]) > 0
    assert vectors[0] == vectors[1]  # deterministic for identical input
