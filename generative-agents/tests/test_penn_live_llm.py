"""The live Penn server's REAL-LLM mode (issue #261, the live-LLM MVP).

Pins the contracts the ``--brain llm`` path stands on, fully offline (no SDK,
no network, no key -- a scripted "real-shaped" brain stands in for Anthropic):

* ``resolve_llm`` -- the mock default builds nothing; the llm mode merges the
  world YAML's ``llm:`` block with CLI overrides, accepts only Anthropic, and
  refuses to start without ``ANTHROPIC_API_KEY``;
* the world YAML declares the model (``claude-haiku-4-5``) and cost ceiling,
  and ``PennWorld``/``meta()`` carry them to the stepper and the viewer.

Run from ``generative-agents``::

    uv run pytest tests/test_penn_live_llm.py -v
"""

import sys
from pathlib import Path

import pytest

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); import them off the sim directory, like test_penn_live.py.
_SIM_DIR = Path(__file__).resolve().parents[2] / "godot-generative-agents" / "sim"
sys.path.insert(0, str(_SIM_DIR))

from penn_world import build_penn_world  # noqa: E402
from serve_penn import DEFAULT_LLM_MODEL, resolve_llm  # noqa: E402

# -------------------------------------------------------------- resolve_llm


def test_mock_brain_resolves_to_none_regardless_of_yaml():
    world_llm = {"provider": "anthropic", "model": "claude-haiku-4-5"}
    assert resolve_llm(world_llm, "mock") is None
    assert resolve_llm(None, "mock") is None


def test_llm_brain_merges_yaml_with_cli_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    world_llm = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }
    llm = resolve_llm(world_llm, "llm")
    assert llm == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }
    # CLI overrides win for one run; the YAML dict itself is never mutated.
    llm = resolve_llm(world_llm, "llm", model="claude-haiku-4-5-20251001", max_cost=0.5)
    assert llm["model"] == "claude-haiku-4-5-20251001"
    assert llm["max_cost_usd"] == 0.5
    assert world_llm["model"] == "claude-haiku-4-5"


def test_llm_brain_defaults_to_haiku_without_a_yaml_block(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    llm = resolve_llm(None, "llm")
    assert llm["provider"] == "anthropic"
    assert llm["model"] == DEFAULT_LLM_MODEL == "claude-haiku-4-5"


def test_llm_brain_accepts_only_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(SystemExit, match="anthropic"):
        resolve_llm({"provider": "openai"}, "llm")


def test_llm_brain_requires_the_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Other keys in the environment must never satisfy (or be read by) the gate.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-be-read")
    monkeypatch.setenv("LLM_API_KEY", "sk-should-never-be-read")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        resolve_llm({"provider": "anthropic"}, "llm")


# ------------------------------------------------- the world's llm: block


def test_world_yaml_declares_haiku():
    # The simulation config is the source of truth for WHICH model drives the
    # live cast: pin it so a silent model swap can't slip through review.
    pw = build_penn_world()
    assert pw.llm == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "max_cost_usd": 5.0,
    }
