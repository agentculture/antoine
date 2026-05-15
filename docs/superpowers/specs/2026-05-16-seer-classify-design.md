# `seer classify` verb + `code-lookup` skill — Design

**Status:** Draft, awaiting implementation plan
**Date:** 2026-05-16
**Repo:** `agentculture/seer-cli`
**Tracking issue:** [#11](https://github.com/agentculture/seer-cli/issues/11)

## Context

Issue [#11](https://github.com/agentculture/seer-cli/issues/11) framed a
problem: even after PR [#13](https://github.com/agentculture/seer-cli/pull/13)
sharpened the `repo-map` SKILL description and tightened `profile.sh`'s
output, the Haiku Explore subagent still skipped `repo-map` in smoke tests
and used `find` + Read directly. The naive read of that result is "the
SKILL description isn't persuasive enough."

The user's reframe during brainstorm is what this spec acts on: **the
adoption gap isn't a persuasion problem, it's a coverage problem.** The
model's "greedy" exploration toolkit includes lots of question shapes
seer-cli has no verb for — `find -name`, `grep -r`, `git log`, `head -40`,
inspecting `pyproject.toml` + `Dockerfile` + `.github/workflows/` to figure
out what kind of project this is. When the model asks one of those, it
correctly reaches for Bash because seer-cli currently has nothing better
to offer.

The fix is therefore not "louder marketing" but **adding verbs that
absorb the model's other greedy exploration tools**, so each new verb
collapses N tool calls into 1.

A test for whether a candidate verb is worth building: **does it reduce
N tool calls or N reasoning steps to 1?** If yes, ship it. If the verb is
a single-call rename of `rg` or `git log`, don't — the model can already
do that one in Bash.

Applying that test to the six candidates the user enumerated:

| Verb | Collapses-N-into-1? | Slice 1? |
|---|---|---|
| `grep <text>` | No — `rg --json` already gives structured output | No (see follow-up) |
| `recent` | No — `git log --pretty=format:` already does it | No (see follow-up) |
| `classify` | **Yes** — synthesizes 5–7 file reads + reasoning into one tag list | **Yes** |
| `outline <file>` | Yes (AST) — but M-effort, depends on AST infra | Later slice |
| `find-symbol <name>` | Yes (AST + cross-file) — but L-effort | Later slice |
| `deps` (deep) | Partial overlap with `profile` + `connections` | Later slice |

This spec covers **`classify` only**. Reshapes of `grep` and `recent` to
make them AST-aware (so they *do* reduce N to 1) are filed as a follow-up
issue at the end of this brainstorm.

## Goals

1. Ship one new verb (`classify`) that collapses the "what kind of
   project is this?" question shape into a single tool call with
   deterministic output.
2. Establish `.claude/skills/code-lookup/` as a sibling to `.claude/skills/repo-map/`
   for future code-lookup verbs (the `outline` / `find-symbol` slot).
3. Keep the SKILL.md frontmatter description's lessons from PR #13: enumerate
   every output field, state the token-math win up front, and include
   "when NOT to use."
4. Stay **deterministic** in v1. No heuristic tags whose false-positive
   rate could mislead a downstream model.

## Non-goals (YAGNI)

- Heuristic tags (`service`, `web-app`, `monorepo`) — false-positive
  risk in v1; revisit when there's a need.
- Language coverage beyond Python / Node / Bash — Go/Rust/etc. added
  when there's demand.
- The `outline` and `find-symbol` verbs — separate spec.
- AST-aware reshapes of `grep` and `recent` — separate follow-up issue.
- Persistent classification cache — `classify` is fast (single-digit
  ms on a typical repo); recompute every call.

## User-visible interface

```bash
seer classify [path]               # markdown to stdout; default path = cwd
seer classify [path] --json        # machine-readable
```

Existing CLI chassis (`seer.cli`) handles `--json`, error routing, and
exit codes — no new infrastructure.

## MVP tag set

All deterministic; each fires from a concrete file existence check or a
direct manifest field. Order is the order they're emitted in.

| Tag | Fires when | Evidence string template |
|---|---|---|
| `python` | `pyproject.toml` exists | `"pyproject.toml present"` |
| `node` | `package.json` exists | `"package.json present"` |
| `bash` | `scripts/*.sh` exists AND no Python/Node manifest | `"scripts/ contains N .sh files; no Python/Node manifest"` |
| `cli` | pyproject `[project.scripts]` non-empty, OR package.json `bin` non-empty | `"[project.scripts] defines <name1>, <name2>"` |
| `library` | importable package: `<name>/__init__.py` or `src/<name>/__init__.py` exists | `"<pkg>/__init__.py present"` |
| `dockerized` | `Dockerfile` exists, or `docker-compose.yml` / `compose.yml` | `"Dockerfile present"` (or compose-named) |
| `tested` | `tests/` exists AND pytest in dev deps (Python) OR `test` script in package.json (Node) | `"tests/ exists; pytest in dependency-groups.dev"` |
| `packaged-pypi` | any `.github/workflows/*.yml` mentions `pypi.org` or `pypa/gh-action-pypi-publish` | `".github/workflows/publish.yml uploads to pypi.org"` |
| `agentculture-sibling` | `culture.yaml` exists | `"culture.yaml present"` |

**Evidence string is part of the contract** — every tag must come with a
non-empty, file-grounded string. Empty/generic evidence is a bug. A test
pins this invariant.

**Polyglot repos** (both `pyproject.toml` AND `package.json` present):
both `python` and `node` tags fire. The single-valued `language` field
goes to the first match in the tag-declaration order above — i.e.,
`"python"`. Callers who need the polyglot fact should read the tag list,
not the scalar `language` field.

## Output shapes

### Markdown (default)

```
# /home/spark/git/agtag
- **Manifest:** pyproject.toml (python)
- **Tags:** python, cli, library, tested, packaged-pypi, agentculture-sibling

---

## Tags

| Tag | Evidence |
|---|---|
| `python` | pyproject.toml present |
| `cli` | [project.scripts] defines `agtag = "agtag.cli:main"` |
| `library` | `agtag/__init__.py` present |
| `tested` | `tests/` exists, pytest in dependency-groups.dev |
| `packaged-pypi` | `.github/workflows/publish.yml` uploads to pypi.org |
| `agentculture-sibling` | `culture.yaml` present |
```

Section separator pattern (`---` before each top-level `##`) mirrors the
v0.4.1 change to `profile`'s renderer — consistent reader experience
across the seer-cli verb suite.

### JSON (`--json`)

```json
{
  "ok": true,
  "data": {
    "path": "/home/spark/git/agtag",
    "manifest": "pyproject.toml",
    "language": "python",
    "tags": [
      {"name": "python", "evidence": "pyproject.toml present"},
      {"name": "cli", "evidence": "[project.scripts] defines agtag = \"agtag.cli:main\""},
      {"name": "library", "evidence": "agtag/__init__.py present"},
      {"name": "tested", "evidence": "tests/ exists, pytest in dependency-groups.dev"},
      {"name": "packaged-pypi", "evidence": ".github/workflows/publish.yml uploads to pypi.org"},
      {"name": "agentculture-sibling", "evidence": "culture.yaml present"}
    ]
  }
}
```

Existing `seer.cli._output.emit_result` handles the `{ok, data}` envelope —
no new envelope code.

## Engine + skill layout

```
seer/lookup/                                # new package — future grep/recent/outline slot
  __init__.py
  classify.py                               # one rule per tag, each returns Optional[Tag]
  render.py                                 # markdown emitter
seer/cli/_commands/classify.py              # verb wiring; register() into chassis
.claude/skills/code-lookup/
  SKILL.md                                  # frontmatter enumerates fields + token-math + when-NOT-to-use
  scripts/classify.sh                       # one-liner: uv run --directory <root> python -m seer classify "$@"
tests/test_classify.py                      # per-tag-rule tests + render tests + edge cases
docs/skill-sources.md                       # add code-lookup as seer-cli-original
```

Reused infrastructure (no new code needed):

- `seer.repo.manifest.read_pyproject` — for `[project.scripts]` + dev deps lookup.
- `seer.cli._errors.SeerError`, `EXIT_USER_ERROR`, `EXIT_ENV_ERROR` — error policy.
- `seer.cli._output.emit_result` — JSON envelope.
- Existing argparse chassis in `seer.cli.__init__` — `--json` detection, verb registration.

## Errors

| Condition | Behavior |
|---|---|
| Path argument does not exist | `SeerError(code=EXIT_USER_ERROR, reason="path not found: <p>", remediation="check the path argument")` |
| Path exists but has no recognized manifest AND no `culture.yaml` AND no `scripts/*.sh` | Return success with `tags: []`, `language: "unknown"`, `manifest: null`. Not an error — caller learns the truth. |
| `pyproject.toml` exists but is malformed TOML | Re-raised as `SeerError(code=EXIT_ENV_ERROR, reason="pyproject.toml TOML parse error", remediation="validate the file")` |
| Path is a file, not a directory | `SeerError(code=EXIT_USER_ERROR, reason="classify expects a directory, got file: <p>", remediation="pass the parent directory")` |

Same exit code policy as `repo-map`: 0 success, 1 user error, 2 environment error.

## SKILL.md frontmatter (the issue #11 adoption hook)

The PR #13 lesson was that the model can't do skill-selection cost/benefit
math unless the description enumerates fields. Draft frontmatter:

```yaml
---
name: code-lookup
description: >
  Classify what kind of project a repo is — in one tool call, with
  deterministic tags + per-tag evidence. `scripts/classify.sh [<path>]`
  returns: manifest type + language, and a tag list (`python`, `node`,
  `bash`, `cli`, `library`, `dockerized`, `tested`, `packaged-pypi`,
  `agentculture-sibling`), each with the concrete evidence that fired
  it (e.g. "Dockerfile present", "[project.scripts] defines `foo = …`",
  ".github/workflows/publish.yml uploads to pypi.org"). Markdown by
  default; `--json` for machine-readable. Prefer this over manually
  reading pyproject.toml + Dockerfile + workflows + culture.yaml
  separately — one call collapses ~5–7 Read/Bash steps into a structured
  tag list with citations. When NOT to use: if you only need one
  specific fact (e.g. "is there a Dockerfile"), Read/glob is cheaper
  than this verb.
---
```

The SKILL body proper covers usage + composition with `repo-map`.

## Test plan

One test per tag rule, plus render tests + edge cases. All in
`tests/test_classify.py`. Following the existing seer-cli convention
(see `tests/test_repo_profile.py`): per-tag fixtures built in `tmp_path`,
no mocks of the filesystem.

| Test | Fixture | Assertion |
|---|---|---|
| `test_classify_python_cli_library` | pyproject with `[project.scripts] foo = "foo.cli:main"`, `foo/__init__.py` | tags include `python`, `cli`, `library` |
| `test_classify_node_cli` | `package.json` with `"bin": {…}` | tags include `node`, `cli`; no `python` |
| `test_classify_bash_only` | `scripts/foo.sh`, `scripts/bar.sh`; no pyproject/package.json | tags include `bash`; no `python`/`node` |
| `test_classify_library_without_scripts` | pyproject `[project]` only, no `[project.scripts]`, package dir | `library` yes, `cli` no |
| `test_classify_dockerized_dockerfile` | `Dockerfile` | tag `dockerized` with evidence `"Dockerfile present"` |
| `test_classify_dockerized_compose` | `docker-compose.yml` only | tag `dockerized` with compose-named evidence |
| `test_classify_tested_pytest` | `tests/`, pyproject with `pytest` in `[dependency-groups] dev` | tag `tested` |
| `test_classify_not_tested_when_no_pytest` | `tests/` exists but pytest not in deps | NO `tested` tag |
| `test_classify_packaged_pypi` | `.github/workflows/publish.yml` containing `pypi.org` | tag `packaged-pypi` |
| `test_classify_agentculture_sibling` | `culture.yaml` present | tag `agentculture-sibling` |
| `test_classify_empty_repo` | empty dir | `tags == []`, `language == "unknown"`, `manifest is None` |
| `test_classify_path_not_found_raises_seer_error` | non-existent path | raises `SeerError(code=EXIT_USER_ERROR)` |
| `test_classify_path_is_file_raises_seer_error` | regular file path | raises `SeerError(code=EXIT_USER_ERROR)` |
| `test_classify_every_tag_has_evidence` | full fixture | for every tag in result, `evidence` is a non-empty string |
| `test_render_classify_markdown_includes_section_break` | full fixture | output contains `---` between header and `## Tags` |
| `test_render_classify_markdown_table_columns` | full fixture | every Tags row matches `\| <tag> \| <evidence> \|` shape |

## Verification (end-to-end)

1. **Unit:** `uv run pytest tests/test_classify.py -v` — all tests green.
2. **Full suite:** `uv run pytest -n auto` — no regressions in the
   existing 192-test baseline.
3. **Lint:** `uv run flake8 --config=.flake8 seer/ tests/`, `uv run black --check seer/ tests/`,
   `uv run isort --check seer/ tests/`, `markdownlint-cli2 ".claude/skills/code-lookup/SKILL.md"`.
4. **E2E on agtag:** `bash .claude/skills/code-lookup/scripts/classify.sh /home/spark/git/agtag`
   — manually verify tag set is `{python, cli, library, tested, packaged-pypi, agentculture-sibling}`,
   each with concrete evidence; no false-positives.
5. **E2E on seer-cli itself (dogfood):** `seer classify .` — expect a
   similar tag set; surface any divergence from agtag as a finding.
6. **JSON shape sanity:** `seer classify . --json | jq '.data.tags | length > 0 and (all(has("name") and has("evidence")))'`
   — must be `true`.
7. **CI:** `lint`, `test`, `test-publish`, `version-check`, SonarCloud
   Quality Gate, GitGuardian — all pass; SonarCloud OPEN issues = 0.
8. **Version bump** (CI enforces): `version-bump patch` to `0.4.2`, with
   a `CHANGELOG.md` entry.

## Out of scope (explicit)

- Heuristic tags: `service`, `web-app`, `monorepo` — deferred for v1.
- The AST-aware reshape of `grep` (return matches with enclosing
  function) and `recent` (commits paired with structural change
  summaries) — separate follow-up issue.
- Language coverage beyond Python / Node / Bash — add per real demand.
- The `outline` and `find-symbol` verbs — separate spec.
- Persisting classification results — recompute every call.
