# Memory retrieval and embeddings

The default relevance score uses deterministic keyword overlap. Forks may enable
the optional local embedding backends for semantic similarity. Embeddings affect
ranking only; recency, importance, record/token limits, and perception boundaries
still apply.

No embedding provider is required for the Penn mock workflow. Tests should use
the deterministic mock embedding client and must not download models or contact a
hosted service.
