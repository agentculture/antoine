# antoine

Codebase lookup and indexing for agent skills.

## What's here

- **`antoine/`** — the package that will eventually expose the lookup
  verbs. Greenfield: `learn` / `explain` / `whoami` are honest
  placeholder stubs. See [`CLAUDE.md`](./CLAUDE.md) for build / test /
  architecture details.

- **`experiments/scripts_eval/`** — A/B-test harness for the `repo-map`
  skill (env-var-gated hooks, three-layer scoring, 5-repo round-1
  corpus). Round 1 is the validation gate before the verb design
  lands. See
  [`experiments/scripts_eval/README.md`](./experiments/scripts_eval/README.md)
  and
  [`experiments/scripts_eval/RUNBOOK.md`](./experiments/scripts_eval/RUNBOOK.md).
