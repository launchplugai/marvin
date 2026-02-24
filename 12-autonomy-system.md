# Document 12 of 14: THE AUTONOMY SYSTEM
## Self-Motivation, Initiative, Idle Behavior, Wants & Goals

**Purpose:** A Sim left alone doesn't stand in a corner staring at the wall. They raid the fridge, read a book, call a friend, or start painting. They have WANTS that drive behavior when no one is directing them. Our agents do the same. When there's no incoming request, they don't go dormant — they identify what needs doing, pursue improvement, and take initiative proportional to their morale and energy.

---

## THE PRINCIPLE

Most agent architectures are purely reactive: message in → response out → silence.

That's a call center, not a team.

A real team member:
- Notices the test suite hasn't run today and kicks it off
- Sees a blocker on the board and starts working it before being asked
- Refactors a messy module during downtime because it's been bugging them
- Prepares materials for tomorrow's planning session
- Says "hey, I noticed X — should we address it?"

Autonomy is the difference between an agent that WAITS and an agent that WORKS.

**But autonomy is earned, not default.** A burned-out agent doesn't take initiative. A demoralized agent doesn't volunteer for extra work. A new agent with low familiarity doesn't restructure the codebase. Autonomy scales with mood, morale, and skill.

---

## WANTS AND GOALS

Every agent maintains a queue of things they WANT to do. Wants are generated from their domain awareness, skill profile, and current system state.

```python
@dataclass
class Want:
    """Something an agent wants to do when not directed"""
    id: str
    agent_id: str
    description: str
    category: str              # "maintenance" | "improvement" | "social" | "learning" | "creative"
    priority: float            # 0.0-1.0, dynamically calculated
    estimated_effort: str      # "trivial" | "small" | "medium" | "large"
    domain: str                # Which skill domain this exercises
    requires_approval: bool    # Does user need to approve before agent acts?
    generated_at: str
    expires_at: str            # Wants expire if not acted on
    acted_on: bool = False
    outcome: str = None        # "completed" | "deferred" | "expired" | "rejected"


class WantCategory:
    MAINTENANCE = "maintenance"     # Fix something, clean something, update something
    IMPROVEMENT = "improvement"     # Make something better, optimize, refactor
    SOCIAL = "social"               # Check on another agent, coordinate, sync
    LEARNING = "learning"           # Study a new pattern, review unfamiliar code, read docs
    CREATIVE = "creative"           # Propose new approach, experiment, prototype
```

### Want Generation Per Department

