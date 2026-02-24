# Document 11 of 14: THE RELATIONSHIP SYSTEM
## Trust, Rapport, Friction, Inter-Agent Dynamics

**Purpose:** In The Sims, relationships aren't optional decoration. Two Sims with low relationship scores argue, refuse to cooperate, sabotage each other's tasks. Two Sims with high relationship scores finish each other's sentences, work faster together, and unlock group activities. Our agents work the same way. Ralph and Tess's coordination quality depends on their relationship. Ira's willingness to accept Tess's "tests pass" sign-off depends on how many times Tess's sign-off was actually reliable. Relationships are earned, not assigned.

---

## THE PRINCIPLE

Every real engineering team has invisible relationship dynamics:
- The two people who just *work well together* and get more done as a pair
- The person who doesn't trust another's code reviews and re-checks everything
- The new hire everyone mentors vs. the veteran everyone defers to
- The friction that builds when one person keeps blocking another's deploys

These aren't bugs — they're data. A system that tracks them can route work to pairs that collaborate well, flag relationships that are degrading, and simulate the organic trust that makes real teams effective.

**Relationships are bidirectional but asymmetric.** Ralph may trust Tess at 0.85 (she always delivers accurate test reports), but Tess may trust Ralph at only 0.60 (he changes sprint priorities mid-sprint too often).

---

## RELATIONSHIP STRUCTURE

```python
@dataclass
class Relationship:
    """Bidirectional relationship between two agents (stored per-direction)"""
    from_agent: str
    to_agent: str
    
    # Core metrics (0.0 to 1.0)
    trust: float = 0.5            # Reliability. Built through consistent follow-through.
    rapport: float = 0.5          # Working chemistry. Built through successful collaboration.
    respect: float = 0.5          # Professional regard. Built through demonstrated competence.
    friction: float = 0.0         # Accumulated tension. Built through conflicts and blocks.
    familiarity: float = 0.0      # How well they know each other's patterns. Pure interaction count.
    
    # Interaction tracking
    total_interactions: int = 0
    successful_handoffs: int = 0
    failed_handoffs: int = 0
    conflicts: int = 0
    assists: int = 0
    last_interaction: str = None
    
    @property
    def overall_health(self) -> float:
        """Net relationship health: positive metrics minus friction"""
        positive = (self.trust + self.rapport + self.respect) / 3
        return max(0.0, min(1.0, positive - (self.friction * 0.5)))
    
    @property
    def chemistry(self) -> str:
        """Human-readable relationship label"""
        health = self.overall_health
        if health > 0.8: return "excellent"
        if health > 0.6: return "good"
        if health > 0.4: return "neutral"
        if health > 0.2: return "strained"
        return "hostile"
```

---

## WHAT EACH METRIC MEANS (Mechanically)

| Metric | Built By | Damaged By | Affects |
|--------|----------|------------|---------|
| **Trust** | Delivering on promises, accurate handoffs, reliable info | Bad info passed, missed deadlines, broken sign-offs | Whether agent accepts other's output without re-verification |
| **Rapport** | Successful joint tasks, complementary work, positive coordination | Ignored context, dismissed input, conflicting approaches | Speed of collaboration. High rapport = less preamble needed. |
| **Respect** | Demonstrating competence, solving hard problems, good judgment | Repeated mistakes, poor quality output, bad advice | Deference level. High respect = agent follows other's recommendations. |
| **Friction** | Blocking each other's work, disagreements, escalations against each other | Time passing, successful conflict resolution, apology/correction | Overhead per interaction. High friction = more tokens spent negotiating. |
| **Familiarity** | Any interaction at all (monotonically increasing, never decreases) | — | Prediction accuracy. High familiarity = better anticipation of other's needs. |

---

## RELATIONSHIP EVENTS

