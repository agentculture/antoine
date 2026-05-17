# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Name

**antoine** = **"N to 1"** (an-to-one). The name encodes the goal: collapse
the N ad-hoc tool calls an agent would otherwise make against a codebase
(`ls` + `cat` + `grep` + `git log` + `git show` + …) into **one** call to a
purpose-built `kata` verb (or its `antoine` alias — both console scripts are
defined in [`pyproject.toml`](./pyproject.toml); `kata-cli` is the PyPI
**distribution** name, not a command name) that returns the same information
as structured data. Every verb antoine ships is a bet that some recurring
N-call pattern
has a 1-call replacement that is cheaper, more reliable, and easier to
delegate to a subagent. You are that agent — when you face a task shape
covered by the dispatching table below, prefer the 1-call verb.

## Project Status

`antoine` is an AgentCulture sibling repo — **codebase lookup and indexing for
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
uv run antoine --version         # or: uv run python -m antoine
uv run antoine learn             # placeholder verbs: learn / explain / whoami
```

## Test

```bash
uv run pytest -n auto         # full suite
uv run pytest tests/test_cli_chassis.py::test_no_args_prints_help_and_returns_zero -v   # single test (example node id)
```

## Lint / Format

```bash
uv run flake8 --config=.flake8 antoine/ tests/
uv run black antoine/ tests/
uv run isort antoine/ tests/
markdownlint-cli2 "**/*.md"
```

Bandit and pylint run in CI (`.github/workflows/security-checks.yml`).

## Architecture

- `antoine/cli/__init__.py` — the argparse CLI chassis: structured error
  routing (`_AntoineArgumentParser`), `--json` hint detection, and
  `_dispatch` (invokes the verb handler, translating `AntoineError` and bare
  exceptions to structured exit codes). `main()` is the entry point, exposed
  as the `antoine` console script and via `python -m antoine`.
- `antoine/cli/_errors.py` — `AntoineError` and the exit-code policy.
- `antoine/cli/_output.py` — strict stdout/stderr split helpers.
- `antoine/cli/_commands/` — one module per verb, each exposing `register()`.
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
`.claude/settings.json` are **env-var-gated** (`ANTOINE_EVAL_RUN_ID`,
`ANTOINE_EVAL_ARM`) and no-op outside an active eval session, so
day-to-day antoine work is unaffected.

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

## Dispatching subagents — code-lens verbs (first catalog this loop produced)

The four task shapes below have 1-call verbs in
[`code-lens-cli`](https://github.com/agentculture/code-lens-cli) —
the first published results catalog of running kata's
capture/reduce/assess loop on a real codebase (this one). Install with
`uv tool install code-lens-cli`. If installed, prefer the verb; if not,
the loop will eventually re-surface the N-call pattern and the next
catalog release will offer a replacement.

This is the **evidence** view of code-lens-cli: it is what running the
loop produces, not a dependency antoine prescribes downstream. The
verbs lived under `antoine/lookup/` + `antoine/repo/` through 0.10.0;
0.11.0 migrated them out (see [code-lens-cli#2](https://github.com/agentculture/code-lens-cli/issues/2)).

| Task shape | Verb |
|---|---|
| "what changed in the last N commits / which functions or classes changed" | `code-lens recent .` |
| "where is `<pattern>` referenced / find usages with enclosing scope" | `code-lens grep <pattern> .` |
| "what kind of project is this — CLI? library? PyPI-published? dockerized?" | `code-lens classify .` |
| "profile this repo / build-test story / repo overview" | `code-lens profile .` |

Empirical adoption notes for this table (PR #18 round-2/3/4 smokes —
why CLAUDE.md is the lever, not skill descriptions) moved with the
verbs to code-lens-cli's CLAUDE.md.

## Workspace Context

The GitHub remote is `agentculture/antoine`. When opening PRs or posting comments here as an AI assistant, sign them so it's clear they're AI-authored — e.g. `- antoine (Claude)`.
