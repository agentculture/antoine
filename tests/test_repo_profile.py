"""Tests for seer.repo.profile (shallow path)."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from seer.repo.profile import profile_deep, profile_shallow


def _mk_fixture_repo(root: Path) -> Path:
    """Create a synthetic repo with every optional source populated."""
    root.mkdir()
    (root / "pyproject.toml").write_text("""
[project]
name = "demo"
version = "0.4.2"
dependencies = ["pyyaml"]

[project.scripts]
demo = "demo.cli:main"
""")
    (root / "demo").mkdir()
    (root / "demo" / "__init__.py").write_text("")
    (root / "CHANGELOG.md").write_text("""# Changelog

## [0.4.2] - 2026-05-10

### Added

- New feature.

## [0.4.1] - 2026-05-01

### Fixed

- A bug.

## [0.4.0] - 2026-04-20

### Added

- Initial.
""")
    (root / "CLAUDE.md").write_text("""# CLAUDE.md

## Project Status

Alpha. Coverage ratchet in progress.

## Architecture

Layers all the way down.
""")
    (root / "CITATION.md").write_text("""# Citations

| local | source | sha |
|---|---|---|
| src/x.py | other-repo | abc1234 |
""")
    (root / ".claude" / "skills" / "cicd").mkdir(parents=True)
    (root / "culture.yaml").write_text("agents:\n  - suffix: democult\n")
    return root


def test_profile_shallow_full_fixture(tmp_path: Path) -> None:
    """Full fixture repo exercises every optional source."""
    repo = _mk_fixture_repo(tmp_path / "demo")
    p = profile_shallow(repo)

    assert p["path"] == str(repo)
    assert p["name"] == "demo"
    assert p["version"] == "0.4.2"
    assert p["language"] == "python"
    assert p["manifest"] == "pyproject.toml"
    assert p["entry_points"] == {"demo": "demo.cli:main"}
    assert p["deps_runtime"] == ["pyyaml"]
    assert p["package_layout"] == ["demo/"]
    assert len(p["vendored_skills"]) == 1
    assert p["vendored_skills"][0]["name"] == "cicd"
    assert p["citations"] == [
        {"local": "src/x.py", "source_repo": "other-repo", "sha": "abc1234"},
    ]
    assert len(p["changelog_recent"]) == 3
    assert p["changelog_recent"][0]["version"] == "0.4.2"
    assert p["changelog_recent"][0]["date"] == "2026-05-10"
    assert "Alpha" in p["claude_md_status"]
    assert p["extra"].get("culture_nick") == "democult"


def test_profile_shallow_empty_repo(tmp_path: Path) -> None:
    """Repo with only pyproject.toml degrades silently on every optional source."""
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "e"\n')
    p = profile_shallow(repo)
    assert p["vendored_skills"] == []
    assert p["citations"] == []
    assert p["changelog_recent"] == []
    assert p["claude_md_status"] == ""
    assert p["extra"] == {}


def test_profile_shallow_no_manifest_repo(tmp_path: Path) -> None:
    """Repo with no pyproject.toml falls back to unknown language and dir name."""
    repo = tmp_path / "doc-only"
    (repo / ".claude" / "skills" / "x").mkdir(parents=True)
    p = profile_shallow(repo)
    assert p["language"] == "unknown"
    assert p["manifest"] is None
    assert p["name"] == "doc-only"


def test_profile_deep_adds_fields(tmp_path: Path) -> None:
    """Deep profile includes readme_intro, claude_md_sections, and commits_recent."""
    repo = _mk_fixture_repo(tmp_path / "demo")
    (repo / "README.md").write_text("""# demo

This is the intro paragraph that should be extracted verbatim, no
trailing newline trimming hassles.

## Subsection

Other stuff.
""")
    (repo / "CLAUDE.md").write_text((repo / "CLAUDE.md").read_text() + """

## Architecture

Three layers. Read top to bottom.

## Design Invariants

