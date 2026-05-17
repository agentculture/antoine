# antoine

Codebase lookup and indexing for agent skills.

The name encodes the goal: **antoine = "N to 1"** (an-to-one). Collapse the
N ad-hoc tool calls an agent would otherwise make against a codebase
(`ls` + `cat` + `grep` + `git log` + `git show` + …) into **one** call to a
purpose-built `kata` verb (or its `antoine` alias — see
[`pyproject.toml`](./pyproject.toml) for the console-script wiring;
`kata-cli` is the PyPI **distribution** name, not a command name) that
returns the same information as structured data. Every verb antoine ships is a bet that some recurring
N-call pattern has a 1-call replacement that is cheaper, more reliable,
and easier to delegate to a subagent.

## What's here

This repo manages three intertwined things — the CLI that ships the
1-call verbs, the evaluation harness that tells us whether the verbs are
actually worth the bet, and the recorded results from past rounds.

- **`antoine/`** — the package that will eventually expose the lookup
  verbs. Greenfield: `learn` / `explain` / `whoami` are honest
  placeholder stubs. See [`CLAUDE.md`](./CLAUDE.md) for build / test /
  architecture details.

- **`kata-cli` (and `code-lens-cli`) — alt-published PyPI distributions**
  carrying the same wheel content as `antoine-cli`. Installing any of the
  three exposes the same pair of console scripts — `antoine` and `kata`
  (see [`pyproject.toml`](./pyproject.toml)). The dispatching directives
  baked into [`CLAUDE.md`](./CLAUDE.md) refer to **verbs** invoked via the
  `kata` / `antoine` commands; `kata-cli` is the distribution label users
  `pip install`, not a command they run. The dual-publish loop is defined
  in [`.github/workflows/`](./.github/workflows/); see
  [`CHANGELOG.md`](./CHANGELOG.md) entries for v0.7.0 / v0.7.1 for the
  history of how the three distribution names were wired up.

- **`experiments/scripts_eval/`** — the A/B-test harness for the
  `repo-map` skill (env-var-gated hooks, three-layer scoring, 5-repo
  round-1 corpus, multi-arm rider design with banned / directed /
  organic modes, multi-pair LLM-as-judge). The eval rounds are the
  validation gate before the `learn` / `explain` / `overview` /
  `doctor` verb redesign lands. See
  [`experiments/scripts_eval/README.md`](./experiments/scripts_eval/README.md)
  and
  [`experiments/scripts_eval/RUNBOOK.md`](./experiments/scripts_eval/RUNBOOK.md).

- **`docs/eval-rounds/`** — write-ups from completed evaluation rounds
  (round 01, smoke 02, round 02 so far). These are the empirical record
  behind the directives in [`CLAUDE.md`](./CLAUDE.md) — including the
  round-2 finding that subagents build their plans from the prompt body
  *before* consulting the skills catalog, which is why the dispatching
  table lives in the parent agent's instructions rather than in skill
  descriptions.
