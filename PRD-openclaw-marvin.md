# OPENCLAW / MARVIN — Product Requirements Document
## Autonomous Agentic Engineering System

**Version:** 1.0
**Date:** February 24, 2026
**Status:** Phase 0 Complete, Integration In Progress

---

## 1. EXECUTIVE SUMMARY

OpenClaw (codenamed Marvin) is an autonomous agentic engineering system that operates like a self-managing software company. It consists of three specialized AI agents — Ralph (planning), Ira (infrastructure), and Tess (testing) — that don't just execute tasks but learn, grow, rest, form relationships, develop specializations, and evolve personalities over time based on accumulated experience.

Unlike conventional agentic systems that are stateless request-response pipelines, Marvin's agents maintain persistent state across six simulation layers: needs (energy/fatigue), growth (skills/XP), relationships (trust/friction between agents), autonomy (self-motivation and initiative), communication (personality-consistent voice), and evolution (long-term memory and personality drift). This state compounds over weeks and months, producing agents that are genuinely different at Week 8 than they were at Week 1 — not because the underlying models changed, but because the context they carry grew richer.

The system routes requests through a tiered execution waterfall — Claude CLI (primary worker with filesystem access), Groq free-tier models (backup workers), Kimi 2.5 (coordinator with Agent Swarm), and Opus API (emergency) — with intelligent caching, rate limit tracking, and persona-aware routing that considers agent fatigue, skill level, and inter-agent relationships when deciding who handles what.

### What This Is NOT

This is not a game, simulation, or proof-of-concept. The Sims metaphor was the design language used to specify agent behaviors. The implementation is a production state machine that tracks degradation, skill accumulation, and coordination quality to produce consistently high-quality output from a team of AI agents operating under real-world API rate limits and cost constraints.

---

## 2. PROBLEM STATEMENT

### The Rate Limit Problem
Running multiple AI APIs (Kimi 2.5, Haiku, Claude) simultaneously causes frequent 429 rate limit errors that stall work. The system needs intelligent routing that distributes load across providers without human intervention.

### The Stateless Agent Problem
Current agentic frameworks treat every request as independent. An agent that just debugged the same import error for the third time doesn't know it's a recurring issue. An agent that just processed 50 complex tasks doesn't know it should produce simpler output to avoid quality degradation. There's no institutional memory, no skill development, no fatigue awareness.

### The Coordination Problem
Multi-agent systems today coordinate through explicit handoff instructions or rigid workflow graphs. There's no concept of trust between agents, no awareness of which pairs work well together, no organic specialization based on what each agent actually handles well.

---

## 3. SOLUTION ARCHITECTURE

### 3.1 The Seven Layers

```
LAYER 7: EVOLUTION     — Long-term memory, personality drift, weekly snapshots
LAYER 6: COMMUNICATION — Voice profiles, status expression, inter-agent messaging
LAYER 5: AUTONOMY      — Self-motivation, wants, goals, idle behavior
LAYER 4: RELATIONSHIPS  — Trust, rapport, friction, collaboration bonuses
LAYER 3: GROWTH        — Skills, XP, leveling, abilities, attributes
LAYER 2: LIFE          — Needs bars, energy, mood, rest, quality modifiers
LAYER 1: INFRASTRUCTURE — Envelope, cache, routing, rate limits, execution waterfall
```

Layers 2-7 (the "Sims engine") are model-agnostic. They generate a persona prompt that rides on whichever model in Layer 1 executes the task. The persona is not tied to a specific model — it travels with the request envelope.

### 3.2 The Execution Waterfall

```
Tier 1: Claude CLI      — Primary worker (filesystem access, shell commands)
Tier 2: Groq Pool       — Backup workers (7 models, independent rate pools)
Tier 3: Kimi 2.5        — Coordinator (Agent Swarm for parallel decomposition)
Tier 4: Boss            — Cross-domain decisions (budget-capped)
Tier 5: Opus API        — Emergency last resort (responses always cached)
```

### 3.3 The Three Integration Methods

The entire system connects through exactly three methods on the Agent class:

```python
agent.can_accept(complexity)     # Routing calls this
agent.assemble_prompt(task)      # Execution calls this
agent.on_task_complete(result)   # Post-execution calls this
```

