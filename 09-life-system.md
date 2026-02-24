# Document 9 of 14: THE LIFE SYSTEM
## Needs Bars, Energy, Moods, Decay Cycles

**Purpose:** Agents are not infinite. They degrade with use, recover with rest, and produce different quality work depending on their state. This isn't flavor — it's a quality control mechanism. A tired agent that knows it's tired will hand off work instead of producing garbage.

---

## THE PRINCIPLE

In The Sims, a Sim with zero energy falls asleep on the floor. They don't keep trying to cook dinner badly — they stop.

In our system, an agent with depleted energy doesn't keep processing requests at degraded quality. It signals its state, hands off to a rested agent or buffer, and enters recovery. The result: consistent output quality, not a slow decay into hallucination.

**This is not roleplay. This is operational state management with a human-readable interface.**

---

## NEEDS BARS

Every agent maintains six needs. Each is a float from 0.0 (critical) to 1.0 (full).

```python
@dataclass
class AgentNeeds:
    energy: float = 1.0       # Depletes with every task. Core work capacity.
    focus: float = 1.0        # Depletes with context switches. Deep work quality.
    morale: float = 1.0       # Depletes on failures, rejections. Affects initiative.
    social: float = 1.0       # Depletes in isolation. Affects collaboration quality.
    knowledge: float = 1.0    # Depletes when working outside expertise. Confidence.
    patience: float = 1.0     # Depletes on repeated failures, user frustration. Composure.

    def clamp(self):
        """Keep all values in [0.0, 1.0]"""
        for field in ['energy', 'focus', 'morale', 'social', 'knowledge', 'patience']:
            setattr(self, field, max(0.0, min(1.0, getattr(self, field))))
```

### What Each Need Controls (Mechanically)

| Need | Depletes When | Recovers When | Below 0.3 Effect |
|------|--------------|---------------|------------------|
| **Energy** | Every task (scales with token count) | Rest period (no tasks for N min) | Only accepts low complexity |
| **Focus** | Context switches (project/domain change) | Sustained same-project work | Single-step reasoning only |
| **Morale** | Failures, rejections, repeated escalations | Successes, solving hard problems | No initiative, waits for orders |
| **Social** | Extended solo work | Collaborating with other agents | Ignores other agents' context |
| **Knowledge** | Unfamiliar problems outside skill profile | Familiar work, learning from resolutions | Hedges everything, escalates more |
| **Patience** | Repeated errors, user frustration, long debugging | Quick wins, variety, rest | Terse responses, escalates faster |

---

## DECAY FORMULAS

```python
class NeedDecay:
    """How much each need depletes per event. Subtracted from 0.0-1.0 bar."""
    
    # Energy: per task, scaled by complexity
    ENERGY_PER_TASK = {
        "low": 0.02,
        "medium": 0.05,
        "high": 0.10,
        "critical": 0.15
    }
    
    # Focus: context switching cost
    FOCUS_CONTEXT_SWITCH = 0.08     # Different project
    FOCUS_DOMAIN_SWITCH = 0.05      # Same project, different domain
    FOCUS_SAME_CONTEXT = 0.01       # Continuing same work
    
    # Morale: outcome-based
    MORALE_TASK_FAILURE = 0.10
    MORALE_ESCALATION = 0.05
    MORALE_USER_NEGATIVE = 0.08
    MORALE_TASK_SUCCESS = -0.03     # Negative = RECOVERY
    MORALE_HARD_WIN = -0.08         # Big recovery on hard solves
    
    # Social: isolation cost
    SOCIAL_SOLO_TASK = 0.03
    SOCIAL_COLLAB = -0.05           # Recovery via collaboration
    SOCIAL_REPORT_TO_BOSS = -0.02
    
    # Knowledge: expertise boundary
    KNOWLEDGE_IN_DOMAIN = 0.01
    KNOWLEDGE_ADJACENT = 0.04
    KNOWLEDGE_OUT_OF_DOMAIN = 0.10
    KNOWLEDGE_LEARNED = -0.05       # Recovery from successful novel solve
    
    # Patience: frustration triggers
    PATIENCE_REPEAT_ERROR = 0.08
    PATIENCE_USER_UNCLEAR = 0.05
    PATIENCE_LONG_DEBUG = 0.03      # Per debug cycle
    PATIENCE_QUICK_WIN = -0.04


def apply_task_decay(agent, task_result: dict):
    """Update agent needs after completing a task"""
    complexity = task_result["complexity"]
    success = task_result["success"]
    project = task_result["project"]
    domain = task_result["domain"]
    
    # Energy
    agent.needs.energy -= NeedDecay.ENERGY_PER_TASK.get(complexity, 0.05)
    
    # Focus
    if project != agent.last_project:
        agent.needs.focus -= NeedDecay.FOCUS_CONTEXT_SWITCH
    elif domain != agent.last_domain:
        agent.needs.focus -= NeedDecay.FOCUS_DOMAIN_SWITCH
    else:
        agent.needs.focus -= NeedDecay.FOCUS_SAME_CONTEXT
    
    # Morale
    if success:
        agent.needs.morale -= NeedDecay.MORALE_TASK_SUCCESS
        if complexity in ("high", "critical"):
            agent.needs.morale -= NeedDecay.MORALE_HARD_WIN
    else:
        agent.needs.morale -= NeedDecay.MORALE_TASK_FAILURE
    
    # Knowledge
    if domain in agent.skills.core_domains:
        agent.needs.knowledge -= NeedDecay.KNOWLEDGE_IN_DOMAIN
    elif domain in agent.skills.adjacent_domains:
        agent.needs.knowledge -= NeedDecay.KNOWLEDGE_ADJACENT
    else:
        agent.needs.knowledge -= NeedDecay.KNOWLEDGE_OUT_OF_DOMAIN
    
    agent.needs.clamp()
    agent.last_project = project
    agent.last_domain = domain
    agent.tasks_since_rest += 1
```

