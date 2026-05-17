---
name: repo-map
description: >
  Mechanical facts about a Python repo or a workspace of related repos —
  in one tool call, instead of N grep/read calls.
  `scripts/profile.sh <path>` returns: package name, version, repo path,
  manifest type + language, entry points, runtime + dev deps, flat
  package layout, depth-2 package tree, build_test (test cmd + coverage
  gate + python_requires), ci_workflows, publish_target (PyPI/GHCR +
  trigger), git_remote (host/owner/repo parsed from origin), module_summaries
  (per-module first-docstring-line summaries), vendored skills with upstream
  provenance, last 3 changelog entries, CITATION.md table, CLAUDE.md
  "Project status" body, extras (culture nick, …); with default online
  enrichment, also returns `github_state` (latest release, open issue count,
  default branch, CI status on default) and `pypi_state` (published version +
  release date). Pass `--basic` to skip Tier-2 and return Tier-1 mechanical
  facts only. Add `--depth deep`
  for: README intro, design-related CLAUDE.md sections, last 10 commit
  subjects.
  `scripts/connections.sh <path> --depth N` returns typed import / cite /
  vendor edges N hops out, plus each neighbor node (add `--profile` to
  inline each node's profile). `scripts/graph.sh [<root>…]` returns every
  repo + every edge in the workspace plus a mermaid diagram. Markdown by
  default; `--json` for machine-readable.
  Prefer this over multiple Read/Bash calls whenever you need ≥2 of those
  fields — one call beats N reads on both tokens and reliability, and the
  output is deterministic so you don't have to defend grep-based guesses.
---

# repo-map

Three verbs, scaling from cheap (one repo, mechanical facts) to opt-in
expensive (entire connected component with deep mind-model materials):

| Mode | Invocation |
| --- | --- |
| One repo, mechanical facts | `scripts/profile.sh <path>` |
| One repo, mind-model materials | `scripts/profile.sh <path> --depth deep` |
| Walk N hops from a repo | `scripts/connections.sh <path> --depth N` |
| Whole workspace at once | `scripts/graph.sh [<root>...]` |

## When to use

When the user asks about a repo or a set of related repos: profile, deps,
who-cites-whom, who-vendors-whom. The scripts collect the deterministic
facts so you (the agent) can spend your tokens on synthesis, not grep.

**Token math:** one `profile.sh` call replaces ~6–10 separate Read calls
(README.md, pyproject.toml, CHANGELOG.md, CLAUDE.md, docs/skill-sources.md,
CITATION.md, culture.yaml, plus directory listings for the package tree
and vendored skills). If your task needs ≥2 of those, call `profile.sh`
once instead of reading them piecemeal.

## When NOT to use

- You already know the exact file you need to read (e.g. one specific
  function's source) — Read it directly.
- You need to *modify* the repo — `repo-map` is read-only.
- The repo isn't a Python project (no `pyproject.toml`) — `profile`
  degrades but the mechanical-facts payload shrinks to mostly empty.

## Compose recipe

For the question "explain how these repos fit together":

1. `scripts/graph.sh [<root>]` once — gets every repo + every edge.
2. If a particular repo needs depth, `scripts/profile.sh <path> --depth deep`.
3. Synthesize the narrative from those outputs. Do **not** re-grep what
   `profile` already reports.

For the question "tell me about *this* repo and what it connects to":

1. `scripts/profile.sh <path>` (or `--depth deep` for narrative-rich).
2. `scripts/connections.sh <path> --depth 1 --profile` for immediate
   neighbors; raise `--depth` to widen.

## Output

Markdown by default — read it directly. Errors include `reason:` and
`hint:` lines. During walks, per-node errors are inlined and the walk
continues (pass `--strict` to flip).

## Configuration

Optional `.claude/skills/repo-map/config.json` for per-workspace defaults:

```json
{
  "roots": ["/home/spark/git"],
  "additional_markers": ["culture.yaml"],
  "skip_dirs": [".git", ".venv", "node_modules", "__pycache__"],
  "default_connections_depth": 1
}
```

Flags always override config.

## Engine

The actual logic lives in `antoine/repo/` and is invoked via
`uv run python -m antoine.repo <verb>`. The shell scripts are one-line wrappers; the
agent-facing contract is the verbs and their flags, not the wrappers.

> **Interpreter note:** the scripts use `uv run --directory <project-root>`
> so they work regardless of the caller's working directory. `uv` resolves
> the correct virtualenv and lock file from the project root automatically.
