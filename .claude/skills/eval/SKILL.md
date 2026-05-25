---
name: eval
type: command
description: >
  Run one scripts-eval set — one `(target, question)` row from
  `experiments/scripts_eval/corpus.yaml` × 3 trials × one arm — including
  tester subagent dispatches + captures, plus (for arm C) judge subagent
  dispatches + records, then `summarize` + commit to the round's
  accumulator file. Use when the user says "run eval set", "eval",
  "scripts-eval", "round-NN set", or asks to execute a row of the corpus.
  Three arms: A (banned — rider forbids the antoine skills), B (directed
  — rider instructs use of antoine skills), C (organic — rider permits
  but doesn't direct). Two judge pairs: A-vs-B ("do the skills help
  when used") and A-vs-C ("do the skills get adopted organically").
  `judge prepare --pair AB|AC` selects the pair.
---

# scripts-eval — running a set

This skill drives one **set** of the scripts-eval harness:
one `(target, question)` row × 3 trials × one arm.

The harness pipeline (`trial` / `validate` / `judge` / `summarize`) and
the corpus (`corpus.yaml`) are repo state — this skill is just the
operator procedure that sequences them per session.

## When to push back

Before doing anything, verify the user's intent matches the session
state. Stop and ask if any of these hold:

- `env | grep ANTOINE_EVAL_RUN_ID` is empty → the harness hooks no-op, no
  metrics get captured. Operator needs to re-launch with the env vars
  exported.
- `ANTOINE_EVAL_ARM` is set to anything other than `A`, `B`, or `C` → bad config.
- User says "do arm C" but the matching arm-A cells don't exist on
  disk under `experiments/scripts_eval/results/$ANTOINE_EVAL_RUN_ID/arm-A/`
  → arm A must complete first; there's nothing to pair against.

All three arms run with `repo-map` and `code-lookup` enabled on disk.
Arm-A's constraint is **verbal** — the rider in the dispatched prompt
is the sole guard against the subagent using the antoine skills. Do not
edit the rider; copy it verbatim. (Earlier versions of this skill
physically moved `.claude/skills/repo-map/` aside for arm A as
defense-in-depth; that step was dropped because the rider proved
sufficient and the move-aside dance made operator setup brittle.)

Three arms, three questions they answer:

- **A (banned)** — verbal rider forbids both antoine skills. Establishes
  the "without the new skills" baseline.
- **B (directed)** — verbal rider instructs the subagent to use the
  antoine skills where applicable. Establishes the "with the new skills,
  when actually used" upper bound.
- **C (organic)** — verbal rider permits but does not direct use of
  the antoine skills. Measures organic adoption rate.

A-vs-B is the primary "do the skills help?" comparison; A-vs-C is the
adoption canary. The judge supports both pairs via the `--pair` flag.

## Preflight (every session)

```bash
env | grep -E "^ANTOINE_EVAL_(RUN_ID|ARM)="
# expect both set to the intended round / arm
```

If unset, export them in your shell before launching `claude`:

```bash
# arm-A session (banned):
export ANTOINE_EVAL_RUN_ID=2026-05-NN-round-XX ANTOINE_EVAL_ARM=A
# arm-B session (directed):
export ANTOINE_EVAL_RUN_ID=2026-05-NN-round-XX ANTOINE_EVAL_ARM=B
# arm-C session (organic):
export ANTOINE_EVAL_RUN_ID=2026-05-NN-round-XX ANTOINE_EVAL_ARM=C
```

`experiments/scripts_eval/switch-arm.sh A|B|C <run_id>` does the same
thing.

If this is the first set of the run (idempotent, safe to re-run):

```bash
uv run --group experiments python -m experiments.scripts_eval.manifest \
    init --run $ANTOINE_EVAL_RUN_ID
```

## Arm-A procedure

**For each trial in {1, 2, 3}:**

1. Read the question template for the target's `question_id` from
   `experiments/scripts_eval/corpus.yaml`. Look up the target's path
   from the same file's `targets:` list.

2. Substitute `{repo_path}` (or `{workspace_root}` for the workspace
   question) in the template, then append **verbatim**:

   ```text

   Constraints (verbatim):
   - You may NOT use the `repo-map` skill, `python -m antoine.repo`,
     the `antoine.repo` Python module, or any `scripts/*.sh` paths under
     `.claude/skills/repo-map/`.
   - You may NOT use the `code-lookup` skill, the `antoine.lookup`
     Python module, the `antoine grep` / `antoine recent` / `antoine classify`
     CLI verbs, or any `scripts/*.sh` paths under
     `.claude/skills/code-lookup/`.
     If you cannot answer without them, say so explicitly and stop.
   - Use only Read, Grep, Glob, and Bash.
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>  (one line per distinct tool)
     ### evidence
     - <one path per line>
   ```

3. **Before dispatch** — start the trial. The script reads
   `CLAUDE_CODE_SESSION_ID` from env, stamps an in-flight record, and
   prints the `trial_id` to stdout:

   ```bash
   TRIAL_ID=$(uv run --group experiments python -m experiments.scripts_eval.trial \
       start --run $ANTOINE_EVAL_RUN_ID --arm $ANTOINE_EVAL_ARM \
       --target <target> --question <question_id> --trial <n>)
   ```

   (For the workspace-scope question, omit `--target`.)

4. Dispatch **one** `Explore` subagent with the full prompt.

5. After the subagent finishes, end the trial. The script reads the
   subagent's sidechain transcript from
   `$HOME/.claude/projects/<encoded_cwd>/<session>/subagents/agent-*.jsonl`
   and writes the cell JSON:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.trial \
       end --trial-id "$TRIAL_ID"
   ```

6. Confirm the cell JSON appeared under
   `experiments/scripts_eval/results/$ANTOINE_EVAL_RUN_ID/arm-A/`.

**After all 3 trials**, summarize + commit:

```bash
uv run --group experiments python -m experiments.scripts_eval.summarize \
    --run $ANTOINE_EVAL_RUN_ID \
    --out docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md

git add docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md
git commit -m "$ANTOINE_EVAL_RUN_ID: arm-A captured for <target>/<question_id> (3 trials)"
```

Report back: cell count under arm-A/, what's pending for arm-B and
arm-C on this set, the next pending set per the run-state table in the
accumulator file.

## Arm-B procedure

Arm-B captures the **directed** trials so the A-vs-B judge run can
assess "do the skills help when actually used?". Capture happens in
its own session (`ANTOINE_EVAL_ARM=B`); the A-vs-B judges then run in
the arm-C session's Judge phase, alongside the A-vs-C judges
(`judge prepare --pair AB`).

**For each trial in {1, 2, 3}:**

1. Substitute the corpus question template (same target / question
   resolution as arm A), then append **verbatim** the arm-B rider:

   ```text

   Constraints (verbatim):
   - For this question, you MUST use the antoine skills where they
     apply:
       * `repo-map` (`scripts/profile.sh`, `scripts/connections.sh`,
         `scripts/graph.sh` under `.claude/skills/repo-map/`) for
         repo overview, dependencies, and workspace shape.
       * `code-lookup` (`antoine grep`, `antoine recent`, `antoine classify`,
         or the equivalent scripts under
         `.claude/skills/code-lookup/`) for symbol references,
         recent commit-symbol diffs, and project-kind classification.
     Only fall back to Read / Grep / Glob / Bash for facts the
     scripts do not cover.
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>  (one line per distinct tool)
     ### evidence
     - <one path per line>
   ```

2. Bookend the dispatch with `trial start` and `trial end` exactly
   as in arm A, just with `--arm B`:

   ```bash
   TRIAL_ID=$(uv run --group experiments python -m experiments.scripts_eval.trial \
       start --run $ANTOINE_EVAL_RUN_ID --arm $ANTOINE_EVAL_ARM \
       --target <target> --question <question_id> --trial <n>)
   # dispatch one Explore subagent with the rendered prompt above
   uv run --group experiments python -m experiments.scripts_eval.trial \
       end --trial-id "$TRIAL_ID"
   ```

3. Confirm the cell JSON appeared under
   `experiments/scripts_eval/results/$ANTOINE_EVAL_RUN_ID/arm-B/`.

**After all 3 trials**, summarize + commit:

```bash
uv run --group experiments python -m experiments.scripts_eval.summarize \
    --run $ANTOINE_EVAL_RUN_ID \
    --out docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md

git add docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md
git commit -m "$ANTOINE_EVAL_RUN_ID: arm-B captured for <target>/<question_id> (3 trials)"
```

Report back: cell count under arm-B/, whether the subagent actually
followed the directive (look at the `### tools_used` of each arm-B
cell — `B_did_not_use_scripts` is a finding, not a bug), the next
pending set per the run-state table.

## Arm-C procedure

**Precondition check (mandatory):**

```bash
ls experiments/scripts_eval/results/$ANTOINE_EVAL_RUN_ID/arm-A/<target>-<question_id>-t*.json
# expect: 3 files (t1, t2, t3)
```

If fewer than 3, stop — arm A must complete first.

### Tester phase

**For each trial in {1, 2, 3}:**

1. Substitute the corpus question template (same as arm A) but with the
   arm-C rider:

   ```text

   Constraints (verbatim):
   - You may use the `repo-map` skill (and its scripts under
     `.claude/skills/repo-map/`) and the `code-lookup` skill (and its
     scripts under `.claude/skills/code-lookup/`) at your discretion.
     This includes `antoine grep` / `antoine recent` / `antoine classify`.
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>
     ### evidence
     - <one path per line>
   ```

2. Bookend the dispatch with `trial start` and `trial end`:

   ```bash
   TRIAL_ID=$(uv run --group experiments python -m experiments.scripts_eval.trial \
       start --run $ANTOINE_EVAL_RUN_ID --arm $ANTOINE_EVAL_ARM \
       --target <target> --question <question_id> --trial <n>)
   # dispatch one Explore subagent with the rendered prompt above
   uv run --group experiments python -m experiments.scripts_eval.trial \
       end --trial-id "$TRIAL_ID"
   ```

   (For the workspace-scope question, omit `--target`.)

### Judge phase

Two pairs are judged independently:

- **A-vs-C** — the original "with vs without (organic)" comparison.
- **A-vs-B** — the new "with (directed) vs without" comparison; needs
  arm-B cells captured first.

Both pairs use the same `prepare` / `record` flow; only `--pair`
(`AC` or `AB`) and the matching `--blind-label-for-<arm>` flags differ.

**For each trial in {1, 2, 3}**, run the A-vs-C judge first (if arm-C
cells exist) and then the A-vs-B judge (if arm-B cells exist):

1. Prepare the blinded job. `--pair` defaults to `AC`; pass `--pair AB`
   for the A-vs-B run.

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       prepare --run $ANTOINE_EVAL_RUN_ID \
       --pair AC \
       --pair-key <target>/<question_id>/<n> \
       --seed 0 > /tmp/judge-AC-<n>.json
   ```

2. Materialise the prompt to a text file for dispatch (`jq -j`
   joins without adding a trailing newline, so the bytes match what
   `prepare` emitted):

   ```bash
   jq -j '.prompt_text' /tmp/judge-AC-<n>.json > /tmp/judge-AC-<n>.txt
   ```

3. Dispatch the judge subagent. **The description prefix is
   load-bearing** — the `pre_tool` hook recognises `scripts_eval judge:`
   and skips logging, so the judge dispatch does not pollute the
   harness's `raw/` directory:

   - `subagent_type`: `general-purpose`
   - `description`: `scripts_eval judge: AC <target>/<question_id>/<n>`
   - `prompt`: the verbatim contents of `/tmp/judge-AC-<n>.txt`

4. Capture the subagent's final-text response and record. The blind
   labels for an AC pair come back as `blind_label_for_A` /
   `blind_label_for_C`:

   ```bash
   A_LABEL=$(jq -r .blind_label_for_A /tmp/judge-AC-<n>.json)
   C_LABEL=$(jq -r .blind_label_for_C /tmp/judge-AC-<n>.json)
   uv run --group experiments python -m experiments.scripts_eval.judge \
       record --run $ANTOINE_EVAL_RUN_ID \
       --pair AC \
       --pair-key <target>/<question_id>/<n> \
       --blind-label-for-a "$A_LABEL" \
       --blind-label-for-c "$C_LABEL" \
       --verdict-file -
   ```

5. **Repeat the four steps with `--pair AB`** to judge the directed
   arm. The job JSON for an AB pair carries `blind_label_for_A` and
   `blind_label_for_B` (no `_C`); use `--blind-label-for-b` instead of
   `--blind-label-for-c`:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       prepare --run $ANTOINE_EVAL_RUN_ID \
       --pair AB \
       --pair-key <target>/<question_id>/<n> \
       --seed 0 > /tmp/judge-AB-<n>.json
   jq -j '.prompt_text' /tmp/judge-AB-<n>.json > /tmp/judge-AB-<n>.txt
   # …dispatch general-purpose subagent with description
   #   "scripts_eval judge: AB <target>/<question_id>/<n>" and the txt prompt…
   A_LABEL=$(jq -r .blind_label_for_A /tmp/judge-AB-<n>.json)
   B_LABEL=$(jq -r .blind_label_for_B /tmp/judge-AB-<n>.json)
   uv run --group experiments python -m experiments.scripts_eval.judge \
       record --run $ANTOINE_EVAL_RUN_ID \
       --pair AB \
       --pair-key <target>/<question_id>/<n> \
       --blind-label-for-a "$A_LABEL" \
       --blind-label-for-b "$B_LABEL" \
       --verdict-file -
   ```

   If `record` exits non-zero with `non-JSON` / `winner` / `margin` /
   `blind_label` in the error, re-dispatch the judge subagent for that
   trial and re-record. `record` is idempotent on replay — the operator's
   recovery path is "re-dispatch + re-record"; no manual cell editing.

Storage: AC verdicts land under `cell["judges"]["AC"]` (and are mirrored
to `cell["judge"]` for back-compat with pre-phase-2 readers); AB verdicts
land under `cell["judges"]["AB"]` only.

### Wrap-up

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $ANTOINE_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.summarize \
    --run $ANTOINE_EVAL_RUN_ID \
    --out docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md

git add docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md
git commit -m "$ANTOINE_EVAL_RUN_ID: completed <target>/<question_id> (both arms + judge)"
```

Report back:
- A-vs-B winners (A / B / tie) and A-vs-C winners (A / C / tie).
- Whether arm B and arm C actually used the antoine scripts (look at the
  `### tools_used` of each cell — `B_did_not_use_scripts` and
  `C_did_not_use_scripts` are findings, not bugs).
- The next pending set per the run-state table.

## Reading the run state

The committed run-state table and per-set verdicts live in
`docs/eval-rounds/$ANTOINE_EVAL_RUN_ID.md`, between the
`<!-- runstate:start -->` / `<!-- runstate:end -->` and
`<!-- evidence:start -->` / `<!-- evidence:end -->` markers. `summarize.py`
rewrites those regions idempotently — do not hand-edit them.

The accumulator file is also the operator's source of truth for what's
pending: a row's `arm-A` or `arm-C` count below `3/3` means more trials
are needed; `judged` below the arm counts means judges still owe verdicts.

## Cite-don't-import

This skill is original to antoine (the harness only exists here). When
promoted upstream, it would re-vendor into steward's skill suppliers —
update `docs/skill-sources.md` accordingly at that point.