1. No LLM calls.
""")
    # init a git repo with one commit so commits_recent has data
    _git = ["git", "-C", str(repo)]  # noqa: S607
    subprocess.run([*_git, "init", "-q"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.email", "x@y"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.name", "x"], check=True)  # noqa: S607
    subprocess.run([*_git, "add", "-A"], check=True)  # noqa: S607
    subprocess.run([*_git, "commit", "-q", "-m", "test: seed commit"], check=True)  # noqa: S607

    p = profile_deep(repo)
    # shallow keys still present
    assert p["name"] == "demo"
    # deep additions
    assert "intro paragraph" in p["readme_intro"]
    assert "Architecture" in p["claude_md_sections"]
    assert "Three layers" in p["claude_md_sections"]
    assert "Design Invariants" in p["claude_md_sections"]
    assert "No LLM calls" in p["claude_md_sections"]
    assert p["commits_recent"] == ["test: seed commit"]


def test_profile_deep_missing_readme_and_git(tmp_path: Path) -> None:
    """Deep profile degrades gracefully when README and .git are absent."""
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "b"\n')
    p = profile_deep(repo)
    assert p["readme_intro"] == ""
    assert p["claude_md_sections"] == ""
    assert p["commits_recent"] == []


def test_profile_shallow_skill_sources_with_backticks(tmp_path: Path) -> None:
    """_read_skill_sources strips backticks from skill names and provenance fields."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / ".claude" / "skills" / "cicd").mkdir(parents=True)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "skill-sources.md").write_text(
        "| Skill | Source | Version |\n" "|---|---|---|\n" "| `cicd` | steward | 0.11.0 |\n"
    )
    p = profile_shallow(repo)
    assert len(p["vendored_skills"]) == 1
    s = p["vendored_skills"][0]
    assert s["name"] == "cicd"
    assert s.get("source") == "steward"
    assert s.get("version") == "0.11.0"


def test_profile_shallow_citations_with_backticked_source_and_multiword_header(
    tmp_path: Path,
) -> None:
    """_read_citations recognises 'Local path' headers and strips backticks from fields."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / "CITATION.md").write_text(
        "| Local path | Source | SHA |\n"
        "|---|---|---|\n"
        "| src/x.py | `agentculture/culture` | abc1234 |\n"
    )
    p = profile_shallow(repo)
    assert p["citations"] == [
        {"local": "src/x.py", "source_repo": "agentculture/culture", "sha": "abc1234"},
    ]


def test_profile_shallow_skill_sources_preserves_inline_backtick_spans(
    tmp_path: Path,
) -> None:
    """A cell with multiple inline `…` spans must not lose any backticks.

    The agtag-shape input is a cell like
    `` `agentculture/steward` (`.claude/skills/cicd/`) `` — only a *fully*
    backtick-wrapped cell should be unwrapped; cells with internal backtick
    spans stay verbatim so the rendered markdown remains valid.
    """
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / ".claude" / "skills" / "cicd").mkdir(parents=True)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "skill-sources.md").write_text(
        "| Skill | Source | Version |\n"
        "|---|---|---|\n"
        "| `cicd` | `agentculture/steward` (`.claude/skills/cicd/`) | adapted |\n"
    )
    p = profile_shallow(repo)
    assert len(p["vendored_skills"]) == 1
    s = p["vendored_skills"][0]
    assert s["name"] == "cicd"
    # Backticks inside the cell are preserved; the outer pair is NOT stripped
    # because the cell isn't a single wrapped span.
    assert s["source"] == "`agentculture/steward` (`.claude/skills/cicd/`)"
    # Every opening backtick has a matching closing backtick.
    assert s["source"].count("`") % 2 == 0
    assert s["version"] == "adapted"


def test_profile_shallow_src_layout_excludes_match_root(tmp_path: Path) -> None:
    """``src/`` scan honors the same dot-dir + ``_PKG_EXCLUDE`` filter as the root scan.

    Without this the src-layout exclude rules silently diverged from the root
    rules and ``tests/`` / dot-directories could leak into ``package_layout``
    and ``package_tree``.
    """
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    src = repo / "src"
    src.mkdir()
    # Legitimate top-level package — should appear.
    (src / "demo").mkdir()
    (src / "demo" / "__init__.py").write_text("")
    # Excluded dir name — should NOT appear even though it has __init__.py.
    (src / "tests").mkdir()
    (src / "tests" / "__init__.py").write_text("")
    # Dot-dir — should NOT appear.
    (src / ".hidden").mkdir()
    (src / ".hidden" / "__init__.py").write_text("")
    p = profile_shallow(repo)
    assert p["package_layout"] == ["src/demo/"]
    tree_names = {node["name"] for node in p["package_tree"]}
    assert tree_names == {"demo"}


def test_profile_shallow_build_test(tmp_path: Path) -> None:
    """build_test extracts test_command, test_addopts, coverage_fail_under, python_requires."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("""
