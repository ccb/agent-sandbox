"""Tests for the embedding client layer (issue #76).

The mock backend is deterministic and dependency-free, so these run offline with
no API key and no model download -- the same contract as the mock LLM client.
The one test that touches the real local model (model2vec) skips itself when the
package or its model download isn't available.
"""

import importlib.util

import pytest

from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    MockEmbeddingClient,
    LocalEmbeddingClient,
    OpenAIEmbeddingClient,
    SentenceTransformerEmbeddingClient,
    create_embedding_client,
    embedding_client_from_env,
    _PROVIDERS,
)
from text_adventure_games.memory import cosine_similarity


def _installed(module: str) -> bool:
    """True if *module* can be imported (used to branch tests on optional SDKs)."""
    return importlib.util.find_spec(module) is not None


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


# --- additional backends: OpenAI + sentence-transformers ---------------------


def test_all_providers_registered():
    assert {str(k) for k in _PROVIDERS} == {
        "local",
        "mock",
        "openai",
        "sentence-transformers",
    }


def test_openai_backend_create():
    """Registered in the factory. Builds when openai is installed (no network at
    construction time), else raises a clear ImportError."""
    cfg = EmbeddingConfig(provider="openai", api_key="test-key")
    if _installed("openai"):
        assert isinstance(create_embedding_client(cfg), OpenAIEmbeddingClient)
    else:
        with pytest.raises(ImportError):
            create_embedding_client(cfg)


def test_sentence_transformers_backend_create():
    """Registered in the factory. Builds when installed (may download a model;
    skip on failure), else raises a clear ImportError."""
    cfg = EmbeddingConfig(provider="sentence-transformers")
    if _installed("sentence_transformers"):
        try:
            client = create_embedding_client(cfg)
        except Exception as exc:  # model download/network issues -> not a failure
            pytest.skip(f"sentence-transformers model unavailable offline: {exc}")
        assert isinstance(client, SentenceTransformerEmbeddingClient)
    else:
        with pytest.raises(ImportError):
            create_embedding_client(cfg)


def test_from_env_missing_sdk_returns_none(monkeypatch):
    """A backend whose SDK isn't installed degrades to None (keyword fallback),
    never raising -- so an unconfigured environment stays playable."""
    if not _installed("openai"):
        provider = "openai"
    elif not _installed("sentence_transformers"):
        provider = "sentence-transformers"
    else:
        pytest.skip("both optional SDKs installed; missing-SDK path not exercisable")
    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)
    assert embedding_client_from_env() is None
