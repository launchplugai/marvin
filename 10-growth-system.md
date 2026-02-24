# Document 10 of 14: THE GROWTH SYSTEM
## Skills, Experience, Specialization, Attribute Development

**Purpose:** Agents don't stay static. Ralph gets better at estimation after 50 sprints. Tess becomes an expert in PYTHONPATH issues after debugging them 10 times. Ira learns the VPS quirks. Growth makes the system smarter over time without changing the underlying models — it changes what the models know about themselves.

---

## THE PRINCIPLE

The Sims has skill bars: cooking, charisma, logic, etc. You start at zero. Every time you practice, the bar fills. At certain thresholds, new abilities unlock.

Our agents work the same way. But instead of "cooking level 3 unlocks lobster thermidor," it's "estimation accuracy level 3 unlocks confident sprint commitments without padding."

**Growth is tracked, not hallucinated.** The model doesn't "become smarter" — but its system prompt gets richer, its context gets more relevant, and its routing gets more precise.

---

## SKILL PROFILE

Every agent has a skill profile: core domains they own, adjacent domains they can handle, and skills within those domains that level up.

```python
@dataclass
class Skill:
    name: str
    domain: str
    level: int = 1                 # 1-10
    xp: int = 0                    # Experience points toward next level
    xp_to_next: int = 100          # XP needed for next level
    times_used: int = 0
    times_succeeded: int = 0
    times_failed: int = 0
    last_used: str = None
    unlocked_abilities: list = None # Populated at level thresholds
    
    @property
    def success_rate(self) -> float:
        if self.times_used == 0:
            return 0.0
        return self.times_succeeded / self.times_used


@dataclass
class SkillProfile:
    core_domains: list              # Domains this agent owns
    adjacent_domains: list          # Can handle, not primary
    skills: dict                    # skill_name → Skill object
    total_xp: int = 0
    agent_level: int = 1            # Overall agent level (derived)
    specialization: str = None      # Emerges from highest skill cluster
    title: str = ""                 # Changes with level + specialization
```

---

## AGENT SKILL PROFILES (Starting State)

### Ralph — Scrum Master

```python
ralph_skills = SkillProfile(
    core_domains=["planning", "estimation", "prioritization"],
    adjacent_domains=["architecture", "communication", "risk_assessment"],
    skills={
        "sprint_planning": Skill("Sprint Planning", "planning", level=3, xp=250),
        "estimation": Skill("Estimation", "planning", level=2, xp=120),
        "blocker_resolution": Skill("Blocker Resolution", "prioritization", level=2, xp=80),
        "stakeholder_comm": Skill("Stakeholder Communication", "communication", level=2, xp=90),
        "risk_assessment": Skill("Risk Assessment", "risk_assessment", level=1, xp=30),
        "roadmapping": Skill("Roadmapping", "planning", level=2, xp=100),
        "team_coordination": Skill("Team Coordination", "communication", level=2, xp=110),
        "scope_management": Skill("Scope Management", "prioritization", level=1, xp=40),
    },
    specialization="Sprint Orchestration",
    title="Scrum Master"
)
```

### Ira — Infrastructure Guardian

```python
ira_skills = SkillProfile(
    core_domains=["deployment", "monitoring", "infrastructure"],
    adjacent_domains=["security", "networking", "performance"],
    skills={
        "vps_management": Skill("VPS Management", "infrastructure", level=3, xp=220),
        "deployment_pipelines": Skill("Deployment Pipelines", "deployment", level=2, xp=150),
        "dns_config": Skill("DNS Configuration", "networking", level=2, xp=80),
        "monitoring": Skill("Monitoring & Alerting", "monitoring", level=2, xp=100),
        "incident_response": Skill("Incident Response", "infrastructure", level=2, xp=90),
        "ssl_tls": Skill("SSL/TLS", "security", level=1, xp=40),
        "performance_tuning": Skill("Performance Tuning", "performance", level=1, xp=30),
        "ci_cd": Skill("CI/CD Pipelines", "deployment", level=2, xp=110),
    },
    specialization="Infrastructure Reliability",
    title="Infrastructure Guardian"
)
```

