# `repo-map` skill + `seer.repo` module — Design

**Status:** Draft, awaiting implementation plan
**Date:** 2026-05-15
**Repo:** `agentculture/seer-cli`

## Context

When asked to explain how a workspace of related repos fits together, an agent
runs the same mechanical workflow per repo: read `pyproject.toml`, `README.md`,
`CLAUDE.md`, `CHANGELOG.md`; list package layout; grep for cross-repo names.
Roughly 60–70% of agent tokens go to deterministic gathering. The remaining 30%
is synthesis — naming the layers, drawing the arrows.

The deterministic part is scriptable. This spec captures it as a Claude Code
skill backed by a small Python module. The skill is deliberately **generic**:
the unit of analysis is "a repo," not "an AgentCulture sibling." It works on
any workspace of Python repos, with optional markers and configuration to feel
native in AgentCulture (or any other) setups.

This is also the paradigmatic use case for `seer-cli`'s eventual `whoami` /
`explain` / `learn` verbs (per its CLAUDE.md). Keeping the engine in
`seer/repo/` — not in bash scripts alone — lets it later become real `seer`
verbs without rewriting.

## Goals

1. Reduce the per-session cost of "tell me about this repo / these repos" by
   surfacing structured facts an agent can synthesize from, rather than
   re-grepping.
2. Stay **generic**: no requirement that target repos be related in any
   particular ecosystem. Detection is by manifest or configured marker, not by
   convention.
3. Make depth and cascade **first-class flags**, with defaults that are cheap.
   The agent escalates explicitly; no surprise expense.
4. Be **forward-compatible** with seer-cli's real verbs: the engine maps onto
   `whoami`, `explain`, and `learn` so migration is mechanical.
5. **Markdown-first** output — the agent reads it directly. JSON is the opt-in
   machine-readable format for composition.
6. **Structured errors** with clear reason and remediation — never a bare exit
   code, never a silent failure.

## Non-goals (YAGNI)

- Persisted index or cache. That is the eventual seer-cli engine's job.
- Cross-machine federation.
- Watch mode / diffs.
- Pretty terminal rendering. Plain markdown + JSON only.
- Non-Python manifests (Node, Rust, Go) — deferred. Repos without a recognized
  manifest are reported as `language: unknown` but still appear in walks.
- LLM synthesis. The script is deterministic; the mind-model is what the agent
  constructs from the script's output.

## Architecture

Two-layer split, mirroring how steward's `cicd` skill wraps `agex pr`:

```
seer-cli/
├── seer/repo/                        ← engine: importable, testable, will later
│   ├── __init__.py                     migrate into seer/cli/_commands/
│   ├── __main__.py                   ← argparse: profile | connections | graph
│   ├── profile.py                    ← single-repo profiler (shallow + deep)
│   ├── connections.py                ← BFS from a seed repo
│   ├── graph.py                      ← multi-root workspace view
│   ├── detect.py                     ← repo detection + name resolution
│   ├── manifest.py                   ← pyproject.toml reader
│   ├── render.py                     ← markdown + JSON emitters
│   ├── errors.py                     ← message/reason/remediation envelopes
│   └── config.py                     ← config.json loader
│
└── .claude/skills/repo-map/
    ├── SKILL.md                      ← agent-facing prose + compose recipe
    ├── config.json                   ← optional per-workspace defaults
    └── scripts/
        ├── profile.sh                ← exec python -m seer.repo profile "$@"
        ├── connections.sh            ← exec python -m seer.repo connections "$@"
        └── graph.sh                  ← exec python -m seer.repo graph "$@"
```

Shell scripts are one-liners; all logic lives in `seer.repo`.

## The three verbs

### `profile <repo-path> [--depth shallow|deep] [--json]`

Emits one repo's facts. Default output: markdown. `--json` switches.

**`shallow` (default):** mechanical facts — fast.

