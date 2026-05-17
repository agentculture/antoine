"""Tests for antoine.repo.render."""

from __future__ import annotations

from antoine.cli._errors import AntoineError
from antoine.repo.render import (
    render_connections_markdown,
    render_error_markdown,
    render_graph_markdown,
    render_profile_markdown,
)


def _shallow_fixture() -> dict[str, object]:
    return {
        "path": "/home/user/projects/demo",
        "name": "demo",
        "version": "0.4.2",
        "language": "python",
        "manifest": "pyproject.toml",
        "entry_points": {"demo": "demo.cli:main"},
        "deps_runtime": ["pyyaml"],
        "deps_dev": [],
        "package_layout": ["demo/"],
        "vendored_skills": [{"name": "cicd", "source": "steward", "version": "0.11.0"}],
        "citations": [{"local": "x.py", "source_repo": "y", "sha": "abc1234"}],
        "changelog_recent": [
            {"version": "0.4.2", "date": "2026-05-10", "summary": "New thing."},
        ],
        "claude_md_status": "Alpha.",
        "extra": {"culture_nick": "democult"},
    }


def test_render_profile_markdown_includes_all_sections() -> None:
    md = render_profile_markdown(_shallow_fixture())
    assert "# demo" in md
    assert "**Version:** 0.4.2" in md
    assert "**Manifest:** pyproject.toml (python)" in md
    assert "`demo` → `demo.cli:main`" in md
    assert "- pyyaml" in md
    assert "demo/" in md
    assert "| cicd | steward | 0.11.0 |" in md
    assert "abc1234" in md
    assert "0.4.2" in md
    assert "Alpha." in md
    assert "democult" in md


def test_render_profile_markdown_inserts_horizontal_rules_between_sections() -> None:
    """Every top-level `## …` section is preceded by a `---` horizontal rule.

    Gives the reader a strong visual anchor between dense table sections.
    """
    md = render_profile_markdown(_shallow_fixture())
    headings = [
        "## Entry points",
        "## Runtime dependencies",
        "## Package layout",
        "## Vendored skills",
        "## Citations",
        "## Recent changelog",
        "## Project status",
        "## Extra",
    ]
    for h in headings:
        assert h in md, f"missing heading: {h}"
        # Each ## heading must be preceded by a `---` rule on its own line.
        idx = md.index(h)
        prefix = md[:idx]
        assert prefix.rstrip().endswith("---"), f"no `---` before {h!r}"


def test_render_profile_markdown_nested_package_tree() -> None:
    """When `package_tree` is populated, subpackages and modules render nested."""
    fx = _shallow_fixture()
    fx["package_tree"] = [
        {
            "name": "demo",
            "modules": ["__init__.py", "nick.py"],
            "subpackages": [
                {
                    "name": "cli",
                    "modules": ["__init__.py", "_errors.py"],
                    "subpackages": [
                        {"name": "_commands", "modules": ["__init__.py"], "subpackages": []},
                    ],
                },
                {
                    "name": "issue",
                    "modules": ["__init__.py", "post.py"],
                    "subpackages": [],
                },
            ],
        }
    ]
    md = render_profile_markdown(fx)
    # Top-level package shown.
    assert "demo/" in md
    # Subpackages.
    assert "cli/" in md
    assert "issue/" in md
    assert "_commands/" in md
    # Modules.
    assert "nick.py" in md
    assert "_errors.py" in md
    assert "post.py" in md


def test_render_profile_markdown_omits_empty_sections() -> None:
    minimal = {
        "path": "/x/min",
        "name": "min",
        "version": "",
        "language": "unknown",
        "manifest": None,
        "entry_points": {},
        "deps_runtime": [],
        "deps_dev": [],
        "package_layout": [],
        "vendored_skills": [],
        "citations": [],
        "changelog_recent": [],
        "claude_md_status": "",
        "extra": {},
    }
    md = render_profile_markdown(minimal)
    assert "# min" in md
    assert "**Manifest:** none (unknown)" in md
    assert "Runtime dependencies" not in md
    assert "Vendored skills" not in md
    assert "Citations" not in md
    assert "Recent changelog" not in md
    assert "Project status" not in md


def test_render_profile_markdown_deep_adds_sections() -> None:
    deep = _shallow_fixture()
    deep["readme_intro"] = "Intro line one.\nIntro line two."
    deep["claude_md_sections"] = "## Architecture\n\nThree layers."
    deep["commits_recent"] = ["fix: a", "feat: b"]
    md = render_profile_markdown(deep)
    assert "## Readme intro" in md
    assert "Intro line one." in md
    assert "## Architecture" in md
    assert "Three layers." in md
    assert "## Recent commits" in md
    assert "fix: a" in md
    assert "feat: b" in md


def test_render_error_markdown() -> None:
    err = AntoineError(
        code=1,
        kind="user_error",
        message="Cannot find pyproject.toml in /x",
        reason="No recognized manifest at the given path.",
        remediation="Confirm the path points to a repo root.",
    )
    md = render_error_markdown(err)
    assert "**Error:** Cannot find pyproject.toml in /x" in md
    assert "**Reason:**" in md
    assert "**Remediation:**" in md
    assert "Exit code: 1 (user error)" in md


