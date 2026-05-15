# `scripts-eval` harness — Design

**Status:** Draft, awaiting implementation plan
**Date:** 2026-05-15
**Repo:** `agentculture/seer-cli`

## Context

`seer-cli` ships a `repo-map` skill backed by the `seer.repo` engine (see
[2026-05-15-repo-map-design.md](./2026-05-15-repo-map-design.md)). Three
verbs — `profile`, `connections`, `graph` — give an agent deterministic
facts about a repo or a workspace of repos so the agent can spend its
tokens on synthesis rather than re-grepping.

We *believe* this helps. We have not measured it. Before promoting the
scripts into first-class `seer` CLI verbs (the planned `learn` /
`explain` / `overview` / `doctor` redesign of the placeholder verbs),
we need an experiment that answers three questions:

1. **Gate:** does an agent armed with `repo-map` produce *better* answers
   than a bare agent with only Read / Grep / Glob, on the same questions?
2. **Calibration:** *where* is the win — which question shapes benefit,
   and how much (in tokens, time, and judged quality)?
3. **Diagnostics:** when do equipped agents *misuse* the scripts (wrong
   verb, re-grep after profile, over-deep when shallow would do)?

This spec defines the harness that produces evidence for all three. It is
designed to be repeatable: by us, in future rounds with new repos; and
by external contributors who clone seer-cli and point it at their own
codebases.

## Goals

1. Produce per-cell **mechanical metrics** (duration, tokens by class,
   model, tools used) from real Claude Code subagent runs, captured via
   hooks rather than self-report.
2. Produce per-cell **code-validation scores** — deterministic recall of
   hand-authored expected-evidence facts in each answer.
3. Produce **pairwise blind LLM-as-judge** verdicts comparing arm A
   (bare) and arm C (full skill) answers on a fixed rubric.
4. Roll all three layers up into a single `REPORT.md` per run, plus
   per-cell JSON for reanalysis.
5. Be **repeatable**: a fresh contributor with seer-cli checked out and
   their own choice of target repos can run the eval end-to-end by
   following `RUNBOOK.md`.
6. Be **opt-in**: the hooks no-op outside of an active eval session
   (gated by an env-var sentinel) so day-to-day seer-cli work is
   unaffected.
7. Be **honest about violations**: if an arm-A subagent calls a script
   despite the prompt, the cell is auto-flagged and re-run, not silently
   dropped.

## Non-goals (YAGNI)

- Statistical inference beyond medians and counts. We are looking for
  effect sizes, not p-values; sample sizes are too small for the latter
  to be meaningful.
- Multiple competing toolsets beyond bare-vs-`repo-map`. A future round
  can compare `repo-map` against alternatives; this round establishes
  the methodology.
- Continuous-integration runs. The harness is a benchmark, not a smoke
  test. CI does not need to run it.
- Verb design (`learn` / `explain` / `overview` / `doctor`). This spec
  intentionally stops at "we have evidence to ground the verb design";
  the verbs are a separate brainstorm.
- Cross-language target repos. Round 1 stays Python (matches what
  `seer.repo` reads today). Adding Node/Go/Rust targets is a follow-up.
- Token-cost dollar conversion. We report token counts; converting to
  USD per arm is a slide-deck problem, not a harness problem.

## Architecture

```
seer-cli/
└── experiments/
    └── scripts_eval/                      ← dir is underscored so the
                                              scripts can import shared
                                              helpers; the concept name
                                              "scripts-eval" stays
                                              hyphenated in prose, branches,
                                              and run-ids.
        ├── README.md             ← what / why / how to read results
        ├── RUNBOOK.md            ← procedure the operator-Claude follows
        ├── corpus.yaml           ← repos × questions (incl. expected_evidence)
        ├── judge_rubric.md       ← scoring rubric for the LLM judge
        ├── capture.py            ← post-process raw hook logs → per-cell JSON
        ├── validate.py           ← code-validation: expected_evidence vs answer
        ├── judge.py              ← LLM-as-judge, pairwise blind A vs C
        ├── report.py             ← results/<run>/ → REPORT.md
        ├── hooks/
        │   ├── pre_tool.py       ← PreToolUse: stamp run-id + start time
        │   ├── post_tool.py      ← PostToolUse: append tool call to run log
        │   └── subagent_stop.py  ← SubagentStop: usage/duration from transcript
        └── results/
            └── 2026-05-15-run-01/
                ├── manifest.json ← corpus version, models, date, env, operator
                ├── raw/          ← hook output, one JSONL per subagent
                ├── arm-A/        ← processed per-cell JSONs (bare)
                ├── arm-C/        ← processed per-cell JSONs (full skill)
                ├── judge/        ← pairwise scores
                └── REPORT.md     ← final story, generated
```

