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

## Workspace Context

The GitHub remote is `agentculture/seer-cli`. When opening PRs or posting comments here as an AI assistant, sign them so it's clear they're AI-authored — e.g. `- seer (Claude)`.
