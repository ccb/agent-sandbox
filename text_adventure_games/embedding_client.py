"""Provider-agnostic embedding client abstraction (issue #76).

Memory retrieval scores a memory's *relevance* to the current situation. By
default that score is keyword overlap (``memory.relevance_score``) -- free,
offline, and good enough for short memory snippets. This module adds an optional
*semantic* relevance: turn text into a vector and compare vectors with cosine
similarity, so "I gave the troll a fish" can be relevant to "the bridge guardian
is hungry" even with no shared words.

It mirrors ``llm_client.py``: a small :class:`EmbeddingClient` Protocol, concrete
adapters, a ``create_embedding_client`` factory, and ``embedding_client_from_env``.
Everything works with no SDK installed -- imports are lazy, so the base package
has no hard dependency. The backends:

* :class:`MockEmbeddingClient` -- a deterministic, dependency-free stand-in. It
  hashes content words into a fixed-length count vector, so overlapping text
  scores higher. The whole test suite uses it: no model, no network, and the
  same input always yields the same vector (it uses :mod:`hashlib`, not the
  per-process-salted built-in ``hash``).
* :class:`LocalEmbeddingClient` -- **the default real backend.** A small static
  model run locally via ``model2vec`` (lazy-imported; ``uv sync --extra
  embeddings``). Free and offline after the model downloads once, with no heavy
  ``torch`` dependency.
* :class:`SentenceTransformerEmbeddingClient` -- a local transformer model via
  ``sentence-transformers`` (lazy-imported; ``uv sync --extra embeddings-st``).
  Higher quality than model2vec, at the cost of pulling ``torch``.
* :class:`OpenAIEmbeddingClient` -- the hosted OpenAI embeddings API
  (lazy-imported; ``uv sync --extra openai``; needs an API key and network).

Other backends (e.g. Voyage, or raw Hugging Face ``transformers`` with manual
pooling) can join later behind this same seam; see
``docs/design/memory-retrieval-embeddings.md``.

Usage::

    from text_adventure_games.embedding_client import (
        EmbeddingConfig, create_embedding_client,
    )

    client = create_embedding_client(EmbeddingConfig(provider="local"))
    [vec] = client.embed(["the troll is hungry"])
"""

from __future__ import annotations

import os
import re
import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Union

from .enums import EmbeddingProvider

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbeddingClient(Protocol):
    """Minimal interface for turning text into vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings, returning one vector (a list of floats)
        per input, in order. Batched so a backend can amortize model/API calls."""
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingConfig:
    """Configuration for creating an embedding client.

    Shaped like :class:`~text_adventure_games.llm_client.LlmConfig` so hosted
    backends can reuse ``api_key`` / ``base_url`` later; the local and mock
    backends only read ``provider`` and ``model``.
    """

    # An :class:`EmbeddingProvider` member or a plain string ("local", "mock").
    provider: Union[EmbeddingProvider, str]
    model: str | None = None  # defaults per provider
    api_key: str | None = None  # falls back to env vars (hosted backends)
    base_url: str | None = None  # e.g. a proxy (hosted backends)


# ---------------------------------------------------------------------------
# Mock adapter (deterministic, offline, no dependencies)
# ---------------------------------------------------------------------------

# Split on any run of non-alphanumeric characters (matches memory.py's tokenizer
# closely enough that overlapping words land in overlapping dimensions).
_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_MOCK_DIM = 64


def _hashed_dim(token: str, dim: int) -> int:
    """Map a token to a stable dimension index in ``[0, dim)``.

    Uses :mod:`hashlib` rather than the built-in ``hash`` so the index is stable
    across processes -- mock vectors must be reproducible for byte-identical
    replays and for embeddings stored in save files.
    """
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


