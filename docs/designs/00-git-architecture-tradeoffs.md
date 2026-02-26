# Git Architecture Trade-offs

## Context
After resetting `launchplugai/marvin` we are rebuilding the agent stack from scratch. The previous documentation implied a sprawling multi-service layout with partially duplicated skills. That no longer matches reality: Marvin is now a focused lobby/dispatcher plus agent team, so we need a clean Git architecture statement to prevent the doc drift that just burned us.

## Goals
- **Simplicity:** keep everything required to bootstrap Marvin in one repository.
- **Deterministic automation:** CI, tests, and deployment should run from predictable paths.
- **Agent team velocity:** new agents should slot in without creating more repos unless there is a compelling isolation reason.
- **Cost + compliance:** maintain clear ownership of secrets, audit logs, and routing configs so the lobby’s cost guard can be reasoned about directly from Git.

## Options Considered
### Option A – Split repos per agent/skill
- **Pros:** isolated blast radius, easier per-agent cadence, smaller deploy artifacts.
- **Cons:** configuration drift, duplicated tooling, hard to share keyword/circuit-breaker code, painful to coordinate lobby changes that affect everyone.

### Option B – Monorepo with service folders (Current)
- **Pros:** single config + dependency surface, one CI pipeline, atomic commits that touch both lobby and agent scaffolding, easier to enforce shared tests (keyword registry, routing contract, etc.).
- **Cons:** requires discipline on ownership boundaries; repo can grow quickly if agents bring heavy dependencies.

### Option C – Monorepo + Git submodules for heavyweight agents
- **Pros:** partial isolation for experimental agents; can pin versions.
- **Cons:** operational complexity, submodules regularly fall out of sync, tooling friction outweighs benefits right now.

## Decision
We standardize on **Option B: single repo, service folders**, with the lobby/dispatcher as the root contract. Additional agents live under `agents/<name>/` (to be added) but leverage shared tooling (config, health, observability). Any proposal to break out a new repo requires an ADR documenting why Option A/C suddenly beats the baseline.

## Implementation Notes
- `config/` is the single source of truth for routing, breakers, keyword registry, and spend caps.
- `src/lobby/` houses reusable primitives; new agents must not fork these locally.
- Additions must include regression tests (especially for routing decisions) before we open the floodgates to more agents.
- If an agent requires custom infra (GPU, private data), isolate secrets in deployment tooling, not by cloning this repo.

## Status
`02/26/2026`: Updated to match the post-reset architecture (lobby-first, Ollama buffer, OpenAI brain). Previous doc suggesting multi-repo sprawl is obsolete.
