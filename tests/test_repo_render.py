"""Tests for seer.repo.render."""

from __future__ import annotations

from seer.cli._errors import SeerError
from seer.repo.render import (
    render_error_markdown,
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
    err = SeerError(
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
