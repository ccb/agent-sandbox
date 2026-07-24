"""The script bake's --persist defaults on (#752).

Live serving already persists by default (#713); this closes the last gap so
EVERY entry point (Godot viewer / script bake / web companion) default-saves
the run under the one shared store. Now a bare `generate_penn_replay.py`
writes a runs/<run_id>/ entry unless you opt out with --no-persist. Pins the
CLI default via the parser seam, offline -- no sim run, no real runs/ dir
touched (mirrors test_persist_default_713.py for serve_penn)."""

import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from generate_penn_replay import _build_parser  # noqa: E402


def test_persist_defaults_on():
    args = _build_parser().parse_args([])
    assert args.persist is True


def test_no_persist_opts_out():
    args = _build_parser().parse_args(["--no-persist"])
    assert args.persist is False


def test_persist_flag_is_still_accepted():
    # Back-compat no-op alias for existing docs/commands that say --persist.
    args = _build_parser().parse_args(["--persist"])
    assert args.persist is True
