# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

`seer-cli` is an AgentCulture sibling repo — **codebase lookup and indexing for
agent skills**. The onboarding scaffold is in place (package, CLI chassis, CI,
vendored skills); the actual lookup and indexing engine — how codebases are
scanned, the index format, where it is stored, and how agent skills consume the
lookups — has **not** been designed yet. The `learn` / `explain` / `whoami`
verbs are honest placeholder stubs.

## Build / Install

```bash
uv sync                       # install the package + dev dependencies
```

## Run

```bash
uv run seer --version         # or: uv run python -m seer
uv run seer learn             # placeholder verbs: learn / explain / whoami
```

## Test

```bash
uv run pytest -n auto         # full suite
uv run pytest tests/test_cli_chassis.py::test_no_args_prints_help_and_returns_zero -v   # single test (example node id)
```

## Lint / Format

```bash
uv run flake8 --config=.flake8 seer/ tests/
uv run black seer/ tests/
uv run isort seer/ tests/
markdownlint-cli2 "**/*.md"
```

Bandit and pylint run in CI (`.github/workflows/security-checks.yml`).

## Architecture

- `seer/cli/__init__.py` — the argparse CLI chassis: structured error
  routing (`_SeerArgumentParser`), `--json` hint detection, and
  `_dispatch` (invokes the verb handler, translating `SeerError` and bare
  exceptions to structured exit codes). `main()` is the entry point, exposed
  as the `seer` console script and via `python -m seer`.
- `seer/cli/_errors.py` — `SeerError` and the exit-code policy.
- `seer/cli/_output.py` — strict stdout/stderr split helpers.
- `seer/cli/_commands/` — one module per verb, each exposing `register()`.
  All three verbs are currently greenfield stubs.

## Version Management

Every PR bumps the version in `pyproject.toml` (CI's `version-check` job
blocks merge if it matches `main`) and prepends a `CHANGELOG.md` entry
(convention — not CI-enforced). The vendored `version-bump` skill does both.

## Vendored Skills

`.claude/skills/` holds skills vendored from `steward` (cite, don't import).
Provenance and divergence are tracked in `docs/skill-sources.md`. Re-sync
from `../steward/.claude/skills/<name>/`.

## Experimental harness

`experiments/scripts_eval/` is the round-1 A/B-test harness for the
`repo-map` skill. The three Claude Code hooks wired in
`.claude/settings.json` are **env-var-gated** (`SEER_EVAL_RUN_ID`,
`SEER_EVAL_ARM`) and no-op outside an active eval session, so
day-to-day seer-cli work is unaffected.

When asked to run an eval round, work the harness, or interpret its
results, read these in order:

1. [`experiments/scripts_eval/README.md`](experiments/scripts_eval/README.md)
   — what / why / repeatability for fresh contributors.
2. [`experiments/scripts_eval/RUNBOOK.md`](experiments/scripts_eval/RUNBOOK.md)
   — operator procedure (per-cell loop, two arm sessions, violation
   handling).
3. [`docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md`](docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md)
   — design rationale and open questions.
4. [`docs/superpowers/plans/2026-05-15-scripts-eval-harness.md`](docs/superpowers/plans/2026-05-15-scripts-eval-harness.md)
   — the full TDD implementation plan that built it.

Install the harness's deps with `uv sync --group experiments` (adds
`anthropic` for the LLM-as-judge and `jsonschema` for corpus
validation). Tests live under `tests/scripts_eval/` and run as part of
the normal `uv run pytest` suite.

The harness gates the planned redesign of the `learn` / `explain` /
`whoami` placeholder verbs into `learn` / `explain` / `overview` /
`doctor`. **That verb redesign is intentionally a follow-up
brainstorm** — fed by the eval results, not by the harness's
existence.

## Dispatching subagents — inject code-lookup / repo-map directives

When delegating a task to a subagent (Explore, general-purpose, Plan, etc.),
check whether the task shape matches one of the rows below; if so, include
the matching directive **verbatim** in the subagent's prompt. **These shapes
apply to your own first-person lookups too — the table is one application
of a broader rule: prefer a small purpose-built script that returns
structured high-value data in one call over an ad-hoc combination of
`ls` / `cat` / `grep` / `git` calls.**

| Subagent task shape | Directive to add to the subagent prompt |
|---|---|
| "what changed in the last N commits / which functions or classes changed across commits" | `Use the code-lookup skill's recent verb (.claude/skills/code-lookup/scripts/recent.sh) for the commit + symbol-diff data. Do not call git log / git diff / git show directly for this question.` |
| "where is `<pattern>` referenced / find usages with enclosing scope" | `Use the code-lookup skill's grep verb (.claude/skills/code-lookup/scripts/grep.sh <pattern>) for match + scope. Do not use raw rg / grep for this question.` |
| "what kind of project is this — CLI? library? PyPI-published? dockerized?" | `Use the code-lookup skill's classify verb (.claude/skills/code-lookup/scripts/classify.sh).` |
| "profile this repo / build-test story / repo overview / what fields does pyproject expose" | `Use the repo-map skill's profile verb (.claude/skills/repo-map/scripts/profile.sh).` |

**Why this lives in CLAUDE.md and not in the skill descriptions:** round-2
of the PR #18 organic-adoption smokes showed that **subagents construct their
plan before consulting the skills catalog**, so a description-shape change
on the skill itself does not move adoption (0 of 2 models picked up `seer
recent` for a question perfectly tuned for it). The dispatcher is the right
lever: the parent agent loads CLAUDE.md at session start and can inject the
directive into the subagent's prompt **before** the subagent forms its plan.
Directed-use adoption is reliable; organic adoption is not.

## Workspace Context

The GitHub remote is `agentculture/seer-cli`. When opening PRs or posting comments here as an AI assistant, sign them so it's clear they're AI-authored — e.g. `- seer (Claude)`.
