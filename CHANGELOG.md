# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-05-15

### Changed

- **scripts-eval: replaced hook-driven cell capture with operator-driven
  `trial.py`.** The new `experiments/scripts_eval/trial.py` exposes two
  subcommands — `start` (stamps in-flight metadata + `start_time`,
  reads `CLAUDE_CODE_SESSION_ID`, prints a `trial_id`) and `end` (reads
  the subagent's sidechain transcript at
  `$HOME/.claude/projects/<encoded_cwd>/<session>/subagents/agent-*.jsonl`,
  parses the real CC schema, and writes the cell JSON). Operator
  workflow per trial becomes `trial start → dispatch Agent → trial end`.
  The previous `SubagentStop` hook + `capture.py` chain parsed a stale
  CC schema (`ts` epoch float, top-level `content`) against the wrong
  file (operator transcript, not subagent sidechain), producing cells
  with empty `answer_text`. Tests now use a sanitized real sidechain as
  the fixture, refusing to mock a schema that might diverge from reality.
- `.claude/skills/eval/SKILL.md` updated to invoke `trial start` /
  `trial end` per dispatch instead of `capture` after dispatch.
- `docs/eval-rounds/2026-05-15-round-01.md` preflight points at
  `switch-arm.sh` for env + skill-state setup.
- Deleted `experiments/scripts_eval/capture.py` (replaced by `trial.py`)
  and `experiments/scripts_eval/hooks/subagent_stop.py` (replaced by
  `trial end`); their tests
  (`tests/scripts_eval/test_capture.py`,
  `tests/scripts_eval/test_hooks_subagent_stop.py`) went with them. The
  fake-schema fixtures
  `tests/scripts_eval/fixtures/{transcript_min,transcript_with_late_msg}.jsonl`
  — which made the broken hook's tests pass — are also gone. The
  `SubagentStop` hook entry was dropped from `.claude/settings.json`.

### Added

- `experiments/scripts_eval/switch-arm.sh` — sourceable helper that
  flips between arm A and arm C: exports `SEER_EVAL_RUN_ID` /
  `SEER_EVAL_ARM` and moves `.claude/skills/repo-map` aside (arm A) or
  restores it (arm C). Idempotent on re-source; refuses direct
  execution; guards against half-broken disk state.
- `experiments/scripts_eval/backfill.py` — one-shot script that
  re-extracts cells captured by the previous (broken) hook from their
  sidechain transcripts. Used to recover the 6 round-01
  `agtag/q-profile-overview` cells. Matches each cell to its sidechain
  via the CC-emitted `<agent>.meta.json` description (e.g.
  `Arm-A t1: agtag profile`) plus a corpus-aware (target, question)
  identification from the sidechain's first user prompt; skips judge
  dispatches whose description starts with `scripts_eval judge:`.
- `tests/scripts_eval/fixtures/sidechain_min.jsonl` — sanitized real
  CC subagent sidechain transcript, the canonical fixture for extraction
  tests.

### Fixed

- Round 01 `agtag/q-profile-overview` cells (both arms, all 3 trials)
  had empty `answer_text` from the previous capture chain. Backfilled
  via the new extraction logic; judges re-run against the now-populated
  text. Final verdicts: A=1, C=2, tie=0 (all slight margins). Notable
  finding: arm-C produced competitive answers without invoking
  `repo-map` — appropriate behavior for an overview question on a small
  repo, per the established evaluation framing (skill should be reached
  for when needed, not unconditionally).

## [0.3.3] - 2026-05-15

### Changed

- `.github/workflows/tests.yml` realigned to `agentculture/steward` as the
  source of truth: the `test` job now runs only pytest + the SonarCloud
  scan, with lint extracted into a sibling `lint` job
  (black/isort/flake8/bandit/markdownlint-cli2). `SONAR_TOKEN` is promoted
  directly to job env so the step's `if:` gates on it inline — matches
  steward's wiring exactly.
- `sonar-project.properties`: dropped `sonar.qualitygate.wait=true` /
  `sonar.qualitygate.timeout=600` (the only real divergence from steward —
  CI no longer blocks on the quality-gate decision; SonarCloud's PR comment
  still surfaces the outcome). Also dropped `sonar.projectName` and
  `sonar.sourceEncoding` for byte-level parity with
  `steward/sonar-project.properties`.

## [0.3.2] - 2026-05-15

### Added