```python
class RelationshipEvent:
    """Events that modify relationships"""
    
    # Trust events
    RELIABLE_HANDOFF = {"trust": 0.03, "rapport": 0.01, "friction": -0.01}
    UNRELIABLE_HANDOFF = {"trust": -0.05, "friction": 0.03}
    ACCURATE_INFO = {"trust": 0.02, "respect": 0.01}
    BAD_INFO = {"trust": -0.04, "respect": -0.02, "friction": 0.02}
    
    # Rapport events
    SUCCESSFUL_COLLAB = {"rapport": 0.04, "trust": 0.02, "friction": -0.02}
    FAILED_COLLAB = {"rapport": -0.03, "friction": 0.02}
    COMPLEMENTARY_WORK = {"rapport": 0.02, "respect": 0.01}
    CONFLICTING_APPROACH = {"rapport": -0.02, "friction": 0.03}
    
    # Respect events
    IMPRESSIVE_SOLVE = {"respect": 0.05, "trust": 0.02}
    REPEATED_MISTAKE = {"respect": -0.03, "trust": -0.01}
    GOOD_JUDGMENT_CALL = {"respect": 0.03, "rapport": 0.01}
    POOR_JUDGMENT = {"respect": -0.04, "friction": 0.02}
    
    # Friction events
    BLOCKED_WORK = {"friction": 0.05, "rapport": -0.02}
    ESCALATED_AGAINST = {"friction": 0.04, "trust": -0.02}
    CONFLICT_RESOLVED = {"friction": -0.06, "rapport": 0.03, "trust": 0.02}
    TIME_DECAY = {"friction": -0.01}  # Applied passively over time
    
    # Assist events
    PROACTIVE_HELP = {"rapport": 0.05, "trust": 0.02, "respect": 0.02}
    ASKED_AND_DELIVERED = {"trust": 0.03, "rapport": 0.02}
    ASKED_AND_FAILED = {"trust": -0.03, "friction": 0.01}


def apply_relationship_event(rel: Relationship, event: dict, event_name: str):
    """Apply a relationship event to a specific relationship"""
    for metric, delta in event.items():
        current = getattr(rel, metric)
        new_val = max(0.0, min(1.0, current + delta))
        setattr(rel, metric, new_val)
    
    rel.total_interactions += 1
    rel.familiarity = min(1.0, rel.familiarity + 0.01)  # Always grows
    rel.last_interaction = iso_now()
    
    # Track specific outcomes
    if "handoff" in event_name.lower():
        if event.get("trust", 0) > 0:
            rel.successful_handoffs += 1
        else:
            rel.failed_handoffs += 1
    if "conflict" in event_name.lower() or "blocked" in event_name.lower():
        rel.conflicts += 1
    if "help" in event_name.lower() or "assist" in event_name.lower():
        rel.assists += 1
    
    log_event("relationship_update", {
        "from": rel.from_agent,
        "to": rel.to_agent,
        "event": event_name,
        "deltas": event,
        "new_state": {
            "trust": rel.trust,
            "rapport": rel.rapport,
            "respect": rel.respect,
            "friction": rel.friction,
            "health": rel.overall_health,
            "chemistry": rel.chemistry
        }
    })
```

---

## RELATIONSHIP MATRIX

The full team relationship state:

```python
class RelationshipMatrix:
    """
    Manages all pairwise relationships in the system.
    Each pair has TWO entries (A→B and B→A).
    """
    
    def __init__(self):
        self.relationships = {}  # (from_id, to_id) → Relationship
        self._init_default_relationships()
    
    def _init_default_relationships(self):
        """Set starting relationships based on org structure"""
        agents = ["ralph", "ira", "tess"]
        
        for a in agents:
            for b in agents:
                if a != b:
                    self.relationships[(a, b)] = Relationship(
                        from_agent=a, to_agent=b,
                        trust=0.5, rapport=0.5, respect=0.5,
                        friction=0.0, familiarity=0.1
                    )
        
        # Pre-existing dynamics (based on established team history)
        # Tess → Ira: slightly higher trust (Tess signs off deploys for Ira)
        self.relationships[("tess", "ira")].trust = 0.6
        
        # Ira → Tess: slightly higher respect (Tess catches real bugs)
        self.relationships[("ira", "tess")].respect = 0.6
        
        # Ralph → both: moderate rapport (he coordinates them daily)
        self.relationships[("ralph", "ira")].rapport = 0.55
        self.relationships[("ralph", "tess")].rapport = 0.55
    
    def get(self, from_agent: str, to_agent: str) -> Relationship:
        return self.relationships.get((from_agent, to_agent))
    
    def get_pair_chemistry(self, agent_a: str, agent_b: str) -> dict:
        """Get bidirectional relationship summary"""
        ab = self.get(agent_a, agent_b)
        ba = self.get(agent_b, agent_a)
        
        return {
            "pair": f"{agent_a} ↔ {agent_b}",
            f"{agent_a}_to_{agent_b}": {
                "trust": ab.trust, "rapport": ab.rapport,
                "respect": ab.respect, "friction": ab.friction,
                "health": ab.overall_health, "chemistry": ab.chemistry
            },
            f"{agent_b}_to_{agent_a}": {
                "trust": ba.trust, "rapport": ba.rapport,
                "respect": ba.respect, "friction": ba.friction,
                "health": ba.overall_health, "chemistry": ba.chemistry
            },
            "mutual_health": (ab.overall_health + ba.overall_health) / 2,
            "collaboration_bonus": calculate_collab_bonus(ab, ba)
        }
    
    def get_best_pair_for_task(self, task_domains: list) -> tuple:
        """Find the agent pair with best chemistry for a cross-domain task"""
        best_pair = None
        best_score = -1
        
        for (a, b), rel in self.relationships.items():
            if a < b:  # Avoid duplicates
                mutual = (rel.overall_health + self.get(b, a).overall_health) / 2
                if mutual > best_score:
                    best_score = mutual
                    best_pair = (a, b)
        
        return best_pair, best_score


# Singleton
relationship_matrix = RelationshipMatrix()
```

