---
name: code-lookup
description: >
  Classify what kind of project a repo is — in one tool call, with
  deterministic tags + per-tag evidence. `scripts/classify.sh [<path>]`
  returns: manifest type + language, and a tag list (`python`, `node`,
  `bash`, `cli`, `library`, `dockerized`, `tested`, `packaged-pypi`,
  `agentculture-sibling`), each with the concrete evidence that fired
  it (e.g. "Dockerfile present", "[project.scripts] defines `foo = …`",
  ".github/workflows/publish.yml uploads to pypi.org"). Markdown by
  default; `--json` for machine-readable. Prefer this over manually
  reading pyproject.toml + Dockerfile + workflows + culture.yaml
  separately — one call collapses ~5–7 Read/Bash steps into a
  structured tag list with citations. When NOT to use: if you only
  need one specific fact (e.g. "is there a Dockerfile"), Read/glob is
  cheaper than this verb.
---

# code-lookup

Sibling of `repo-map`. While `repo-map` answers *"tell me about this
repo"* (profile + connections + workspace graph), `code-lookup` is the
slot for *"what shape is this project? where is X? what's in this
file?"* questions. v1 ships `classify` only; future verbs (`outline`,
`find-symbol`) will land here.

## When to use

| Mode | Invocation |
| --- | --- |
| Classify a project by type tags | `scripts/classify.sh [<path>]` |

## Output

`scripts/classify.sh /path/to/repo` returns one markdown report with:

- a header line naming the path
- `**Manifest:**` line with the canonical manifest + language
- `**Tags:**` summary line
- a `## Tags` table where each row is `| <tag> | <evidence> |`

Pass `--json` for the machine-readable envelope (`{ok, data}` shape,
same as `repo-map`).

## Composition with repo-map

For "tell me about this repo from scratch":

1. `classify <path>` — what *kind* of repo is this (CLI? service?
   dockerized?). Cheap.
2. `bash .claude/skills/repo-map/scripts/profile.sh <path>` — the
   structured profile (deps, package tree, vendored skills, recent
   changelog).

One call each, no re-grepping.

## Engine

`seer/lookup/` — `python -m seer classify <path>`. The shell wrapper is
a one-liner; the agent-facing contract is the verb and its flags.
