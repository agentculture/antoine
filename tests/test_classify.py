"""Tests for seer.lookup.classify."""

from __future__ import annotations

from pathlib import Path

import pytest

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.lookup.classify import classify


def test_classify_empty_repo_returns_no_tags(tmp_path: Path) -> None:
    """Empty dir with no manifest, no markers — empty tag list, unknown language."""
    repo = tmp_path / "empty"
    repo.mkdir()
    result = classify(repo)
    assert result["path"] == str(repo)
    assert result["manifest"] is None
    assert result["language"] == "unknown"
    assert result["tags"] == []


def test_classify_path_not_found_raises_seer_error(tmp_path: Path) -> None:
    """Nonexistent path raises SeerError with EXIT_USER_ERROR code."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SeerError) as exc:
        classify(missing)
    assert exc.value.code == EXIT_USER_ERROR
    assert "path not found" in exc.value.message


def test_classify_path_is_file_raises_seer_error(tmp_path: Path) -> None:
    """File path raises SeerError with EXIT_USER_ERROR code and 'directory' hint."""
    f = tmp_path / "regular_file.txt"
    f.write_text("hi")
    with pytest.raises(SeerError) as exc:
        classify(f)
    assert exc.value.code == EXIT_USER_ERROR
    assert "directory" in exc.value.message


def test_classify_python_manifest_fires_python_tag(tmp_path: Path) -> None:
    repo = tmp_path / "py"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "py"\nversion = "0.1.0"\n')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    py_tag = next(t for t in result["tags"] if t["name"] == "python")
    assert py_tag["evidence"] == "pyproject.toml present"
    assert result["manifest"] == "pyproject.toml"
    assert result["language"] == "python"


def test_classify_node_manifest_fires_node_tag(tmp_path: Path) -> None:
    repo = tmp_path / "node"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "node-app", "version": "0.1.0"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "node" in tag_names
    assert "python" not in tag_names
    node_tag = next(t for t in result["tags"] if t["name"] == "node")
    assert node_tag["evidence"] == "package.json present"
    assert result["manifest"] == "package.json"
    assert result["language"] == "node"


def test_classify_bash_only_fires_bash_tag(tmp_path: Path) -> None:
    repo = tmp_path / "bash"
    repo.mkdir()
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "foo.sh").write_text("#!/bin/bash\n")
    (scripts / "bar.sh").write_text("#!/bin/bash\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "bash" in tag_names
    assert "python" not in tag_names
    assert "node" not in tag_names
    bash_tag = next(t for t in result["tags"] if t["name"] == "bash")
    assert "scripts/" in bash_tag["evidence"]
    assert "2 .sh file" in bash_tag["evidence"]


def test_classify_polyglot_both_python_and_node_tags(tmp_path: Path) -> None:
    """Both manifests present → both tags fire; scalar language defaults to python."""
    repo = tmp_path / "poly"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "poly"\n')
    (repo / "package.json").write_text('{"name": "poly"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    assert "node" in tag_names
    assert result["language"] == "python"
    assert result["manifest"] == "pyproject.toml"


def test_classify_python_cli_with_entry_point(tmp_path: Path) -> None:
    repo = tmp_path / "tool"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "tool"\nversion = "0.1.0"\n'
        '[project.scripts]\ntool = "tool.cli:main"\n'
    )
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "cli" in tag_names
    cli_tag = next(t for t in result["tags"] if t["name"] == "cli")
    assert "tool" in cli_tag["evidence"]
    assert "tool.cli:main" in cli_tag["evidence"]


def test_classify_node_cli_with_bin(tmp_path: Path) -> None:
    repo = tmp_path / "ncli"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "ncli", "bin": {"ncli": "./cli.js"}}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "cli" in tag_names
    cli_tag = next(t for t in result["tags"] if t["name"] == "cli")
    assert "ncli" in cli_tag["evidence"]


def test_classify_python_library_fires_library_tag(tmp_path: Path) -> None:
    repo = tmp_path / "lib"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "lib"\n')
    pkg = repo / "lib"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    lib_tag = next(t for t in result["tags"] if t["name"] == "library")
    assert "lib/__init__.py" in lib_tag["evidence"]


def test_classify_library_src_layout(tmp_path: Path) -> None:
    repo = tmp_path / "srclib"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "srclib"\n')
    pkg = repo / "src" / "srclib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    lib_tag = next(t for t in result["tags"] if t["name"] == "library")
    assert "src/srclib/__init__.py" in lib_tag["evidence"]


def test_classify_library_without_scripts_no_cli_tag(tmp_path: Path) -> None:
    repo = tmp_path / "libnocli"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "libnocli"\n')
    pkg = repo / "libnocli"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    assert "cli" not in tag_names


def test_classify_dockerized_from_dockerfile(tmp_path: Path) -> None:
    repo = tmp_path / "docked"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM python:3.12\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "dockerized" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "dockerized")
    assert tag["evidence"] == "Dockerfile present"


def test_classify_dockerized_from_compose_only(tmp_path: Path) -> None:
    repo = tmp_path / "composed"
    repo.mkdir()
    (repo / "docker-compose.yml").write_text("version: '3'\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "dockerized" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "dockerized")
    assert "docker-compose.yml" in tag["evidence"]


def test_classify_agentculture_sibling(tmp_path: Path) -> None:
    repo = tmp_path / "sib"
    repo.mkdir()
    (repo / "culture.yaml").write_text("agents:\n  - suffix: sib\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "agentculture-sibling" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "agentculture-sibling")
    assert tag["evidence"] == "culture.yaml present"


def test_classify_tested_python_pytest_in_dev(tmp_path: Path) -> None:
    repo = tmp_path / "tpy"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "tpy"\n' '[dependency-groups]\ndev = ["pytest>=8.0"]\n'
    )
    (repo / "tests").mkdir()
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "tested")
    assert "tests/" in tag["evidence"]
    assert "pytest" in tag["evidence"]


def test_classify_not_tested_when_pytest_missing(tmp_path: Path) -> None:
    repo = tmp_path / "tno"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "tno"\n')
    (repo / "tests").mkdir()  # dir exists but pytest not in deps
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" not in tag_names


def test_classify_tested_node_with_test_script(tmp_path: Path) -> None:
    repo = tmp_path / "tnode"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "tnode", "scripts": {"test": "jest"}}')
    (repo / "tests").mkdir()
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "tested")
    assert "test" in tag["evidence"]


def test_classify_packaged_pypi_from_workflow(tmp_path: Path) -> None:
    repo = tmp_path / "pkg"
    repo.mkdir()
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "publish.yml").write_text(
        "on: push\njobs:\n  pub:\n    steps:\n      - uses: pypa/gh-action-pypi-publish@v1\n"
    )
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "packaged-pypi" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "packaged-pypi")
    assert "publish.yml" in tag["evidence"]


def test_classify_every_returned_tag_has_evidence(tmp_path: Path) -> None:
    """No rule may emit an empty evidence string — contract invariant."""
    repo = tmp_path / "full"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "full"\n[project.scripts]\nfull = "full.cli:main"\n'
        '[dependency-groups]\ndev = ["pytest"]\n'
    )
    pkg = repo / "full"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (repo / "Dockerfile").write_text("FROM python:3.12\n")
    (repo / "tests").mkdir()
    (repo / "culture.yaml").write_text("agents:\n  - suffix: full\n")
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "publish.yml").write_text("uses: pypa/gh-action-pypi-publish@v1\n")
    result = classify(repo)
    assert result["tags"], "expected at least one tag"
    for tag in result["tags"]:
        assert isinstance(tag.get("name"), str) and tag["name"], f"empty name in {tag}"
        assert isinstance(tag.get("evidence"), str) and tag["evidence"], f"empty evidence in {tag}"


def test_classify_pyproject_non_utf8_raises_env_error(tmp_path: Path) -> None:
    """A pyproject.toml with non-UTF8 bytes raises a structured env_error.

    Without explicit UnicodeDecodeError handling, the dispatcher would wrap
    this as a generic "unexpected" error — the contract is a clean SeerError.
    """
    repo = tmp_path / "badpy"
    repo.mkdir()
    # 0xff 0xfe is not valid UTF-8; will trigger UnicodeDecodeError on read.
    (repo / "pyproject.toml").write_bytes(b'\xff\xfe[project]\nname = "x"\n')
    with pytest.raises(SeerError) as exc:
        classify(repo)
    assert exc.value.code == EXIT_ENV_ERROR
    assert "pyproject.toml" in exc.value.message


def test_classify_package_json_non_utf8_silently_skipped(tmp_path: Path) -> None:
    """A package.json with non-UTF8 bytes is treated as absent — no crash, no node tag."""
    repo = tmp_path / "badnode"
    repo.mkdir()
    (repo / "package.json").write_bytes(b'\xff\xfe{"name": "x"}')
    # Should not raise. Node tag must NOT fire when the file is unreadable.
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "node" not in tag_names


def test_classify_workflow_non_utf8_skipped(tmp_path: Path) -> None:
    """A workflow YAML with non-UTF8 bytes is skipped, not crashed on."""
    repo = tmp_path / "badwf"
    repo.mkdir()
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    # First workflow is undecodable; second one is the real pypi marker.
    (workflows / "broken.yml").write_bytes(b"\xff\xfe...")
    (workflows / "publish.yml").write_text(
        "uses: pypa/gh-action-pypi-publish@v1\n", encoding="utf-8"
    )
    # Should not raise on the broken file; should still fire packaged-pypi
    # from the readable one.
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "packaged-pypi" in tag_names