The harness lives in a top-level `experiments/` dir (sibling to
`seer/`, `tests/`, `docs/`). It is **not** Python-packaged; the
`scripts_eval` directory is invoked as scripts (`python
experiments/scripts_eval/judge.py`). This keeps it out of `seer-cli`'s
import surface and makes clear it is not part of the shipped CLI.

## Per-cell run flow

A single **cell** is one (repo, question, arm, trial) combination.
Default trial count is 3, so a 5-repo × 5-per-repo-question × 2-arm
corpus is 5 × 5 × 2 × 3 = 150 cells, plus a workspace-graph question
that runs once per arm × trial = 6 cells. Total ≈ 156 cells per run.

**Per-cell sequence:**

1. Operator-Claude (in the right arm's session — see *Operator session
   topology* below) reads `RUNBOOK.md` and looks up the next pending
   row in `corpus.yaml`.
2. Operator dispatches an `Explore` subagent with:
   - The arm-specific system prompt (from `RUNBOOK.md`).
   - The question template, with `{repo_path}` substituted.
   - A tail instruction the agent obeys verbatim:
     > After answering, append two sections and stop.
     > `### tools_used` — list every tool you called, with counts.
     > `### evidence` — list every file/path you read.
3. Hooks fire automatically:
   - `PreToolUse` (filter `Agent`) writes a per-subagent JSONL with
     `run_id`, `arm`, `repo`, `question_id`, `trial`, `start_time`,
     `prompt`.
   - `PostToolUse` (any tool) appends `{tool, args_summary, ts}` to
     that subagent's JSONL.
   - `SubagentStop` reads the transcript path from the hook payload,
     extracts the last assistant `usage` block, computes `duration`,
     and finalises the JSONL with `end_time`, `model`, `usage`,
     `final_text`.
