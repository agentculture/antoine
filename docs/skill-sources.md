# Skill sources — vendored skill provenance

seer-cli vendors cross-sibling skills from `steward`, the AgentCulture skill
supplier. This follows the **cite, don't import** pattern: each skill is
copied into `.claude/skills/`, owned locally, and may diverge. Nothing
imports across repos at runtime.

This file is the upstream/downstream map. When upstream changes, re-sync
explicitly — these copies do not auto-update.

| Skill | Re-vendor from | Vendored | Runtime backing & notes |
|-------|----------------|----------|-------------------------|
| `cicd` | `steward` (`../steward/.claude/skills/cicd/`) | 2026-05-15 | **Runtime:** as of steward 0.12.0 the core PR-lifecycle verbs (`lint` / `open` / `read` / `reply` / `delta`) are a thin delegate to `agex pr` from `agentculture/agex-cli` — `agex` must be installed (`uv tool install agex-cli`). Steward keeps two extensions on top — `status` (SonarCloud gate + hotspots + unresolved-thread tally) and `await` (`agex pr read --wait` + `status`, non-zero exit on Sonar ERROR / unresolved threads). **Divergence:** local script patch — `scripts/portability-lint.sh` drops the GNU-only `xargs -r` flag (two sites, marked `# seer-cli divergence:`) so the lint runs on BSD/macOS `xargs`; `-r` was redundant because both inputs are already guarded non-empty. Raised by Qodo on PR #3; should be filed upstream on `agentculture/steward` so the fix re-converges on next re-vendor. Body prose also references steward-specific constructs (e.g. `steward doctor`, the `STEWARD_PR_AWAIT_WAIT` env var); these are inherited context, not seer-cli-actionable. |
| `communicate` | `steward` (`../steward/.claude/skills/communicate/`) | 2026-05-15 | **Runtime:** as of steward 0.11.0 the GitHub issue-I/O verbs (`post-issue` / `post-comment` / `fetch-issues`) are thin wrappers around `agtag` (>=0.1) — `agtag` must be installed. Signatures resolve from the local `culture.yaml` first-agent `suffix` (here: `seer`); mesh messages stay unsigned. **Divergence:** none — vendored verbatim. Body prose references steward as the supplier; the `steward announce-skill-update` broadcast verb is steward-cli-only and not available to seer-cli. |
| `run-tests` | `steward` (`../steward/.claude/skills/run-tests/`) | 2026-05-15 | None — portable verbatim. Coverage source resolves from `[tool.coverage.run]` in `pyproject.toml`. |
| `sonarclaude` | `steward` (`../steward/.claude/skills/sonarclaude/`) | 2026-05-15 | None — portable verbatim. Project key resolves from `$SONAR_PROJECT` / `--project` (seer-cli's key is `agentculture_seer-cli`). |
| `version-bump` | `steward` (`../steward/.claude/skills/version-bump/`) | 2026-05-15 | None — portable verbatim. Pure Python, no per-repo customization. seer-cli's `CHANGELOG.md` keeps a `# Changelog` + intro-prose header, so the first `## [` entry is a valid insertion point for the upstream script. |

## Vendoring policy

- **Cite, don't import.** Skills are copied, not symlinked or installed as
  a dependency.
- **Re-sync explicitly.** When upstream changes, re-vendor from
  `../steward/.claude/skills/<name>/`.
- **Diverge intentionally.** Record any divergence in the table above and
  in the downstream `SKILL.md` frontmatter `description`.
