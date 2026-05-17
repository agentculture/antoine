"""End-to-end tests for `python -m antoine.repo <verb>`."""

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


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "antoine.repo", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
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


def test_malformed_config_json_is_wrapped_not_leaked(tmp_path: Path) -> None:
    """Malformed config.json must surface as a structured AntoineError, not a Python traceback."""
    cfg_dir = tmp_path / ".claude" / "skills" / "repo-map"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text("{not valid json")
    repo = _mkrepo(tmp_path, "demo")
    result = _run("profile", str(repo), "--json", cwd=tmp_path)
    assert result.returncode == 2  # EXIT_ENV_ERROR
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stderr)
    assert payload["code"] == 2
    assert payload["kind"] == "env_error"
    assert "config.json" in payload["message"]
    assert "JSON" in payload["reason"] or "json" in payload["reason"].lower()
    assert payload["remediation"]


def test_connections_uses_config_default_depth_when_flag_omitted(tmp_path: Path) -> None:
    """When --depth is omitted, fall through to cfg.default_connections_depth."""
    # Three-level chain: alpha -> beta -> gamma (-> not in deps_runtime beyond)
    a = _mkrepo(tmp_path, "alpha", deps=["beta"])
    _mkrepo(tmp_path, "beta", deps=["gamma"])
    _mkrepo(tmp_path, "gamma")
    # Config sets depth=2; without it, depth would default to 1 and gamma would not be reached.
    cfg_dir = tmp_path / ".claude" / "skills" / "repo-map"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(json.dumps({"default_connections_depth": 2}))
    result = _run("connections", str(a), "--root", str(tmp_path), "--json", cwd=tmp_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    node_ids = {n["id"] for n in payload["data"]["nodes"]}
    assert {"alpha", "beta", "gamma"} <= node_ids, (
        "depth=2 from config should have reached gamma; got " f"{node_ids}"
    )


def test_profile_basic_flag_skips_tier2(tmp_path: Path) -> None:
    """``profile --basic --json`` returns JSON with github_state and pypi_state as None.

    The test verifies that the --basic flag is wired through the argparse layer
    into profile_shallow.  No network calls are made because no git remote or
    PyPI name resolves to a real endpoint in the tmp fixture repo.
    """
    repo = _mkrepo(tmp_path, "demo")
    result = _run("profile", str(repo), "--basic", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert data.get("github_state") is None
    assert data.get("pypi_state") is None
