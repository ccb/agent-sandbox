"""Offline tests for the prompt-chain visualizer (text_adventure_games.promptviz).

Everything here runs without a network, a browser, or an LLM: rendering goes
through prompt_templates.render() (no model call), and the Flask app is exercised
with test_client(). The Cytoscape/dagre front-end is verified separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from text_adventure_games import prompt_templates
from text_adventure_games import promptviz
from text_adventure_games.promptviz import (
    ChainSpec,
    Edge,
    Node,
    load_runlog,
    load_spec,
    map_to_chain,
    node_prompt,
)
from text_adventure_games.promptviz.app import create_app

CHAINS_DIR = Path(promptviz.__file__).parent / "chains"
ACTION_CASTLE = CHAINS_DIR / "action_castle.yaml"
PKG = "text_adventure_games.prompt_templates"


# --------------------------------------------------------------------------- #
# spec.py
# --------------------------------------------------------------------------- #
def test_action_castle_spec_loads_and_validates():
    spec = load_spec(ACTION_CASTLE)
    assert spec.name == "action_castle"
    ids = {n.id for n in spec.nodes}
    assert {"turn_start", "decide", "precondition_gate", "narrate_npc"} <= ids
    # the reflect-and-retry back-edge is the spec's signature loop
    assert any(
        e.source == "precondition_gate"
        and e.target == "decide"
        and e.condition == "precondition_failure"
        for e in spec.edges
    )


def test_validate_rejects_duplicate_ids():
    spec = ChainSpec(
        "x", "", PKG, [Node("a", "A", "start"), Node("a", "A2", "start")], []
    )
    with pytest.raises(ValueError, match="duplicate node ids"):
        spec.validate()


def test_validate_rejects_dangling_edge():
    spec = ChainSpec("x", "", PKG, [Node("a", "A", "start")], [Edge("a", "ghost")])
    with pytest.raises(ValueError, match="unknown target"):
        spec.validate()


def test_validate_rejects_unknown_kind():
    spec = ChainSpec("x", "", PKG, [Node("a", "A", "wat")], [])
    with pytest.raises(ValueError, match="unknown kind"):
        spec.validate()


def test_validate_rejects_template_on_gate():
    spec = ChainSpec(
        "x", "", PKG, [Node("g", "G", "gate", template="npc_decision")], []
    )
    with pytest.raises(ValueError, match="control point"):
        spec.validate()


def test_validate_allows_templateless_decision():
    # gen-agents' mock decision has no prompt yet -- this must be allowed.
    spec = ChainSpec("x", "", PKG, [Node("d", "D", "decision")], [])
    assert spec.validate() is spec


# --------------------------------------------------------------------------- #
# templates.py
# --------------------------------------------------------------------------- #
def test_every_templated_node_renders_like_the_engine():
    spec = load_spec(ACTION_CASTLE)
    for n in spec.nodes:
        if not n.template:
            continue
        detail = node_prompt(n.template, n.example_vars, spec.templates)
        assert "error" not in detail, detail
        assert detail["rendered"], n.id
        # node_prompt must defer to the package's own render() (byte-identical),
        # using the template's sample when the node sets no example_vars.
        variables = n.example_vars or detail["frontmatter"]["sample"]
        assert detail["rendered"] == prompt_templates.render(n.template, **variables)
        assert detail["frontmatter"]["name"] == n.template
        assert detail["raw_source"]


def test_node_prompt_npc_decision_shape():
    detail = node_prompt("npc_decision", None, PKG)
    assert detail["rendered"].startswith("You are an NPC")
    assert "persona" in detail["frontmatter"]["inputs"]


def test_node_prompt_unknown_template_is_friendly():
    detail = node_prompt("nope_not_real", None, PKG)
    assert "error" in detail
    assert "rendered" not in detail


# --------------------------------------------------------------------------- #
# overlay.py
# --------------------------------------------------------------------------- #
def _write_runlog(path: Path, lines: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(o) for o in lines) + "\n", encoding="utf-8")
    return path


def test_overlay_maps_decision_and_retry(tmp_path):
    spec = load_spec(ACTION_CASTLE)
    sys_decide = prompt_templates.render("npc_decision", persona="I am the guard.")
    runlog = _write_runlog(
        tmp_path / "run.jsonl",
        [
            {"kind": "run", "seed": 7, "provider": "mock", "model": "mock"},
            {
                "kind": "call",
                "turn": 1,
                "actor": "guard",
                "attempt": 0,
                "messages": [
                    {"role": "system", "content": sys_decide},
                    {"role": "user", "content": "You see a door."},
                ],
                "response": "Action: wait",
            },
            {
                "kind": "call",
                "turn": 1,
                "actor": "guard",
                "attempt": 1,
                "messages": [
                    {"role": "system", "content": sys_decide},
                    {"role": "user", "content": "That failed."},
                ],
                "response": "Action: wait",
            },
            {"kind": "summary", "calls": 2},
        ],
    )
    ov = map_to_chain(load_runlog(runlog), spec)
    assert ov.has_prompts and ov.call_count == 2
    assert "decide" in ov.fired_nodes
    # routing always passes the gate / starts the turn (non-LLM, added structurally)
    assert {"precondition_gate", "turn_start"} <= ov.fired_nodes
    assert ("precondition_gate", "decide") in ov.fired_edges  # retry back-edge lit
    assert len(ov.actuals["decide"]) == 2


def test_overlay_without_prompts_notes_log_prompts(tmp_path):
    spec = load_spec(ACTION_CASTLE)
    runlog = _write_runlog(
        tmp_path / "run.jsonl",
        [
            {"kind": "run", "provider": "mock", "model": "mock"},
            {"kind": "call", "turn": 1, "actor": "guard", "attempt": 0},
            {"kind": "summary", "calls": 1},
        ],
    )
    ov = map_to_chain(load_runlog(runlog), spec)
    assert not ov.has_prompts
    assert not ov.fired_nodes
    assert "log_prompts" in ov.note


# --------------------------------------------------------------------------- #
# app.py (Flask JSON API)
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    return create_app([load_spec(ACTION_CASTLE)]).test_client()


def test_healthz(client):
    assert client.get("/healthz").get_data(as_text=True) == "ok"


def test_index_serves_page(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="cy"' in html
    assert "promptviz.js" in html


def test_chains_endpoint(client):
    data = client.get("/chains").get_json()
    assert any(c["id"] == "action_castle" for c in data)


def test_graph_json(client):
    g = client.get("/graph.json?chain=action_castle").get_json()
    assert g["chain"] == "action_castle"
    assert len(g["elements"]["nodes"]) == 10
    assert any(
        e["data"]["condition"] == "precondition_failure" for e in g["elements"]["edges"]
    )


def test_prompt_endpoint_templated_node(client):
    p = client.get("/prompt/action_castle/decide").get_json()
    assert p["template"] == "npc_decision"
    assert p["rendered"].startswith("You are an NPC")


def test_prompt_endpoint_gate_has_no_template(client):
    p = client.get("/prompt/action_castle/precondition_gate").get_json()
    assert p["template"] is None
    assert "no prompt" in p["note"].lower()


def test_unknown_node_and_chain_404(client):
    assert client.get("/prompt/action_castle/nope").status_code == 404
    assert client.get("/graph.json?chain=nope").status_code == 404


def test_overlay_flows_through_app(tmp_path):
    spec = load_spec(ACTION_CASTLE)
    sys_decide = prompt_templates.render("npc_decision", persona="I am the guard.")
    runlog = _write_runlog(
        tmp_path / "run.jsonl",
        [
            {"kind": "run", "provider": "mock", "model": "mock"},
            {
                "kind": "call",
                "turn": 1,
                "actor": "guard",
                "attempt": 0,
                "messages": [{"role": "system", "content": sys_decide}],
                "response": "Action: wait",
            },
        ],
    )
    client = create_app([spec], runlog_path=str(runlog)).test_client()
    g = client.get("/graph.json?chain=action_castle").get_json()
    assert g["overlay"]["active"] and g["overlay"]["call_count"] == 1
    fired = [n["data"]["id"] for n in g["elements"]["nodes"] if n["data"]["fired"]]
    assert "decide" in fired
    p = client.get("/prompt/action_castle/decide").get_json()
    assert len(p["actual"]) == 1
