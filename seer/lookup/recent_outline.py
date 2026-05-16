"""seer.lookup.recent_outline — git log + AST symbol diff per commit.

Provides:
  recent_with_outline  — run ``git log`` and pair every changed file with
                         a structural symbol-diff (functions/classes added /
                         removed / modified) at the AST level.
  render_recent_markdown — format the result as a Markdown commit log.
"""

from __future__ import annotations

import ast
import subprocess  # noqa: S404  # nosec B404
from pathlib import Path
from typing import Any

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.lookup.ast_scope import list_symbols

__all__ = ["recent_with_outline", "render_recent_markdown"]


def _run_git(  # type: ignore[type-arg]
    args: list[str],
    path: Path,
    allow_nonzero: bool = False,
) -> subprocess.CompletedProcess:
    """Run a git command in *path* and return the CompletedProcess.

    Raises:
        SeerError(EXIT_ENV_ERROR): git not found on PATH.
        SeerError(EXIT_ENV_ERROR): git exits non-zero (unless *allow_nonzero*).
    """
    try:
        result = subprocess.run(  # noqa: S603,S607  # nosec B603 B607
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message="git not found on PATH",
            remediation="install git and ensure it is on your PATH.",
        )
    except subprocess.SubprocessError as exc:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message=f"git subprocess failed: {exc}",
        )

    if not allow_nonzero and result.returncode != 0:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message=f"git exited with code {result.returncode}",
            reason=result.stderr.strip()[:400],
        )

    return result