[project]
name = "demo"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
addopts = "-n auto --cov=seer"

[tool.coverage.report]
fail_under = 80
""")
    p = profile_shallow(repo)
    bt = p["build_test"]
    assert bt is not None
    assert bt["test_command"] == "pytest"
    assert bt["test_addopts"] == "-n auto --cov=seer"
    assert bt["coverage_fail_under"] == 80
    assert bt["python_requires"] == ">=3.11"


def test_profile_shallow_ci_workflows(tmp_path: Path) -> None:
    """ci_workflows returns sorted list of workflow file/name dicts."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "publish.yml").write_text("name: Publish\non: push\njobs: {}\n")
    (wf_dir / "tests.yml").write_text("name: Tests\non: push\njobs: {}\n")
    p = profile_shallow(repo)
    wf = p["ci_workflows"]
    assert isinstance(wf, list)
    assert len(wf) == 2
    # sorted alphabetically by filename
    assert wf[0]["file"] == "publish.yml"
    assert wf[0]["name"] == "Publish"
    assert wf[1]["file"] == "tests.yml"
    assert wf[1]["name"] == "Tests"


def test_profile_shallow_publish_target_pypi(tmp_path: Path) -> None:
    """publish_target detects pypa/gh-action-pypi-publish + push:tags trigger."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "publish.yml").write_text(
        "name: Publish\n"
        "on:\n"
        "  push:\n"
        "    tags: [v*]\n"
        "jobs:\n"
        "  publish:\n"
        "    uses: pypa/gh-action-pypi-publish@v1\n"
    )
    p = profile_shallow(repo)
    pt = p["publish_target"]
    assert pt is not None
    assert pt["kind"] == "pypi"
    assert pt["workflow"] == "publish.yml"
    assert pt["trigger"] == "push: tags"


def test_profile_shallow_publish_target_ghcr(tmp_path: Path) -> None:
    """publish_target detects ghcr.io references."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "docker.yml").write_text(
        "name: Docker\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - run: docker push ghcr.io/owner/image:latest\n"
    )
    p = profile_shallow(repo)
    pt = p["publish_target"]
    assert pt is not None
    assert pt["kind"] == "ghcr"
    assert pt["workflow"] == "docker.yml"


def test_profile_shallow_git_remote_ssh(tmp_path: Path) -> None:
    """git_remote parses SSH origin URL into host/owner/repo."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    _git = ["git", "-C", str(repo)]  # noqa: S607
    subprocess.run([*_git, "init", "-q"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.email", "x@y"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.name", "x"], check=True)  # noqa: S607
    subprocess.run(
        [*_git, "remote", "add", "origin", "git@github.com:agentculture/agtag.git"],
        check=True,
    )  # noqa: S607
    p = profile_shallow(repo)
    gr = p["git_remote"]
    assert gr is not None
    assert gr["host"] == "github.com"
    assert gr["owner"] == "agentculture"
    assert gr["repo"] == "agtag"
    assert gr["ref"] == "origin"


def test_profile_shallow_git_remote_https(tmp_path: Path) -> None:
    """git_remote parses HTTPS origin URL into host/owner/repo."""
    repo = tmp_path / "demo2"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo2"\n')
    _git = ["git", "-C", str(repo)]  # noqa: S607
    subprocess.run([*_git, "init", "-q"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.email", "x@y"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.name", "x"], check=True)  # noqa: S607
    subprocess.run(
        [*_git, "remote", "add", "origin", "https://github.com/agentculture/agtag.git"],
        check=True,
    )  # noqa: S607
    p = profile_shallow(repo)
    gr = p["git_remote"]
    assert gr is not None
    assert gr["host"] == "github.com"
    assert gr["owner"] == "agentculture"
    assert gr["repo"] == "agtag"


def test_profile_shallow_module_summaries(tmp_path: Path) -> None:
    """module_summaries returns sorted list of modules with first docstring line."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Package init."""\n')
    (pkg / "cli.py").write_text('"""Command-line entry point."""\n\ndef main():\n    pass\n')
    (pkg / "empty.py").write_text("# no docstring\ndef helper(): pass\n")
    p = profile_shallow(repo)
    ms = p["module_summaries"]
    assert isinstance(ms, list)
    assert len(ms) == 2
    module_names = [e["module"] for e in ms]
    assert "pkg/__init__.py" in module_names
    assert "pkg/cli.py" in module_names
    assert "pkg/empty.py" not in module_names
    init_entry = next(e for e in ms if e["module"] == "pkg/__init__.py")
    assert init_entry["summary"] == "Package init."
    cli_entry = next(e for e in ms if e["module"] == "pkg/cli.py")
    assert cli_entry["summary"] == "Command-line entry point."
    # Sorted by module path
    assert ms == sorted(ms, key=lambda x: x["module"])