- `name`, `version` (from `pyproject.toml`'s `[project]`)
- `manifest` filename, `language` (`"python"` if `pyproject.toml`, else
  `"unknown"`)
- `entry_points` (console scripts)
- `deps_runtime`, `deps_dev`
- `package_layout` — one-level directory listing under `src/<pkg>/` or top
  level, filtered to actual Python packages
- `vendored_skills` — `.claude/skills/*/` directories, augmented with
  provenance from `docs/skill-sources.md` when present
- `citations` — parsed from `CITATION.md` at repo root when present
- `changelog_recent` — first 3 entries of `CHANGELOG.md` (Keep-a-Changelog
  format)
- `claude_md_status` — content of `## Project Status` section in `CLAUDE.md`
  when present
- `extra.culture_nick` — populated only when `culture.yaml` exists at repo root
  (an opportunistic field; AgentCulture-friendly without being required)

**`deep`:** shallow + raw materials for a mind-model.

- `readme_intro` — first paragraph (or first non-heading block) of `README.md`
- `claude_md_sections` — text content of `## Architecture`, `## Project Status`,
  and any section whose heading contains `"invariant"`, `"rule"`, or
  `"contract"` (case-insensitive)
- `commits_recent` — last 10 commit message subjects from `git log`

All non-required sources degrade silently: missing `CITATION.md` ⇒ empty
`citations` field, not an error.

### `connections <repo-path> [--depth N|all] [--profile] [--depth-profile shallow|deep] [--json] [--strict]`

Walks outward from a seed repo via three edge types:

- `import` — extracted from manifest `deps_runtime` where the target name
  matches a discovered repo's `name`.
- `cite` — extracted from per-repo `citations` (`CITATION.md`).
- `vendor` — extracted from `vendored_skills`.

**Edge resolution:** for each edge target name (e.g. `"cultureagent"`), look
across configured `roots` for a repo whose `name` (or directory basename)
matches. Unresolvable targets become `external` nodes — named in output, but
with no path and no profile.

**Depth:**

- `--depth 1` (default): immediate neighbors only, names + paths, no profiles
  unless `--profile` is passed.
- `--depth N` for N ≥ 1: BFS to N hops.
- `--depth all`: walk the entire connected component.

**Profile flags:**

- `--profile`: emit each internal node's profile (default shallow).
- `--depth-profile deep`: use deep profile depth for each node. Implies
  `--profile`.

**Strictness:**

- Default: per-node errors are inlined in output, walk continues, exit 0 if
  the seed itself is fine.
- `--strict`: any per-node error fails the whole walk with exit 65.

### `graph [<root>...] [--json] [--strict]`

Multi-root workspace view. Union of every repo found under the given roots,
plus every edge between them.

- Default root: `$HOME/git`.
- Multiple roots supported: `graph /home/spark/git /home/spark/work`.
- Each node carries its shallow profile by default.
- Output includes a `mermaid` field/section — a ready-to-paste diagram source.

Use this when the question is "show me what's in this workspace" rather than
"walk outward from this repo."

## Repo detection

A directory counts as a repo if any of the following are true, evaluated in
order (any match qualifies):

1. It has `pyproject.toml`.
2. It has `.claude/skills/`.
3. It has any file listed in `additional_markers` config (e.g. `culture.yaml`,
   `pubspec.yaml`, anything the user wants).

The `name` field uses:

1. `pyproject.toml`'s `[project].name` when available
2. else the configured marker's parseable name field (only `culture.yaml`
   supported in MVP — `agents[0].suffix` or whatever the field turns out to be;
   verify during implementation)
3. else the directory basename

## Output format

**Markdown by default.** `--json` switches to a JSON envelope.

Profile in markdown looks like:

```markdown
# culture
- **Version:** 12.1.7
- **Manifest:** pyproject.toml (python)

## Entry points
- `culture` → `culture.cli:main`

## Runtime dependencies (3)
- cultureagent ~=0.4.0
- agentirc-cli >=9.6,<10
- irc-lens >=0.5.3,<1.0

## Vendored skills (1)
| Skill | Source | Version |
|---|---|---|
| communicate | steward | 0.11.1 |

## Recent changelog
- **12.1.7** (2026-05-14) — Bumped irc-lens floor for SSO support.

## Project status
Alpha; 90% coverage ratchet in progress.
```

Profile in JSON has the same fields under a top-level success envelope:

```json
{"ok": true, "data": { ...profile fields... }}
```

Strict stdout/stderr split (cites `seer/cli/_output.py`): success on stdout,
errors on stderr, nothing crosses.

## Error model

Every error path produces three fields. Bare exit codes are never the only
signal.

| Field | Purpose |
|---|---|
| `message` | What went wrong, one plain-English sentence. |
| `reason` | Root cause — what the script tried, why it failed. |
| `remediation` | Concrete next step the user (or agent) can take. |

Markdown error to stderr:

```markdown
**Error:** Cannot find pyproject.toml in /home/spark/git/foobar

**Reason:** No recognized manifest at the given path. Looked for
`pyproject.toml`, `.claude/skills/`, and any configured `additional_markers`
(none configured).

**Remediation:** Confirm the path points to a repo root, not a subdirectory.
To treat this directory as a repo regardless, add a marker file to
`.claude/skills/repo-map/config.json` → `additional_markers`.

Exit code: 1 (user error)
```

JSON error to stderr:

```json
{
  "ok": false,
  "error": {
    "code": 1,
    "kind": "user_error",
    "message": "Cannot find pyproject.toml in /home/spark/git/foobar",
    "reason": "No recognized manifest at the given path. Looked for pyproject.toml, .claude/skills/, and any configured additional_markers.",
    "remediation": "Confirm the path points to a repo root, not a subdirectory. To treat this directory as a repo regardless, add a marker via .claude/skills/repo-map/config.json → additional_markers."
  }
}
```

Exit codes (already defined in `seer/cli/_errors.py`; `EXIT_INTERNAL = 3`
added by this work):

| Code | Constant | Kind | When |
|---|---|---|---|
| 0 | `EXIT_SUCCESS` | success | normal exit |
| 1 | `EXIT_USER_ERROR` | user_error | bad path, bad flag, missing required input |
| 2 | `EXIT_ENV_ERROR` | env_error | unreadable file, malformed manifest, git missing for `--depth deep` |
| 3 | `EXIT_INTERNAL` | bug | unexpected internal exception (caught and wrapped) |

