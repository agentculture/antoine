---
name: repo-map
description: >
  Profile a Python repo, walk its connected repos N hops out, or build a
  whole-workspace graph — deterministically, without re-grepping. Backed
  by `seer.repo` in this repo. Use when a user asks to understand a repo
  or a workspace of related repos: what's there, what depends on what,
  and how they fit together. Output is markdown by default; pass `--json`
  for machine-readable.
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

The actual logic lives in `seer/repo/` and is invoked via
`uv run python -m seer.repo <verb>`. The shell scripts are one-line wrappers; the
agent-facing contract is the verbs and their flags, not the wrappers.

> **Interpreter note:** the scripts use `uv run --directory <project-root>`
> so they work regardless of the caller's working directory. `uv` resolves
> the correct virtualenv and lock file from the project root automatically.
