---
name: code-lookup
description: >
  Three verbs for codebase structure — each collapses N reads into 1
  structured call.

  **`classify`** — `scripts/classify.sh [<path>]` returns: manifest type +
  language, and a tag list (`python`, `node`, `bash`, `cli`, `library`,
  `dockerized`, `tested`, `packaged-pypi`, `agentculture-sibling`), each with
  the concrete evidence that fired it (e.g. "Dockerfile present",
  "[project.scripts] defines `foo = …`", ".github/workflows/publish.yml uploads
  to pypi.org"). Prefer over manually reading pyproject.toml + Dockerfile +
  workflows + culture.yaml separately — one call collapses ~5–7 Read/Bash steps
  into a structured tag list with citations. When NOT to use: if you only need
  one specific fact (e.g. "is there a Dockerfile"), Read/glob is cheaper.
  Markdown by default; `--json` for machine-readable.

  **`grep`** — `scripts/grep.sh <pattern> [<path>]` runs ripgrep across a
  codebase and annotates every match with its enclosing Python function/class
  name via the AST scope resolver. Returns `{"pattern": "…", "matches":
  [{"file", "line", "scope", "text"}, …]}`. Requires `ripgrep` (`rg`) on PATH.
  Prefer over raw `grep` when you also need to know *which function* owns the
  match. Markdown by default; `--json` for machine-readable.

  **`recent`** — `scripts/recent.sh [<path>] [-n N]` runs `git log -n N` and
  for each commit pairs every changed file with a structural symbol-diff at the
  AST level. Returns `{"commits": [{"sha", "date", "subject", "changes":
  [{"file", "added": […], "removed": […], "modified": […]}, …]}, …]}`.
  Non-Python files always have empty `added`/`removed`/`modified` lists (callers
  see *that* the file changed, no symbol detail). The `modified` heuristic
  compares function line-spans; pure line shifts can cause false positives (a
  deferred improvement). Prefer over `git log` + manual file reading when you
  need to know *which symbols* changed across N commits. Markdown by default;
  `--json` for machine-readable.
---

# code-lookup

Sibling of `repo-map`. While `repo-map` answers *"tell me about this
repo"* (profile + connections + workspace graph), `code-lookup` is the
slot for *"what shape is this project? where is X? what changed
recently?"* questions.

## When to use

| Mode | Invocation |
| --- | --- |
| Classify a project by type tags | `scripts/classify.sh [<path>]` |
| Search with enclosing-scope annotation | `scripts/grep.sh <pattern> [<path>]` |
| Recent commits with AST symbol diffs | `scripts/recent.sh [<path>] [-n N]` |

## Output shapes

### `classify`

`scripts/classify.sh /path/to/repo` returns one markdown report with:

- a header line naming the path
- `**Manifest:**` line with the canonical manifest + language
- `**Tags:**` summary line
- a `## Tags` table where each row is `| <tag> | <evidence> |`

Pass `--json` for the machine-readable envelope.

### `grep`

`scripts/grep.sh <pattern> [<path>]` returns a Markdown table with columns
`File | Line | Scope | Text`. Each match includes the enclosing Python
function or class name (`scope`). Module-level lines show `_module_`.

Pass `--json` for `{"pattern": "…", "matches": [{…}, …]}`.

Note: requires `ripgrep` (`rg`) on PATH.

### `recent`

`scripts/recent.sh [<path>] [-n N]` (default N=20) returns Markdown
`### <sha> (<date>) <subject>` headings with bullet lists of changed
files. Python files with non-empty symbol diffs render as:
`- **file.py**: +added, -removed, ~modified`.

Pass `--json` for the full structured envelope.

## Composition with repo-map

For "tell me about this repo from scratch":

1. `classify <path>` — what *kind* of repo is this (CLI? service?
   dockerized?). Cheap.
2. `bash .claude/skills/repo-map/scripts/profile.sh <path>` — the
   structured profile (deps, package tree, vendored skills, recent
   changelog).

One call each, no re-grepping.

## Engine

`seer/lookup/` — `python -m seer <verb> …`. Each shell wrapper is a
one-liner; the agent-facing contract is the verb and its flags.
