"""Markdown emitter for antoine.lookup.classify."""

from __future__ import annotations

from typing import Any


def _section_break(lines: list[str]) -> None:
    """Emit a blank line + horizontal rule before a top-level section heading."""
    lines.append("")
    lines.append("---")


def render_classify_markdown(data: dict[str, Any]) -> str:
    """Render a classify() dict as a markdown report."""
    lines: list[str] = []
    lines.append(f"# {data.get('path', '(unknown)')}")

    manifest = data.get("manifest")
    language = data.get("language") or "unknown"
    if manifest:
        lines.append(f"- **Manifest:** {manifest} ({language})")
    else:
        lines.append(f"- **Manifest:** none ({language})")

    tags = data.get("tags") or []
    if tags:
        names = ", ".join(t["name"] for t in tags)
        lines.append(f"- **Tags:** {names}")
    else:
        lines.append("- **Tags:** _(none)_")

    if tags:
        _section_break(lines)
        lines.append("## Tags")
        lines.append("| Tag | Evidence |")
        lines.append("|---|---|")
        for t in tags:
            lines.append(f"| `{t['name']}` | {t['evidence']} |")

    return "\n".join(lines) + "\n"
