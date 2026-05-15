"""Tests for seer.lookup.render."""

from __future__ import annotations

from seer.lookup.render import render_classify_markdown


def _fixture() -> dict:
    return {
        "path": "/home/user/projects/demo",
        "manifest": "pyproject.toml",
        "language": "python",
        "tags": [
            {"name": "python", "evidence": "pyproject.toml present"},
            {"name": "cli", "evidence": '[project.scripts] defines demo = "demo.cli:main"'},
            {"name": "library", "evidence": "`demo/__init__.py` present"},
            {"name": "tested", "evidence": "tests/ exists; pytest in dependency-groups.dev"},
            {"name": "agentculture-sibling", "evidence": "culture.yaml present"},
        ],
    }


def test_render_includes_path_header() -> None:
    md = render_classify_markdown(_fixture())
    assert md.startswith("# /home/user/projects/demo\n")


def test_render_includes_manifest_and_language_line() -> None:
    md = render_classify_markdown(_fixture())
    assert "- **Manifest:** pyproject.toml (python)" in md


def test_render_includes_tag_summary_line() -> None:
    md = render_classify_markdown(_fixture())
    assert "- **Tags:** python, cli, library, tested, agentculture-sibling" in md


def test_render_inserts_section_break_before_tags_heading() -> None:
    md = render_classify_markdown(_fixture())
    idx = md.index("## Tags")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` separator before `## Tags`"


def test_render_tags_table_has_two_columns_per_row() -> None:
    md = render_classify_markdown(_fixture())
    # Find the Tags table body (lines between the column-separator row and the next
    # blank line or EOF). Each body row must be `| <tag> | <evidence> |`.
    lines = md.splitlines()
    in_table = False
    for line in lines:
        if line.startswith("|---|"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            # 3 pipes = 2 columns
            assert line.count("|") == 3, f"row not 2-col shape: {line!r}"


def test_render_empty_tags_still_renders_header() -> None:
    empty = {"path": "/x", "manifest": None, "language": "unknown", "tags": []}
    md = render_classify_markdown(empty)
    assert "# /x\n" in md
    assert "**Manifest:** none (unknown)" in md
    assert "**Tags:** _(none)_" in md
    # No Tags table when list is empty.
    assert "## Tags" not in md


def test_render_no_manifest_renders_none() -> None:
    no_mf = {
        "path": "/y",
        "manifest": None,
        "language": "unknown",
        "tags": [{"name": "bash", "evidence": "scripts/ contains 1 .sh file"}],
    }
    md = render_classify_markdown(no_mf)
    assert "**Manifest:** none (unknown)" in md