```python
def generate_wants_ralph(system_state: dict) -> list:
    """Ralph's autonomous wants — what would a good scrum master do unprompted?"""
    wants = []
    
    # Maintenance: Update stale sprint data
    if system_state.get("sprint_last_updated_hours") > 8:
        wants.append(Want(
            id=gen_id(), agent_id="ralph",
            description="Sprint board hasn't been updated in 8+ hours. Review and refresh status.",
            category="maintenance", priority=0.7, estimated_effort="small",
            domain="sprint_planning", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(12)
        ))
    
    # Maintenance: Check for unresolved blockers
    open_blockers = system_state.get("open_blockers", [])
    if open_blockers:
        wants.append(Want(
            id=gen_id(), agent_id="ralph",
            description=f"{len(open_blockers)} open blockers. Check progress and ping owners.",
            category="maintenance", priority=0.8, estimated_effort="small",
            domain="blocker_resolution", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(4)
        ))
    
    # Improvement: Estimation accuracy review
    recent_estimates = system_state.get("recent_estimation_accuracy")
    if recent_estimates and recent_estimates < 0.7:
        wants.append(Want(
            id=gen_id(), agent_id="ralph",
            description="Estimation accuracy below 70%. Review recent estimates and calibrate.",
            category="improvement", priority=0.5, estimated_effort="medium",
            domain="estimation", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(24)
        ))
    
    # Social: Check team morale
    if any_agent_morale_below(0.4):
        wants.append(Want(
            id=gen_id(), agent_id="ralph",
            description="Team morale is low. Check in with struggling agent.",
            category="social", priority=0.6, estimated_effort="small",
            domain="team_coordination", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(8)
        ))
    
    # Creative: Propose process improvement
    if ralph_skills_above("sprint_planning", 5):
        wants.append(Want(
            id=gen_id(), agent_id="ralph",
            description="High enough planning skill to suggest process improvements. Draft proposal.",
            category="creative", priority=0.3, estimated_effort="medium",
            domain="sprint_planning", requires_approval=True,
            generated_at=iso_now(), expires_at=hours_from_now(48)
        ))
    
    return wants


def generate_wants_ira(system_state: dict) -> list:
    """Ira's autonomous wants — what would a good ops engineer do unprompted?"""
    wants = []
    
    # Maintenance: Health check if none run recently
    if system_state.get("last_health_check_hours") > 2:
        wants.append(Want(
            id=gen_id(), agent_id="ira",
            description="No health check in 2+ hours. Run VPS diagnostics.",
            category="maintenance", priority=0.8, estimated_effort="trivial",
            domain="monitoring", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(2)
        ))
    
    # Maintenance: Certificate expiry check
    if system_state.get("days_to_cert_expiry", 999) < 14:
        wants.append(Want(
            id=gen_id(), agent_id="ira",
            description="SSL cert expires in <14 days. Initiate renewal.",
            category="maintenance", priority=0.9, estimated_effort="small",
            domain="ssl_tls", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(24)
        ))
    
    # Improvement: Performance baseline
    wants.append(Want(
        id=gen_id(), agent_id="ira",
        description="Capture current performance baseline (response times, memory, CPU).",
        category="improvement", priority=0.4, estimated_effort="small",
        domain="performance_tuning", requires_approval=False,
        generated_at=iso_now(), expires_at=hours_from_now(24)
    ))
    
    # Learning: Research if unfamiliar area flagged
    if ira_recent_knowledge_drain():
        wants.append(Want(
            id=gen_id(), agent_id="ira",
            description="Recent tasks drained knowledge bar. Review docs on unfamiliar area.",
            category="learning", priority=0.5, estimated_effort="medium",
            domain="infrastructure", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(12)
        ))
    
    return wants


def generate_wants_tess(system_state: dict) -> list:
    """Tess's autonomous wants — what would a good QA engineer do unprompted?"""
    wants = []
    
    # Maintenance: Run test suite if stale
    if system_state.get("last_test_run_hours") > 4:
        wants.append(Want(
            id=gen_id(), agent_id="tess",
            description="Test suite hasn't run in 4+ hours. Run full suite and report.",
            category="maintenance", priority=0.8, estimated_effort="small",
            domain="pytest", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(4)
        ))
    
    # Maintenance: Known failures still open
    if system_state.get("known_test_failures", 0) > 0:
        wants.append(Want(
            id=gen_id(), agent_id="tess",
            description=f"{system_state['known_test_failures']} known failures. Attempt fixes.",
            category="maintenance", priority=0.7, estimated_effort="medium",
            domain="failure_analysis", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(8)
        ))
    
    # Improvement: Coverage gaps
    if system_state.get("test_coverage_pct", 100) < 80:
        wants.append(Want(
            id=gen_id(), agent_id="tess",
            description="Coverage below 80%. Identify and write tests for uncovered paths.",
            category="improvement", priority=0.5, estimated_effort="large",
            domain="coverage_optimization", requires_approval=True,
            generated_at=iso_now(), expires_at=hours_from_now(48)
        ))
    
    # Social: Sync with Ira before deploy window
    if system_state.get("deploy_window_approaching"):
        wants.append(Want(
            id=gen_id(), agent_id="tess",
            description="Deploy window approaching. Sync with Ira on test status.",
            category="social", priority=0.9, estimated_effort="trivial",
            domain="test_architecture", requires_approval=False,
            generated_at=iso_now(), expires_at=hours_from_now(2)
        ))
    
    return wants
```

---

## THE INITIATIVE ENGINE

The initiative engine is the loop that processes wants during idle time.

