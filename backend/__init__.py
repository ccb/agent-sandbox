"""The project's simulation backend (issue #179).

The one canonical package behind every frontend: it builds the generative-agents
worlds (Smallville and the Penn campus) on top of the ``text_adventure_games``
engine and drives their casts, and it hosts the headless HTTP API (``backend.api``,
a FastAPI app) that any out-of-process renderer polls for the typed world-state
snapshot + change feed. Extracted from ``generative-agents/backend`` in #167 and
renamed here so it reads as the shared backend rather than one frontend's folder.
See ``generative-agents/README.md`` and ``backend/api.py``.
"""
