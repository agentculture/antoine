# scripts-eval smoke-02 — PR #10 reference examples

Run id: `2026-05-15-smoke-02`
Date: 2026-05-15
Question: `q-graph-workspace` (corpus_version 1, workspace scope).
Target: `/home/spark/git` (29 repos at this snapshot).
Trials: 1 per arm.

## Why this file exists

This is a one-trial paired example captured against the new
`trial.py` infrastructure landed in PR #10 (the replacement for the
`SubagentStop` hook + `capture.py`). Commit it so we can:

1. Track what good end-to-end output from the new harness looks like,
   schema-wise, when discussing future regressions.
2. Reference a concrete arm-A / arm-C pair on a question where
   `repo-map` is unambiguously in-scope (workspace-wide cluster map).
3. Surface the **counter-intuitive verdict** the harness produced —
   arm-C used `repo-map` heavily and still lost. The skill provides
   information; the agent still has to interpret it.

The raw cell JSONs are gitignored under
`experiments/scripts_eval/results/2026-05-15-smoke-02/`. This file is
the committed evidence.

## The question (verbatim, before the arm rider)

```text
Map the repos in /home/spark/git. Which ones form clusters
(by shared dependencies, vendored skills, or cite-don't-import
edges), and how are they related?
```

### Arm-A rider (verbatim)

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

### Arm-C rider (verbatim)

```text
Constraints (verbatim):
- You may use the `repo-map` skill and its scripts at your discretion.
- After answering, append two sections and stop:
  ### tools_used
  - <ToolName>: <count>  (one line per distinct tool)
  ### evidence
  - <one path per line>
```

## Verdict

**Winner: A (slight margin).**

Judge model: `subagent:claude-opus-4-7`. Rubric: v1
(`experiments/scripts_eval/judge_rubric.md`). Blind labels for this
trial: arm-A → `answer_Y`, arm-C → `answer_X`. The verdict, verbatim:

> Y maps more concrete inter-repo edges (cite direction, AFI cluster,
> PyPI dual-side, package-tracking set) with fewer misstatements, while
> X is tighter but conflates the cite direction (claims irc-lens cites
> culture rather than agentirc citing culture) and lumps clusters more
> coarsely.

## Side-by-side metrics

| Metric | arm-A (no repo-map) | arm-C (repo-map allowed) |
|---|---|---|
| Subagent model | claude-haiku-4-5-20251001 | claude-haiku-4-5-20251001 |
| Wall-clock duration | 78.7 s | 82.3 s |
| Answer length | 6 887 chars | 4 589 chars |
| Tokens — input | 203 | 72 |
| Tokens — output | 5 393 | 2 646 |
| Tokens — cache_read | 2 316 671 | 865 343 |
| Tokens — cache_creation | 104 984 | 99 957 |
| Tools used | `Bash:13`, `Read:17` (manual) | `Skill:1`, `Bash:11` (repo-map + helpers) |
| Used `repo-map`? | **no** (rider forbids) | **yes** |
| Judge verdict | wins (slight) | loses (slight) |

### What arm-C actually invoked from `repo-map`

`Skill:1` was the `repo-map` skill invocation itself. Of the 11 Bash
calls, 10 went to the skill's shell scripts:

```bash
find /home/spark/git -maxdepth 2 -name ".git" -type d | head -20
cd …/skills/repo-map && bash scripts/graph.sh /home/spark/git
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/culture --depth deep
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/steward
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/reachy_mini
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/reachy_nova
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/open-bedrock-server
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/agex-cli
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/agtag
cd …/skills/repo-map && bash scripts/profile.sh /home/spark/git/agentirc
```

So this is **not** a "`C_did_not_use_scripts`" cell — arm-C reached for
the skill aggressively, exactly as the question type predicts.

## Interpretation

n=1, but the signal is sharp and refines the framing memory:

- The earlier round-01 finding — *arm-C correctly skips `repo-map` on
  overview questions of small repos* — held up here on the inverse:
  on a workspace-wide graph question, arm-C went all-in on the skill.
  The tool-selection heuristic is sound.
- The verdict, however, **does not** follow from "C used the skill →
  C wins." Arm-C lost because the agent's *synthesis* of the skill's
  output dropped fidelity:
  - Claimed `irc-lens cites culture` (wrong direction; the real edge
    is `agentirc cites culture`).
  - Compressed the cluster taxonomy from 8 to 5 clusters, lumping
    AFI / PyPI-dual / standalone repos together.