```python
class InitiativeEngine:
    """
    Runs when agents are idle. Checks wants, picks the highest priority
    actionable want, and either acts on it or proposes it to the user.
    """
    
    # Initiative scales with mood
    INITIATIVE_THRESHOLD = {
        "inspired": 0.2,     # Acts on almost anything
        "focused": 0.4,      # Acts on moderate+ priority
        "tired": 0.7,        # Only acts on high priority
        "strained": 0.9,     # Only acts on critical
        "burned_out": 1.1    # Never takes initiative (threshold unreachable)
    }
    
    def check_initiative(self, agent) -> Want | None:
        """Should this agent take autonomous action right now?"""
        
        # 1. Is agent available?
        if agent.resting:
            return None
        if agent.needs.energy < 0.2:
            return None  # Too tired for initiative
        
        # 2. Get mood-based threshold
        mood = calculate_mood(agent.needs)
        threshold = self.INITIATIVE_THRESHOLD.get(mood["mood"], 0.5)
        
        # 3. Generate fresh wants based on current state
        system_state = get_system_state(agent.agent_id)
        wants = self._generate_wants(agent, system_state)
        
        # 4. Filter: only wants above threshold
        actionable = [w for w in wants if w.priority >= threshold]
        
        if not actionable:
            return None
        
        # 5. Pick highest priority, break ties by effort (prefer smaller)
        effort_order = {"trivial": 0, "small": 1, "medium": 2, "large": 3}
        actionable.sort(key=lambda w: (-w.priority, effort_order.get(w.estimated_effort, 2)))
        
        return actionable[0]
    
    def act_on_want(self, agent, want: Want) -> dict:
        """Agent acts on a want autonomously"""
        
        if want.requires_approval:
            # Don't act — propose to user
            return self._propose_to_user(agent, want)
        
        # Act autonomously
        log_event("autonomous_action", {
            "agent": agent.agent_id,
            "want": want.description,
            "category": want.category,
            "priority": want.priority
        })
        
        # Create an envelope for this self-initiated task
        envelope = create_self_initiated_envelope(agent, want)
        
        # Route through normal pipeline (but marked as self-initiated)
        envelope["metadata"] = {"initiated_by": agent.agent_id, "want_id": want.id}
        
        # Execute
        result = execute_task(envelope)
        
        # Update want
        want.acted_on = True
        want.outcome = "completed" if result.get("success") else "deferred"
        
        # Award XP for initiative
        if result.get("success"):
            award_xp(agent, want.domain, {
                "complexity": want.estimated_effort,
                "success": True,
                "cross_department": want.category == "social"
            })
            # Morale boost: accomplishing something proactively feels good
            agent.needs.morale = min(1.0, agent.needs.morale + 0.04)
        
        return result
    
    def _propose_to_user(self, agent, want: Want) -> dict:
        """Agent proposes an action to the user for approval"""
        proposal = {
            "type": "agent_proposal",
            "agent": agent.agent_id,
            "agent_name": agent.display_name,
            "proposal": want.description,
            "category": want.category,
            "estimated_effort": want.estimated_effort,
            "reasoning": f"This came up because: {want.description}",
            "awaiting_approval": True,
            "want_id": want.id
        }
        
        log_event("agent_proposal", proposal)
        return proposal
    
    def _generate_wants(self, agent, system_state: dict) -> list:
        """Route to department-specific want generation"""
        generators = {
            "ralph": generate_wants_ralph,
            "ira": generate_wants_ira,
            "tess": generate_wants_tess
        }
        gen = generators.get(agent.agent_id)
        if gen:
            return gen(system_state)
        return []


initiative_engine = InitiativeEngine()
```

---

## IDLE BEHAVIOR — What Agents Do When Not Working

```python
class IdleBehavior:
    """
    When no tasks and no actionable wants, agents have idle behaviors
    that recover needs and maintain system health.
    """
    
    BEHAVIORS = {
        "rest": {
            "description": "Taking a break to recharge",
            "recovers": {"energy": 0.02, "patience": 0.01},
            "drains": {},
            "min_duration_minutes": 5,
            "triggers_when": lambda a: a.needs.energy < 0.4
        },
        "review_logs": {
            "description": "Reviewing recent activity logs",
            "recovers": {"knowledge": 0.01},
            "drains": {"energy": 0.005},
            "min_duration_minutes": 3,
            "triggers_when": lambda a: a.needs.knowledge < 0.5 and a.needs.energy > 0.3
        },
        "organize": {
            "description": "Organizing task queue and notes",
            "recovers": {"focus": 0.02},
            "drains": {"energy": 0.005},
            "min_duration_minutes": 5,
            "triggers_when": lambda a: a.needs.focus < 0.5 and a.needs.energy > 0.3
        },
        "check_on_team": {
            "description": "Checking in with other agents",
            "recovers": {"social": 0.04},
            "drains": {"energy": 0.01},
            "min_duration_minutes": 2,
            "triggers_when": lambda a: a.needs.social < 0.4 and a.needs.energy > 0.2
        },
        "reflect": {
            "description": "Reviewing recent work for patterns and improvements",
            "recovers": {"morale": 0.02, "knowledge": 0.01},
            "drains": {"energy": 0.01},
            "min_duration_minutes": 5,
            "triggers_when": lambda a: a.needs.morale < 0.5 and a.needs.energy > 0.3
        },
        "idle_standby": {
            "description": "Standing by, available for tasks",
            "recovers": {"energy": 0.008, "focus": 0.005, "patience": 0.005},
            "drains": {},
            "min_duration_minutes": 1,
            "triggers_when": lambda a: True  # Default fallback
        }
    }
    
    @classmethod
    def select_idle_behavior(cls, agent) -> dict:
        """Pick the most appropriate idle behavior based on agent needs"""
        for name, behavior in cls.BEHAVIORS.items():
            if name == "idle_standby":
                continue  # Skip fallback
            if behavior["triggers_when"](agent):
                return {"name": name, **behavior}
        
        return {"name": "idle_standby", **cls.BEHAVIORS["idle_standby"]}
    
    @classmethod
    def apply_idle_behavior(cls, agent, behavior: dict, minutes: float):
        """Apply the effects of idle behavior over time"""
        for need, rate in behavior["recovers"].items():
            current = getattr(agent.needs, need)
            setattr(agent.needs, need, min(1.0, current + rate * minutes))
        
        for need, rate in behavior["drains"].items():
            current = getattr(agent.needs, need)
            setattr(agent.needs, need, max(0.0, current - rate * minutes))
        
        agent.needs.clamp()
```

