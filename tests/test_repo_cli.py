"""End-to-end tests for `python -m seer.repo <verb>`."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _mkrepo(root: Path, name: str, deps: list[str] | None = None) -> Path:
    p = root / name
    p.mkdir()
    dep_block = (
        "dependencies = [" + ", ".join(f'"{d}"' for d in (deps or [])) + "]\n" if deps else ""
    )
    (p / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "0.1.0"\n{dep_block}')
    return p


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "seer.repo", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_profile_markdown_default(tmp_path: Path) -> None:
    repo = _mkrepo(tmp_path, "demo")
    result = _run("profile", str(repo))
    assert result.returncode == 0
    assert result.stdout.startswith("# demo")
    assert "**Version:** 0.1.0" in result.stdout
    assert result.stderr == ""


def test_profile_json(tmp_path: Path) -> None:
    repo = _mkrepo(tmp_path, "demo")
    result = _run("profile", str(repo), "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["name"] == "demo"
    assert result.stderr == ""


def test_profile_no_manifest_renders_unknown_language(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / ".claude" / "skills").mkdir(parents=True)  # qualifies as a repo
    result = _run("profile", str(bare))
    assert result.returncode == 0
    assert "**Manifest:** none (unknown)" in result.stdout


def test_profile_path_not_directory_errors(tmp_path: Path) -> None:
    result = _run("profile", str(tmp_path / "nope"))
    assert result.returncode == 1
    assert "error:" in result.stderr
    assert "reason:" in result.stderr
    assert "hint:" in result.stderr


def test_profile_path_not_directory_json(tmp_path: Path) -> None:
    result = _run("profile", str(tmp_path / "nope"), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["code"] == 1
    assert payload["kind"] == "user_error"
    assert "reason" in payload
    assert "remediation" in payload


def test_connections_markdown(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta")
    result = _run("connections", str(a), "--root", str(tmp_path))
    assert result.returncode == 0
    assert "alpha — connections" in result.stdout
    assert "## Imports" in result.stdout
    assert "beta" in result.stdout


def test_connections_invalid_depth(tmp_path: Path) -> None:
    a = _mkrepo(tmp_path, "alpha")
    result = _run("connections", str(a), "--root", str(tmp_path), "--depth", "foo")
    assert result.returncode == 1
    assert "Invalid --depth" in result.stderr


def test_graph_markdown(tmp_path: Path) -> None:
    _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta")
    result = _run("graph", str(tmp_path))
    assert result.returncode == 0
    assert "# Workspace graph" in result.stdout
    assert "alpha" in result.stdout
    assert "beta" in result.stdout
    assert "```mermaid" in result.stdout


def test_no_args_prints_help() -> None:
    result = _run()
    assert result.returncode == 0
    assert "usage:" in result.stdout
