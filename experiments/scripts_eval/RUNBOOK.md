# scripts-eval RUNBOOK

This is the operator-facing procedure. It is followed by an
interactive Claude Code session ("operator-Claude"), arm at a time,
one cell at a time.

## Prerequisites

- `uv sync --group experiments` has run.
- `corpus.yaml` lists the targets and questions for this round.
- A run id is chosen, e.g. `2026-05-15-run-01`.

The judge LLM call is performed by an operator-dispatched subagent in
the same Claude Code session, so no `ANTHROPIC_API_KEY` needs to be in
the operator's shell.

**Note for non-spark contributors:** edit `corpus.yaml`'s `config.workspace_root` to point at *your* checkout root before round 1 — the `q-graph-workspace` question substitutes this path verbatim.

## One run = two operator sessions

Round 1 uses two distinct Claude Code sessions, one per arm:

| Arm | Skill state | Operator system prompt |
| --- | --- | --- |
| A   | `repo-map` skill **not loaded** in this session | "Dispatch only `Explore` subagents. In each subagent prompt, forbid the `repo-map` skill and the `antoine.repo` / `scripts/*.sh` paths." |
| C   | `repo-map` skill **loaded** in this session | "Dispatch only `Explore` subagents. Each may use the `repo-map` skill and its scripts at its discretion." |

Both sessions export the same env vars before launching:

```bash
export ANTOINE_EVAL_RUN_ID=2026-05-15-run-01
export ANTOINE_EVAL_ARM=A   # or C in the other session
```

The hooks pick up these env vars; without them, hooks no-op.

Once per run (in either arm session — it is idempotent), write the
manifest:

```bash
uv run --group experiments python -m experiments.scripts_eval.manifest init \
    --run $ANTOINE_EVAL_RUN_ID
```

## Per-cell loop (within an arm session)

For each `(repo_id or workspace, question_id, trial)` row in
`corpus.yaml` not yet present in this run's `arm-<X>/`:

1. Look up the question template in `corpus.yaml`. Substitute
   `{repo_path}` (per-repo) or `{workspace_root}` (workspace).
2. Dispatch one `Explore` subagent. Subagent prompt:

   ```text
   <substituted question template>

   Constraints (verbatim):
   - <arm-specific restrictions, see table above>
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>  (one line per distinct tool)
     ### evidence
     - <one path per line>
   ```

3. Wait for the subagent to finish. Hooks fire automatically.
4. Run capture:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.capture \
       --run $ANTOINE_EVAL_RUN_ID --repo <repo_id_or_blank> \
       --question <question_id> --trial <n>
   ```

5. Verify a per-cell JSON appeared under
   `experiments/scripts_eval/results/$ANTOINE_EVAL_RUN_ID/arm-<X>/`.
6. Move to the next row.

**Sequential, not parallel.** One cell at a time. Round 1 favours
observability over speed.

## After both arms finish

### 1. Validate

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $ANTOINE_EVAL_RUN_ID
```

### 2. Judge (per-pair, subagent-driven)

The judge LLM call happens inside an operator-dispatched
`general-purpose` subagent — there is no API client in `judge.py`.
The Python side owns deterministic plumbing (pairing, seeded
blinding, evidence-tail strip, JSON parse, disk write); the subagent
owns only the cognition.

For each `(repo_id, question_id, trial)` pair (workspace pairs use
`_workspace_` in place of `repo_id`):

1. **List remaining pairs:**

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       prepare --run $ANTOINE_EVAL_RUN_ID --list
   ```

2. **Prepare one pair.** This emits a single JSON object with the
   blinded prompt and the blind labels:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       prepare --run $ANTOINE_EVAL_RUN_ID \
       --pair-key <repo_or__workspace_>/<question_id>/<trial>
   ```

3. **Dispatch the judge subagent.** Operator-Claude calls the Agent
   tool with:

   - `subagent_type`: `general-purpose`
   - `description`: must start with `"scripts_eval judge: "` followed
     by the pair_key. **This prefix is load-bearing** — the
     `pre_tool` hook recognises it and skips logging so the judge
     dispatch does not pollute `raw/`.
   - `prompt`: the `prompt_text` field from prepare's output.

   Wait for the subagent to finish; collect its final-text response.

4. **Record the verdict.** Pipe the subagent's final text into
   `record` via stdin (the subagent may produce surrounding prose
   around the JSON — `record` extracts the first `{…}` blob):

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.judge \
       record --run $ANTOINE_EVAL_RUN_ID \
       --pair-key <…> \
       --blind-label-for-a <answer_X|answer_Y> \
       --blind-label-for-c <answer_X|answer_Y> \
       --verdict-file - <<'EOF'
   <paste subagent's final text here>
   EOF
   ```

   `record` writes the locked-surface `judge` block to both paired
   cell JSONs. It is idempotent — re-running with a different verdict
   overwrites cleanly, so if a subagent answer was clearly bad you can
   simply re-dispatch and re-record without manual cell editing.

If `record` exits non-zero with `"non-JSON"` or a vocabulary error
(`winner` must be `X|Y|tie`; `margin` must be `tie|slight|clear|decisive`),
re-dispatch the judge subagent for that pair. The Python side never
silently falls back to a tie.

### 3. Report

```bash
uv run --group experiments python -m experiments.scripts_eval.report \
    --run $ANTOINE_EVAL_RUN_ID
```

Read `results/$ANTOINE_EVAL_RUN_ID/REPORT.md`.

## Violations

`REPORT.md` lists two kinds:

- `A_used_scripts: ...` — an arm-A subagent invoked the scripts despite
  the prompt. Re-dispatch that cell with this stricter system prompt
  prepended:

  ```text
  ABSOLUTE: do not run any of: scripts/profile.sh, scripts/connections.sh,
  scripts/graph.sh, python -m antoine.repo, or any path containing antoine/repo.
  If you cannot answer without them, say so explicitly and stop.
  ```

  Re-run capture for the cell. Replace the prior arm-A JSON in place.

- `C_did_not_use_scripts: ...` — an arm-C subagent never called the
  scripts. Keep the cell; this is a finding ("the scripts didn't seem
  necessary"), not a bug.

## Adding a target repo or question type mid-corpus

Edit `corpus.yaml`. For a new target, add an `expected_evidence` row
under every per-repo question. Re-run only the new cells (capture
takes `--repo` and `--question` so partial runs are natural).
