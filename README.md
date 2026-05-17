# antoine

Codebase lookup and indexing for agent skills.

The name encodes the goal: **antoine = "N to 1"** (an-to-one). Collapse the
N ad-hoc tool calls an agent would otherwise make against a codebase
(`ls` + `cat` + `grep` + `git log` + `git show` + …) into **one** call to a
purpose-built `kata-cli` verb that returns the same information as
structured data. Every verb antoine ships is a bet that some recurring
N-call pattern has a 1-call replacement that is cheaper, more reliable,
and easier to delegate to a subagent.

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