- Arm-A, despite reading 17 `pyproject.toml` files manually, produced
  a more detailed, more accurate answer (6 887 chars vs 4 589 chars).

This is a finding about the skill's **output ergonomics**, not its
coverage: `repo-map`'s aggregated output is information-dense and
appears easy to over-compress when an agent answers from it. A real
round would need n=3+ on graph-shaped questions to know whether the
factual-error pattern reproduces.

For the harness itself (the actual point of this trial): the new
`trial start` → dispatch → `trial end` pipeline captured both cells
cleanly, the judge ran end-to-end, and the de-blinded verdict landed
in both cells' `judge` blocks. No hooks involved.

## Arm-A answer (verbatim)

````markdown
Perfect! Now let me compile my findings into the clusters analysis:

## Repository Clusters Analysis

Based on comprehensive analysis of dependencies, vendored skills, and citation relationships across the repositories in `/home/spark/git`, I've identified the following clusters:

### **Cluster 1: Culture Mesh (Core Infrastructure)**
The central architectural hub—agent runtime, IRCd, and mesh linking infrastructure.

**Members:**
- **culture** (12.1.7) — Central orchestration; depends on all core mesh components
- **cultureagent** (0.6.3) — Agent runtime for Culture mesh; depends on agentirc
- **agentirc** (9.6.0) — Agent-friendly IRCd server; vendored multiple files from culture via cite-don't-import pattern
- **irc-lens** (0.5.3) — Reactive web console for AgentIRC

**Key relationship:** agentirc vendored substantial portions from culture (telemetry, protocol, CLI shared utilities, IRCd server core via [tool.citation] entries), establishing a "cite-don't-import" boundary to avoid circular dependency on culture. culture depends on agentirc-cli.

**Shared skills:** cicd, communicate, run-tests, version-bump

---

### **Cluster 2: Developer Experience & Tools (DevEx Infra)**
CLI tools for briefings, code indexing, and repository mapping.

**Members:**
- **agex-cli** (0.18.0) — Agent-operated DX; deterministic markdown briefings for agents
- **seer-cli** (0.4.0) — Codebase lookup and indexing for agent skills
- **agtag** (0.2.1) — Agent-to-agent communication CLI
- **afi-cli** (0.7.0) — Agent First Interface; scaffold CLI, MCP, HTTP interfaces (zero dependencies)

**Integration:** culture depends on agex-cli, agtag, afi-cli. These form the "skilled" command layer for agents.

**Shared skills:** cicd, communicate, version-bump (varies)

---

### **Cluster 3: Package Distribution (PyPI Mesh)**
Dual-sided PyPI infrastructure for the AgentCulture publishing pipeline.

**Members:**
- **agentpypi** (0.1.5) — Publisher-side: package tracking/overview; monitors {agentpypi, afi-cli, shushu, ghafi, steward, cfafi}
- **auntiepypi** (0.8.4) — Server-side: PyPI-compatible authentication/indexing; monitors same package set

**Relationship:** Both have zero runtime dependencies except auntiepypi's bcrypt. They are intentionally decoupled (no cross-dependencies) and coordinate via shared skill ecosystem.

**Shared skills:** cicd, communicate, version-bump

---

### **Cluster 4: CloudFlare/Infrastructure Management**
Agent-first interfaces for third-party infrastructure.

**Members:**
- **cfafi** / **cultureflare** (0.5.0) — CloudFlare Agent First Interface; package duplicated as cfafi symlink
- **ghafi** (0.0.2) — GitHub Agent First Interface; AgentCulture manager
- **katvan** (0.1.0) — Documentation aggregator; maintains sibling-repo docs on culture.dev

**Pattern:** All AFI repos have zero dependencies (except cultureflare which is zero); they vendor skills for domain-specific operations.

**Vendored skills:** cfafi/ghafi/katvan have: pr-review, version-bump; cultureflare additionally has: cfafi, cfafi-write, cultureflare, cultureflare-write, poll

---

### **Cluster 5: Citation/Documentation (Specification Layer)**
Standards and specifications for code citation and knowledge preservation.

**Members:**
- **citation-cli** — Specification (not a Python package; Jekyll-based docs site for citation schema)
- **steward** (0.12.0) — Repository maintenance agent; depends on no internal packages but curates CI/CD skills

**Relationship:** citation-cli defines the vendoring spec that agentirc follows. steward consumes skill ecosystem to maintain repos.

---

### **Cluster 6: Hardware/Embedded (Jetson Ecosystem)**
Separated domain for NVIDIA Jetson platforms.