---

## COLLABORATION BONUS

Good relationships = tangible work benefits.

```python
def calculate_collab_bonus(ab: Relationship, ba: Relationship) -> dict:
    """
    When two agents work together, their relationship quality
    affects the work product.
    """
    mutual_trust = (ab.trust + ba.trust) / 2
    mutual_rapport = (ab.rapport + ba.rapport) / 2
    mutual_friction = (ab.friction + ba.friction) / 2
    
    # Speed bonus: high rapport = less preamble, faster coordination
    speed_modifier = 1.0
    if mutual_rapport > 0.7:
        speed_modifier = 0.8  # 20% faster (fewer tokens for coordination)
    elif mutual_rapport < 0.3:
        speed_modifier = 1.3  # 30% slower (more negotiation needed)
    
    # Quality bonus: high trust = output accepted, no re-verification
    verification_needed = True
    if mutual_trust > 0.8:
        verification_needed = False  # Trust their output directly
    
    # Friction tax: high friction = extra tokens spent on diplomacy
    friction_overhead_tokens = int(mutual_friction * 200)  # 0-200 extra tokens
    
    # Handoff format: high familiarity = can use shorthand
    handoff_format = "full"  # Full context needed
    familiarity = (ab.familiarity + ba.familiarity) / 2
    if familiarity > 0.7:
        handoff_format = "shorthand"  # Can skip obvious context
    elif familiarity > 0.4:
        handoff_format = "standard"
    
    return {
        "speed_modifier": speed_modifier,
        "verification_needed": verification_needed,
        "friction_overhead_tokens": friction_overhead_tokens,
        "handoff_format": handoff_format,
        "effective_quality": max(0.5, 1.0 - mutual_friction * 0.3)
    }
```

---

## AUTOMATIC RELATIONSHIP TRIGGERS

These fire automatically during normal operations — no manual tracking needed.