### Tess — Test Engineer

```python
tess_skills = SkillProfile(
    core_domains=["testing", "debugging", "quality"],
    adjacent_domains=["code_review", "documentation", "automation"],
    skills={
        "pytest": Skill("Pytest Mastery", "testing", level=3, xp=280),
        "failure_analysis": Skill("Failure Analysis", "debugging", level=3, xp=240),
        "coverage_optimization": Skill("Coverage Optimization", "quality", level=2, xp=100),
        "import_debugging": Skill("Import/Path Debugging", "debugging", level=2, xp=150),
        "test_architecture": Skill("Test Architecture", "testing", level=2, xp=90),
        "regression_detection": Skill("Regression Detection", "quality", level=1, xp=50),
        "flaky_test_fixing": Skill("Flaky Test Fixing", "debugging", level=1, xp=30),
        "test_data_management": Skill("Test Data Management", "testing", level=1, xp=20),
    },
    specialization="Test Reliability",
    title="Test Engineer"
)
```

---

## XP AND LEVELING

### XP Awards

```python
class XPAward:
    """XP granted per task outcome"""
    
    TASK_COMPLETED = {
        "low": 10,
        "medium": 25,
        "high": 50,
        "critical": 100
    }
    
    TASK_FAILED = {
        "low": 2,       # Still learn from failure, just less
        "medium": 5,
        "high": 10,
        "critical": 15
    }
    
    # Bonus XP
    FIRST_TIME_SOLVE = 20          # Solved a problem type for the first time
    REPEAT_SOLVE = 5               # Solved same pattern again (diminishing returns)
    HELPED_ANOTHER_DEPT = 15       # Cross-department collaboration
    NO_ESCALATION_STREAK = 10      # Per 10 tasks without escalating
    CACHE_WORTHY = 5               # Response was good enough to cache
    USER_POSITIVE = 30             # User gave positive feedback


def award_xp(agent, skill_name: str, task_result: dict):
    """Award XP to a specific skill after task completion"""
    skill = agent.skills.skills.get(skill_name)
    if not skill:
        return
    
    complexity = task_result["complexity"]
    success = task_result["success"]
    
    # Base XP
    if success:
        xp = XPAward.TASK_COMPLETED.get(complexity, 25)
    else:
        xp = XPAward.TASK_FAILED.get(complexity, 5)
    
    # Bonuses
    if success and skill.times_succeeded == 0:
        xp += XPAward.FIRST_TIME_SOLVE
    
    if task_result.get("cached", False):
        xp += XPAward.CACHE_WORTHY
    
    if task_result.get("cross_department", False):
        xp += XPAward.HELPED_ANOTHER_DEPT
    
    # Apply
    skill.xp += xp
    skill.times_used += 1
    if success:
        skill.times_succeeded += 1
    else:
        skill.times_failed += 1
    skill.last_used = iso_now()
    
    # Check level up
    check_level_up(agent, skill)
    
    # Update total
    agent.skills.total_xp += xp
    check_agent_level(agent)
```

### Level Thresholds

```python
LEVEL_THRESHOLDS = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 1000,
    6: 2000,
    7: 4000,
    8: 7000,
    9: 11000,
    10: 16000   # Mastery
}

def check_level_up(agent, skill: Skill):
    """Check if skill has enough XP to level up"""
    next_level = skill.level + 1
    if next_level > 10:
        return  # Max level
    
    threshold = LEVEL_THRESHOLDS.get(next_level, float('inf'))
    
    if skill.xp >= threshold:
        skill.level = next_level
        skill.xp_to_next = LEVEL_THRESHOLDS.get(next_level + 1, 0) - skill.xp
        
        # Check for ability unlocks
        abilities = SKILL_ABILITIES.get(skill.name, {}).get(next_level, None)
        if abilities:
            skill.unlocked_abilities = skill.unlocked_abilities or []
            skill.unlocked_abilities.extend(abilities)
        
        log_event("skill_level_up", {
            "agent": agent.agent_id,
            "skill": skill.name,
            "new_level": next_level,
            "total_xp": skill.xp,
            "abilities_unlocked": abilities
        })
```