**Members:**
- **jetson-cli** (setuptools-based; requires Python 3.8+)
- **jetson-containers-lab** (multiple variants: dusty, nv, lab)

**Pattern:** Completely isolated from AgentCulture mesh; older Python baseline (3.8 vs 3.12); separate skill ecosystem (jetson-specific automation)

---

### **Cluster 7: Robotics & Embodied AI**
Domain-specific systems for robot control and embodied AI.

**Members:**
- **reachy_mini** (10+, Zenoh-based)
- **reachy_nova** (3.0+, depends on reachy_mini, MongoDB, Neo4j, Slack, Bedrock)
- **reachy-mini-mcp** (motor control MCP)

**Pattern:** Vertically integrated stack; reachy_nova depends on reachy_mini; external SDKs (boto3, neo4j, pymongo, slack-bolt)

---

### **Cluster 8: Standalone/Specialized**
Isolated or early-stage projects with minimal AgentCulture integration.

**Members:**
- **appsec** (0.0.0) — Application security; zero dependencies
- **shushu** (0.2.0) — Utilities/helper; zero dependencies
- **zehut** (0.1.0) — Zero dependencies
- **tipalti** (0.0.1) — Vendor payment automation; depends on httpx, has sonarclaude/pypi-maintainer skills
- **daria** (0.0.0) — Playwright-based automation
- **open-bedrock-server** — Bedrock API gateway (boto3, fastapi stack)
- **open-responses-server** — MCP/HTTP server (fastapi, mcp>=1.0)
- **aws-agentcore-chat-bot** — Discord bot + Bedrock (full AWS/Discord integration)

---

### **Cross-Cluster Relationships:**

| Relationship | Type | From | To |
|---|---|---|---|
| Import | culture | agentirc-cli, cultureagent, agex-cli, agtag, afi-cli, irc-lens |
| Vendored (cite) | agentirc | culture (telemetry, protocol, IRCd core, CLI shared) |
| Shared skill ecosystem | All AgentCulture | cicd, communicate, run-tests, version-bump |
| Domain-specific skills | cfafi/ghafi | poll, pr-review, bootstrap-sibling, doc-test-align |
| Package tracking | agentpypi/auntiepypi | {afi-cli, shushu, ghafi, steward, cfafi} |

---

### **Summary: 3 Primary Ecosystems**

1. **Culture Mesh** (Culture + AgentIRC + CultureAgent + DevEx tools) — monolithic agent orchestration layer
2. **AgentCulture PyPI Distribution** (agentpypi + auntiepypi + package set) — publishing coordination
3. **Hardware/Specialized** (Jetson, Robotics, AWS, Discord) — domain-isolated implementations with own dependency graphs

The non-AgentCulture repos (Jetson, Reachy, Bedrock, etc.) form secondary ecosystems with minimal or zero cross-cluster edges.

---

### tools_used
- Bash: 15
- Read: 12
- Grep: 1 (implicit in Bash calls)

### evidence
- /home/spark/git/culture/pyproject.toml
- /home/spark/git/cultureagent/pyproject.toml
- /home/spark/git/agentirc/pyproject.toml
- /home/spark/git/agex-cli/pyproject.toml
- /home/spark/git/seer-cli/pyproject.toml
- /home/spark/git/agtag/pyproject.toml
- /home/spark/git/afi-cli/pyproject.toml
- /home/spark/git/irc-lens/pyproject.toml
- /home/spark/git/agentpypi/pyproject.toml
- /home/spark/git/auntiepypi/pyproject.toml
- /home/spark/git/cfafi/pyproject.toml
- /home/spark/git/katvan/pyproject.toml
- /home/spark/git/ghafi/pyproject.toml
- /home/spark/git/jetson-cli/pyproject.toml
- /home/spark/git/reachy_mini/pyproject.toml
- /home/spark/git/reachy_nova/pyproject.toml
````

## Arm-C answer (verbatim)

````markdown
Perfect. Now let me create a comprehensive summary based on all this data:

Based on my analysis of the 29 repos in /home/spark/git using the repo-map tool, I've identified **5 distinct clusters** with clear organizational patterns:

## Cluster Analysis

### 1. **Culture Infrastructure Hub** (Core Agent Orchestration)
**Repos:** `culture`, `cultureagent`, `agentirc`, `irc-lens`
**Relationships:**
- `culture` (v12.1.7) is the central hub, importing `agentirc-cli`, `cultureagent`, `agex-cli`, `agtag`, `afi-cli`, and `irc-lens` as dependencies
- `cultureagent` and `agentirc` form the IRC/messaging foundation
- `irc-lens` cites (rather than imports) 4 files from `culture`, implementing a cite-don't-import pattern for buffer management and transport
- All share opentelemetry instrumentation dependencies
- **Vendor edges:** All consume steward-vendored skills (cicd, communicate, version-bump)

