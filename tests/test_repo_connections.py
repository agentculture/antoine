"""Tests for seer.repo.connections."""

from __future__ import annotations

from pathlib import Path

import pytest

from seer.cli._errors import SeerError
from seer.repo.connections import walk


def _mkrepo(
    root: Path,
    name: str,
    *,
    deps: list[str] | None = None,
    citations: list[tuple[str, str, str]] | None = None,
    vendored: list[tuple[str, str]] | None = None,
) -> Path:
    repo = root / name
    repo.mkdir()
    dep_block = ""
    if deps:
        dep_block = "dependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]\n"
    (repo / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n{dep_block}')
    if citations:
        rows = ["| local | source | sha |", "|---|---|---|"]
        rows += [f"| {l} | {s} | {sha} |" for (l, s, sha) in citations]
        (repo / "CITATION.md").write_text("\n".join(rows))
    if vendored:
        for skill_name, _source in vendored:
            (repo / ".claude" / "skills" / skill_name).mkdir(parents=True)
        rows = ["| name | source | version |", "|---|---|---|"]
        rows += [f"| {n} | {s} | x |" for (n, s) in vendored]
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs" / "skill-sources.md").write_text("\n".join(rows))
    return repo


def test_walk_depth_1_internal_and_external(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta", "external-pkg"])
    _mkrepo(tmp_path, "beta")
    result = walk(seed=a, roots=[tmp_path], depth=1)
    edges = {(e["from"], e["to"], e["type"]) for e in result["edges"]}
    assert ("alpha", "beta", "import") in edges
    assert ("alpha", "external-pkg", "import") in edges
    node_ids = {n["id"] for n in result["nodes"]}
    assert {"alpha", "beta", "external-pkg"} <= node_ids
    by_id = {n["id"]: n for n in result["nodes"]}
    assert by_id["beta"].get("external") is False
    assert by_id["external-pkg"].get("external") is True


def test_walk_depth_2_traverses_further(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta", deps=["gamma"])
    _mkrepo(tmp_path, "gamma")
    result = walk(seed=a, roots=[tmp_path], depth=2)
    node_ids = {n["id"] for n in result["nodes"]}
    assert {"alpha", "beta", "gamma"} <= node_ids


def test_walk_depth_all_walks_component(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta", deps=["gamma"])
    _mkrepo(tmp_path, "gamma", deps=["delta"])
    _mkrepo(tmp_path, "delta")
    _mkrepo(tmp_path, "unrelated")  # not connected
    result = walk(seed=a, roots=[tmp_path], depth="all")
    node_ids = {n["id"] for n in result["nodes"]}
    assert {"alpha", "beta", "gamma", "delta"} <= node_ids
    assert "unrelated" not in node_ids


def test_walk_citations_and_vendors_are_edges(tmp_path: Path) -> None:
    a = _mkrepo(
        tmp_path,
        "alpha",
        citations=[("file.py", "beta", "abc1234")],
        vendored=[("cicd", "gamma")],
    )
    _mkrepo(tmp_path, "beta")
    _mkrepo(tmp_path, "gamma")
    result = walk(seed=a, roots=[tmp_path], depth=1)
    edges = {(e["from"], e["to"], e["type"]) for e in result["edges"]}
    assert ("alpha", "beta", "cite") in edges
    assert ("alpha", "gamma", "vendor") in edges


def test_walk_per_node_error_inlined(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    beta = tmp_path / "beta"
    beta.mkdir()
    (beta / "pyproject.toml").write_text('[project\nname="beta"')  # malformed
    result = walk(seed=a, roots=[tmp_path], depth=1, with_profile=True)
    errs = result.get("walk_errors") or []
    assert any("beta" in e["node"] for e in errs)


def test_walk_strict_raises_on_per_node_error(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    beta = tmp_path / "beta"
    beta.mkdir()
    (beta / "pyproject.toml").write_text('[project\nname="beta"')  # malformed
    with pytest.raises(SeerError):
        walk(seed=a, roots=[tmp_path], depth=1, with_profile=True, strict=True)


def test_walk_invalid_depth_raises(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha")
    with pytest.raises(SeerError):
        walk(seed=a, roots=[tmp_path], depth="foo")
