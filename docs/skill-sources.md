# Skill sources — vendored skill provenance

antoine vendors cross-sibling skills from `guildmaster`, the AgentCulture
skill supplier. The supplier role migrated from `steward` to `guildmaster` on
2026-05-25 ([antoine#28](https://github.com/agentculture/antoine/issues/28)).
This follows the **cite, don't import** pattern: each skill is copied into
`.claude/skills/`, owned locally, and may diverge. Nothing imports across
repos at runtime.

This file is the upstream/downstream map. When upstream changes, re-sync
explicitly — these copies do not auto-update.

| Skill | Re-vendor from | Vendored | Runtime backing & notes |
|-------|----------------|----------|-------------------------|
| `agent-config` | `guildmaster` (`../guildmaster/.claude/skills/agent-config/`) | 2026-05-25 | New in the cutover. Backs guildmaster's `guild show` — a read-only inventory of one agent's config (system-prompt file + `culture.yaml` + `.claude/skills` index). Ships `scripts/show.sh` + `data/backend-fingerprints.yaml`. Soft dep `PyYAML` for suffix mode only. **Divergence:** (1) SKILL.md description reworded `Vendored from steward` → `Vendored from guildmaster (originated in steward)` — antoine cites guildmaster (its supplier); steward is the origin author. (2) `scripts/show.sh`'s awk description-extractor also stops at the frontmatter terminator (`^---$`), not just the next YAML key (marked `# antoine divergence:`); without it, a `description:` that is the last frontmatter key bleeds into the markdown body — triggered by this PR's `type: command` normalization placing `type:` before `description:`. Raised by Qodo on PR #29; file upstream on `agentculture/guildmaster` so it re-converges on next re-vendor. Otherwise verbatim (incl. upstream `type: command`). |
| `assign-to-workforce` | `guildmaster` (re-broadcast; origin `agentculture/devague`, `../guildmaster/.claude/skills/assign-to-workforce/`) | 2026-05-25 | New, **inbound** — origin `agentculture/devague`, guildmaster only re-broadcasts. Plan→parallel-implementation operator: reads `devague plan waves` (read-only) and fans tasks out to worktree subagents with TDD-gated merges. **Runtime:** `uv tool install devague` + `git worktree` + the vendored `cicd` skill (gate-3 `agex pr open`). Vendored verbatim (incl. upstream `type: command`). |
| `cicd` | `guildmaster` (`../guildmaster/.claude/skills/cicd/`) | 2026-05-25 | **Runtime:** the core PR-lifecycle verbs (`lint` / `open` / `read` / `reply` / `delta`) are a thin delegate to `agex pr` from `agentculture/agex-cli` — `agex` must be installed (`uv tool install agex-cli`). Two extensions on top — `status` (SonarCloud gate + hotspots + unresolved-thread tally) and `await` (`agex pr read --wait` + `status`, non-zero exit on Sonar ERROR / unresolved threads). **Divergence:** (1) local script patch — `scripts/portability-lint.sh` drops the GNU-only `xargs -r` flag (two sites, marked `# antoine divergence:`) so the lint runs on BSD/macOS `xargs`; `-r` was redundant because both inputs are already guarded non-empty. Raised by Qodo on PR #3; file upstream on `agentculture/guildmaster` so it re-converges on next re-vendor. (2) `type: command` added to `SKILL.md` (guildmaster's copy omits it). Body prose references guildmaster/steward-specific constructs (e.g. the `STEWARD_PR_AWAIT_WAIT` env var); inherited context, not antoine-actionable. |
| `communicate` | `guildmaster` (`../guildmaster/.claude/skills/communicate/`) | 2026-05-25 | **Runtime:** the GitHub issue-I/O verbs (`post-issue` / `post-comment` / `fetch-issues`) are thin wrappers around `agtag` (>=0.1) — `agtag` must be installed. Signatures resolve from the local `culture.yaml` first-agent `suffix` (here: `antoine`); mesh messages stay unsigned. Now also ships the supplier briefing templates (`scripts/templates/skill-new-brief.md`, `skill-update-brief.md`). **Divergence:** `type: command` added to `SKILL.md` (guildmaster's copy omits it); otherwise verbatim. Body prose names guildmaster as the supplier — inherited context; antoine's runtime nick stays `antoine`. |
| `doc-test-alignment` | `guildmaster` (`../guildmaster/.claude/skills/doc-test-alignment/`) | 2026-05-25 | New in the cutover. **STUB** — `scripts/check.sh` exits not-yet-implemented today; the SKILL.md carries the contract for what it will do (verify committed docs still describe what code + tests actually do). **Divergence:** `type: command` added to `SKILL.md`. |
| `pypi-maintainer` | `guildmaster` (`../guildmaster/.claude/skills/pypi-maintainer/`) | 2026-05-25 | New in the cutover. Switches a package install between production PyPI, TestPyPI pre-release builds, and a local editable checkout via `scripts/switch-source.sh`. Directly relevant to antoine (publishes the `kata-cli` distribution). **Divergence:** `type: command` added to `SKILL.md`. |
| `run-tests` | `guildmaster` (`../guildmaster/.claude/skills/run-tests/`) | 2026-05-25 | Portable. Coverage source resolves from `[tool.coverage.run]` in `pyproject.toml`. **Divergence:** `type: command` added to `SKILL.md`; otherwise verbatim. |
| `sonarclaude` | `guildmaster` (`../guildmaster/.claude/skills/sonarclaude/`) | 2026-05-25 | Portable. Project key resolves from `$SONAR_PROJECT` / `--project` (antoine's key is `agentculture_antoine`). **Divergence:** `type: command` added to `SKILL.md`; otherwise verbatim. |
| `spec-to-plan` | `guildmaster` (re-broadcast; origin `agentculture/devague`, `../guildmaster/.claude/skills/spec-to-plan/`) | 2026-05-25 | New, **inbound** — origin `agentculture/devague`, guildmaster only re-broadcasts. Spec→plan operator; drives the `devague plan` CLI group. **Runtime:** `uv tool install devague`. Vendored verbatim (incl. upstream `type: command`). |
| `think` | `guildmaster` (re-broadcast; origin `agentculture/devague`, `../guildmaster/.claude/skills/think/`) | 2026-05-25 | New, **inbound** — origin `agentculture/devague`, guildmaster only re-broadcasts. Idea→spec operator; drives the `devague` CLI. Hands off to `spec-to-plan` once a spec exports. **Runtime:** `uv tool install devague`. Vendored verbatim (incl. upstream `type: command`). |
| `version-bump` | `guildmaster` (`../guildmaster/.claude/skills/version-bump/`) | 2026-05-25 | Pure Python, no per-repo customization. antoine's `CHANGELOG.md` keeps a `# Changelog` + intro-prose header, so the first `## [` entry is a valid insertion point for the upstream script. **Divergence:** `type: command` added to `SKILL.md`; otherwise verbatim. |
| `repo-map` | `code-lens-cli` (`agentculture/code-lens-cli/.claude/skills/repo-map/`) | 2026-05-17 | **Migrated out.** As of antoine 0.11.0, this skill lives in `code-lens-cli` v0.10.0+. Install via `uv tool install code-lens-cli`; verbs are `code-lens profile` and `python -m code_lens.repo {connections,graph}`. Re-vendor from the new upstream if antoine ever needs a local copy. Handover history: [code-lens-cli#2](https://github.com/agentculture/code-lens-cli/issues/2). |
| `code-lookup` | `code-lens-cli` (`agentculture/code-lens-cli/.claude/skills/code-lookup/`) | 2026-05-17 | **Migrated out.** As of antoine 0.11.0, this skill lives in `code-lens-cli` v0.10.0+. Install via `uv tool install code-lens-cli`; verbs are `code-lens classify` / `code-lens grep` / `code-lens recent`. Same handover history as above. |
| `eval` | _internal implementation_ — antoine origin | 2026-05-16 | **Runtime:** locked operator procedure for one scripts-eval set (one `(target, question)` row × 3 trials × one arm). Three arms — **A** (banned), **B** (directed), **C** (organic) — and two judge pairs — **A-vs-B** ("do the skills help when used?") and **A-vs-C** ("do the skills get adopted organically?"). Backing CLIs live in `experiments/scripts_eval/` (`trial`, `validate`, `judge`, `summarize`, `manifest`); hooks live in `experiments/scripts_eval/hooks/`. `judge prepare --pair AB\|AC` selects the pair; verdicts land under `cell["judges"][pair]` (the AC pair also mirrors to legacy `cell["judge"]`). Round-agnostic — reads `$ANTOINE_EVAL_RUN_ID` and writes the round's accumulator at `docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md`. **Divergence:** N/A — original to antoine (the harness only exists here); `type: command` added to `SKILL.md` in 0.12.0 alongside the cutover. If/when promoted upstream, this row flips to a `Re-vendor from guildmaster` pointer. |

## Vendoring policy

- **Cite, don't import.** Skills are copied, not symlinked or installed as
  a dependency.
- **Re-sync explicitly.** When upstream changes, re-vendor the canonical set
  from `../guildmaster/.claude/skills/<name>/`. The inbound devague-origin
  trio is re-broadcast by guildmaster, so re-vendor it from guildmaster too —
  but track `agentculture/devague` as the true upstream.
- **Diverge intentionally.** Record any divergence in the table above and
  in the downstream `SKILL.md` frontmatter `description`.
- **`type: command` on every `SKILL.md`.** antoine declares a culture agent
  (`culture.yaml`: `suffix: antoine`), and culture/agex's `core.skill_loader`
  silently skips a `SKILL.md` that lacks `type:` (via
  `backends/claude_code/probe.py`). Every vendored and origin `SKILL.md`
  therefore carries `type: command` — load-bearing on the culture backend,
  harmless on the claude-code backend. guildmaster ships it on 4 of the 11
  (`agent-config`, `assign-to-workforce`, `spec-to-plan`, `think`); antoine
  adds it to the rest (recorded as a divergence per row).
- **Supplier cutover (steward → guildmaster), 2026-05-25.** The AgentCulture
  skills-supplier role moved from `steward` to `guildmaster`
  ([antoine#28](https://github.com/agentculture/antoine/issues/28)). All
  canonical rows were repointed; re-sync now targets guildmaster.
- **Origin-skills may graduate to a sibling repo** when their surface
  stabilizes and warrants its own distribution. Precedent: `code-lookup`
  and `repo-map` → `code-lens-cli`, 2026-05-17 (antoine PR #25 closes
  the loop opened by code-lens-cli #2).