4. `capture.py` reads the JSONL written by `SubagentStop` (which
   already includes the subagent's `final_text`) and writes a
   normalised per-cell JSON to
   `results/<run>/arm-<X>/<repo>-<qid>-<trial>.json`. The operator
   does not copy answers manually; everything routes through hook
   output.
5. Once **all** cells are captured, operator runs:
   - `validate.py` — fills the `validation` block on every cell.
   - `judge.py` — pairwise blind A-vs-C, fills the `judge` block.
   - `report.py` — emits `REPORT.md`.

**Sequential, not parallel.** Within an arm's operator session, cells
are dispatched one at a time, not fanned out in parallel. Round 1
favours observability (the operator sees each cell's hook output land
before moving on) over throughput. A future round may parallelise
across cells once the harness is trusted.

## Hooks

### Scoping

Hooks are configured in `seer-cli/.claude/settings.json` (or
`settings.local.json`) and are **opt-in per session** via two
environment variables the operator exports before starting a session:

| Var | Meaning |
| --- | --- |
| `SEER_EVAL_RUN_ID` | Unique run id (e.g. `2026-05-15-run-01`). When unset, hooks no-op. |
| `SEER_EVAL_ARM` | `A` or `C`. Determines which arm directory results land in. |

Each hook script's first action is to check `SEER_EVAL_RUN_ID`; if
unset, it exits 0 immediately. This keeps the hooks invisible during
normal seer-cli development.

A future cleanup pass can remove the hooks from `settings.json`
entirely once the eval round is done — they are not part of the
shipped product.

### What each hook captures

| Hook | Filter | Records |
| --- | --- | --- |
| `PreToolUse` | `Agent` tool only | `run_id`, `arm`, `subagent_id` (synthesised), dispatch `start_time`, `agent_type`, `prompt` |
| `PostToolUse` | every tool, only when invoked by a subagent | `subagent_id`, `tool_name`, `args_summary` (truncated), `ts` |
| `SubagentStop` | n/a | `subagent_id`, `end_time`, `duration_seconds`, `model`, `usage` block (input/output/cache), `final_text` |

`subagent_id` is synthesised at `PreToolUse` time (e.g.
`<run_id>-<arm>-<repo>-<qid>-<trial>-<short-uuid>`) and propagated via
filename so the three hooks can stitch their output together.

### Reading the transcript for usage

`SubagentStop` receives the transcript path in its hook input payload.
The script opens the JSONL, finds the last `assistant`-role message
emitted *during the matching subagent invocation*, and reads the
`usage` block (`input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`, `model`).
Identifying the right slice of the transcript is the trickiest part of
the implementation — the plan should specify the exact heuristic
(likely: timestamps bracket between `PreToolUse` and `SubagentStop`).

## Per-cell record schema

After `capture.py` rolls up hook output, each cell looks like:

```json
{
  "run_id": "2026-05-15-run-01",
  "arm": "C",
  "repo": "/home/spark/git/culture",
  "repo_id": "culture",
  "question_id": "q-profile-overview",
  "question_text": "Give me an overview of this repo: …",
  "trial": 2,
  "operator": "claude-opus-4-7",
  "subagent": {
    "agent_type": "Explore",
    "model": "claude-opus-4-7",
    "duration_seconds": 47.3,
    "tokens": {
      "input": 12480,
      "output": 1890,
      "cache_read": 8200,
      "cache_creation": 2100
    },
    "tools_used": [
      {"name": "Bash", "count": 3,
       "patterns": ["scripts/profile.sh", "ls", "head"]},
      {"name": "Read", "count": 2}
    ]
  },
  "answer_text": "...",
  "validation": {
    "expected_evidence": ["pyproject.toml", "uv sync",
                          "async IRCd", "agent harness"],
    "found": ["pyproject.toml", "uv sync", "async IRCd"],
    "missing": ["agent harness"],
    "score": 0.75
  },
  "judge": null
}
```

`judge` is filled later by `judge.py` and looks like:

```json
{
  "judge_model": "claude-opus-4-7",
  "rubric_version": "v1",
  "comparison": {
    "winner": "C",
    "margin": "clear",
    "reasoning": "…",
    "blind_label_for_C": "answer_X",
    "blind_label_for_A": "answer_Y"
  }
}
```

## Three-layer scoring

| Layer | Output | Source | Cost |
| --- | --- | --- | --- |
| **Mechanical** | duration, tokens by class, model, tool distribution | hooks | free (just bookkeeping) |
| **Code validation** | recall of hand-authored expected-evidence | `validate.py` | free (deterministic regex/substring match) |
| **LLM-as-judge** | pairwise blind A-vs-C verdict + margin | `judge.py` | one judge call per (cell-A, cell-C) pair |

The three are independent. A run can re-judge by re-running `judge.py`
with a different rubric or model; mechanical metrics never change.

### Judge details

- Mode: **pairwise blind**. Judge sees the two answers labelled
  `answer_X` and `answer_Y`, the question, and the rubric. It must
  pick a winner and a margin (`tie` / `slight` / `clear` / `decisive`)
  with a one-paragraph reasoning.
- Blinding: which of A/C is X vs Y is randomised per cell-pair and
  recorded in the result so post-hoc analysis can de-blind.
- Rubric: lives in `judge_rubric.md` (versioned). Round 1 rubric covers
  factual correctness, completeness vs the question scope,
  actionability for the asker's likely next step, and absence of
  unsupported claims.
- Model: same model family as the operator (Claude Opus). A future
  round can cross-check with a different model to estimate judge bias.

### Code validation rubric

Each `corpus.yaml` question carries an `expected_evidence` map keyed
by `repo_id`:

```yaml
expected_evidence:
  culture: [pyproject.toml, "uv sync", "async IRCd", "agent harness"]
  daria: [pyproject.toml, "uv sync", "awareness agent", "culture"]
```

Each entry is a substring (case-insensitive) or `/regex/` form.
`validate.py` records `found` / `missing` and a `score` =
`len(found) / len(expected_evidence)`. The score is a *recall*
estimate — it does not penalise extra detail, only missing facts.

Authoring the lists is **the operator's responsibility before round
1**. The spec defines the schema and worked examples below; the full
lists are reviewed by the user (per brainstorm answer #2).

## Corpus design

### Targets — sibling AgentCulture repos

Default round-1 set, all under `/home/spark/git/`:

| `repo_id` | Path | Why this repo |
| --- | --- | --- |
| `culture` | `/home/spark/git/culture` | Large async Python; IRCd + agent harness; many subdirs. |
| `daria` | `/home/spark/git/daria` | Agent that consumes culture; cite-don't-import edges. |
| `claude-code-guide` | `/home/spark/git/claude-code-guide` | Different shape — Claude Code plugin (`plugin.json`, `marketplace.json`). |
| `agtag` | `/home/spark/git/agtag` | Small CLI; dense `pyproject.toml`. |
| `citation-cli` | `/home/spark/git/citation-cli` | Cite-don't-import reference; `packages/` shape. |

All five are Python repos for round 1, matching what `seer.repo`
reads today. Adding non-Python or differently-shaped targets is a
follow-up round once the harness itself is trusted. Operators
running their own round simply edit `corpus.yaml` to point at their
own paths and `repo_id`s.

### Question types

Six question types, mapped to script verbs and to the user's
real-question list:

| `question_id` | Type | Maps to | Per-repo or workspace |
| --- | --- | --- | --- |
| `q-profile-overview` | profile-shaped | `profile.sh` (shallow) | per-repo |
| `q-connections-1hop` | connections-shaped | `connections.sh --depth 1` | per-repo |
| `q-graph-workspace` | graph-shaped | `graph.sh` | workspace (once per arm) |
| `q-narrative` | narrative | `profile.sh --depth deep` | per-repo |
| `q-transfer-cli` | transfer | profile + synthesis | per-repo |
| `q-transfer-quality` | transfer | profile + synthesis | per-repo |

Each carries a question template with `{repo_path}` substitution
(workspace questions use `{workspace_root}`):

```yaml
- id: q-profile-overview
  type: profile
  template: |
    You are exploring the repository at {repo_path}.
    Give me a clear overview: what is this repo for, what is the
    build/test story, what are its top-level components.
  expected_evidence:
    culture: [pyproject.toml, "uv sync", "async IRCd",
              "agent harness", culture.yaml]
    daria: [pyproject.toml, "uv sync", "awareness agent",
            "claude agent sdk"]
    # … per repo

- id: q-connections-1hop
  type: connections
  template: |
    What does the repository at {repo_path} connect to (depend on,
    vendor from, or get cited by)? Walk one hop out.
  expected_evidence:
    culture: ["claude agent sdk", anthropic, "irc"]
    daria: [culture, "claude agent sdk"]
    # …

- id: q-graph-workspace
  type: graph
  template: |
    Map the repos in {workspace_root}. Which ones form clusters
    (by shared dependencies, vendored skills, or cite-don't-import
    edges), and how are they related?
  expected_evidence:
    _global: [agentculture, AgentCulture, culture, daria,
              steward, citation-cli]

- id: q-narrative
  type: narrative
  template: |
    Explain to me how the repository at {repo_path} works.
    Walk me through the main flow end-to-end. Be concrete: name files
    and functions where relevant.
  expected_evidence:
    culture: ["IRCd", "agent connect", "channel join", "message route"]
    # …

- id: q-transfer-cli
  type: transfer
  template: |
    The repository at {repo_path} has a CLI. Explain how I could
    build something like it in my own Python repo. Be concrete: what
    files, what entry points, what conventions, what packaging.
  expected_evidence:
    culture: [argparse, "console_scripts", pyproject.toml,
              "entry point", subcommand]
    # …

- id: q-transfer-quality
  type: transfer
  template: |
    The repository at {repo_path} has a CI / quality pipeline.
    What do I need to add to a generic Python repo to get the same
    pipeline (lint, test, security, version-bump enforcement)?
  expected_evidence:
    culture: [".github/workflows", pytest, flake8, bandit,
              "version-bump", pre-commit]
    # …
```

The workspace question (`q-graph-workspace`) only runs once per arm
per trial (3 trials × 2 arms = 6 cells), since "map the workspace"
isn't per-repo.

Per-repo question count (5 repos × 5 per-repo questions × 2 arms × 3
trials) = 150 cells. Plus 6 workspace cells. Plus violation re-runs.
Estimate: **160–170 cells per round**, ~30s of subagent wall time
each, plus operator overhead. Not free, but a long evening.

## Operator session topology

Two distinct Claude Code sessions, one per arm:

- **Arm A session.** The `repo-map` skill is **not loaded** (operator
  starts the session in a context where it's removed from
  `.claude/skills/` symlink, or operator manually unloads via skill
  controls — exact mechanism specified in `RUNBOOK.md`). Operator's
  system prompt tells the session: dispatch only `Explore` subagents,
  forbid the seer-related scripts and skills in subagent system
  prompts.
- **Arm C session.** The `repo-map` skill **is loaded**. Operator's
  system prompt invites the session to use it freely.

This physical separation guarantees the arm-A session cannot leak the
skill to its subagents (because it does not have it). It is the
strongest defence against accidental contamination short of
process-level sandboxing.

Both sessions export `SEER_EVAL_RUN_ID` (same value) and
`SEER_EVAL_ARM` (`A` or `C`). Hooks pick up both and write into the
same run directory under different `arm-*/` subdirs.

## Verification gate

After capture, `validate.py` makes one pass over every cell to flag
arm violations:

- **Arm A cell that called any of:** `seer.repo`, `seer/repo/`,
  `scripts/profile.sh`, `scripts/connections.sh`, `scripts/graph.sh`,
  `python -m seer` → flagged `arm_violation: A_used_scripts`.
- **Arm C cell that called none of those** → flagged
  `arm_violation: C_did_not_use_scripts`. Not always wrong (some
  questions don't need them), but interesting.

Flagged cells appear in `REPORT.md` under a "Violations" section.
A-violations are scheduled for **operator-driven re-run** with a
stricter system prompt — `RUNBOOK.md` includes the stricter prompt
template and the procedure for a targeted re-dispatch. C-violations
are kept and analysed (sometimes the question simply did not need
the scripts; this is a finding, not a bug).

## Repeatability

A new contributor (or future-us) running this against their own repos:

1. Clone seer-cli; `uv sync`.
2. Edit `experiments/scripts_eval/corpus.yaml`:
   - Replace `targets:` with their own `repo_id` + `path` rows.
   - Replace per-`repo_id` `expected_evidence` lists with their own.
   - Optionally edit question templates if their repos need different
     framings.
3. Pick a `run_id`, e.g. `2026-06-01-myorg-run-01`.
4. In two terminals, start two Claude Code sessions in the seer-cli
   checkout — one per arm. In each, export `SEER_EVAL_RUN_ID` and
   `SEER_EVAL_ARM`.
5. Both sessions read `RUNBOOK.md` and dispatch their assigned cells.
6. After both arms complete:
   - `python experiments/scripts_eval/capture.py --run <run_id>`
   - `python experiments/scripts_eval/validate.py --run <run_id>`
   - `python experiments/scripts_eval/judge.py --run <run_id>`
   - `python experiments/scripts_eval/report.py --run <run_id>`
7. Read `results/<run_id>/REPORT.md`.

`RUNBOOK.md` and `README.md` carry this procedure with concrete
commands. The hooks no-op without the env vars, so step 1 leaves the
checkout in a normal state.

### Adding a new repo to an existing corpus

Append to `targets:`, then for each existing question, add an
`expected_evidence` row keyed by the new `repo_id`. Re-run.

### Adding a new question type

Append to `questions:`. If it is a per-repo question, populate
`expected_evidence` for every existing target. Re-run.

## Open questions / deferred decisions

These are intentionally left to the implementation plan to resolve:

1. **Transcript-slicing heuristic.** `SubagentStop` reads the transcript;
   exactly *which* assistant message corresponds to the subagent's
   final output is implementation-defined. Likely: bracket by
   timestamp between `PreToolUse` and `SubagentStop`, take the last
   `usage`-bearing message.
2. **Args summary truncation.** `PostToolUse` records each tool call's
   `args_summary`; the truncation rule (length, redaction of secrets)
   is a plan-level detail.
3. **Judge model choice for round 1.** Default is operator's model
   (Claude Opus 4.7). Implementation may want a thinking-budget cap.
4. **`expected_evidence` authoring tooling.** For round 1 the lists
   are hand-written. If round 2's corpus grows, a small helper that
   pre-fills candidates from `seer.repo profile` output may be useful.

## What this spec doesn't cover

- The `seer learn` / `explain` / `overview` / `doctor` verb redesign.
  That is the next brainstorm, fed by this experiment's results.
- Adoption of `afi-cli` to scaffold the verb implementations from a
  template. Same follow-up brainstorm.
- A reusable cross-skill eval framework. If a second skill needs an
  eval harness, we generalise then; not now.

## Acceptance

This spec is acceptable when:

- The operator can read it and derive what files exist, where they
  live, what they contain, and what each script does, without further
  questions to the spec author.
- An external contributor can read `README.md` and `RUNBOOK.md`
  (whose contents this spec defines) and run an eval round against
  their own repos.
- The implementation plan derived from this spec produces an
  executable harness with no further design decisions to make beyond
  the five "open questions" above.