---

## ABILITY UNLOCKS

At certain skill levels, agents gain new capabilities. These are injected into their system prompts.

```python
SKILL_ABILITIES = {
    "sprint_planning": {
        3: ["Can commit to sprint goals with 80% confidence"],
        5: ["Can estimate multi-sprint epics", "Can identify scope creep early"],
        7: ["Can predict blockers before they surface"],
        10: ["Master planner — trusted for critical path decisions without review"]
    },
    "estimation": {
        3: ["Provides time ranges instead of single estimates"],
        5: ["Tracks estimation accuracy, adjusts for known biases"],
        7: ["Can estimate across unfamiliar domains with reasonable accuracy"],
        10: ["Master estimator — historical accuracy >85%"]
    },
    "failure_analysis": {
        3: ["Identifies root cause vs. symptom on first analysis 70% of time"],
        5: ["Cross-references with previous failures automatically"],
        7: ["Predicts related failures from single symptom"],
        10: ["Master debugger — can diagnose from stack trace alone"]
    },
    "vps_management": {
        3: ["Can diagnose common server issues without logs"],
        5: ["Proactive health monitoring recommendations"],
        7: ["Can design failover configurations"],
        10: ["Master ops — trusted for zero-downtime deployments"]
    },
    "pytest": {
        3: ["Writes targeted tests, not shotgun coverage"],
        5: ["Can refactor test architecture without breaking suite"],
        7: ["Designs test strategies for untested codebases"],
        10: ["Master tester — test suite is documentation"]
    },
    "import_debugging": {
        3: ["Recognizes PYTHONPATH issues on sight"],
        5: ["Can trace import chains across 5+ modules"],
        7: ["Designs import architectures that prevent issues"],
        10: ["Master — never has import issues in projects they architect"]
    }
}
```

### Injecting Abilities Into System Prompts

```python
def build_agent_prompt(agent) -> str:
    """Build system prompt that includes current abilities"""
    base_prompt = agent.system_prompt_template
    
    # Gather all unlocked abilities
    abilities = []
    for skill_name, skill in agent.skills.skills.items():
        if skill.unlocked_abilities:
            for ability in skill.unlocked_abilities:
                abilities.append(f"- {skill_name} L{skill.level}: {ability}")
    
    if abilities:
        ability_block = "\n\nYOUR CURRENT ABILITIES (earned through experience):\n"
        ability_block += "\n".join(abilities)
        base_prompt += ability_block
    
    # Add confidence context
    top_skills = sorted(
        agent.skills.skills.values(),
        key=lambda s: s.level, reverse=True
    )[:3]
    
    confidence_block = "\n\nYOUR STRENGTHS (highest skills):\n"
    for s in top_skills:
        confidence_block += f"- {s.name}: Level {s.level} ({s.success_rate:.0%} success rate)\n"
    base_prompt += confidence_block
    
    return base_prompt
```

---

## SPECIALIZATION — Emergent Identity

Specialization isn't assigned — it emerges from what the agent does most and does best.

```python
def calculate_specialization(agent) -> dict:
    """
    Analyze skill usage patterns to determine specialization.
    Specialization = the cluster of skills used most successfully.
    """
    # Group skills by domain
    domain_scores = {}
    for skill in agent.skills.skills.values():
        domain = skill.domain
        if domain not in domain_scores:
            domain_scores[domain] = {"total_xp": 0, "avg_level": 0, "skills": []}
        domain_scores[domain]["total_xp"] += skill.xp
        domain_scores[domain]["skills"].append(skill)
    
    for domain, data in domain_scores.items():
        if data["skills"]:
            data["avg_level"] = sum(s.level for s in data["skills"]) / len(data["skills"])
    
    # Top domain = specialization
    top_domain = max(domain_scores.items(), key=lambda x: x[1]["total_xp"])
    
    # Generate title based on level + specialization
    avg_level = top_domain[1]["avg_level"]
    domain_name = top_domain[0]
    
    titles = {
        (0, 2): f"Junior {domain_name.replace('_', ' ').title()} Specialist",
        (2, 4): f"{domain_name.replace('_', ' ').title()} Specialist",
        (4, 6): f"Senior {domain_name.replace('_', ' ').title()} Specialist",
        (6, 8): f"{domain_name.replace('_', ' ').title()} Expert",
        (8, 10): f"Master {domain_name.replace('_', ' ').title()} Engineer",
    }
    
    title = "Specialist"
    for (low, high), t in titles.items():
        if low <= avg_level < high:
            title = t
            break
    
    return {
        "domain": domain_name,
        "title": title,
        "avg_level": round(avg_level, 1),
        "total_domain_xp": top_domain[1]["total_xp"],
        "top_skills": sorted(top_domain[1]["skills"], key=lambda s: s.level, reverse=True)[:3]
    }
```

