"""Anchor pytest's import path.

This directory (``generative-agents/``) can't be a Python package — the hyphen
isn't a legal identifier — so ``backend`` is imported as a top-level package
instead. pytest inserts the directory containing this conftest.py onto
``sys.path``, which makes ``import backend`` work no matter where pytest is
invoked from.
"""
