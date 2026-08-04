"""Offline tests for the static Penn prompt-chain data."""

from pathlib import Path

import pytest

from text_adventure_games.promptviz import (
    ChainSpec,
    Edge,
    Node,
    graph_elements,
    load_spec,
    node_prompt,
)

ROOT = Path(__file__).resolve().parents[1]
PENN_CHAIN = (
    ROOT / "godot-generative-agents" / "backend" / "promptviz_chains" / "cognition.yaml"
)
PKG = "text_adventure_games.prompt_templates"


def test_penn_cognition_spec_loads_and_validates():
    spec = load_spec(PENN_CHAIN)
    assert spec.name == "cognition"
    assert spec.nodes
    assert spec.edges
    assert {"start", "gate", "decision"} & {node.kind for node in spec.nodes}


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


def test_node_template_package_override():
    spec = ChainSpec(
        "x",
        "",
        "pkg.default",
        [
            Node("a", "A", "decision", template="t"),
            Node("b", "B", "decision", template="t", templates="pkg.other"),
        ],
        [],
    )
    assert spec.templates_for(spec.node("a")) == "pkg.default"
    assert spec.templates_for(spec.node("b")) == "pkg.other"


def test_every_templated_penn_node_has_renderable_prompt_metadata():
    spec = load_spec(PENN_CHAIN)
    rendered = 0
    for node in spec.nodes:
        if not node.template:
            continue
        detail = node_prompt(
            node.template,
            node.example_vars,
            spec.templates_for(node),
        )
        assert "error" not in detail, (node.id, detail)
        assert detail["rendered"], node.id
        assert detail["raw_source"], node.id
        rendered += 1
    assert rendered > 0


def test_node_prompt_unknown_template_is_friendly():
    detail = node_prompt("nope_not_real", None, PKG)
    assert "error" in detail
    assert "rendered" not in detail


def test_graph_elements_match_the_spec():
    spec = load_spec(PENN_CHAIN)
    elements = graph_elements(spec)
    assert len(elements["nodes"]) == len(spec.nodes)
    assert len(elements["edges"]) == len(spec.edges)
    assert all(node["data"]["fired"] is False for node in elements["nodes"])
    assert all(edge["data"]["fired"] is False for edge in elements["edges"])
    assert {node["data"]["id"] for node in elements["nodes"]} == {
        node.id for node in spec.nodes
    }