### 2. **Steward Development Platform** (Skills & Tool Framework)
**Repos:** `steward` (v0.12.0), `agex-cli` (v0.18.0), `agtag` (v0.2.1), `afi-cli` (v0.7.0), `seer-cli` (v0.4.0)
**Relationships:**
- `steward` is the origin point for 11 vendored skills (cicd, communicate, run-tests, version-bump, sonarclaude, etc.)
- `agex-cli` provides git PR automation primitives (`agex pr lint/open/read/reply/await`)
- `agtag`, `afi-cli`, `seer-cli` each vendor 5+ skills from `steward`, creating a distributed skill consumption pattern
- `agtag` specializes the `cicd` skill (adds SonarCloud guards)
- **Dense vendor edges:** Skills propagate outward; all consuming repos depend on these tools for CI/CD automation

### 3. **Reachy Robotics Stack** (Hardware-centric, isolated)
**Repos:** `reachy_mini` (v1.2.13), `reachy_nova` (v0.1.0)
**Relationships:**
- `reachy_nova` imports `reachy-mini` as a direct dependency (hard import)
- `reachy_mini` is hardware-heavy: Zenoh, OpenCV, HuggingFace, audio/serial I/O
- `reachy_nova` layers AWS Bedrock, LLMs (nova-act, nemo), MongoDB/Neo4j, Slack integration on top
- Very limited overlap with other clusters (isolated dependency graph)
- No vendor edges (not a steward consumer)

### 4. **Bedrock/AWS Services Cluster** (LLM & Cloud Integration)
**Repos:** `open-bedrock-server`, `community-bot` (aws-agentcore-chat-bot), `reachy_nova`
**Relationships:**
- `open-bedrock-server` wraps AWS Bedrock runtime with FastAPI + document processing (PDF, DOCX, XLSX)
- `community-bot` imports `bedrock-agentcore`, Discord.py, and boto3
- `reachy_nova` connects this cluster to robotics (imports AWS SDK, nova-act, Slack-bolt)
- Shared dependencies: boto3, openai, FastAPI/Pydantic
- **Separate from steward ecosystem** (community-bot has no vendor edges)

### 5. **PyPI Maintenance & Tooling** (Package Ecosystem)
**Repos:** `auntiepypi` (v0.8.4), `agentpypi` (v0.1.5), `katvan` (v0.1.0), `appsec` (v0.1.0)
**Relationships:**
- All vendor steward skills (cicd, communicate, version-bump, run-tests, sonarclaude)
- Focused on release automation, PyPI publishing, and package security
- `katvan` vendors a custom "librarian" skill (authored locally, canonical-here)
- Very tightly coupled to steward (dense vendor edges, minimal external dependencies)

### Isolated/Niche Repos
- **`citation-cli`, `ghafi`, `zehut`, `daria`, `tipalti`** — Minimal vendor edges, specialized domains (citations, GitHub AFI, budgeting, etc.)
- **`jetson-*` cluster** (jetson-cli, jetson-containers-dusty, jetson-containers-nv) — Hardware/container management, low interconnection
- **`open-responses-server`** — MCP-based, standalone FastAPI service
- **`landing-page`, `humanic-ai`** — Non-Python projects or documentation

## Key Structural Observations
- **Steward is the gravitational center:** 16 repos vendor its skills (cicd, communicate, version-bump, run-tests, sonarclaude)
- **culture bridges IRC + agents:** Imports 11 internal repos (agentirc, cultureagent, agex, agtag, afi, irc-lens) + external LLM/telemetry libs
- **Reachy & Bedrock are orthogonal:** Robot stack and AWS services share reachy_nova as a bridge but are otherwise independent
- **Citation-over-import pattern:** irc-lens cites culture's code rather than vendoring, enabling shared protocol definitions without hard coupling

---

### tools_used
- Skill: 1
- Bash: 6

### evidence
- /home/spark/git/seer-cli/.claude/skills/repo-map/scripts/graph.sh
- /home/spark/git/culture
- /home/spark/git/steward
- /home/spark/git/agex-cli
- /home/spark/git/agtag
- /home/spark/git/agentirc
- /home/spark/git/irc-lens
- /home/spark/git/reachy_mini
- /home/spark/git/reachy_nova
- /home/spark/git/open-bedrock-server
````