def test_render_connections_markdown_basic() -> None:
    walk_data = {
        "seed": "/home/user/projects/alpha",
        "seed_name": "alpha",
        "depth": 1,
        "nodes": [
            {"id": "alpha", "path": "/home/user/projects/alpha", "external": False},
            {"id": "beta", "path": "/home/user/projects/beta", "external": False},
            {"id": "external-pkg", "path": None, "external": True},
        ],
        "edges": [
            {"from": "alpha", "to": "beta", "type": "import", "spec": "*"},
            {"from": "alpha", "to": "external-pkg", "type": "import", "spec": "*"},
        ],
        "walk_errors": [],
    }
    md = render_connections_markdown(walk_data)
    assert "alpha — connections (depth 1)" in md
    assert "## Imports (2)" in md
    assert "(/home/user/projects/beta)" in md
    assert "(external)" in md


def test_render_connections_markdown_inlines_errors() -> None:
    walk_data = {
        "seed": "/home/user/projects/alpha",
        "seed_name": "alpha",
        "depth": 1,
        "nodes": [{"id": "alpha", "path": "/home/user/projects/alpha", "external": False}],
        "edges": [],
        "walk_errors": [
            {
                "node": "beta (/home/user/projects/beta)",
                "reason": "TOML syntax error.",
                "remediation": "validate the file.",
            }
        ],
    }
    md = render_connections_markdown(walk_data)
    assert "## Errors during walk (1)" in md
    assert "**beta (/home/user/projects/beta)**" in md
    assert "TOML syntax error." in md


def test_render_profile_markdown_build_test_positive() -> None:
    """build_test section renders as bullet list preceded by --- separator."""
    fx = _shallow_fixture()
    fx["build_test"] = {
        "test_command": "pytest",
        "test_addopts": "-n auto",
        "coverage_fail_under": 80,
        "python_requires": ">=3.11",
    }
    md = render_profile_markdown(fx)
    assert "## Build & test" in md
    idx = md.index("## Build & test")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## Build & test"
    assert "- test_command: pytest" in md
    assert "- test_addopts: -n auto" in md
    assert "- coverage_fail_under: 80" in md
    assert "- python_requires: >=3.11" in md


def test_render_profile_markdown_build_test_negative() -> None:
    """build_test section absent when field is None."""
    fx = _shallow_fixture()
    fx["build_test"] = None
    md = render_profile_markdown(fx)
    assert "## Build & test" not in md


def test_render_profile_markdown_ci_workflows_positive() -> None:
    """ci_workflows section renders as markdown table preceded by --- separator."""
    fx = _shallow_fixture()
    fx["ci_workflows"] = [
        {"file": "publish.yml", "name": "Publish"},
        {"file": "tests.yml", "name": "Tests"},
    ]
    md = render_profile_markdown(fx)
    assert "## CI workflows" in md
    idx = md.index("## CI workflows")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## CI workflows"
    assert "| File | Name |" in md
    assert "| publish.yml | Publish |" in md
    assert "| tests.yml | Tests |" in md


def test_render_profile_markdown_ci_workflows_negative() -> None:
    """ci_workflows section absent when list is empty."""
    fx = _shallow_fixture()
    fx["ci_workflows"] = []
    md = render_profile_markdown(fx)
    assert "## CI workflows" not in md


def test_render_profile_markdown_publish_target_positive() -> None:
    """publish_target section renders as bullet block preceded by --- separator."""
    fx = _shallow_fixture()
    fx["publish_target"] = {"kind": "pypi", "workflow": "publish.yml", "trigger": "push: tags"}
    md = render_profile_markdown(fx)
    assert "## Publish target" in md
    idx = md.index("## Publish target")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## Publish target"
    assert "- kind: pypi" in md
    assert "- workflow: publish.yml" in md
    assert "- trigger: push: tags" in md


def test_render_profile_markdown_publish_target_negative() -> None:
    """publish_target section absent when field is None."""
    fx = _shallow_fixture()
    fx["publish_target"] = None
    md = render_profile_markdown(fx)
    assert "## Publish target" not in md


def test_render_profile_markdown_git_remote_positive() -> None:
    """git_remote section renders all keys preceded by --- separator."""
    fx = _shallow_fixture()
    fx["git_remote"] = {
        "host": "github.com",
        "owner": "agentculture",
        "repo": "antoine",
        "url": "git@github.com:agentculture/antoine.git",
        "ref": "origin",
    }
    md = render_profile_markdown(fx)
    assert "## Git remote" in md
    idx = md.index("## Git remote")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## Git remote"
    assert "host" in md
    assert "github.com" in md
    assert "agentculture" in md


def test_render_profile_markdown_git_remote_negative() -> None:
    """git_remote section absent when field is None."""
    fx = _shallow_fixture()
    fx["git_remote"] = None
    md = render_profile_markdown(fx)
    assert "## Git remote" not in md


