# scripts-eval RUNBOOK

This is the operator-facing procedure. It is followed by an
interactive Claude Code session ("operator-Claude"), arm at a time,
one cell at a time.

## Prerequisites

- `uv sync --group experiments` has run.
- `ANTHROPIC_API_KEY` is set in the operator's shell (for `judge.py`).
- `corpus.yaml` lists the targets and questions for this round.
- A run id is chosen, e.g. `2026-05-15-run-01`.

## One run = two operator sessions

Round 1 uses two distinct Claude Code sessions, one per arm:

| Arm | Skill state | Operator system prompt |
| --- | --- | --- |
| A   | `repo-map` skill **not loaded** in this session | "Dispatch only `Explore` subagents. In each subagent prompt, forbid the `repo-map` skill and the `seer.repo` / `scripts/*.sh` paths." |
| C   | `repo-map` skill **loaded** in this session | "Dispatch only `Explore` subagents. Each may use the `repo-map` skill and its scripts at its discretion." |

Both sessions export the same env vars before launching:

```bash
export SEER_EVAL_RUN_ID=2026-05-15-run-01
export SEER_EVAL_ARM=A   # or C in the other session
```

The hooks pick up these env vars; without them, hooks no-op.

Once per run (in either arm session — it is idempotent), write the
manifest:

```bash
uv run --group experiments python -m experiments.scripts_eval.manifest init \
    --run $SEER_EVAL_RUN_ID
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
       --run $SEER_EVAL_RUN_ID --repo <repo_id_or_blank> \
       --question <question_id> --trial <n>
   ```

5. Verify a per-cell JSON appeared under
   `experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-<X>/`.
6. Move to the next row.

**Sequential, not parallel.** One cell at a time. Round 1 favours
observability over speed.

## After both arms finish

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $SEER_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.judge \
    --run $SEER_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.report \
    --run $SEER_EVAL_RUN_ID
```

Read `results/$SEER_EVAL_RUN_ID/REPORT.md`.

## Violations

`REPORT.md` lists two kinds:

- `A_used_scripts: ...` — an arm-A subagent invoked the scripts despite
  the prompt. Re-dispatch that cell with this stricter system prompt
  prepended:

  ```text
  ABSOLUTE: do not run any of: scripts/profile.sh, scripts/connections.sh,
  scripts/graph.sh, python -m seer.repo, or any path containing seer/repo.
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