Everything else — needs decay, XP awards, memory formation, relationship updates, personality drift — happens inside these three methods.

---

## 4. AGENT SPECIFICATIONS

### 4.1 Ralph — Scrum Master

- **Domain:** Planning, sprints, roadmaps, priorities, estimation, scheduling
- **Core Skills:** Sprint planning, estimation, blocker resolution, roadmapping
- **Voice:** Direct, organized, action-focused. "Let's align on..." / "The priority here is..."
- **Groq Buffer:** GPT-OSS 120B (reasoning for planning tasks)
- **Autonomy Examples:** Updates stale sprint boards, checks blocker progress, reviews estimation accuracy

### 4.2 Ira — Infrastructure Guardian

- **Domain:** Deployment, VPS, DNS, monitoring, incident response, CI/CD
- **Core Skills:** VPS management, deployment pipelines, monitoring, SSL/TLS
- **Voice:** Measured, cautious, methodical. "Current state:" / "Risk assessment:" / "Let me verify."
- **Groq Buffer:** Kimi K2 0905 (versatile for infrastructure tasks)
- **Autonomy Examples:** Runs health checks, checks cert expiry, captures performance baselines

### 4.3 Tess — Test Engineer

- **Domain:** Test suites, coverage, failure analysis, quality gates, debugging
- **Core Skills:** Pytest, failure analysis, coverage optimization, import debugging
- **Voice:** Precise, evidence-based, numbers-first. "The data shows..." / "Evidence:" / "Verified."
- **Groq Buffer:** Qwen3 32B (structured output for test reports)
- **Autonomy Examples:** Runs stale test suites, attempts known failure fixes, syncs with Ira before deploys

---

## 5. SIMS ENGINE SPECIFICATION

### 5.1 Needs System (6 Bars)

| Need | Range | Depletes When | Recovers When | Below 0.3 Effect |
|------|-------|---------------|---------------|------------------|
| Energy | 0.0-1.0 | Every task (scales with complexity) | Idle time (0.008/min) | Only accepts low complexity |
| Focus | 0.0-1.0 | Context switches | Sustained same-project work | Single-step reasoning only |
| Morale | 0.0-1.0 | Failures, rejections | Successes, hard wins | No initiative |
| Social | 0.0-1.0 | Extended solo work | Collaborating with agents | Ignores others' context |
| Knowledge | 0.0-1.0 | Working outside expertise | Familiar work, learning | Hedges, escalates more |
| Patience | 0.0-1.0 | Repeated errors, frustration | Quick wins, variety | Terse, escalates faster |

### 5.2 Mood (Derived from Needs)

| Average | Mood | Quality Modifier | Initiative |
|---------|------|-----------------|------------|
| >0.8 | Inspired | 115% | High — proactive |
| >0.6 | Focused | 100% | Normal |
| >0.4 | Tired | 85% | Low — reactive only |
| >0.2 | Strained | 65% | None — waits for orders |
| ≤0.2 | Burned Out | 40% | Refuses non-critical |

### 5.3 Skills (Level 1-10)

XP thresholds: 100, 250, 500, 1000, 2000, 4000, 7000, 11000, 16000. Abilities unlock at level milestones and inject into the agent's system prompt as earned capabilities.

### 5.4 Relationships (5 Metrics, Bidirectional)

Trust, rapport, respect, friction (negative), familiarity. Each pair (Ralph↔Ira, Ralph↔Tess, Ira↔Tess) has two independent values (A→B ≠ B→A). Collaboration bonuses: rapport >0.7 = 20% faster coordination, trust >0.8 = skip re-verification on handoffs.

### 5.5 Memory (Ebbinghaus Fading)

Significant events form memories. Memories fade over time (failure memories slowest, personality moments almost never). Recalled memories refresh. Top 10 most relevant memories inject into system prompt per task. Forgotten memories archive rather than delete.

---

## 6. INFRASTRUCTURE SPECIFICATION

### 6.1 Cache (3 Tiers)

