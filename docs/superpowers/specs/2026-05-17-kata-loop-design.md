# kata-cli loop: capture → reduce → assess

**Status:** design  
**Date:** 2026-05-17  
**Predecessors:** [#17](https://github.com/agentculture/antoine/issues/17) (Kata direction), `experiments/scripts_eval/` (round-1 bootstrap)

## Goal

Generalize the `experiments/scripts_eval/` methodology into a product
external repos can run on themselves. Three observable outcomes per
candidate kata: **tool calls reduced, tokens reduced, quality change**.
The product surface is the antoine CLI; the intelligence lives one layer
up in the LLM agent that uses it.

## Non-goals

- antoine never calls an LLM. No reasoning happens inside the CLI.
- antoine never sits in the runtime path of a normal agent turn.
- antoine does not interpret kata bodies. Katas are skills in the host
  agent's native skill format.
- antoine is not a general autonomous agent (per issue #17 non-goals).
- No "kata format" beyond a registry pointer. We do not invent another
  YAML recipe DSL.

## Identity & boundaries

antoine is a **deterministic instrumentation + measurement substrate.**
Four properties hold:

1. **Tool, not agent.** No LLM calls in the CLI. Every verb returns
   structured data, writes a file, or prints documentation, and exits.
2. **Out of the runtime path.** Capture is done by the agent's own
   backend (hooks / transcript ingest / self-emit). antoine ships zero
   adapter code.
3. **Optional dependency at runtime.** Uninstall antoine, port the repo
   to another machine: `.antoine/katas.toml` is still readable plain
   TOML, `.antoine/log/*.jsonl` is still plain JSONL, every authored
   kata-skill still works. antoine returns later for `suggest`/`assess`
   cycles.
4. **Errors are remediable.** Every non-zero exit prints a three-line
   block (Error / Fix / Then) so the operator always knows what
   happened, what to do, and what success looks like.
5. **antoine never crashes.** No Python traceback ever reaches stderr.
   The caller is an agent — its planner expects structured output, not
   a crash dump. Every unexpected exception is caught, written to an
   internal debug log, and reported to the caller in the same
   Error/Fix/Then format as a known error.

## Architecture

```
                  ┌─────────────────────────────────────┐
   target repo →  │  .claude/skills/  (or backend eqv)  │
                  │   └── <kata-N>/   (agent-authored)  │
                  ├─────────────────────────────────────┤
                  │  .antoine/                          │
                  │   ├── log/                          │ ← agent writes here
                  │   │   ├── *.jsonl  (shape)          │   (per the schema
                  │   │   └── args/*.jsonl  (raw args)  │    in this doc)
                  │   └── katas.toml  (committed)       │ ← `kata skill *` writes
                  └─────────────────────────────────────┘
                            ↑
            agent's backend (hooks / transcripts / self-emit)
            — antoine documents the contract, ships no code

   antoine CLI verbs:
     concept (read-only): learn, overview, doctor, explain
     skill lifecycle:     kata skill {list, suggest, create, assess, remove}
     log power-user:      kata log {tail, gc, grep}
```

`antoine` and `kata` are the same console-script (two PyPI distribution
names: `antoine-cli`, `kata-cli` — aliases for one wheel).
`code-lens-cli` was previously dual-published as a sibling; that stream
is paused and will be reconnected when the future tool/skills split
happens.

## Data model

### Log entry (JSONL, per tool call)

```json
{
  "ts": "2026-05-17T14:22:01Z",
  "session": "<adapter-assigned id>",
  "agent": "claude-code|codex|…",
  "tool": "Bash|Read|Edit|…",
  "args_digest": "sha256:…",
  "bash_argv0": "git",
  "tokens_in": 1234,
  "tokens_out": 567,
  "duration_ms": 412
}
```

Written one line per call to `.antoine/log/<date>.jsonl`. Raw args live
in a sibling `.antoine/log/args/<session>.jsonl`, keyed by row index,
separate from the shape index so a TTL pass can remove the raw side
without dropping aggregate stats.

**No `tag` field.** Baseline/treatment selection is done by time window
(see `assess`).

### Ledger (`.antoine/katas.toml`, committed)

```toml
[katas.recent]
path = ".claude/skills/code-lookup/scripts/recent.sh"
replaces = ["Bash:git log:*", "Bash:git show:*"]
created_at = "2026-05-12T09:14:00Z"
created_by_agent = "claude-code"

[katas.recent.assessments.2026-05-12T11_30_00Z]
window_before = "2026-05-10T00:00:00Z"
window_after  = "2026-05-12T09:14:00Z"
sessions_baseline = 8
sessions_treatment = 8
calls_per_session  = { baseline = 14.2, treatment = 4.8 }
tokens_per_session = { baseline = 9421, treatment = 3110 }
wall_time_per_session_ms = { baseline = 18420, treatment = 6810 }
top_removed_patterns = [
  { pattern = "Bash:git log --format=…", removed = 47 },
  { pattern = "Bash:git show <sha>",     removed = 39 },
]
quality_score = 0.91                # written by agent via --record-quality
judge_notes_path = ".antoine/judge/recent-2026-05-12.md"
```

**The ledger is the product.** Committed, reviewable in PR diffs, a
portable receipt of "value kata-cli added to this repo." Plain TOML so
it survives antoine uninstall.

### Privacy & retention

- The `.gitignore` pattern is "everything under `.antoine/` except
  `katas.toml`" — so the ledger is committed, every other antoine
  byproduct (log, debug log, internal state) is local-only.
- `.antoine/log/**` is gitignored and ephemeral.
- Raw args (`.antoine/log/args/`) are deleted after 7 days by
  `kata log gc` (runs lazily on every `suggest`/`assess`).
- Shape-level log lines can be kept longer via config; default also 7
  days.
- If `gc` cannot delete (permissions), it exits non-zero. The privacy
  invariant is non-negotiable.

## Verb surface

### Concept verbs (read-only / status)

| Verb | Purpose |
|---|---|
| `kata learn` | Onboarding cockpit. Prints the instruction sheet: log schema + three adapter patterns + eval-skill recipe, each pointing at the antoine GitHub repo as the canonical worked example. Writes nothing outside `.antoine/`. |
| `kata overview` (no args) | Full repo kata story: ledger summary, capture-activity stats (last 7d), headline deltas across all registered katas. |
| `kata overview <name>` | Single-entry view: prints the kata's `katas.toml` block, the latest assessment, the path on disk. |
| `kata doctor [--probe]` | Diagnostics. No `--probe`: is the log fresh, are registered katas resolvable on disk, is gc up to date. With `--probe`: detect the host agent backend and recommend which of the three adapter patterns to install. Read-only; mutates no user config. |
| `kata explain <verb>` | Help-style doc for a single antoine verb. `kata explain kata` (or `antoine explain antoine`) is the self-introspection case — what this CLI is. Replaces the old `whoami` stub. |

### Skill lifecycle

| Verb | Purpose |
|---|---|
| `kata skill list` | List registered katas with their `replaces` patterns + latest assessment summary. |
| `kata skill suggest` | Read the log, cluster by `(tool, bash_argv0, args_digest-prefix)`, rank candidates not yet covered by any registered kata's `replaces` field. Output: JSON list of `{cluster_id, count, total_tokens, avg_duration, example_sessions, suggested_parameters}`. **No LLM.** Agent reads, picks one to author. |
| `kata skill create <name> --path <skill-dir> --replaces <patterns…>` | Register a newly-authored skill in `.antoine/katas.toml`. Agent must have written the skill on disk first; antoine exits non-zero otherwise. Refuses if `--replaces` collides with an existing entry (agent decides merge vs supersede). |
| `kata skill assess <name>` | Mechanical A/B over the log, pivoting by default on the kata's `created_at`. Override with `--before <ts> --after <ts>`. Writes a new `[katas.<name>.assessments.<ts>]` block to the ledger. `--record-quality <score> --judge-notes <path>` is a separate invocation that writes the quality fields back; antoine never computes the score itself. |
| `kata skill remove <name>` | Deregister from `katas.toml`. Does not delete the skill dir; that's the agent's. |

### Log/store ops (power-user)

| Verb | Purpose |
|---|---|
| `kata log tail` | Live tail of the JSONL log for debugging. |
| `kata log gc` | Prune `.antoine/log/**` past TTL. Also runs lazily inside `suggest`/`assess`. |
| `kata log grep <pattern>` | Search the shape index. |

## Adapters: the agent is the adapter

antoine ships **no adapter code**. `kata learn` prints an instruction
sheet describing the log schema + three documented patterns. The agent
picks one and implements it in its own backend.

1. **Native hooks** (Claude Code etc.) — register project-scoped
   `PreToolUse` / `PostToolUse` hooks that append JSONL.  
   *Reference:* this repo's `.claude/settings.json` +
   `experiments/scripts_eval/hooks/`.
2. **Transcript ingest** (any backend that writes session transcripts)
   — write a small per-backend parser that runs at `SessionEnd` or via
   cron and appends normalized entries.  
   *Reference:* this repo's `experiments/scripts_eval/` capture path.
3. **Self-emit** (agent has direct runtime control) — write the JSONL
   from inside the agent loop.  
   *Reference:* same `experiments/scripts_eval/` patterns, adapted.

Backends without any of these capabilities today get
`kata doctor --probe` output saying "no adapter pattern yet for this
backend — contribute one." There is no fallback wrapper; the bet is that
hooks adoption is broadening fast enough to make a fallback unnecessary.

## The eval skill (same posture as adapters)

`kata learn` also documents what an `eval` skill should do (arms A/B/C,
judge subagent dispatch, deltas-in / quality-out), and points at this
repo's vendored `.claude/skills/eval/` + `experiments/scripts_eval/` as
the worked example. antoine does **not** write the skill into the
target's skill directory. The agent reads the recipe, copies the
pattern, customizes for its corpus.

Quality scoring flows back to antoine only as a final
`kata skill assess <name> --record-quality <score>` invocation — a pure
ledger edit, no LLM call from antoine.

## Error handling

Every non-zero exit prints:

```
Error: <what happened in plain English>
Fix:   <one concrete remediation step, or "no automatic fix" if manual>
Then:  <what should be true after the fix — the success signal>
```

Selected contracts:

- **Exit 2** — no log present (`suggest`/`assess` with empty
  `.antoine/log/`).
- **Exit 3** — `--before` / `--after` window is empty.
- **Exit 4** — `kata skill create` for a `--path` that doesn't exist.
- **Exit 5** — `--replaces` collides with an existing registered kata.
- **Exit 6** — `katas.toml` is corrupted; antoine refuses to rewrite.
  Manual fix only (the file is committed; silent recovery would erase
  audit trail).
- **Exit 7** — `kata log gc` cannot delete files past TTL. Privacy
  invariant takes precedence over all other behavior.
- **Exit 99** — unexpected internal error (antoine bug). Distinct from
  user-actionable codes so the agent can route on it.

`kata doctor` reports warnings using the same three-line format.

### Crash safety contract

antoine never crashes. The existing CLI chassis
(`antoine/cli/__init__.py`) already catches all exceptions from
handlers and wraps them; this spec elevates that behavior to a named
design invariant and tightens the unexpected-error path:

- **No Python traceback ever reaches stderr.** Argparse errors,
  handler `AntoineError`s, and bare exceptions all route through the
  Error/Fix/Then formatter.
- **Unexpected exceptions** (anything not raised as `AntoineError`):
  exit 99 with a message of the form `unexpected: <ExcClass>: <msg>`.
  The full traceback, antoine version, argv, and a recent log-tail
  snapshot are written to `.antoine/last-error.log` (overwritten each
  run; size-capped at 1 MiB).
- **The Fix line in that case** is: `Include .antoine/last-error.log
  when filing a bug at <repo URL>.` The agent can read that file and
  attach it.
- **The Then line in that case** is: `kata doctor` reports no recent
  internal errors.
- **OS-level signals** (SIGTERM, SIGINT) exit cleanly with a brief
  Error/Fix/Then noting that the run was interrupted.

This contract holds for every verb. There is no `--debug` flag that
re-enables tracebacks-on-stderr; the debug log is always available and
the agent's planner is never surprised by unstructured output.

## Testing

- **Unit (`tests/test_<verb>.py`)** — pure-function tests for the log
  parser, the clustering in `suggest`, the delta computation in
  `assess`, the TOML round-trip for the ledger.
- **Integration (`tests/integration/`)** — full cycle against a
  fixture: write a synthetic log, run `suggest`, register a fake kata,
  write a synthetic post-kata log, `assess`, verify the new ledger
  entry. No LLM, no network.
- **Doctor tests** — probe a fake-backend env (env vars + parent
  process name) and assert the recommended adapter pattern is correct.
- **No tests against real Claude Code / Codex.** antoine's contract is
  the JSONL schema and the TOML ledger; honoring it on each backend is
  the agent's job.

The existing `experiments/scripts_eval/` tests stay as-is — that's the
bootstrap experiment that the `eval` skill template references.

## Scope cells

Each cell is one PR with a version bump.

1. **Cell 1 — Schema + log primitives.** JSONL schema doc. Two-tier log
   store. `kata log {tail, gc, grep}`. TTL gc with privacy invariant.
2. **Cell 2 — Read verbs.** `kata explain` (polymorphic over the verb
   list, with `explain kata` as self-doc), `kata overview` (no-args +
   single-kata variants), `kata doctor` (no `--probe` mode).
3. **Cell 3 — Onboarding.** `kata learn` instruction sheet. `kata
   doctor --probe` backend detection and adapter recommendation.
4. **Cell 4 — Skill CRUD.** `kata skill {list, create, remove}` over
   `katas.toml`.
5. **Cell 5 — Suggest.** `kata skill suggest` clustering and
   parameterization over the log.
6. **Cell 6 — Assess.** `kata skill assess` with time-window pivoting
   and `--record-quality` ledger writes.
7. **Cell 7 — Stub removal.** Delete the old placeholder
   `learn`/`explain`/`whoami` stubs (replaced by real implementations
   in cells 2–3).
8. **Cell 8 — Dogfood on antoine itself.** Run the full loop against
   this repo: install a self-emit adapter into the agent doing the
   work, capture during real antoine development, `kata skill suggest`
   to surface patterns, author or re-register the existing
   `code-lookup` / `repo-map` skills as proper katas, `kata skill
   assess` to measure deltas, commit the resulting `.antoine/katas.toml`.
   **This is the acceptance test for the design.** The PR isn't done
   until the repo's own ledger has real entries with non-zero measured
   deltas.

## Open questions

- **Cluster shape granularity in `suggest`.** How aggressive should the
  `args_digest-prefix` be? Too coarse and unrelated calls get merged;
  too fine and every `git log` with a different `--since` looks like a
  separate cluster. Probably tunable, defaulting to "first N tokens of
  the canonicalized argv." Decide empirically in Cell 5.
- **Multi-agent log merge.** If two agents (e.g. a developer's CC
  session and a CI agent) both write to the same `.antoine/log/`, does
  `assess` separate them by the `agent` field? Probably yes, with a
  `--agent <name>` filter. Decide in Cell 6.
- **`assess` with no baseline window.** If the kata existed before any
  capture happened, there's no baseline data. Should `assess` fall back
  to "treatment-only" stats with a clear note in the ledger, or refuse?
  Refuse for v1; revisit if Cell 8 dogfooding hits this.

## Relation to issue #17

This design is the "capture/reduce/assess loop" framing of #17's "Kata"
direction. Differences:

- We don't ship "basic calls" as a separate antoine layer — those are
  the *result* of past kata work and live in the future `code-lens-cli`
  catalog, not in kata-cli itself.
- Repo-specific katas are the only kind. There are no "generic katas
  built into the CLI" because the agent's authored skills are repo-local
  by construction.
- Ad-hoc kata recording is `kata skill create` — the agent decides
  what's reusable and registers it; antoine doesn't try to auto-record.
- The product is the **measurement substrate + ledger**, not the kata
  runtime.