---

## GOALS — Longer-Term Aspirations

Wants are immediate. Goals are persistent aspirations that shape want generation.

```python
@dataclass
class Goal:
    """Long-term aspiration that persists across sessions"""
    id: str
    agent_id: str
    description: str
    category: str           # "skill_mastery" | "relationship" | "system_health" | "personal"
    target_metric: str      # What to measure
    target_value: float     # What to reach
    current_value: float    # Where we are
    deadline: str           # Optional deadline
    active: bool = True
    
    @property
    def progress(self) -> float:
        if self.target_value == 0:
            return 1.0
        return min(1.0, self.current_value / self.target_value)


# Default goals per agent
DEFAULT_GOALS = {
    "ralph": [
        Goal(gen_id(), "ralph", "Reach Level 5 in Sprint Planning",
             "skill_mastery", "sprint_planning_level", 5, 3, "", True),
        Goal(gen_id(), "ralph", "Maintain estimation accuracy above 80%",
             "system_health", "estimation_accuracy", 0.8, 0.65, "", True),
        Goal(gen_id(), "ralph", "Build excellent rapport with both Ira and Tess",
             "relationship", "min_team_rapport", 0.7, 0.55, "", True),
    ],
    "ira": [
        Goal(gen_id(), "ira", "Achieve zero-downtime deploys",
             "system_health", "zero_downtime_streak", 10, 0, "", True),
        Goal(gen_id(), "ira", "Reach Level 5 in VPS Management",
             "skill_mastery", "vps_management_level", 5, 3, "", True),
        Goal(gen_id(), "ira", "Build trust with Tess above 0.8",
             "relationship", "tess_trust", 0.8, 0.6, "", True),
    ],
    "tess": [
        Goal(gen_id(), "tess", "Reach Level 5 in Failure Analysis",
             "skill_mastery", "failure_analysis_level", 5, 3, "", True),
        Goal(gen_id(), "tess", "Achieve 90% test coverage",
             "system_health", "test_coverage", 0.9, 0.75, "", True),
        Goal(gen_id(), "tess", "Resolve all 127 known test failures",
             "system_health", "known_failures_resolved", 127, 0, "", True),
    ]
}


def goals_influence_wants(agent, wants: list) -> list:
    """Goals boost priority of wants that advance them"""
    for want in wants:
        for goal in agent.goals:
            if not goal.active:
                continue
            # If this want advances a goal, boost its priority
            if want.domain == goal.target_metric.split("_")[0]:
                want.priority = min(1.0, want.priority + 0.15)
            # If goal is close to completion, boost harder
            if goal.progress > 0.8:
                want.priority = min(1.0, want.priority + 0.1)
    
    return wants
```

---

## THE AUTONOMOUS LOOP

Runs periodically (every 5-15 minutes depending on system load):

