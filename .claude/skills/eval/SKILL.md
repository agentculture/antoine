---
name: eval
description: >
  Run one scripts-eval set — one `(target, question)` row from
  `experiments/scripts_eval/corpus.yaml` × 3 trials × one arm — including
  tester subagent dispatches + captures, plus (for arm C) judge subagent
  dispatches + records, then `summarize` + commit to the round's
  accumulator file. Use when the user says "run eval set", "eval",
  "scripts-eval", "round-NN set", or asks to execute a row of the corpus.
  Two sessions per `(target, question)` pair — arm A first, arm C second
  (which also runs the judges, summary, and commit).
---

# scripts-eval — running a set

This skill drives one **set** of the scripts-eval harness:
one `(target, question)` row × 3 trials × one arm.

The harness pipeline (`capture` / `validate` / `judge` / `report`) and
the corpus (`corpus.yaml`) are repo state — this skill is just the
operator procedure that sequences them per session.

## When to push back

Before doing anything, verify the user's intent matches the session
state. Stop and ask if any of these hold:

- `env | grep SEER_EVAL_RUN_ID` is empty → the harness hooks no-op, no
  metrics get captured. Operator needs to re-launch with the env vars
  exported.
- `SEER_EVAL_ARM=A` but the available-skills list at session start
  includes `repo-map` → defense-in-depth is broken. Ask the operator
  to move `.claude/skills/repo-map/` aside before relaunch.
- `SEER_EVAL_ARM=C` but `repo-map` is NOT listed → arm C is being run
  without the equipment under test. Same fix.
- User says "do arm C" but the matching arm-A cells don't exist on
  disk under `experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-A/`
  → arm A must complete first; there's nothing to pair against.

## Preflight (every session)

```bash
env | grep -E "^SEER_EVAL_(RUN_ID|ARM)="
# expect both set to the intended round / arm
```

If this is the first set of the run (idempotent, safe to re-run):

```bash
uv run --group experiments python -m experiments.scripts_eval.manifest \
    init --run $SEER_EVAL_RUN_ID
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
   - You may NOT use the `repo-map` skill. You may NOT invoke
     `python -m seer.repo`, the `seer.repo` Python module, or any
     `scripts/*.sh` paths under `.claude/skills/repo-map/`.
     If you cannot answer without them, say so explicitly and stop.
   - Use only Read, Grep, Glob, and Bash.
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>  (one line per distinct tool)
     ### evidence
     - <one path per line>
   ```

3. Dispatch **one** `Explore` subagent with that full prompt.

4. After the subagent finishes, run capture:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.capture \
       --run $SEER_EVAL_RUN_ID --repo <target> \
       --question <question_id> --trial <n>
   ```

   (For the workspace-scope question, omit `--repo`.)

5. Confirm the cell JSON appeared under
   `experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-A/`.

**After all 3 trials**, summarize + commit:

```bash
uv run --group experiments python -m experiments.scripts_eval.summarize \
    --run $SEER_EVAL_RUN_ID \
    --out docs/eval-rounds/$SEER_EVAL_RUN_ID.md

git add docs/eval-rounds/$SEER_EVAL_RUN_ID.md
git commit -m "$SEER_EVAL_RUN_ID: arm-A captured for <target>/<question_id> (3 trials)"
```

Report back: cell count under arm-A/, what's pending for arm-C on
this set, the next pending set per the run-state table in the
accumulator file.

## Arm-C procedure

**Precondition check (mandatory):**

```bash
ls experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-A/<target>-<question_id>-t*.json
# expect: 3 files (t1, t2, t3)
```

If fewer than 3, stop — arm A must complete first.

### Tester phase

**For each trial in {1, 2, 3}:**

1. Substitute the corpus question template (same as arm A) but with the
   arm-C rider:

   ```text

   Constraints (verbatim):
   - You may use the `repo-map` skill and its scripts at your discretion.
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>
     ### evidence
     - <one path per line>
   ```

2. Dispatch one `Explore` subagent.

3. Capture:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.capture \
       --run $SEER_EVAL_RUN_ID --repo <target> \
       --question <question_id> --trial <n>
   ```

### Judge phase

**For each trial in {1, 2, 3}:**

1. Prepare the blinded job (writes pair_key, blind labels, and the
   already-blinded prompt with `### tools_used` / `### evidence` tails
   stripped from both answer bodies):

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       prepare --run $SEER_EVAL_RUN_ID \
       --pair-key <target>/<question_id>/<n> \
       --seed 0 > /tmp/judge-<n>.json
   ```

2. Materialise the prompt to a text file for dispatch (`jq -j`
   joins without adding a trailing newline, so the bytes match what
   `prepare` emitted):

   ```bash
   jq -j '.prompt_text' /tmp/judge-<n>.json > /tmp/judge-<n>.txt
   ```

3. Dispatch the judge subagent. **The description prefix is
   load-bearing** — the `pre_tool` hook recognises `scripts_eval judge:`
   and skips logging, so the judge dispatch does not pollute the
   harness's `raw/` directory:

   - `subagent_type`: `general-purpose`
   - `description`: `scripts_eval judge: <target>/<question_id>/<n>`
   - `prompt`: the verbatim contents of `/tmp/judge-<n>.txt`

4. Capture the subagent's final-text response and record:

   ```bash
   A_LABEL=$(jq -r .blind_label_for_A /tmp/judge-<n>.json)
   C_LABEL=$(jq -r .blind_label_for_C /tmp/judge-<n>.json)
   # Pipe the subagent's verdict text on stdin:
   uv run --group experiments python -m experiments.scripts_eval.judge \
       record --run $SEER_EVAL_RUN_ID \
       --pair-key <target>/<question_id>/<n> \
       --blind-label-for-a "$A_LABEL" \
       --blind-label-for-c "$C_LABEL" \
       --verdict-file -
   ```

   If `record` exits non-zero with `non-JSON` / `winner` / `margin` /
   `blind_label` in the error, re-dispatch the judge subagent for that
   trial and re-record. `record` is idempotent on replay — the operator's
   recovery path is "re-dispatch + re-record"; no manual cell editing.

### Wrap-up

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $SEER_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.summarize \
    --run $SEER_EVAL_RUN_ID \
    --out docs/eval-rounds/$SEER_EVAL_RUN_ID.md

git add docs/eval-rounds/$SEER_EVAL_RUN_ID.md
git commit -m "$SEER_EVAL_RUN_ID: completed <target>/<question_id> (both arms + judge)"
```

Report back:
- Judge winners on this set (A / C / tie counts).
- Whether arm C actually used the `repo-map` scripts (look at the
  `### tools_used` of each arm-C cell — `C_did_not_use_scripts` is a
  finding, not a bug).
- The next pending set per the run-state table.

## Reading the run state

The committed run-state table and per-set verdicts live in
`docs/eval-rounds/$SEER_EVAL_RUN_ID.md`, between the
`<!-- runstate:start -->` / `<!-- runstate:end -->` and
`<!-- evidence:start -->` / `<!-- evidence:end -->` markers. `summarize.py`
rewrites those regions idempotently — do not hand-edit them.

The accumulator file is also the operator's source of truth for what's
pending: a row's `arm-A` or `arm-C` count below `3/3` means more trials
are needed; `judged` below the arm counts means judges still owe verdicts.

## Cite-don't-import

This skill is original to seer-cli (the harness only exists here). When
promoted upstream, it would re-vendor into steward's skill suppliers —
update `docs/skill-sources.md` accordingly at that point.