class MockEmbeddingClient:
    """Deterministic, offline embedding stand-in (the test suite's backend).

    Embeds text as a hashed bag-of-words count vector: each content word bumps
    one dimension. Texts that share words share dimensions, so their cosine
    similarity is higher -- enough to exercise the embedding retrieval path
    without a model or a network, and fully reproducible.
    """

    def __init__(self, config: EmbeddingConfig | None = None, dim: int = _MOCK_DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.split(text.lower()):
            if token:
                vec[_hashed_dim(token, self.dim)] += 1.0
        return vec


# ---------------------------------------------------------------------------
# Local adapter (model2vec static embeddings, lazy-imported)
# ---------------------------------------------------------------------------

_DEFAULT_LOCAL_MODEL = "minishlab/potion-base-8M"


class LocalEmbeddingClient:
    """Embeds text with a small static model run locally via ``model2vec``.

    model2vec distills a sentence-transformer into static token vectors, so it
    needs only the lightweight ``model2vec`` package (no ``torch``) and runs on
    CPU in milliseconds. The model downloads from the Hugging Face hub on first
    use, then is cached locally; after that it works offline.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        try:
            from model2vec import StaticModel
        except ImportError:
            raise ImportError(
                "The model2vec package is required for local embeddings. "
                "Install with: pip install model2vec  (or: uv sync --extra embeddings)"
            )
        model = (config.model if config else None) or _DEFAULT_LOCAL_MODEL
        self._model = StaticModel.from_pretrained(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # encode() returns a numpy array; hand back plain Python lists so the
        # rest of the engine (and save files) never see numpy types.
        vectors = self._model.encode(list(texts))
        return [[float(x) for x in vector] for vector in vectors]


# ---------------------------------------------------------------------------
# sentence-transformers adapter (local transformer model, lazy-imported)
# ---------------------------------------------------------------------------

_DEFAULT_ST_MODEL = "all-MiniLM-L6-v2"


class SentenceTransformerEmbeddingClient:
    """Embeds text with a local transformer model via ``sentence-transformers``.

    Higher quality than the static model2vec backend, but it pulls in ``torch``
    (a heavy install). ``encode()`` handles tokenization, mean-pooling, and
    normalization. The model downloads from the Hugging Face hub on first use,
    then runs offline. A future backend could use the raw ``transformers``
    library with manual pooling; see the design doc.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "The sentence-transformers package is required for this backend. "
                "Install with: pip install sentence-transformers  "
                "(or: uv sync --extra embeddings-st)"
            )
        model = (config.model if config else None) or _DEFAULT_ST_MODEL
        self._model = SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts))
        return [[float(x) for x in vector] for vector in vectors]


# ---------------------------------------------------------------------------
# OpenAI adapter (hosted API, lazy-imported)
# ---------------------------------------------------------------------------

_DEFAULT_OPENAI_EMBED_MODEL = "text-embedding-3-small"


class OpenAIEmbeddingClient:
    """Embeds text with the hosted OpenAI embeddings API (lazy-imported).

    Needs the ``openai`` SDK, an API key (``EmbeddingConfig.api_key`` or the
    ``OPENAI_API_KEY`` env var), and a network connection. ``text-embedding-3-small``
    is the default model -- cheap and good for short memory snippets;
    ``text-embedding-3-large`` is available but overkill here.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "The openai package is required for OpenAI embeddings. "
                "Install with: pip install openai  (or: uv sync --extra openai)"
            )
        cfg = config or EmbeddingConfig(provider="openai")
        api_key = cfg.api_key or os.environ.get("OPENAI_API_KEY")
        kwargs: dict = {"api_key": api_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = cfg.model or _DEFAULT_OPENAI_EMBED_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        return [list(item.embedding) for item in response.data]


# ---------------------------------------------------------------------------
# Factory + environment helper
# ---------------------------------------------------------------------------

# Keyed by EmbeddingProvider members; since EmbeddingProvider IS a str, a lookup
# with the raw string "local" still resolves.
_PROVIDERS = {
    EmbeddingProvider.LOCAL: LocalEmbeddingClient,
    EmbeddingProvider.MOCK: MockEmbeddingClient,
    EmbeddingProvider.OPENAI: OpenAIEmbeddingClient,
    EmbeddingProvider.SENTENCE_TRANSFORMERS: SentenceTransformerEmbeddingClient,
}


def create_embedding_client(config: EmbeddingConfig) -> EmbeddingClient:
    """Create an embedding client from a config, or raise on an unknown provider."""
    provider = str(config.provider).lower()
    if provider not in _PROVIDERS:
        choices = [str(p) for p in _PROVIDERS]
        raise ValueError(
            f"Unknown embedding provider '{provider}'. Choose from: {choices}"
        )
    return _PROVIDERS[provider](config)


def embedding_client_from_env() -> EmbeddingClient | None:
    """Create an embedding client from environment variables, or return None.

    Reads ``EMBEDDING_PROVIDER`` ("local", "sentence-transformers", "openai", or
    "mock"), plus optional ``EMBEDDING_MODEL`` / ``EMBEDDING_API_KEY`` /
    ``EMBEDDING_BASE_URL``. Returns ``None`` when no provider is set or the client
    can't be created (e.g. a missing SDK), so callers fall back to keyword-overlap
    relevance -- the same graceful pattern as ``llm_client.client_from_env``.
    """
    provider = os.environ.get("EMBEDDING_PROVIDER")
    if not provider:
        return None
    try:
        config = EmbeddingConfig(
            provider=provider,
            model=os.environ.get("EMBEDDING_MODEL"),
            api_key=os.environ.get("EMBEDDING_API_KEY"),
            base_url=os.environ.get("EMBEDDING_BASE_URL"),
        )
        return create_embedding_client(config)
    except (ImportError, ValueError) as e:
        print(f"Warning: Could not create embedding client: {e}")
        return None
