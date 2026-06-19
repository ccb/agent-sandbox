"""Backend for the Generative Agents ("Smallville") port.

Builds the Smallville world on top of the ``text_adventure_games`` engine,
drives a small cast with the mock LLM client, and exports per-step movement
files that the upstream Django frontend replays. See ``generative-agents/README.md``.
"""