def test_render_profile_markdown_module_summaries_positive() -> None:
    """module_summaries section renders as table preceded by --- separator."""
    fx = _shallow_fixture()
    fx["module_summaries"] = [
        {"module": "pkg/__init__.py", "summary": "Package init."},
        {"module": "pkg/cli.py", "summary": "Command-line entry point."},
    ]
    md = render_profile_markdown(fx)
    assert "## Module summaries" in md
    idx = md.index("## Module summaries")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## Module summaries"
    assert "| Module | Summary |" in md
    assert "| pkg/__init__.py | Package init. |" in md
    assert "| pkg/cli.py | Command-line entry point. |" in md


def test_render_profile_markdown_module_summaries_negative() -> None:
    """module_summaries section absent when list is empty."""
    fx = _shallow_fixture()
    fx["module_summaries"] = []
    md = render_profile_markdown(fx)
    assert "## Module summaries" not in md


def test_render_profile_markdown_section_ordering() -> None:
    """Tier-1 sections appear in specified order in the rendered output."""
    fx = _shallow_fixture()
    fx["build_test"] = {"test_command": "pytest"}
    fx["ci_workflows"] = [{"file": "tests.yml", "name": "Tests"}]
    fx["publish_target"] = {"kind": "pypi", "workflow": "publish.yml", "trigger": "push: tags"}
    fx["git_remote"] = {
        "host": "github.com",
        "owner": "x",
        "repo": "y",
        "url": "u",
        "ref": "origin",
    }
    fx["module_summaries"] = [{"module": "x.py", "summary": "X."}]
    md = render_profile_markdown(fx)
    # Extract positions of all expected section headings
    sections = [
        "## Runtime dependencies",
        "## Package layout",
        "## Build & test",
        "## CI workflows",
        "## Publish target",
        "## Git remote",
        "## Module summaries",
        "## Vendored skills",
        "## Citations",
        "## Recent changelog",
        "## Project status",
        "## Extra",
    ]
    positions = []
    for s in sections:
        assert s in md, f"missing section: {s}"
        positions.append(md.index(s))
    assert positions == sorted(positions), "sections are not in expected order"


def test_render_graph_markdown_includes_mermaid() -> None:
    g = {
        "roots": ["/home/user/projects"],
        "nodes": [
            {
                "id": "alpha",
                "path": "/home/user/projects/alpha",
                "external": False,
                "version": "1.0",
            },
            {"id": "beta", "path": "/home/user/projects/beta", "external": False, "version": "2.0"},
        ],
        "edges": [{"from": "alpha", "to": "beta", "type": "import", "spec": "*"}],
        "mermaid": "graph TD\n  alpha --> beta\n",
    }
    md = render_graph_markdown(g)
    assert "# Workspace graph" in md
    assert "alpha" in md and "beta" in md
    assert "```mermaid" in md
    assert "graph TD" in md


# ---------------------------------------------------------------------------
# B4 — Tier-2 render sections
# ---------------------------------------------------------------------------


def _tier2_fixture() -> dict[str, object]:
    """Fixture with both Tier-2 fields populated."""
    fx = _shallow_fixture()
    fx["github_state"] = {
        "latest_release": {"tag": "v0.5.0", "published_at": "2025-12-01T10:00:00Z"},
        "open_issues": 4,
        "default_branch": "main",
        "ci_status_on_default": "success",
    }
    fx["pypi_state"] = {
        "latest_version": "0.5.0",
        "released_at": "2026-05-15T12:00:00Z",
    }
    return fx


def test_render_profile_markdown_github_state_section() -> None:
    """github_state renders a ## GitHub section with all 4 keys."""
    md = render_profile_markdown(_tier2_fixture())
    assert "## GitHub" in md
    # preceded by ---
    idx = md.index("## GitHub")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## GitHub"
    assert "v0.5.0" in md
    assert "2025-12-01" in md
    assert "open_issues" in md or "4" in md
    assert "main" in md
    assert "success" in md


def test_render_profile_markdown_pypi_state_section() -> None:
    """pypi_state renders a ## PyPI section."""
    md = render_profile_markdown(_tier2_fixture())
    assert "## PyPI" in md
    idx = md.index("## PyPI")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` before ## PyPI"
    assert "0.5.0" in md
    assert "2026-05-15" in md


def test_render_profile_markdown_tier2_absent_when_none() -> None:
    """When github_state and pypi_state are None, headings are absent."""
    fx = _shallow_fixture()
    fx["github_state"] = None
    fx["pypi_state"] = None
    md = render_profile_markdown(fx)
    assert "## GitHub" not in md
    assert "## PyPI" not in md


def test_render_profile_markdown_tier2_section_order() -> None:
    """github_state and pypi_state sections appear after extra."""
    md = render_profile_markdown(_tier2_fixture())
    sections = ["## Extra", "## GitHub", "## PyPI"]
    positions = []
    for s in sections:
        assert s in md, f"missing section: {s}"
        positions.append(md.index(s))
    assert positions == sorted(
        positions
    ), f"sections not in order: {list(zip(sections, positions))}"
