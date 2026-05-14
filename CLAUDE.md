# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Status: seed stub.** This repo has no source, build config, or tests yet — just
> `README.md`, `LICENSE`, `.gitignore`, and this file. The sections below record what is
> *verifiable today* plus the workspace conventions this project is expected to follow.
> Expand this file (commands, architecture) once the first implementation lands.

## What this is

`seer-cli` — **codebase lookup and indexing for agent skills** (per `README.md`). An
AgentCulture project (MIT, © 2026 AgentCulture). It is developed as one project within a
larger multi-project workspace, which may carry its own workspace-level `CLAUDE.md`; that
file is not part of this repository.

## Expected conventions (not yet realized in code)

These are inherited from the workspace, not from anything in this repo — apply them when
scaffolding the project, and update this file with the concrete commands once they exist:

- **Language/tooling:** Python with **uv** for dependency management — the workspace default,
  and `.gitignore` is the standard Python template. Expect `uv venv && uv pip install -e ".[dev]"`
  then `pytest` once `pyproject.toml` exists.
- **Linting (Python):** `flake8`, `pylint`, `bandit -r src/`, `black`, `isort`.
- **Git workflow:** branch out, implement, bump version, open PR, address review, merge.
- **Naming:** the memory graph groups `seer-cli` with sibling AgentCulture CLIs (`appsec`,
  `agtag`, `steward`, `shushu`) that share a common CLI-scaffold shape — a parser, a
  sub-command registration hook, and a `main(argv)` entry point. Treat that as a likely
  template, not a spec; confirm against actual code before relying on it.

## When code exists, document here

- Build / run / test commands, including how to run a single test.
- The indexing pipeline: how codebases are scanned, what the index format is, where it's
  stored, and how "agent skills" consume the lookups.
- CLI surface: sub-commands and their entry points.
