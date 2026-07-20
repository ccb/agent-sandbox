"""The project's simulation backend (issue #179).

The one canonical package behind the Godot viewer: it builds the generative-agents
world -- primarily the UPenn campus -- on top of the ``text_adventure_games`` engine
and drives its cast, and it hosts the headless HTTP API (``backend.api``, a FastAPI
app) that the out-of-process renderer polls for the typed world-state snapshot +
change feed. Extracted from ``generative-agents/backend`` in #167 and folded under
``godot-generative-agents/`` in #399. See ``backend/README.md`` and ``backend/api.py``.
"""