- scripts-eval: `eval` skill (`.claude/skills/eval/SKILL.md`) — locks the operator procedure for running one set of the harness (one `(target, question)` row × 3 trials × one arm) as a reusable, round-agnostic skill. Reads `$SEER_EVAL_RUN_ID` and writes to `docs/eval-rounds/$SEER_EVAL_RUN_ID.md`, so it serves round 01 today and future rounds without modification. Bundles the preflight checks (env vars, `repo-map` skill state, manifest init), arm-A/arm-C procedures, the judge-subagent dispatch contract (`description: scripts_eval judge: <pair_key>`), and the post-set summarize + commit. Listed in `docs/skill-sources.md` as a seer-cli-original skill (like `repo-map`).

### Changed

- docs/eval-rounds/2026-05-15-round-01.md trimmed to round-specific bits only (run metadata, preflight, paste templates, evidence accumulator). The procedure now lives in the `eval` skill — single source of truth, picked up automatically when an operator session triggers the skill.
- scripts-eval: `eval` skill replaces the `python3 -c "import json; …"` prompt-extraction step with `jq -j '.prompt_text'` — no Python required, and `-j` joins without a trailing newline so the dispatched bytes match what `prepare` emitted. Aligns with the project's `uv run`-managed Python and avoids ad-hoc stdlib invocations in operator runbooks.

### Fixed

- scripts-eval: `summarize._replace_between` switched from a `re.DOTALL` regex pattern to index-based slicing on the original text. A judge's reasoning that verbatim quoted a section-end marker (e.g., `<!-- evidence:end -->`) could previously terminate the regex at the inner occurrence on a subsequent summarize call, corrupting the file and breaking idempotence. The render step now also disarms any literal marker strings in the payload by rewriting `<!--` to `<\!--` inside the matched marker text — markdown renders identically, and `str.find` no longer matches the escaped form as a marker on later passes.

## [0.3.1] - 2026-05-15

### Added

- scripts-eval: `summarize.py` — accumulator that walks `results/<run_id>/arm-A/` and `arm-C/`, groups paired cells by `(repo_id, question_id)`, and rewrites two marker-bracketed regions of a tracked evidence markdown file: a per-set progress table (`<!-- runstate:... -->`) and per-set verdict tables with judge reasoning (`<!-- evidence:... -->`). Idempotent on replay so the operator runs it at the end of every session without thinking about state.
- docs/eval-rounds/2026-05-15-round-01.md — single tracked file that serves as both the runbook (preflight + per-arm procedure + paste templates) and the evidence accumulator (auto-updated by `summarize.py`). Raw per-cell JSONs stay gitignored under `results/2026-05-15-round-01/`; this file is the committed evidence for round 01.

## [0.3.0] - 2026-05-15

### Changed

- scripts-eval: judge.py now runs the pairwise blind LLM-as-judge through an operator-dispatched `general-purpose` subagent instead of calling the Anthropic API directly. CLI gains `prepare` (emit subagent jobs, one per paired cell, in a stable seeded-blinding order) and `record` (parse the subagent's verdict text, validate the vocabulary, de-blind A/C, and write the locked-surface `judge` block to both paired cell JSONs; idempotent on replay). All LLM cognition in the harness now happens inside subagents.
- scripts-eval: `pre_tool` hook skips Agent dispatches whose `tool_input.description` starts with `scripts_eval judge:` so judge dispatches don't drop orphan `.jsonl` files into `raw/` (capture.py picks the oldest-mtime *.jsonl and would otherwise consume a judge file as the wrong tester cell). The description prefix is a load-bearing contract documented in RUNBOOK.md.
- scripts-eval: RUNBOOK judging section rewritten for the per-pair prepare → dispatch → record operator loop. `ANTHROPIC_API_KEY` is no longer a prerequisite in the operator's shell — the subagent's API call is harness-managed.

### Fixed

- scripts-eval: judge no longer sees each answer's `### tools_used` / `### evidence` tail. Those tails de-blind the pairwise comparison — arm C's tail can name `scripts/profile.sh` or `seer.repo`, immediately revealing the equipped arm to the judge. The strip is applied in `prepare`'s view only; `answer_text` on disk is unchanged so `validate.py` recall scores stay stable.
- scripts-eval: `_extract_json` now scans for balanced `{...}` spans (respecting nested braces and quoted strings) and returns the *first* valid JSON object, matching the RUNBOOK contract. The previous greedy `r"\{.*\}"` regex captured from the first `{` to the *last* `}`, so a chatty subagent emitting multiple JSON blobs (false start + correction) would either fail to parse or persist the wrong object.
- scripts-eval: `record_verdict` now validates blind-label complementarity before any disk I/O — both labels must be in `{answer_X, answer_Y}` and distinct. The previous code allowed identical labels through `_de_blind`, which would silently return `A` and persist the wrong winner to the locked-surface `judge.comparison`.

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