def test_profile_shallow_git_remote_no_git(tmp_path: Path) -> None:
    """git_remote is None when no .git directory exists."""
    repo = tmp_path / "no-git"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "no-git"\n')
    p = profile_shallow(repo)
    assert p["git_remote"] is None


def test_profile_shallow_publish_target_none(tmp_path: Path) -> None:
    """publish_target is None when no pypi/ghcr workflows are found."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "tests.yml").write_text("name: Tests\non: push\njobs: {}\n")
    p = profile_shallow(repo)
    assert p["publish_target"] is None


def test_profile_shallow_ci_workflows_no_workflows_dir(tmp_path: Path) -> None:
    """ci_workflows returns empty list when .github/workflows is absent."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    p = profile_shallow(repo)
    assert p["ci_workflows"] == []


def test_profile_shallow_build_test_no_pyproject(tmp_path: Path) -> None:
    """build_test is None when no pyproject.toml is present."""
    repo = tmp_path / "no-manifest"
    (repo / ".claude" / "skills" / "x").mkdir(parents=True)
    p = profile_shallow(repo)
    assert p["build_test"] is None


def test_profile_shallow_package_tree_nested(tmp_path: Path) -> None:
    """package_tree exposes top-level subpackages and modules to ~depth 2."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / "demo").mkdir()
    (repo / "demo" / "__init__.py").write_text("")
    (repo / "demo" / "nick.py").write_text("")
    (repo / "demo" / "cli").mkdir()
    (repo / "demo" / "cli" / "__init__.py").write_text("")
    (repo / "demo" / "cli" / "_errors.py").write_text("")
    (repo / "demo" / "cli" / "_commands").mkdir()
    (repo / "demo" / "cli" / "_commands" / "__init__.py").write_text("")
    (repo / "demo" / "issue").mkdir()
    (repo / "demo" / "issue" / "__init__.py").write_text("")
    (repo / "demo" / "issue" / "post.py").write_text("")
    # Excluded dirs must NOT appear in the tree.
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "demo" / "__pycache__").mkdir()
    p = profile_shallow(repo)
    tree = p["package_tree"]
    assert isinstance(tree, list)
    assert len(tree) == 1
    root = tree[0]
    assert root["name"] == "demo"
    assert "nick.py" in root["modules"]
    assert "__init__.py" in root["modules"]
    sub_names = {sp["name"] for sp in root["subpackages"]}
    assert sub_names == {"cli", "issue"}
    cli = next(sp for sp in root["subpackages"] if sp["name"] == "cli")
    assert "_errors.py" in cli["modules"]
    cli_sub = {sp["name"] for sp in cli["subpackages"]}
    assert cli_sub == {"_commands"}
    issue = next(sp for sp in root["subpackages"] if sp["name"] == "issue")
    assert "post.py" in issue["modules"]
    # Excluded dirs stay out.
    assert "tests" not in sub_names
    assert "__pycache__" not in {sp["name"] for sp in root["subpackages"]}


# ---------------------------------------------------------------------------
# B1 — github_state
# ---------------------------------------------------------------------------

def _gh_api_side_effect(git_remote_url: str = "git@github.com:agentculture/demo.git") -> object:
    """Return a factory that handles git + gh api calls with canned responses."""
    _REPO_JSON = json.dumps({
        "default_branch": "main",
        "open_issues_count": 4,
    })
    _RELEASE_JSON = json.dumps({
        "tag_name": "v0.5.0",
        "published_at": "2025-12-01T10:00:00Z",
    })
    _RUNS_JSON = json.dumps({
        "workflow_runs": [{"conclusion": "success"}],
    })

    class _FakeResult:
        def __init__(self, stdout: str, returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode
            self.stderr = ""

    def _fake_run(args: list, **kwargs: object) -> _FakeResult:
        # Handle git remote get-url
        if args and args[0] == "git" and "get-url" in args:
            return _FakeResult(stdout=git_remote_url)
        # Sequence gh api calls by endpoint
        if args and args[0] == "gh" and len(args) >= 3 and args[1] == "api":
            endpoint = args[2]
            if "releases/latest" in endpoint:
                return _FakeResult(stdout=_RELEASE_JSON)
            if "actions/runs" in endpoint:
                return _FakeResult(stdout=_RUNS_JSON)
            # Default: repo metadata
            return _FakeResult(stdout=_REPO_JSON)
        return _FakeResult(stdout="", returncode=1)

    return _fake_run


def _mk_github_repo(root: Path) -> Path:
    """Minimal fixture with a git origin so _git_remote returns owner/repo."""
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    _git = ["git", "-C", str(root)]  # noqa: S607
    subprocess.run([*_git, "init", "-q"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.email", "x@y"], check=True)  # noqa: S607
    subprocess.run([*_git, "config", "user.name", "x"], check=True)  # noqa: S607
    subprocess.run(
        [*_git, "remote", "add", "origin", "git@github.com:agentculture/demo.git"],
        check=True,
    )  # noqa: S607
    return root


def test_profile_shallow_github_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """github_state returns 4-key dict from canned gh api responses."""
    repo = _mk_github_repo(tmp_path / "demo")
    monkeypatch.setattr(subprocess, "run", _gh_api_side_effect())
    p = profile_shallow(repo)
    gs = p.get("github_state")
    assert gs is not None
    assert gs["default_branch"] == "main"
    assert gs["open_issues"] == 4
    assert gs["latest_release"] == {"tag": "v0.5.0", "published_at": "2025-12-01T10:00:00Z"}
    assert gs["ci_status_on_default"] == "success"


def test_profile_shallow_github_state_gh_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """github_state is None when the gh CLI is absent (FileNotFoundError)."""
    repo = _mk_github_repo(tmp_path / "demo2")
    original_run = subprocess.run

    def _selective_raise(args: list, **kwargs: object) -> object:
        if args and args[0] == "gh":
            raise FileNotFoundError("gh not found")
        return original_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _selective_raise)
    p = profile_shallow(repo)
    assert p.get("github_state") is None


# ---------------------------------------------------------------------------
# B2 — pypi_state
# ---------------------------------------------------------------------------

def _make_fake_urlopen(version: str = "0.5.0", upload_time: str = "2026-05-15T12:00:00Z"):
    """Return a fake urlopen context-manager factory with canned PyPI JSON."""
    pypi_payload = json.dumps({
        "info": {"version": version},
        "releases": {
            version: [{"upload_time_iso_8601": upload_time}]
        },
    }).encode()

    class _FakeResponse:
        def read(self) -> bytes:
            return pypi_payload

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def _fake_urlopen(url: str, timeout: int = 5) -> _FakeResponse:
        return _FakeResponse()

    return _fake_urlopen


def test_profile_shallow_pypi_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pypi_state returns latest_version and released_at from canned PyPI JSON."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.5.0"\n')
    monkeypatch.setattr(urllib.request, "urlopen", _make_fake_urlopen())
    p = profile_shallow(repo)
    ps = p.get("pypi_state")
    assert ps is not None
    assert ps["latest_version"] == "0.5.0"
    assert ps["released_at"] == "2026-05-15T12:00:00Z"


def test_profile_shallow_pypi_state_url_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pypi_state is None when urlopen raises URLError."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    def _raise(url: str, timeout: int = 5) -> None:
        raise urllib.error.URLError("network unavailable")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    p = profile_shallow(repo)
    assert p.get("pypi_state") is None


# ---------------------------------------------------------------------------
# B3 — --basic flag
# ---------------------------------------------------------------------------

def test_profile_shallow_basic_skips_tier2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """basic=True skips github_state and pypi_state without invoking subprocess gh / urlopen."""
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    def _should_not_be_called_for_gh(*args: object, **kwargs: object) -> object:
        # Allow git calls (for _git_remote), but not gh
        if args and isinstance(args[0], list) and args[0] and args[0][0] == "gh":
            raise AssertionError("subprocess.run called with gh in basic mode")
        return subprocess.CompletedProcess(
            args=args[0] if args else [], returncode=1, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _should_not_be_called_for_gh)

    def _should_not_be_called_for_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("urlopen called in basic mode")

    monkeypatch.setattr(urllib.request, "urlopen", _should_not_be_called_for_urlopen)

    p = profile_shallow(repo, basic=True)
    assert p.get("github_state") is None
    assert p.get("pypi_state") is None
