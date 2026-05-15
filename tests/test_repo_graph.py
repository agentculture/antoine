"""Tests for seer.repo.graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from seer.cli._errors import SeerError
from seer.repo.graph import _safe, build_graph


def _mkrepo(root: Path, name: str, deps: list[str] | None = None) -> Path:
    p = root / name
    p.mkdir()
    dep_block = ""
    if deps:
        dep_block = "dependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]\n"
    (p / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n{dep_block}')
    return p


def test_build_graph_single_root(tmp_path: Path) -> None:
    _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta")
    _mkrepo(tmp_path, "gamma")
    g = build_graph([tmp_path])
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {"alpha", "beta", "gamma"}
    edges = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
    assert ("alpha", "beta", "import") in edges
    assert "graph TD" in g["mermaid"]
    assert "alpha" in g["mermaid"]
    assert "beta" in g["mermaid"]


def test_build_graph_multi_root_unions(tmp_path: Path) -> None:
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    _mkrepo(r1, "alpha")
    _mkrepo(r2, "beta")
    g = build_graph([r1, r2])
    assert {n["id"] for n in g["nodes"]} == {"alpha", "beta"}


def test_build_graph_surfaces_external_targets(tmp_path: Path) -> None:
    _mkrepo(tmp_path, "alpha", deps=["pyyaml"])
    _mkrepo(tmp_path, "beta")
    g = build_graph([tmp_path])
    ids = {n["id"] for n in g["nodes"]}
    assert "pyyaml" in ids
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id["pyyaml"].get("external") is True
    assert by_id["alpha"].get("external") is False


def test_build_graph_strict_raises_on_per_node_error(tmp_path: Path) -> None:
    """strict=True re-raises SeerError instead of inlining it."""
    _mkrepo(tmp_path, "alpha")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "pyproject.toml").write_text("[project\nname='bad'")  # malformed TOML
    with pytest.raises(SeerError):
        build_graph([tmp_path], strict=True)


def test_build_graph_non_strict_inlines_walk_errors(tmp_path: Path) -> None:
    """Non-strict build continues and surfaces per-node errors in walk_errors."""
    _mkrepo(tmp_path, "alpha")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "pyproject.toml").write_text("[project\nname='bad'")  # malformed TOML
    g = build_graph([tmp_path])
    assert any("bad" in e.get("node", "") for e in g["walk_errors"])


def test_safe_preserves_already_valid_identifier() -> None:
    """Pure alphanumeric+underscore names pass through unchanged."""
    assert _safe("alpha") == "alpha"
    assert _safe("beta_one") == "beta_one"


def test_safe_replaces_unsafe_characters() -> None:
    """Anything outside [A-Za-z0-9_] becomes _, with a hash suffix appended."""
    out = _safe("foo bar")
    assert " " not in out
    assert out.startswith("foo_bar_")  # sanitised + 6-char hash

    out = _safe("agentculture/culture")
    assert "/" not in out
    assert out.startswith("agentculture_culture_")

    out = _safe("`cicd`")
    assert "`" not in out


def test_safe_prevents_collisions_between_distinct_inputs() -> None:
    """Two distinct names that sanitise to the same prefix must still be distinct."""
    a = _safe("a-b")
    b = _safe("a_b")
    c = _safe("a.b")
    # Pre-hash all three would collapse to "a_b"; hash suffix keeps them distinct.
    assert a != b
    assert b != c
    assert a != c


def test_safe_prepends_n_for_digit_first_identifier() -> None:
    """Mermaid identifiers cannot start with a digit."""
    out = _safe("1foo")
    assert not out[0].isdigit()


def test_safe_handles_empty_string() -> None:
    """An empty input must still produce a usable Mermaid id."""
    assert _safe("") == "n_"
