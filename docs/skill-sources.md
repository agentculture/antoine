# Skill sources — vendored skill provenance

antoine vendors cross-sibling skills from `steward`, the AgentCulture skill
supplier. This follows the **cite, don't import** pattern: each skill is
copied into `.claude/skills/`, owned locally, and may diverge. Nothing
imports across repos at runtime.

This file is the upstream/downstream map. When upstream changes, re-sync
explicitly — these copies do not auto-update.

| Skill | Re-vendor from | Vendored | Runtime backing & notes |
|-------|----------------|----------|-------------------------|
| `cicd` | `steward` (`../steward/.claude/skills/cicd/`) | 2026-05-15 | **Runtime:** as of steward 0.12.0 the core PR-lifecycle verbs (`lint` / `open` / `read` / `reply` / `delta`) are a thin delegate to `agex pr` from `agentculture/agex-cli` — `agex` must be installed (`uv tool install agex-cli`). Steward keeps two extensions on top — `status` (SonarCloud gate + hotspots + unresolved-thread tally) and `await` (`agex pr read --wait` + `status`, non-zero exit on Sonar ERROR / unresolved threads). **Divergence:** local script patch — `scripts/portability-lint.sh` drops the GNU-only `xargs -r` flag (two sites, marked `# antoine divergence:`) so the lint runs on BSD/macOS `xargs`; `-r` was redundant because both inputs are already guarded non-empty. Raised by Qodo on PR #3; should be filed upstream on `agentculture/steward` so the fix re-converges on next re-vendor. Body prose also references steward-specific constructs (e.g. `steward doctor`, the `STEWARD_PR_AWAIT_WAIT` env var); these are inherited context, not antoine-actionable. |
| `communicate` | `steward` (`../steward/.claude/skills/communicate/`) | 2026-05-15 | **Runtime:** as of steward 0.11.0 the GitHub issue-I/O verbs (`post-issue` / `post-comment` / `fetch-issues`) are thin wrappers around `agtag` (>=0.1) — `agtag` must be installed. Signatures resolve from the local `culture.yaml` first-agent `suffix` (here: `antoine`); mesh messages stay unsigned. **Divergence:** none — vendored verbatim. Body prose references steward as the supplier; the `steward announce-skill-update` broadcast verb is steward-cli-only and not available to antoine. |
| `run-tests` | `steward` (`../steward/.claude/skills/run-tests/`) | 2026-05-15 | None — portable verbatim. Coverage source resolves from `[tool.coverage.run]` in `pyproject.toml`. |
| `sonarclaude` | `steward` (`../steward/.claude/skills/sonarclaude/`) | 2026-05-15 | None — portable verbatim. Project key resolves from `$SONAR_PROJECT` / `--project` (antoine's key is `agentculture_antoine`). |
| `version-bump` | `steward` (`../steward/.claude/skills/version-bump/`) | 2026-05-15 | None — portable verbatim. Pure Python, no per-repo customization. antoine's `CHANGELOG.md` keeps a `# Changelog` + intro-prose header, so the first `## [` entry is a valid insertion point for the upstream script. |
| `repo-map` | _internal implementation_ — antoine origin | 2026-05-15 | **Runtime:** thin shell wrappers under `.claude/skills/repo-map/scripts/{profile,connections,graph}.sh` that invoke `uv run --directory <repo-root> python -m antoine.repo <verb>`. Engine lives in `antoine/repo/` in this repo. **Divergence:** N/A — this skill is original to antoine, not vendored from steward. If/when promoted upstream, this row flips to a `Re-vendor from steward` pointer. |
| `code-lookup` | _internal implementation_ — antoine origin | 2026-05-16 | **Runtime:** thin shell wrapper under `.claude/skills/code-lookup/scripts/classify.sh` that invokes `uv run --directory <repo-root> python -m antoine classify`. Engine lives in `antoine/lookup/` in this repo. **Divergence:** N/A — original to antoine, sibling of `repo-map`. If/when promoted upstream, this row flips to a `Re-vendor from steward` pointer. |
| `eval` | _internal implementation_ — antoine origin | 2026-05-16 | **Runtime:** locked operator procedure for one scripts-eval set (one `(target, question)` row × 3 trials × one arm). Three arms — **A** (banned), **B** (directed), **C** (organic) — and two judge pairs — **A-vs-B** ("do the skills help when used?") and **A-vs-C** ("do the skills get adopted organically?"). Backing CLIs live in `experiments/scripts_eval/` (`trial`, `validate`, `judge`, `summarize`, `manifest`); hooks live in `experiments/scripts_eval/hooks/`. `judge prepare --pair AB\|AC` selects the pair; verdicts land under `cell["judges"][pair]` (the AC pair also mirrors to legacy `cell["judge"]`). Round-agnostic — reads `$ANTOINE_EVAL_RUN_ID` and writes the round's accumulator at `docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md`. **Divergence:** N/A — original to antoine (the harness only exists here). If/when promoted upstream, this row flips to a `Re-vendor from steward` pointer. |

## Vendoring policy

- **Cite, don't import.** Skills are copied, not symlinked or installed as
  a dependency.
- **Re-sync explicitly.** When upstream changes, re-vendor from
  `../steward/.claude/skills/<name>/`.
- **Diverge intentionally.** Record any divergence in the table above and
  in the downstream `SKILL.md` frontmatter `description`.