`SeerError` is extended (not replaced) with two optional fields:

- `reason: str = ""` — root-cause sentence between message and remediation
- `kind: str = ""` — one of `"user_error" | "env_error" | "bug"`, derived
  from `code` when not set explicitly

### Partial-failure policy

- `profile <one-repo>` — one repo, one result. Any error fails the call, exit
  non-zero, stdout empty.
- `connections <seed>` / `graph <root>` — walking many repos. Per-node errors
  are inlined in the output; the walk continues. Exit 0 if the seed itself is
  fine. `--strict` flips this and fails on any per-node error.

Inlined error section in a walk:

```markdown
## Errors during walk (1)

**irc-lens (/home/spark/git/irc-lens)**
- Reason: pyproject.toml has TOML syntax error at line 12.
- Remediation: validate with `python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`.
```

## Configuration

Optional per-workspace defaults at `.claude/skills/repo-map/config.json`:

```json
{
  "roots": ["/home/spark/git", "/home/spark/work"],
  "additional_markers": ["culture.yaml"],
  "skip_dirs": ["backups", ".venv", "node_modules"],
  "default_connections_depth": 1
}
```

All fields optional. Missing `roots` falls back to `[$HOME/git]`. Missing
`additional_markers` falls back to manifest-based detection. Flags always
override config.

## SKILL.md compose recipe

The skill's `SKILL.md` tells the agent how the three verbs compose:

> Use this skill when the user asks to understand a repo or a workspace of
> related repos — what's there, what depends on what, and how they fit
> together.
>
> Pick the mode that fits the question:
>
> 1. **One repo, mechanical facts** — `scripts/profile.sh <path>`
> 2. **One repo, mind-model raw materials** — `scripts/profile.sh <path> --depth deep`
> 3. **Walk N hops from a repo** — `scripts/connections.sh <path> --depth N --profile`
> 4. **Whole workspace at once** — `scripts/graph.sh [<root>]`
>
> Output is markdown by default — read it directly. Pass `--json` if you need
> to pipe it. Synthesize the narrative from the script output; do **not**
> re-grep what `profile` already reports.

## Migration path to real seer verbs

The three engine verbs map onto seer-cli's existing stubs:

- `seer whoami` → `profile $PWD` (current repo's profile)
- `seer explain <path-or-name>` → `profile <path> --depth deep` for one repo,
  or `connections <path>` when the question is about relationships
- `seer learn` → `graph $(dirname $PWD)` (the workspace this repo lives in)

When that migration happens, `seer/repo/` moves into `seer/cli/_commands/` and
the skill's `scripts/*.sh` switch from `python -m seer.repo` to `seer`. The
agent-facing surface — flag shapes, output formats, error shapes — stays
identical.

## Tests

Mirroring the style of existing `tests/test_cli_chassis.py`:

| File | Coverage |
|---|---|
| `tests/test_repo_profile.py` | tmpdir fixture with synthetic `pyproject.toml` + `CHANGELOG.md`; assert shallow + deep shapes, missing-file degradation |
| `tests/test_repo_connections.py` | three synthetic repos with crossed `deps_runtime` and `CITATION.md`; assert depth 1, depth 2, depth all, external nodes, per-node error inlining, `--strict` |
| `tests/test_repo_graph.py` | multi-root walk over synthetic repos; assert union behavior, mermaid output |
| `tests/test_repo_detect.py` | detection with `pyproject.toml` only, `.claude/skills/` only, configured marker only, none-of-the-above |
| `tests/test_repo_errors.py` | each error path: missing dir, missing manifest, malformed TOML, bad `--depth`; assert message/reason/remediation are all populated; markdown + JSON forms; exit codes |
| `tests/test_repo_cli.py` | `python -m seer.repo <verb> ...` end-to-end, stdout/stderr split, default-markdown vs `--json` |

No tests for shell scripts (one-liners).

## Dependencies added

- `pyyaml>=6.0` — for `culture.yaml` and any other YAML markers.
- `tomllib` (Python 3.11+ stdlib). If `seer-cli/pyproject.toml` requires
  Python <3.11, add `tomli` as fallback. Verify `requires-python` during
  implementation.

No new dev-dep additions; existing `pytest` setup suffices.

## Open items (verify during implementation)

- `requires-python` in `seer-cli/pyproject.toml` — affects whether `tomli`
  fallback is needed.
- Exact `culture.yaml` schema field for nick (likely `agents[0].suffix`).
  Verify against an existing file.
- Whether `Keep-a-Changelog` parsing should aggregate sub-bullets (probably
  no — just heading + first-line summary is enough for `changelog_recent`).
- Whether `git` must be installed for shallow profile (no — shallow doesn't
  read git). For `--depth deep`, `git` is required; emit a clear env_error
  if missing.

None of these block implementation; they're cosmetic refinements to confirm
in code rather than in spec.
