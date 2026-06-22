"""Tests for codegen.extract using a MockLlmClient.

These exercise the extraction wiring -- prompt assembly, JSON parsing,
validation, retry on validation failure -- without making any network
calls. The gold Action Castle spec is fed back through the mock so we can
confirm extract -> emit -> import -> scenario still works when the LLM is
in the loop (even a fake one).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from text_adventure_games.codegen.extract import (
    ExtractionError,
    ExtractionPartial,
    RetryUnusable,
    WalkthroughCheckFailed,
    extract_spec,
)
from text_adventure_games.codegen import emit_module, validate
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.scenario import blocked, play, prop

FIXTURE = Path(__file__).parent / "fixtures" / "action_castle.spec.json"


def _gold_json() -> str:
    """The handwritten Action Castle spec, returned as a single JSON string."""
    with open(FIXTURE) as f:
        return f.read()


def _gold_dict() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


def _empty_pages():
    """Extraction needs `pages` but the mock ignores them; this keeps the
    test deterministic without touching PyMuPDF."""
    return []


def test_extract_returns_valid_gamespec_from_mock():
    mock = MockLlmClient(responses=[_gold_json()])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
    )
    assert validate(spec) == []
    assert spec.game_name == "Action Castle"
    assert spec.start_at == "Cottage"


def test_extract_strips_markdown_fences():
    """The mock returns the JSON wrapped in ```json fences; the extractor
    must tolerate models that ignore the 'no fences' instruction."""
    wrapped = "```json\n" + _gold_json() + "\n```"
    mock = MockLlmClient(responses=[wrapped])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
    )
    assert validate(spec) == []


def test_extract_retries_once_on_validation_failure_then_succeeds():
    """First response has a broken cross-reference; second is the gold spec."""
    bad = _gold_dict()
    bad["start_at"] = "Atlantis"
    mock = MockLlmClient(responses=[json.dumps(bad), _gold_json()])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
    )
    assert validate(spec) == []
    # Confirm both calls happened.
    assert len(mock.calls) == 2


def test_extract_raises_when_second_attempt_still_invalid():
    bad = _gold_dict()
    bad["start_at"] = "Atlantis"
    bad_json = json.dumps(bad)
    mock = MockLlmClient(responses=[bad_json, bad_json])
    with pytest.raises(ExtractionError):
        extract_spec(
            _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
        )


def test_extract_raises_on_empty_response():
    mock = MockLlmClient(responses=[None])
    with pytest.raises(ExtractionError):
        extract_spec(
            _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
        )


def test_extract_raises_on_malformed_json():
    mock = MockLlmClient(responses=["{not valid json"])
    with pytest.raises(ExtractionError):
        extract_spec(
            _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
        )


def test_retry_unparseable_response_falls_back_to_first_attempt_spec():
    """When the retry's response is empty / non-JSON, we should fall back to
    the first attempt's spec (so the CLI can still write artifacts for
    debugging) instead of throwing the work away.

    Reproduces the real-world failure mode where Anthropic returned a
    thinking-only response with no text content on the retry."""
    # First attempt: a valid-JSON spec with a broken cross-reference, which
    # forces a retry.
    bad = _gold_dict()
    bad["start_at"] = "Atlantis"
    # Second attempt: completely empty content (the same shape the user hit).
    mock = MockLlmClient(responses=[json.dumps(bad), ""])
    with pytest.raises(RetryUnusable) as exc_info:
        extract_spec(
            _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
        )
    # The exception carries the FIRST attempt's spec for the CLI to fall
    # back on. It's structurally broken (Atlantis isn't a location), but
    # that's the whole point -- the user needs the artifact to fix it.
    assert exc_info.value.spec is not None
    assert exc_info.value.spec.start_at == "Atlantis"
    # RetryUnusable inherits from ExtractionPartial inherits from
    # ExtractionError so existing `except ExtractionError` callers still
    # catch it.
    assert isinstance(exc_info.value, ExtractionPartial)
    assert isinstance(exc_info.value, ExtractionError)


def test_parse_error_includes_raw_response_in_message():
    """A non-JSON LLM response should be quoted in the error message so the
    user can see what came back without re-running with --verbose."""
    mock = MockLlmClient(responses=["Here is your spec:\n\n(coming soon!)"])
    with pytest.raises(ExtractionError) as exc_info:
        extract_spec(
            _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
        )
    assert "coming soon" in str(exc_info.value)


def test_solution_outline_prepass_adds_outline_to_extract_prompt():
    """When ``solution_outline=True`` (the default), extract_spec first asks
    the LLM for a winning-path outline, then quotes that outline back into
    the extract prompt as a constraint. Two calls total; the second one's
    user-message must contain the outline text."""
    outline = (
        "## Solution outline for Action Castle\n\n"
        "### Win condition\nThe player must end up reigning.\n\n"
        "### Step-by-step winning sequence\n"
        "1. get pole -> player carries pole\n"
        "2. catch fish with pole -> fish in inventory\n"
    )
    mock = MockLlmClient(responses=[outline, _gold_json()])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=True
    )
    assert validate(spec) == []
    # Two calls: outline pre-pass, then the spec extraction.
    assert len(mock.calls) == 2
    # The second call's user message must include the outline text so the
    # main extraction can use it as a constraint.
    extract_call = mock.calls[1]
    extract_user_msg = next(
        m["content"] for m in extract_call["messages"] if m["role"] == "user"
    )
    assert "SOLUTION OUTLINE" in extract_user_msg
    assert "catch fish with pole" in extract_user_msg


def test_solution_outline_prepass_soft_fails_on_empty_outline():
    """If the outline pre-pass returns nothing usable, extraction proceeds
    without it -- the outline is opportunistic, never required."""
    # Outline call returns empty; extraction call returns the gold spec.
    mock = MockLlmClient(responses=["", _gold_json()])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=True
    )
    assert validate(spec) == []
    # The extract prompt should NOT carry an outline block.
    extract_call = mock.calls[1]
    extract_user_msg = next(
        m["content"] for m in extract_call["messages"] if m["role"] == "user"
    )
    assert "SOLUTION OUTLINE" not in extract_user_msg


def test_walkthrough_failure_attaches_spec_for_debugging():
    """When the retried spec validates but the walkthrough does not win, the
    raised :class:`WalkthroughCheckFailed` carries the spec. The CLI uses
    that hook to keep emitting the module so the user has artifacts to
    debug instead of an empty output directory."""
    # Break the walkthrough by replacing it with a single, useless command.
    # Validation still passes; the walkthrough check fails on every round.
    # Pin max_retries=1 so this test stays a "single retry" scenario with
    # exactly two mock responses to feed.
    bad = _gold_dict()
    bad["walkthrough"] = {"commands": ["wait"], "expects_win": True}
    bad_json = json.dumps(bad)
    mock = MockLlmClient(responses=[bad_json, bad_json])
    with pytest.raises(WalkthroughCheckFailed) as exc_info:
        extract_spec(
            _empty_pages(),
            "Action Castle",
            llm_client=mock,
            solution_outline=False,
            max_retries=1,
        )
    assert exc_info.value.spec is not None
    assert exc_info.value.spec.game_name == "Action Castle"
    # WalkthroughCheckFailed must inherit from ExtractionError so existing
    # `except ExtractionError` callers still catch it.
    assert isinstance(exc_info.value, ExtractionError)


def test_multi_round_retry_eventually_succeeds():
    """With max_retries=2, an extraction that needs two rounds of edits
    still wins (3 total LLM calls, the 3rd returns a clean spec)."""
    bad = _gold_dict()
    bad["start_at"] = "Atlantis"  # validation error
    mock = MockLlmClient(responses=[json.dumps(bad), json.dumps(bad), _gold_json()])
    spec = extract_spec(
        _empty_pages(),
        "Action Castle",
        llm_client=mock,
        solution_outline=False,
        max_retries=2,
    )
    assert validate(spec) == []
    # Three calls: initial + two retries.
    assert len(mock.calls) == 3
    # The third call's user message must reference the prior spec
    # ("MODIFY the JSON spec you just returned"), confirming the LLM is
    # asked to edit, not regenerate.
    last_call_user_msg = (
        next(m["content"] for m in mock.calls[2]["messages"] if m["role"] == "user")[
            -1:
        ][0]
        if False
        else mock.calls[2]["messages"][-1]["content"]
    )
    assert "MODIFY" in last_call_user_msg


def test_multi_round_retry_raises_after_budget_with_latest_spec():
    """When max_retries=2 is exhausted with errors still present, the raise
    carries the LATEST parseable spec (not the original)."""
    bad_v1 = _gold_dict()
    bad_v1["start_at"] = "Atlantis"
    bad_v2 = _gold_dict()
    bad_v2["start_at"] = "Narnia"  # a different bad value -- proves we
    # got the latest, not the first
    bad_v3 = _gold_dict()
    bad_v3["start_at"] = "Eldorado"
    mock = MockLlmClient(
        responses=[json.dumps(bad_v1), json.dumps(bad_v2), json.dumps(bad_v3)]
    )
    with pytest.raises(RetryUnusable) as exc_info:
        extract_spec(
            _empty_pages(),
            "Action Castle",
            llm_client=mock,
            solution_outline=False,
            max_retries=2,
        )
    assert exc_info.value.spec.start_at == "Eldorado"


def test_full_pipeline_mocked_extract_then_emit_then_play(tmp_path):
    """End-to-end mocked pipeline: PDF (mocked away) -> extract -> emit ->
    import -> the canonical winning solution should still win."""
    mock = MockLlmClient(responses=[_gold_json()])
    spec = extract_spec(
        _empty_pages(), "Action Castle", llm_client=mock, solution_outline=False
    )
    src = emit_module(spec)
    path = tmp_path / "ac.py"
    path.write_text(src)
    module_spec = importlib.util.spec_from_file_location("ac_extracted", path)
    mod = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(mod)
    game = mod.build_game()

    # Pre-state matches the spec.
    assert blocked(game, "Drawbridge", "east")
    assert prop(game, "troll", "is_hungry")

    # Feed the troll (subset of the full solution -- enough to prove the
    # extracted spec wires up correctly).
    play(
        game,
        [
            "get pole",
            "go out",
            "go south",
            "catch fish with pole",
            "go north",
            "go north",
            "go east",
            "give fish to troll",
        ],
    )
    assert not blocked(game, "Drawbridge", "east")
    assert not prop(game, "troll", "is_hungry")