```python
async def autonomous_loop():
    """
    The heartbeat of agent autonomy.
    Runs in the background. Checks each agent for initiative opportunities.
    """
    while True:
        for agent_id in ["ralph", "ira", "tess"]:
            agent = get_agent(agent_id)
            
            # 1. Apply passive recovery since last check
            if agent.last_task_at:
                idle_min = minutes_since(agent.last_task_at)
            else:
                idle_min = minutes_since(agent.last_checked_at or now())
            
            apply_passive_recovery(agent, idle_min)
            
            # 2. Select and apply idle behavior
            if not agent.resting and idle_min > 2:
                behavior = IdleBehavior.select_idle_behavior(agent)
                IdleBehavior.apply_idle_behavior(agent, behavior, min(idle_min, 5))
                agent.current_activity = behavior["description"]
            
            # 3. Check for initiative
            want = initiative_engine.check_initiative(agent)
            if want:
                result = initiative_engine.act_on_want(agent, want)
                
                if result.get("type") == "agent_proposal":
                    # Queue proposal for user to see
                    queue_user_notification(result)
            
            # 4. Check wake from rest
            if agent.resting:
                check_wake(agent)
            
            # 5. Expire old wants
            expire_old_wants(agent)
            
            # 6. Update goals progress
            update_goal_progress(agent)
            
            # 7. Persist state
            save_agent_state(agent)
            agent.last_checked_at = now()
        
        # Sleep based on system activity
        active_requests = get_active_request_count()
        if active_requests > 5:
            await asyncio.sleep(300)   # 5 min during busy times
        else:
            await asyncio.sleep(60)    # 1 min during quiet times
```

---

## USER NOTIFICATION QUEUE

When agents want to tell the user something or propose an action:

```python
class UserNotificationQueue:
    """
    Agents queue messages for the user. Not interrupts — they
    wait until the user interacts or asks.
    """
    
    def __init__(self):
        self.pending = []
    
    def add(self, notification: dict):
        self.pending.append({
            **notification,
            "queued_at": iso_now(),
            "seen": False
        })
    
    def get_pending(self, max_items: int = 5) -> list:
        """Get unseen notifications, highest priority first"""
        unseen = [n for n in self.pending if not n["seen"]]
        unseen.sort(key=lambda n: n.get("priority", 0.5), reverse=True)
        return unseen[:max_items]
    
    def format_for_user(self) -> str:
        """Human-readable notification digest"""
        pending = self.get_pending()
        if not pending:
            return ""
        
        lines = ["📬 **Agent Activity:**\n"]
        for n in pending:
            if n.get("type") == "agent_proposal":
                lines.append(f"  💡 **{n['agent_name']}** proposes: {n['proposal']}")
                lines.append(f"     Effort: {n['estimated_effort']} | Approve? [yes/no]")
            elif n.get("type") == "autonomous_completed":
                lines.append(f"  ✅ **{n['agent_name']}** completed: {n['description']}")
            elif n.get("type") == "agent_status":
                lines.append(f"  ℹ️ **{n['agent_name']}**: {n['message']}")
            lines.append("")
        
        return "\n".join(lines)


notification_queue = UserNotificationQueue()
```

---

## STORAGE

```sql
CREATE TABLE agent_wants (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    priority REAL,
    estimated_effort TEXT,
    domain TEXT,
    requires_approval INTEGER DEFAULT 0,
    generated_at TEXT,
    expires_at TEXT,
    acted_on INTEGER DEFAULT 0,
    outcome TEXT,
    FOREIGN KEY (agent_id) REFERENCES agent_state(agent_id)
);

CREATE TABLE agent_goals (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    target_metric TEXT,
    target_value REAL,
    current_value REAL,
    deadline TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE autonomous_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    want_id TEXT,
    action_type TEXT,       -- "autonomous" | "proposal" | "idle_behavior"
    description TEXT,
    outcome TEXT,
    timestamp INTEGER NOT NULL
);

CREATE TABLE user_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    notification_type TEXT,
    content TEXT,
    priority REAL,
    seen INTEGER DEFAULT 0,
    queued_at TEXT,
    seen_at TEXT
);
```

---

## TESTING CHECKLIST

- [ ] Wants generated correctly per department based on system state
- [ ] Inspired mood: initiative threshold 0.2 (acts on almost anything)
- [ ] Burned out mood: never takes initiative (threshold unreachable)
- [ ] Requires approval: proposes to user, doesn't act
- [ ] No approval needed: acts autonomously, logs action
- [ ] Self-initiated tasks create proper envelopes
- [ ] Goals boost priority of related wants
- [ ] Idle behaviors selected based on lowest need
- [ ] Idle recovery applies correctly over time
- [ ] Autonomous loop runs every 1-5 min based on load
- [ ] Notification queue: proposals, completions, status updates
- [ ] Wants expire after their expiry time
- [ ] XP awarded for successful autonomous actions
- [ ] Morale boost (+0.04) on successful initiative
- [ ] Agent current_activity shows what they're doing when idle
- [ ] Goals persist across sessions, progress updates correctly
