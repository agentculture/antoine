# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-05-15

### Changed

- `[tool.coverage.run]`: added `parallel=true`, `concurrency=["thread","multiprocessing"]`, `sigterm=true` so pytest-xdist (`-n auto`) worker shards merge into a single `coverage.xml`. Mirrors `agentculture/culture`. Local verification: 86.03% coverage on 130 tests (was effectively unmergeable across xdist workers before).
- `sonar-project.properties`: added `sonar.projectName=seer-cli`, `sonar.qualitygate.wait=true`, `sonar.qualitygate.timeout=600`. The wait/timeout pair lets `tests.yml` block on SonarCloud's quality-gate decision rather than racing past it, bounded so an unavailable SonarCloud does not hang the runner.

## [0.2.1] - 2026-05-15

### Added

- scripts-eval harness for A/B-testing the repo-map skill (experiments/scripts_eval/) — env-var-gated hooks, three-layer scoring (mechanical/code-validation/LLM-judge), 5-repo round-1 corpus, RUNBOOK + README + judge_rubric.
- experiments dep group with anthropic and jsonschema (use uv sync --group experiments to install).

### Changed

- .claude/settings.json registers the three eval hooks; they no-op outside an active SEER_EVAL_RUN_ID session.

## [0.2.0] - 2026-05-15

### Added

- `repo-map` Claude Code skill plus the underlying `seer.repo` Python
  module. Three verbs — `profile`, `connections`, `graph` — emit
  deterministic markdown (default) or JSON (`--json`) about one repo,
  its connected neighbors, or an entire workspace.
- Generic repo detection: any directory with `pyproject.toml`,
  `.claude/skills/`, or a user-configured marker file qualifies.
  Optional `.claude/skills/repo-map/config.json` for per-workspace
  defaults (roots, additional markers, skip dirs).
- `SeerError` extended with `reason` and `kind` fields; `emit_error`
  text mode now prints a `reason:` line between `error:` and `hint:`
  when present. `EXIT_INTERNAL = 3` reserved for bug-wrapped exceptions.

### Changed

- `pyyaml>=6.0` added as the first runtime dependency (used for
  `culture.yaml` parsing and any other YAML marker the user configures).

## [0.1.0] - 2026-05-15

### Added

- AgentCulture sibling scaffold: the `seer` package (hatchling,
  Python >=3.12, zero runtime deps) with the shared CLI chassis —
  structured errors, a strict stdout/stderr split, and `--json` support.
- Placeholder agent-first verbs `learn` / `explain` / `whoami` — honest
  "not yet implemented; seer is greenfield" stubs.
- CI workflows: `tests.yml` (pytest + coverage + flake8 + bandit +
  SonarCloud + version-check), `security-checks.yml` (bandit + pylint),
  `publish.yml` (TestPyPI on PR, PyPI on main, via OIDC Trusted Publishing).
- `culture.yaml` declaring the `seer` agent nick.
- Vendored skills from steward: `cicd`, `communicate`, `run-tests`,
  `sonarclaude`, `version-bump`. Provenance tracked in
  `docs/skill-sources.md`.
- Repo-local lint configs: `.flake8`, `.markdownlint-cli2.yaml`,
  `.pre-commit-config.yaml`; `sonar-project.properties`; the
  `.claude/skills.local.yaml.example` per-machine config template.

Resolves #1.