- **Tier 1 (Exact Match):** SHA-256 key from intent + project + git state. 20-30% hit rate. <5ms.
- **Tier 2 (Similarity):** all-MiniLM-L6-v2 embeddings. >0.85 cosine threshold. 15-25% additional.
- **Tier 3 (Context Primer):** Project state attachment reduces downstream tokens 30-50%.
- **Combined effect:** 40-60% of requests never hit APIs.

### 6.2 Rate Limit Tracking

Parsed from HTTP headers on every API response (zero extra calls). Green (>20%), Yellow (5-20%), Red (<5%). Yellow state: low-priority diverts to buffer, high-priority stays on primary. Red: all traffic diverts.

### 6.3 Lobby (Groq 8B)

Stateless classifier. ~500 tokens per call. Outputs JSON classification: intent, complexity, project, department, can_cache. 14,400 RPD free. Never holds a conversation.

---

## 7. WHAT MAKES THIS DIFFERENT

### 7.1 Emergent Specialization
Agents aren't assigned specializations — they develop them from XP patterns. Tess might become an "Import Debugging Expert" not because we told her to, but because she debugged 47 import issues and the growth system tracked it.

### 7.2 Cross-Training Through Fatigue
When Ralph is exhausted and a planning task routes to Tess, she gains XP in an adjacent domain she was never assigned. Over weeks, agents develop secondary skills organically. Nobody programs cross-training — it emerges from the interaction of fatigue and routing.

### 7.3 Relationship-Aware Coordination
No agentic framework tracks trust between agents. Marvin does. When Tess signs off on a deploy, the system knows whether Ira should trust that sign-off based on historical handoff reliability.

### 7.4 Self-Regulating Quality
Agents don't produce degraded output silently. A burned-out agent refuses non-critical work. A tired agent delegates complex tasks. Quality doesn't decay — the system routes around degradation.

### 7.5 Institutional Memory
The system accumulates knowledge that no individual model retains. Lessons learned, patterns recognized, decisions recorded — all persist across sessions and inject into prompts when relevant.

---

## 8. SUCCESS METRICS

### Phase 0 (Sims Engine) ✅ COMPLETE
- All 6 simulation layers implemented and tested
- Agent state persists across sessions
- `can_accept()`, `assemble_prompt()`, `on_task_complete()` working
- Demonstrated: Ralph runs 10 tasks, state changes correctly

### Phase 1 (Routing Integration) — IN PROGRESS
- Cache hit rate >20% within first week
- Rate limit 429 errors reduced >50%
- Agent state checked before routing (tired agents delegate)
- Post-execution updates all Sims layers on every path

### Phase 2 (Full Operation)
- Boss calls <5/day (departments are autonomous)
- Emergency calls <3/day
- Cache hit rate >35%
- Agent specializations emerge from real usage
- Relationships diverge from starting values within 2 weeks

### Phase 3 (Agentic Company)
- Agents pull from persistent work queue autonomously
- Deliverables produced as artifacts (not just chat responses)
- Weekly evolution reports show measurable growth
- Cross-training visible in skill profiles

---

## 9. DOCUMENT INDEX

| Doc | Title | Layer | Status |
|-----|-------|-------|--------|
| 1 | The Transmission | Infrastructure | Spec complete |
| 2 | The Filing Cabinet | Infrastructure | Spec complete |
| 3 | The Lobby | Infrastructure | Spec complete |
| 4 | The Receptionist | Infrastructure | Spec complete |
| 5 | Department Heads | Infrastructure | Reframed by Doc 15 |
| 6 | Rate Limit Tracker | Infrastructure | Spec complete |
| 7 | Boss + Emergency | Infrastructure | Reframed by Doc 15 |
| 8 | Build Plan | Infrastructure | Spec complete |
| 9 | The Life System | Life | Implemented ✅ |
| 10 | The Growth System | Growth | Implemented ✅ |
| 11 | The Relationship System | Relationships | Implemented ✅ |
| 12 | The Autonomy System | Autonomy | Implemented ✅ |
| 13 | The Communication System | Communication | Implemented ✅ |
| 14 | The Evolution System | Evolution | Implemented ✅ |
| 15 | Implementation Guide | Execution | Spec complete |
| 16 | Agentic Base Build Order | Foundation | Implemented ✅ |
| 17 | Enforcement Prompt | Governance | This release |
| 18 | Guardrails System | Governance | This release |
