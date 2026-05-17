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

- **`kata-cli` — alt-published PyPI distribution** carrying the same
  wheel content as `antoine-cli`. Installing either exposes the same
  pair of console scripts — `antoine` and `kata`
  (see [`pyproject.toml`](./pyproject.toml)). `kata-cli` is the
  distribution label users `pip install`, not a command they run. The
  dual-publish loop is defined in
  [`.github/workflows/`](./.github/workflows/); see
  [`CHANGELOG.md`](./CHANGELOG.md) entries for v0.7.0 / v0.7.1 for the
  history of how the distribution names were wired up. (A third name,
  `code-lens-cli`, was published from this repo through v0.9.2; from
  v0.10.0 onward it lives in [its own
  repo](https://github.com/agentculture/code-lens-cli) — see "Results
  of this loop" below.)

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

## Results of this loop

antoine ships the *tool*. The first published *catalog of results* from
running its capture/reduce/assess loop is
[`code-lens-cli`](https://github.com/agentculture/code-lens-cli) —
four 1-call verbs (`classify` / `recent` / `grep` / `profile`) that
antoine maintainers identified as recurring N-call patterns and
packaged into a sibling distribution. Install with
`uv tool install code-lens-cli`. Most agents will install both.

The migration history (antoine 0.10.0 → code-lens-cli 0.10.0,
2026-05-17) is the first concrete proof that the loop produces shippable
artifacts. Future cells (2–8) of the loop are designed to make catalogs
like this one routine rather than artisanal.