```python
def on_handoff(from_agent: str, to_agent: str, envelope: dict, outcome: str):
    """Called when one agent hands work to another"""
    rel = relationship_matrix.get(from_agent, to_agent)
    
    if outcome == "success":
        apply_relationship_event(rel, RelationshipEvent.RELIABLE_HANDOFF, "reliable_handoff")
        # Reverse: receiving agent now trusts sender more
        rev = relationship_matrix.get(to_agent, from_agent)
        apply_relationship_event(rev, RelationshipEvent.ACCURATE_INFO, "received_good_handoff")
    
    elif outcome == "failure":
        apply_relationship_event(rel, RelationshipEvent.UNRELIABLE_HANDOFF, "unreliable_handoff")
        rev = relationship_matrix.get(to_agent, from_agent)
        apply_relationship_event(rev, RelationshipEvent.BAD_INFO, "received_bad_handoff")


def on_escalation(from_dept: str, about_dept: str, envelope: dict):
    """Called when one department escalates about another to the boss"""
    rel = relationship_matrix.get(from_dept, about_dept)
    apply_relationship_event(rel, RelationshipEvent.ESCALATED_AGAINST, "escalation")
    
    # The other side feels it too
    rev = relationship_matrix.get(about_dept, from_dept)
    apply_relationship_event(rev, {"friction": 0.03, "rapport": -0.01}, "was_escalated_about")


def on_collab_task(agents: list, envelope: dict, success: bool):
    """Called when multiple agents work on the same envelope"""
    event = RelationshipEvent.SUCCESSFUL_COLLAB if success else RelationshipEvent.FAILED_COLLAB
    name = "successful_collab" if success else "failed_collab"
    
    for i, a in enumerate(agents):
        for b in agents[i+1:]:
            apply_relationship_event(relationship_matrix.get(a, b), event, name)
            apply_relationship_event(relationship_matrix.get(b, a), event, name)


def on_proactive_help(helper: str, helped: str, envelope: dict):
    """Called when an agent voluntarily assists another"""
    rel = relationship_matrix.get(helped, helper)
    apply_relationship_event(rel, RelationshipEvent.PROACTIVE_HELP, "received_help")
    
    # Helper's social need recovers
    agent = get_agent(helper)
    agent.needs.social = min(1.0, agent.needs.social + 0.05)


def on_conflict_resolved(agent_a: str, agent_b: str, resolver: str):
    """Called when a conflict between two agents is resolved (usually by boss)"""
    apply_relationship_event(
        relationship_matrix.get(agent_a, agent_b),
        RelationshipEvent.CONFLICT_RESOLVED, "conflict_resolved"
    )
    apply_relationship_event(
        relationship_matrix.get(agent_b, agent_a),
        RelationshipEvent.CONFLICT_RESOLVED, "conflict_resolved"
    )
```

---

## PASSIVE FRICTION DECAY

Friction fades over time if there are no new conflicts. Like real coworkers — distance helps.

```python
def decay_friction_passive():
    """Run periodically (every hour or on day boundary)"""
    for key, rel in relationship_matrix.relationships.items():
        if rel.friction > 0 and rel.last_interaction:
            hours_since = hours_since_last(rel.last_interaction)
            if hours_since > 4:  # Friction starts cooling after 4 hours
                decay = min(rel.friction, 0.01 * (hours_since / 4))
                rel.friction = max(0.0, rel.friction - decay)
```

---

## ROUTING INTEGRATION

Relationships affect routing decisions for cross-department work:

```python
def route_cross_department_task(envelope: dict, required_depts: list) -> dict:
    """
    When a task needs multiple departments, consider their relationships.
    """
    if len(required_depts) < 2:
        return envelope  # Single dept, no relationship consideration
    
    # Get pairwise chemistry
    pairs = []
    for i, a in enumerate(required_depts):
        for b in required_depts[i+1:]:
            chemistry = relationship_matrix.get_pair_chemistry(a, b)
            pairs.append(chemistry)
    
    # Calculate coordination cost
    avg_health = sum(p["mutual_health"] for p in pairs) / len(pairs)
    total_friction_overhead = sum(
        calculate_collab_bonus(
            relationship_matrix.get(a, b),
            relationship_matrix.get(b, a)
        )["friction_overhead_tokens"]
        for i, a in enumerate(required_depts)
        for b in required_depts[i+1:]
    )
    
    # Inject into envelope
    envelope["collaboration_context"] = {
        "departments_involved": required_depts,
        "avg_relationship_health": round(avg_health, 2),
        "friction_overhead_tokens": total_friction_overhead,
        "chemistry_summary": {
            p["pair"]: p["mutual_health"] for p in pairs
        }
    }
    
    # If relationship is strained, add mediation context
    if avg_health < 0.4:
        envelope["collaboration_context"]["warning"] = "strained_relationships"
        envelope["collaboration_context"]["recommendation"] = "boss_mediation"
    
    return envelope
```

---

## RELATIONSHIP DISPLAY