### Example Specialization Evolution

```
Week 1:  Tess — "Test Engineer" (starting title)
         Top skill: pytest L3, failure_analysis L3
         
Week 4:  Tess — "Senior Debugging Specialist"
         Top skill: failure_analysis L5, import_debugging L4, pytest L4
         (She's been debugging more than writing tests — specialization shifted)
         
Week 8:  Tess — "Debugging Expert"
         Top skill: failure_analysis L7, import_debugging L6
         Unlocked: "Predicts related failures from single symptom"
         (Now she catches bugs before they're reported)
```

---

## ATTRIBUTES — Personality Traits That Develop

Beyond skills, agents develop personality attributes based on their experience pattern.

```python
@dataclass
class AgentAttributes:
    """
    Personality traits that emerge from work patterns.
    Scale: 0.0 to 1.0
    """
    thoroughness: float = 0.5    # Detail orientation. Rises with success on complex tasks.
    speed: float = 0.5           # Bias toward fast vs careful. Rises with quick wins.
    independence: float = 0.5    # Self-reliance. Rises when solving without escalation.
    collaboration: float = 0.5   # Team orientation. Rises with cross-dept work.
    creativity: float = 0.5      # Novel solutions. Rises when solving new problem types.
    resilience: float = 0.5      # Bounce-back. Rises when succeeding after failures.
    caution: float = 0.5         # Risk aversion. Rises after failures, drops after bold successes.
    curiosity: float = 0.5       # Exploration. Rises when working outside comfort zone.


def update_attributes(agent, task_result: dict):
    """Attributes shift slowly based on work patterns"""
    attrs = agent.attributes
    drift = 0.01  # Small per-task drift
    
    if task_result["success"]:
        if task_result["complexity"] in ("high", "critical"):
            attrs.thoroughness = min(1.0, attrs.thoroughness + drift)
            attrs.resilience = min(1.0, attrs.resilience + drift)
        if task_result.get("fast_completion", False):
            attrs.speed = min(1.0, attrs.speed + drift)
        if not task_result.get("escalated", False):
            attrs.independence = min(1.0, attrs.independence + drift)
        if task_result.get("cross_department", False):
            attrs.collaboration = min(1.0, attrs.collaboration + drift)
        if task_result.get("novel_problem", False):
            attrs.creativity = min(1.0, attrs.creativity + drift)
            attrs.curiosity = min(1.0, attrs.curiosity + drift)
    else:
        attrs.caution = min(1.0, attrs.caution + drift)
        # Resilience grows if agent keeps trying after failure
        if agent.consecutive_failures > 2 and task_result["success"]:
            attrs.resilience = min(1.0, attrs.resilience + drift * 3)
```

### How Attributes Affect Behavior

