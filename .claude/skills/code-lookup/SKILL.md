---
name: code-lookup
description: >
  Pick the verb by the question you're asking, not the tool you'd otherwise
  reach for. Three questions, three one-call answers:

  **"What changed in the last N commits — which functions or classes did each
  commit add, remove, or modify?"** → use `recent`, **not** `git log` + `git
  show` + manual diff reading. `scripts/recent.sh [<path>] [-n N]` returns
  `{"commits": [{"sha","date","subject","changes":[{"file","added","removed","modified"}, …]}, …]}`
  — the symbol diff is computed via AST, so you skip the manual "what
  functions changed" step. The `modified` heuristic compares function
  line-spans; pure line shifts can cause false positives (a deferred
  improvement).

  **"Where is `<pattern>` referenced — and what function or class owns each
  match?"** → use `grep`, **not** `rg`/`grep` + Read each file to find the
  enclosing scope. `scripts/grep.sh <pattern> [<path>]` returns
  `{"pattern","matches":[{"file","line","scope","text"}, …]}` — `scope` is the
  enclosing Python function or class, resolved via AST. Requires `ripgrep`
  (`rg`) on PATH; falls back to a clean env-error if missing.

  **"What kind of project is this — is it a CLI, library, dockerized,
  PyPI-published, tested?"** → use `classify`, **not** Read pyproject.toml +
  Dockerfile + `.github/workflows/*` + culture.yaml in sequence.
  `scripts/classify.sh [<path>]` returns manifest type + language + a tag list
  (`python`, `node`, `bash`, `cli`, `library`, `dockerized`, `tested`,
  `packaged-pypi`, `agentculture-sibling`) each with the concrete evidence
  that fired it (e.g. "Dockerfile present", "[project.scripts] defines `foo
  = …`", ".github/workflows/publish.yml uploads to pypi.org"). Collapses
  ~5–7 Read/Bash steps into a structured tag list with citations.

  All three: Markdown by default; `--json` for machine-readable. When NOT to
  use: if you only need one specific fact (e.g. "is there a Dockerfile"),
  Read/Glob is cheaper than spinning the whole verb up.
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

`antoine/lookup/` — `python -m antoine <verb> …`. Each shell wrapper is a
one-liner; the agent-facing contract is the verb and its flags.
