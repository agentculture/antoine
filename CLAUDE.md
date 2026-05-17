# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Dispatching subagents — inject code-lookup / repo-map directives

This table applies in two places for **the conversational agent that loads
this CLAUDE.md at session start** (i.e. you, the parent reading this now —
not subagents you dispatch):

1. **When you delegate** a task to a subagent (Explore, general-purpose,
   Plan, etc.) whose task shape matches a row below: include the matching
   directive **verbatim** in the subagent's prompt.
2. **When you answer first-person** a task shape that matches a row below
   without delegating: invoke the named verb yourself rather than
   ad-hoc combinations of `ls` / `cat` / `grep` / `git` calls. The table
   is one application of a broader rule: prefer a small purpose-built
   script that returns structured high-value data in one call.

| Task shape | Directive (verbatim if delegating; otherwise the verb to invoke yourself) |
|---|---|
| "what changed in the last N commits / which functions or classes changed across commits" | `Use the code-lookup skill's recent verb (.claude/skills/code-lookup/scripts/recent.sh) for the commit + symbol-diff data. Do not call git log / git diff / git show directly for this question.` |
| "where is `<pattern>` referenced / find usages with enclosing scope" | `Use the code-lookup skill's grep verb (.claude/skills/code-lookup/scripts/grep.sh <pattern>) for match + scope. Do not use raw rg / grep for this question.` |
| "what kind of project is this — CLI? library? PyPI-published? dockerized?" | `Use the code-lookup skill's classify verb (.claude/skills/code-lookup/scripts/classify.sh).` |
| "profile this repo / build-test story / repo overview / what fields does pyproject expose" | `Use the repo-map skill's profile verb (.claude/skills/repo-map/scripts/profile.sh).` |

**Why this lives in CLAUDE.md and not in the skill descriptions:** round-2
of the PR #18 organic-adoption smokes showed that **subagents construct
their plan from the prompt body before consulting the skills catalog** —
so a description-shape change on the skill itself does not move adoption
(0 of 2 models picked up `antoine recent` for a question perfectly tuned for
it). Round-3 confirmed the parent-agent path: a fresh session loading the
table delegated *and the subagent invoked the verb directly via the
injected directive*.

**Scope of this rule — empirical:** the table directly governs the parent
agent's behavior at delegation time and first-person execution time. It
does **not** reliably propagate to subagents through CLAUDE.md alone —
round-4 of the smokes (PR #18 commit `171980f`) showed a fresh subagent
receiving the broadened table as ambient context still defaulted to `git
log` via Bash (7 calls, no skill use) for a perfectly-shaped question.
The lever for subagent adoption stays the prompt-body directive injection
in row 1 above — the table does not change that.

## Workspace Context

The GitHub remote is `agentculture/antoine`. When opening PRs or posting comments here as an AI assistant, sign them so it's clear they're AI-authored — e.g. `- antoine (Claude)`.