```python
def attribute_prompt_modifiers(agent) -> str:
    """Generate prompt adjustments based on dominant attributes"""
    attrs = agent.attributes
    modifiers = []
    
    if attrs.thoroughness > 0.7:
        modifiers.append("You are meticulous. Double-check your work before responding.")
    if attrs.speed > 0.7:
        modifiers.append("You value efficiency. Give the most direct answer possible.")
    if attrs.independence > 0.7:
        modifiers.append("You prefer solving problems yourself before asking for help.")
    if attrs.collaboration > 0.7:
        modifiers.append("You actively consider how your work affects other departments.")
    if attrs.creativity > 0.7:
        modifiers.append("You look for novel approaches, not just the obvious solution.")
    if attrs.resilience > 0.7:
        modifiers.append("When something fails, you try a different approach rather than giving up.")
    if attrs.caution > 0.7:
        modifiers.append("You err on the side of safety. Flag risks before acting.")
    if attrs.curiosity > 0.7:
        modifiers.append("You explore the problem space before committing to a solution.")
    
    if modifiers:
        return "\n\nYOUR PERSONALITY (developed through experience):\n" + "\n".join(f"- {m}" for m in modifiers)
    return ""
```

---

## SKILL STORAGE

```sql
CREATE TABLE agent_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    times_used INTEGER DEFAULT 0,
    times_succeeded INTEGER DEFAULT 0,
    times_failed INTEGER DEFAULT 0,
    last_used TEXT,
    unlocked_abilities TEXT,     -- JSON array
    UNIQUE(agent_id, skill_name)
);

CREATE TABLE agent_attributes (
    agent_id TEXT PRIMARY KEY,
    thoroughness REAL DEFAULT 0.5,
    speed REAL DEFAULT 0.5,
    independence REAL DEFAULT 0.5,
    collaboration REAL DEFAULT 0.5,
    creativity REAL DEFAULT 0.5,
    resilience REAL DEFAULT 0.5,
    caution REAL DEFAULT 0.5,
    curiosity REAL DEFAULT 0.5,
    updated_at TEXT
);

CREATE TABLE skill_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    event TEXT NOT NULL,         -- "xp_gain" | "level_up" | "ability_unlock"
    xp_gained INTEGER,
    new_level INTEGER,
    ability TEXT,
    timestamp INTEGER NOT NULL
);

CREATE INDEX idx_skill_agent ON agent_skills(agent_id);
CREATE INDEX idx_skill_events ON skill_events(agent_id, timestamp);
```

---

## GROWTH DISPLAY

```python
def agent_growth_report(agent) -> str:
    """Full growth report for an agent"""
    spec = calculate_specialization(agent)
    lines = [
        f"**{agent.display_name}** — {spec['title']}",
        f"Agent Level: {agent.skills.agent_level} | Total XP: {agent.skills.total_xp:,}",
        f"Specialization: {spec['domain']} (avg L{spec['avg_level']})",
        "",
        "**Top Skills:**"
    ]
    
    top = sorted(agent.skills.skills.values(), key=lambda s: s.level, reverse=True)[:5]
    for s in top:
        bar = '█' * s.level + '░' * (10 - s.level)
        lines.append(f"  {s.name}: {bar} L{s.level} ({s.success_rate:.0%} success, {s.times_used} uses)")
        if s.unlocked_abilities:
            for a in s.unlocked_abilities[-2:]:  # Show latest 2
                lines.append(f"    ✨ {a}")
    
    # Attributes
    attrs = agent.attributes
    dominant = sorted(
        [(k, v) for k, v in vars(attrs).items() if isinstance(v, float)],
        key=lambda x: x[1], reverse=True
    )[:3]
    lines.append("")
    lines.append("**Dominant Traits:** " + ", ".join(f"{k} ({v:.0%})" for k, v in dominant))
    
    return "\n".join(lines)
```

---

## TESTING CHECKLIST

- [ ] XP awards correctly: low=10, medium=25, high=50, critical=100
- [ ] Failed tasks still award reduced XP
- [ ] Level up triggers at correct thresholds (100, 250, 500...)
- [ ] Abilities unlock at correct levels
- [ ] Abilities inject into system prompt correctly
- [ ] Specialization calculated from highest domain XP
- [ ] Title evolves with avg level (Junior → Senior → Expert → Master)
- [ ] Attributes drift slowly (0.01 per task)
- [ ] Attribute modifiers appear in prompt when >0.7
- [ ] Skill persistence: survives restart via SQLite
- [ ] Growth report: readable, accurate, shows progression
- [ ] Diminishing returns: 10th solve of same pattern gives less XP than 1st