```python
def team_relationship_report() -> str:
    """Full team relationship matrix display"""
    agents = ["ralph", "ira", "tess"]
    lines = ["## Team Relationships\n"]
    
    for i, a in enumerate(agents):
        for b in agents[i+1:]:
            chem = relationship_matrix.get_pair_chemistry(a, b)
            ab = relationship_matrix.get(a, b)
            ba = relationship_matrix.get(b, a)
            
            health_bar = lambda v: '█' * int(v * 10) + '░' * (10 - int(v * 10))
            
            label = {
                "excellent": "🤝",
                "good": "👍",
                "neutral": "😐",
                "strained": "😬",
                "hostile": "⚡"
            }.get(ab.chemistry, "❓")
            
            lines.append(f"**{a.title()} ↔ {b.title()}** {label}")
            lines.append(f"  Mutual Health: {health_bar(chem['mutual_health'])} {chem['mutual_health']:.0%}")
            lines.append(f"  {a.title()} → {b.title()}: trust={ab.trust:.0%} rapport={ab.rapport:.0%} friction={ab.friction:.0%}")
            lines.append(f"  {b.title()} → {a.title()}: trust={ba.trust:.0%} rapport={ba.rapport:.0%} friction={ba.friction:.0%}")
            lines.append(f"  Interactions: {ab.total_interactions} | Handoffs: ✅{ab.successful_handoffs} ❌{ab.failed_handoffs}")
            
            collab = calculate_collab_bonus(ab, ba)
            if collab["speed_modifier"] < 1.0:
                lines.append(f"  ⚡ Speed bonus: {(1 - collab['speed_modifier']):.0%} faster coordination")
            if collab["speed_modifier"] > 1.0:
                lines.append(f"  🐌 Friction tax: {(collab['speed_modifier'] - 1):.0%} slower coordination")
            if not collab["verification_needed"]:
                lines.append(f"  ✅ Trusted: skip re-verification on handoffs")
            
            lines.append("")
    
    return "\n".join(lines)


def relationship_status_for_agent(agent_id: str) -> str:
    """How one agent sees its relationships"""
    agents = ["ralph", "ira", "tess"]
    others = [a for a in agents if a != agent_id]
    
    lines = [f"**{agent_id.title()}'s Relationships:**\n"]
    
    for other in others:
        rel = relationship_matrix.get(agent_id, other)
        emoji = {"excellent": "🤝", "good": "👍", "neutral": "😐",
                 "strained": "😬", "hostile": "⚡"}.get(rel.chemistry, "❓")
        
        lines.append(f"{emoji} **{other.title()}**: {rel.chemistry}")
        
        # What this agent thinks about the other
        if rel.trust > 0.7:
            lines.append(f"  \"I trust {other.title()}'s work.\"")
        elif rel.trust < 0.3:
            lines.append(f"  \"I double-check everything from {other.title()}.\"")
        
        if rel.friction > 0.5:
            lines.append(f"  \"There's tension. We need to resolve things.\"")
        
        if rel.rapport > 0.7:
            lines.append(f"  \"We work well together. Good flow.\"")
        
        lines.append("")
    
    return "\n".join(lines)
```

---

## STORAGE

```sql
CREATE TABLE agent_relationships (
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    trust REAL DEFAULT 0.5,
    rapport REAL DEFAULT 0.5,
    respect REAL DEFAULT 0.5,
    friction REAL DEFAULT 0.0,
    familiarity REAL DEFAULT 0.0,
    total_interactions INTEGER DEFAULT 0,
    successful_handoffs INTEGER DEFAULT 0,
    failed_handoffs INTEGER DEFAULT 0,
    conflicts INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    last_interaction TEXT,
    updated_at TEXT,
    PRIMARY KEY (from_agent, to_agent)
);

CREATE TABLE relationship_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    deltas TEXT,            -- JSON of metric changes
    new_state TEXT,         -- JSON of post-event state
    envelope_id TEXT,       -- Which task triggered this
    timestamp INTEGER NOT NULL
);
```

---

## TESTING CHECKLIST

- [ ] Default relationships initialize at 0.5 trust, 0.5 rapport, 0.0 friction
- [ ] Reliable handoff: trust +0.03, friction -0.01
- [ ] Unreliable handoff: trust -0.05, friction +0.03
- [ ] Successful collaboration: rapport +0.04, trust +0.02
- [ ] Escalation against: friction +0.04, trust -0.02
- [ ] Conflict resolved: friction -0.06, rapport +0.03
- [ ] Relationships are asymmetric (A→B ≠ B→A)
- [ ] Familiarity only goes up, never down
- [ ] Friction decays passively over time (after 4h)
- [ ] Collaboration bonus: rapport >0.7 = 20% speed boost
- [ ] Trust >0.8: skip re-verification on handoffs
- [ ] Strained relationship (<0.4 health): boss mediation recommended
- [ ] Cross-department routing includes relationship context in envelope
- [ ] Relationship display: readable, shows both directions
- [ ] Proactive help: boosts helper's social need + helped's trust
- [ ] All events log to relationship_events table