---

## PASSIVE RECOVERY (Time-Based)

When an agent isn't working, needs regenerate over time.

```python
class PassiveRecovery:
    """Per-minute recovery rates when agent is idle"""
    ENERGY_PER_MINUTE = 0.008       # 0→1 in ~2 hours
    FOCUS_PER_MINUTE = 0.012        # Faster than energy
    MORALE_PER_MINUTE = 0.004       # Slow — morale is sticky
    SOCIAL_PER_MINUTE = 0.002       # Very slow — needs real interaction
    KNOWLEDGE_PER_MINUTE = 0.001    # Almost none — needs learning events
    PATIENCE_PER_MINUTE = 0.010     # Recovers well with distance

def apply_passive_recovery(agent, idle_minutes: float):
    """Called when agent hasn't had a task for N minutes"""
    agent.needs.energy = min(1.0, agent.needs.energy + PassiveRecovery.ENERGY_PER_MINUTE * idle_minutes)
    agent.needs.focus = min(1.0, agent.needs.focus + PassiveRecovery.FOCUS_PER_MINUTE * idle_minutes)
    agent.needs.morale = min(1.0, agent.needs.morale + PassiveRecovery.MORALE_PER_MINUTE * idle_minutes)
    agent.needs.social = min(1.0, agent.needs.social + PassiveRecovery.SOCIAL_PER_MINUTE * idle_minutes)
    agent.needs.knowledge = min(1.0, agent.needs.knowledge + PassiveRecovery.KNOWLEDGE_PER_MINUTE * idle_minutes)
    agent.needs.patience = min(1.0, agent.needs.patience + PassiveRecovery.PATIENCE_PER_MINUTE * idle_minutes)
```

---

## MOOD — Derived From Needs

Mood isn't stored — it's calculated from needs combination.

```python
def calculate_mood(needs: AgentNeeds) -> dict:
    avg = (needs.energy + needs.focus + needs.morale + needs.patience) / 4
    
    if avg > 0.8:
        return {"mood": "inspired", "quality_modifier": 1.15, "initiative": "high",
                "emoji": "🔥", "description": "Firing on all cylinders"}
    elif avg > 0.6:
        return {"mood": "focused", "quality_modifier": 1.0, "initiative": "normal",
                "emoji": "✅", "description": "Steady and productive"}
    elif avg > 0.4:
        return {"mood": "tired", "quality_modifier": 0.85, "initiative": "low",
                "emoji": "😤", "description": "Getting worn down, still functional"}
    elif avg > 0.2:
        return {"mood": "strained", "quality_modifier": 0.65, "initiative": "none",
                "emoji": "⚠️", "description": "Running on fumes — consider rest"}
    else:
        return {"mood": "burned_out", "quality_modifier": 0.4, "initiative": "refusing",
                "emoji": "💤", "description": "Needs rest — only handling emergencies"}
```

### Mood → Routing Impact

```python
def mood_affects_routing(agent, task_complexity: str) -> str:
    """Returns: 'accept' | 'delegate' | 'rest'"""
    mood = calculate_mood(agent.needs)
    
    if mood["mood"] == "burned_out":
        return "accept" if task_complexity == "critical" else "rest"
    if mood["mood"] == "strained":
        return "delegate" if task_complexity in ("high", "critical") else "accept"
    if mood["mood"] == "tired":
        return "delegate" if task_complexity == "high" else "accept"
    return "accept"  # focused or inspired: take everything
```

---

## REST MODE

