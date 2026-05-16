"""seer.lookup.grep_context — ripgrep-backed search with AST scope annotation.

Provides:
  grep_with_context  — run ``rg --json`` and pair every match with the
                       enclosing Python scope from the AST resolver.
  render_grep_markdown — format grep results as a Markdown table.
"""

from __future__ import annotations

import ast
import json
import subprocess  # noqa: S404  # nosec B404
from pathlib import Path
from typing import Any

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.lookup.ast_scope import find_enclosing

__all__ = ["grep_with_context", "render_grep_markdown"]


def grep_with_context(pattern: str, path: str | Path) -> dict[str, Any]:
    """Search *path* for *pattern* via ``rg --json`` and annotate each match.

    Each match in the returned dict has the shape::

        {"file": str, "line": int, "scope": str | None, "text": str}

    ``scope`` is the qualified name of the enclosing function / method / class
    for Python files (``None`` for module-level lines and all non-Python files).

    Raises:
        SeerError(EXIT_USER_ERROR): *path* does not exist.
        SeerError(EXIT_ENV_ERROR):  ``rg`` is not on PATH, or rg exits with
                                    code 2+ (real error, not "no matches").
    """
    p = Path(path)
    if not p.exists():
        raise SeerError(
            code=EXIT_USER_ERROR,
            kind="user_error",
            message=f"path not found: {path}",
            remediation="pass an existing file or directory.",
        )

    try:
        result = subprocess.run(  # noqa: S603,S607  # nosec B603 B607
            ["rg", "--json", pattern, str(p)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message="`rg` not found on PATH",
            reason="seer grep requires ripgrep (rg) for match-finding.",
            remediation=("install ripgrep (e.g. `apt install ripgrep` or `brew install ripgrep`)."),
        )
    except subprocess.SubprocessError as exc:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message=f"rg subprocess failed: {exc}",
        )

    # rg exits 1 when there are no matches — that is not an error.
    if result.returncode >= 2:
        stderr_snippet = result.stderr.strip()[:200]
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message=f"rg exited with code {result.returncode}",
            reason=stderr_snippet or "rg reported an error.",
            remediation="check that the pattern is a valid regex and the path is readable.",
        )

    # Parse rg --json output.  Each line is a JSON object; we only care about
    # type == "match" events.
    matches_by_file: dict[str, list[dict[str, Any]]] = {}
    # Keep insertion order so we preserve rg's emission sequence.
    for raw_line in result.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        file_str = (data.get("path") or {}).get("text", "")
        line_num = data.get("line_number", 0)
        line_text = ((data.get("lines") or {}).get("text") or "").rstrip("\n")
        entry: dict[str, Any] = {
            "file": file_str,
            "line": line_num,
            "scope": None,  # filled in below
            "text": line_text,
        }
        matches_by_file.setdefault(file_str, []).append(entry)

    # Resolve scopes for Python files.
    for file_str, entries in matches_by_file.items():
        if not file_str.endswith(".py"):
            continue
        try:
            source = Path(file_str).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            # Best-effort: leave scope=None for all matches in this file.
            continue
        for entry in entries:
            scope_obj = find_enclosing(tree, entry["line"])
            entry["scope"] = scope_obj.name if scope_obj else None

    # Flatten back into a single ordered list.
    all_matches = [entry for entries in matches_by_file.values() for entry in entries]

    return {"pattern": pattern, "matches": all_matches}


def render_grep_markdown(data: dict[str, Any]) -> str:
    """Render a :func:`grep_with_context` result dict as a Markdown table."""
    lines: list[str] = []
    pattern = data.get("pattern", "")
    matches = data.get("matches") or []

    lines.append(f"# grep: `{pattern}`")
    lines.append("")

    if not matches:
        lines.append("_No matches found._")
        return "\n".join(lines) + "\n"

    lines.append("| File | Line | Scope | Text |")
    lines.append("|---|---|---|---|")
    for m in matches:
        file_cell = m.get("file", "")
        line_cell = str(m.get("line", ""))
        scope_cell = m.get("scope") or "_module_"
        text_cell = (m.get("text") or "").replace("|", "\\|")
        lines.append(f"| {file_cell} | {line_cell} | {scope_cell} | {text_cell} |")

    return "\n".join(lines) + "\n"
