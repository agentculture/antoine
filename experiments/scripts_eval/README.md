# scripts-eval

A/C subagent comparison harness for the `repo-map` skill.

This experiment answers three questions about the scripts under
`.claude/skills/repo-map/scripts/`:

1. **Gate** — does an agent armed with `repo-map` produce better
   answers than a bare agent (Read/Grep/Glob only)?
2. **Calibration** — *where* is the win — which question shapes
   benefit, and how much (in tokens, time, judged quality)?
3. **Diagnostics** — when do equipped agents misuse the scripts?

See `docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md`
for the design and `RUNBOOK.md` for the operator procedure.

## Layout

```text
experiments/scripts_eval/
├── README.md             ← this file
├── RUNBOOK.md            ← operator procedure
├── corpus.yaml           ← targets × questions × expected_evidence
├── judge_rubric.md       ← rubric for the LLM-as-judge
├── _io.py                ← shared helpers
├── corpus.py             ← corpus loader
├── manifest.py           ← per-run manifest.json (date, env, models)
├── capture.py            ← raw hook JSONL → per-cell JSON
├── validate.py           ← code-validation against expected_evidence
├── judge.py              ← pairwise blind LLM-as-judge
├── report.py             ← REPORT.md generator
├── hooks/                ← Claude Code hook scripts
└── results/              ← per-run artefacts (gitignored)
```

## Three-layer scoring

| Layer | Source |
| --- | --- |
| Mechanical (duration, tokens, model, tools) | hooks |
| Code validation (recall of expected_evidence) | validate.py |
| Pairwise blind LLM judge (winner + margin) | judge.py |

## Repeatability

A new contributor pointing this at their own repos:

1. `uv sync --group experiments`
2. Edit `corpus.yaml`: replace `targets:` with their own repos and
   each question's `expected_evidence` with their own facts.
3. Pick a run id, export `SEER_EVAL_RUN_ID` and `SEER_EVAL_ARM`,
   follow `RUNBOOK.md`.
4. Read `results/<run_id>/REPORT.md`.

The hooks no-op without the env vars, so day-to-day seer-cli work in
the same checkout is unaffected.