```python
class RestMode:
    MIN_REST_MINUTES = 15
    FULL_REST_MINUTES = 60
    ENERGY_THRESHOLD_REST = 0.2    # Auto-rest below this
    ENERGY_THRESHOLD_WAKE = 0.5    # Wake when energy hits this

def enter_rest_mode(agent):
    agent.resting = True
    agent.rest_started_at = now()
    agent.min_wake_at = now() + timedelta(minutes=RestMode.MIN_REST_MINUTES)
    log_event("agent_rest", {"agent": agent.agent_id, "energy": agent.needs.energy})

def check_wake(agent) -> bool:
    if not agent.resting:
        return True
    if now() < agent.min_wake_at:
        return False
    if agent.needs.energy >= RestMode.ENERGY_THRESHOLD_WAKE:
        agent.resting = False
        agent.last_rest_at = now()
        return True
    return False
```

---

## INTEGRATION WITH ROUTING

The receptionist checks agent state AFTER basic routing:

```python
def route_with_agent_state(envelope: dict) -> dict:
    department = envelope["routing"]["department"]
    agent = get_agent(department)
    complexity = envelope["classification"]["complexity"]
    
    # Apply passive recovery since last task
    if agent.last_task_at:
        idle = (now() - agent.last_task_at).total_seconds() / 60
        apply_passive_recovery(agent, idle)
    
    decision = mood_affects_routing(agent, complexity)
    
    if decision == "accept":
        return envelope
    elif decision == "delegate":
        alt = find_rested_agent(complexity, exclude=[department])
        target = alt.agent_id if alt else DEPARTMENT_BUFFERS[department]
        envelope["routing"]["destination"] = target
        envelope["routing"]["reason"] += f" | {department} delegated ({agent.mood})"
    elif decision == "rest":
        envelope["routing"]["destination"] = DEPARTMENT_BUFFERS[department]
        envelope["routing"]["reason"] += f" | {department} resting (burned out)"
        enter_rest_mode(agent)
    
    return envelope
```

---

## STATUS DISPLAY

```python
def agent_status_report(agent) -> str:
    mood = calculate_mood(agent.needs)
    bar = lambda v: '█' * int(v * 10) + '░' * (10 - int(v * 10))
    
    lines = [
        f"**{agent.display_name}** ({agent.role}) {mood['emoji']}",
        f"Mood: {mood['mood']} — {mood['description']}",
        f"Energy:    {bar(agent.needs.energy)} {agent.needs.energy:.0%}",
        f"Focus:     {bar(agent.needs.focus)} {agent.needs.focus:.0%}",
        f"Morale:    {bar(agent.needs.morale)} {agent.needs.morale:.0%}",
        f"Patience:  {bar(agent.needs.patience)} {agent.needs.patience:.0%}",
        f"Tasks today: {agent.tasks_completed_today} | Since rest: {agent.tasks_since_rest}",
    ]
    if agent.resting:
        lines.append(f"💤 RESTING — back ~{agent.min_wake_at.strftime('%H:%M')}")
    return "\n".join(lines)
```

---

## STATE STORAGE

```sql
CREATE TABLE agent_state (
    agent_id TEXT PRIMARY KEY,
    energy REAL DEFAULT 1.0,
    focus REAL DEFAULT 1.0,
    morale REAL DEFAULT 1.0,
    social REAL DEFAULT 1.0,
    knowledge REAL DEFAULT 1.0,
    patience REAL DEFAULT 1.0,
    mood TEXT DEFAULT 'focused',
    quality_modifier REAL DEFAULT 1.0,
    resting INTEGER DEFAULT 0,
    rest_started_at TEXT,
    min_wake_at TEXT,
    tasks_completed_today INTEGER DEFAULT 0,
    tasks_since_rest INTEGER DEFAULT 0,
    last_task_at TEXT,
    last_rest_at TEXT,
    last_project TEXT,
    last_domain TEXT,
    updated_at TEXT
);

CREATE TABLE agent_needs_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    energy REAL, focus REAL, morale REAL,
    social REAL, knowledge REAL, patience REAL,
    mood TEXT,
    event TEXT
);
```

---

## TESTING CHECKLIST

- [ ] Agent starts at all needs = 1.0
- [ ] Low task: energy drops ~0.02, high task: ~0.10
- [ ] Context switch: focus drops 0.08, same context: 0.01
- [ ] Failure: morale drops 0.10, success: recovers 0.03
- [ ] Idle 30 min: energy recovers ~0.24
- [ ] Mood: avg >0.8 = inspired, <0.2 = burned_out
- [ ] Burned out: refuses non-critical, accepts critical
- [ ] Tired: delegates high-complexity
- [ ] Rest mode: 15 min minimum, wakes at energy 0.5
- [ ] Routing integration: tired agent → buffer absorbs
- [ ] Status report: readable bars, accurate mood
- [ ] State persists in SQLite across sessions