def _symbols_from_source(source: str) -> dict[str, Any]:
    """Parse *source* and return a mapping of symbol name → Scope.

    On parse failure (SyntaxError, ValueError) returns an empty dict —
    graceful degradation for files with syntax errors.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    return {s.name: s for s in list_symbols(tree)}


def _file_diff(sha: str, file_path: str, repo_path: Path, is_initial: bool) -> dict[str, Any]:
    """Return the symbol diff for a single *file_path* in commit *sha*.

    For non-Python files always returns empty added/removed/modified.

    The "modified" heuristic compares (start_line, end_line) tuples between
    before and after versions.  A pure line-shift (e.g. adding a blank line
    above a function) can cause a false positive here; content hashing would
    eliminate these false positives but is deferred as a future improvement.
    """
    # Get "before" content (parent version).  For the initial commit the
    # parent reference <sha>^ does not exist, so we treat before as empty.
    if is_initial:
        before = ""
    else:
        before_result = _run_git(
            ["show", f"{sha}^:{file_path}"],
            repo_path,
            allow_nonzero=True,
        )
        before = before_result.stdout if before_result.returncode == 0 else ""

    # Get "after" content (this commit's version).
    after_result = _run_git(
        ["show", f"{sha}:{file_path}"],
        repo_path,
        allow_nonzero=True,
    )
    after = after_result.stdout if after_result.returncode == 0 else ""

    entry: dict[str, Any] = {"file": file_path, "added": [], "removed": [], "modified": []}

    if not file_path.endswith(".py"):
        return entry

    before_map = _symbols_from_source(before)
    after_map = _symbols_from_source(after)

    before_names = set(before_map)
    after_names = set(after_map)

    entry["added"] = sorted(after_names - before_names)
    entry["removed"] = sorted(before_names - after_names)
    entry["modified"] = sorted(
        name
        for name in before_names & after_names
        if (before_map[name].start_line, before_map[name].end_line)
        != (after_map[name].start_line, after_map[name].end_line)
    )

    return entry


def recent_with_outline(n: int = 20, path: str | Path = ".") -> dict[str, Any]:
    """Return the last *n* commits in *path*, each paired with AST symbol diffs.

    The returned dict has the shape::

        {"commits": [
          {"sha": "abc1234",  # 7-char prefix
           "date": "2026-05-15",  # YYYY-MM-DD
           "subject": "feat: ...",
           "changes": [
             {"file": "lib.py",
              "added": ["bar"], "removed": [], "modified": ["foo"]},
             {"file": "README.md",
              "added": [], "removed": [], "modified": []},
           ]},
          ...
        ]}

    Commits are ordered newest-first (same as ``git log``).

    Raises:
        SeerError(EXIT_USER_ERROR): *n* < 1 or *path* is not an existing directory.
        SeerError(EXIT_ENV_ERROR):  git not found, or git exits with a fatal error.
    """
    repo = Path(path)

    if n < 1:
        raise SeerError(
            code=EXIT_USER_ERROR,
            kind="user_error",
            message=f"n must be >= 1, got {n}",
            remediation="pass a positive integer for the commit count.",
        )
    if not repo.exists() or not repo.is_dir():
        raise SeerError(
            code=EXIT_USER_ERROR,
            kind="user_error",
            message=f"path is not an existing directory: {path}",
            remediation="pass an existing directory that contains a git repository.",
        )

    # Validate that path is inside a git work tree before running git log.
    rev_parse = _run_git(
        ["rev-parse", "--is-inside-work-tree"],
        repo,
        allow_nonzero=True,
    )
    if rev_parse.returncode != 0 or rev_parse.stdout.strip() != "true":
        raise SeerError(
            code=EXIT_USER_ERROR,
            kind="user_error",
            message=f"not a git repository: {path}",
            reason=(rev_parse.stderr.strip()[:200] or "git rev-parse rejected the path."),
            remediation="pass a path that is inside a git work tree.",
        )

    # Retrieve the last n commits: SHA <TAB> ISO date <TAB> subject
    log_result = _run_git(
        ["log", f"-n{n}", "--pretty=format:%H%x09%cI%x09%s"],
        repo,
        allow_nonzero=True,
    )

    # git log exits 128 in a completely empty repo (no commits at all).
    # Only treat exit 128 as "empty repo" when the sentinel phrase is present;
    # any other fatal error is surfaced as EXIT_ENV_ERROR.
    if log_result.returncode == 128:
        stderr_lc = log_result.stderr.lower()
        if "does not have any commits yet" not in stderr_lc and "fatal" in stderr_lc:
            raise SeerError(
                code=EXIT_ENV_ERROR,
                kind="env_error",
                message="git log failed",
                reason=log_result.stderr.strip()[:400],
            )
    elif log_result.returncode != 0:
        raise SeerError(
            code=EXIT_ENV_ERROR,
            kind="env_error",
            message=f"git log exited with code {log_result.returncode}",
            reason=log_result.stderr.strip()[:400],
        )

    raw_log = log_result.stdout.strip()
    if not raw_log:
        return {"commits": []}

    # Determine which commit is the initial commit (no parent).
    # We do this by getting the root commit SHA.
    root_result = _run_git(
        ["rev-list", "--max-parents=0", "HEAD"],
        repo,
        allow_nonzero=True,
    )
    root_sha = root_result.stdout.strip() if root_result.returncode == 0 else None

    commits: list[dict[str, Any]] = []

    for line in raw_log.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        full_sha, iso_date, subject = parts
        short_sha = full_sha[:7]
        date = iso_date.split("T")[0]
        is_initial = root_sha is not None and full_sha == root_sha

        # Get the list of files changed in this commit.
        if is_initial:
            diff_args = ["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", full_sha]
        else:
            diff_args = ["diff-tree", "--no-commit-id", "--name-only", "-r", full_sha]

        files_result = _run_git(diff_args, repo, allow_nonzero=True)
        changed_files = [f.strip() for f in files_result.stdout.splitlines() if f.strip()]

        changes = [_file_diff(full_sha, f, repo, is_initial=is_initial) for f in changed_files]

        commits.append(
            {
                "sha": short_sha,
                "date": date,
                "subject": subject,
                "changes": changes,
            }
        )

    return {"commits": commits}


def _render_change_line(ch: dict[str, Any]) -> str:
    """Format one changed-file entry as a Markdown bullet line."""
    file_name = ch.get("file", "")
    added = ch.get("added") or []
    removed = ch.get("removed") or []
    modified = ch.get("modified") or []
    if not (added or removed or modified):
        return f"- {file_name}"
    parts: list[str] = []
    if added:
        parts.append(f"+{', '.join(added)}")
    if removed:
        parts.append(f"-{', '.join(removed)}")
    if modified:
        parts.append(f"~{', '.join(modified)}")
    return f"- **{file_name}**: {', '.join(parts)}"


def render_recent_markdown(data: dict[str, Any]) -> str:
    """Render a :func:`recent_with_outline` result dict as Markdown.

    Each commit gets a ``###`` heading followed by a bullet list of changed
    files.  Python files with non-empty symbol diffs render with ``+added``,
    ``-removed``, ``~modified`` inline annotations.
    """
    commits = data.get("commits") or []
    if not commits:
        return "_No commits found._\n"

    lines: list[str] = []
    for commit in commits:
        sha = commit.get("sha", "")
        date = commit.get("date", "")
        subject = commit.get("subject", "")
        changes = commit.get("changes") or []
        lines.append(f"### {sha} ({date}) {subject}")
        lines.append("")
        for ch in changes:
            lines.append(_render_change_line(ch))
        lines.append("")

    return "\n".join(lines)
