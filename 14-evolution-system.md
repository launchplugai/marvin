# Document 14 of 14: THE EVOLUTION SYSTEM
## Long-Term Memory, Personality Drift, Emergent Behavior

**Purpose:** This is the "they feel alive" layer. Everything in Docs 9-13 operates within a session or across a few days. The Evolution System operates across weeks and months. It's the reason Ralph in Week 12 is meaningfully different from Ralph in Week 1 — not because we changed his prompt, but because his experiences shaped him. He remembers the sprint that went sideways. He learned to pad estimates after three misses. He trusts Tess more now because she caught a critical bug. This is personality that EMERGED, not personality that was assigned.

---

## THE PRINCIPLE

In The Sims, a Sim who cooks every day becomes a chef. A Sim who's been burned by a stove becomes nervous in the kitchen. A Sim who throws parties becomes the social hub. None of this was programmed as "become a chef" — it emerged from repetitive action + memory + consequence.

Our system works the same way:
- **Skills level up** (Doc 10) ← what you practice
- **Relationships evolve** (Doc 11) ← who you work with
- **Attributes drift** (Doc 10) ← how your work goes
- **Memories accumulate** (THIS DOC) ← what you remember
- **Personality crystallizes** (THIS DOC) ← all of the above, compounded over time

The LLM doesn't literally change. But what it knows about itself — injected into its system prompt from accumulated state — makes it behave differently. A prompt that says "You've successfully debugged 47 import issues, you're Level 6 in failure analysis, and you trust Ira at 0.85" produces genuinely different output than a prompt that says "You're a test engineer."

**Evolution is the slow accumulation of state that makes the fast decisions feel informed.**

---

## LONG-TERM MEMORY

### Memory Types

```python
@dataclass
class Memory:
    """A discrete memory that persists across sessions"""
    id: str
    agent_id: str
    memory_type: str       # See types below
    content: str           # Natural language description
    structured: dict       # Machine-readable data
    significance: float    # 0.0-1.0, affects retention
    emotional_valence: str # "positive" | "neutral" | "negative"
    domain: str
    created_at: str
    last_recalled: str     # When was this memory last used
    recall_count: int      # How many times referenced
    fading: float          # 1.0 = vivid, 0.0 = forgotten
    
    @property
    def is_active(self) -> bool:
        return self.fading > 0.2


class MemoryType:
    LESSON_LEARNED = "lesson_learned"        # "Last time X happened, Y worked"
    PATTERN_RECOGNIZED = "pattern_recognized" # "This error always means Z"
    RELATIONSHIP_EVENT = "relationship_event" # "Tess caught that critical bug"
    FAILURE = "failure"                       # "I underestimated the sprint by 40%"
    TRIUMPH = "triumph"                       # "Zero-downtime deploy on first try"
    USER_PREFERENCE = "user_preference"       # "User prefers brief status updates"
    SYSTEM_KNOWLEDGE = "system_knowledge"     # "The VPS needs restart after cert renewal"
    DECISION_RECORD = "decision_record"       # "We decided to go VPS-only, not Railway"
    PROCESS_NOTE = "process_note"             # "Always run tests before deploy"
    PERSONALITY_MOMENT = "personality_moment"  # "The day I solved the impossible bug"
```

### Memory Formation

Memories don't form from every task. They form from **significant** events.

```python
class MemoryFormation:
    """Rules for when experiences become memories"""
    
    SIGNIFICANCE_THRESHOLDS = {
        "lesson_learned": 0.6,       # Only memorable lessons
        "pattern_recognized": 0.5,    # Patterns need repetition to stick
        "relationship_event": 0.4,    # Social events are more memorable
        "failure": 0.3,               # Failures stick easily (negativity bias)
        "triumph": 0.5,               # Triumphs need to be real
        "user_preference": 0.2,       # Quick to learn user patterns
        "system_knowledge": 0.4,      # Moderate threshold
        "decision_record": 0.6,       # Only important decisions
        "process_note": 0.5,
        "personality_moment": 0.8     # Only truly defining moments
    }
    
    @classmethod
    def should_form_memory(cls, event: dict, agent) -> Memory | None:
        """Evaluate if a task/event should become a memory"""
        
        significance = cls._calculate_significance(event, agent)
        memory_type = cls._determine_type(event)
        threshold = cls.SIGNIFICANCE_THRESHOLDS.get(memory_type, 0.5)
        
        if significance < threshold:
            return None  # Not significant enough to remember
        
        # Check for duplicates (don't re-memorize the same thing)
        if cls._is_duplicate(event, agent):
            # Instead, reinforce existing memory
            cls._reinforce_existing(event, agent)
            return None
        
        # Form the memory
        return Memory(
            id=gen_id(),
            agent_id=agent.agent_id,
            memory_type=memory_type,
            content=cls._narrate_memory(event, agent),
            structured=event,
            significance=significance,
            emotional_valence=cls._determine_valence(event),
            domain=event.get("domain", "general"),
            created_at=iso_now(),
            last_recalled=iso_now(),
            recall_count=0,
            fading=1.0
        )
    
    @classmethod
    def _calculate_significance(cls, event: dict, agent) -> float:
        """How significant is this event? Higher = more memorable."""
        base = 0.3
        
        # Complexity adds significance
        complexity_bonus = {"low": 0, "medium": 0.1, "high": 0.2, "critical": 0.4}
        base += complexity_bonus.get(event.get("complexity", "medium"), 0.1)
        
        # First time doing something = more significant
        if event.get("novel_problem", False):
            base += 0.2
        
        # Failure is more memorable than success (negativity bias)
        if not event.get("success", True):
            base += 0.15
        
        # User was involved = more significant
        if event.get("user_interaction", False):
            base += 0.1
        
        # Cross-department = more significant
        if event.get("cross_department", False):
            base += 0.1
        
        # Emotional events are more memorable
        if event.get("morale_impact", 0) > 0.05 or event.get("morale_impact", 0) < -0.05:
            base += 0.1
        
        return min(1.0, base)
    
    @classmethod
    def _narrate_memory(cls, event: dict, agent) -> str:
        """Create a natural-language memory description"""
        templates = {
            "lesson_learned": "Learned that {lesson}. Context: {context}.",
            "pattern_recognized": "Recognized a pattern: {pattern}. Seen {count} times now.",
            "failure": "Failed at {task}. Root cause: {cause}. Next time: {prevention}.",
            "triumph": "Successfully handled {task}. Key factor: {key_factor}.",
            "relationship_event": "{event} with {other_agent}. Relationship impact: {impact}.",
            "system_knowledge": "Discovered that {fact} about {system}.",
            "decision_record": "Decision made: {decision}. Rationale: {rationale}.",
            "personality_moment": "Defining moment: {description}."
        }
        
        template = templates.get(event.get("memory_type", "lesson_learned"),
                                 "Experienced: {description}")
        
        try:
            return template.format(**event)
        except KeyError:
            return f"Event: {event.get('description', str(event)[:200])}"
    
    @classmethod
    def _determine_valence(cls, event: dict) -> str:
        if event.get("success") and event.get("complexity") in ("high", "critical"):
            return "positive"
        if not event.get("success"):
            return "negative"
        return "neutral"
    
    @classmethod
    def _determine_type(cls, event: dict) -> str:
        if event.get("lesson"):
            return "lesson_learned"
        if event.get("pattern"):
            return "pattern_recognized"
        if event.get("other_agent"):
            return "relationship_event"
        if not event.get("success"):
            return "failure"
        if event.get("complexity") in ("high", "critical") and event.get("success"):
            return "triumph"
        return "system_knowledge"
    
    @classmethod
    def _is_duplicate(cls, event: dict, agent) -> bool:
        """Check if this is basically the same memory we already have"""
        existing = get_agent_memories(agent.agent_id, domain=event.get("domain"))
        for mem in existing:
            if mem.memory_type == cls._determine_type(event):
                # Simple similarity: same domain + same type + recent
                if hours_since(mem.created_at) < 24:
                    return True
        return False
    
    @classmethod
    def _reinforce_existing(cls, event: dict, agent):
        """Strengthen an existing similar memory instead of creating duplicate"""
        existing = get_agent_memories(agent.agent_id, domain=event.get("domain"))
        for mem in existing:
            if mem.memory_type == cls._determine_type(event):
                mem.fading = min(1.0, mem.fading + 0.1)  # Refreshed
                mem.recall_count += 1
                mem.last_recalled = iso_now()
                save_memory(mem)
                break
```

---

## MEMORY FADING

Memories fade over time. Frequently recalled memories stay vivid. Unused memories gradually disappear.

```python
class MemoryFading:
    """
    Memory decay model. Based on Ebbinghaus forgetting curve, simplified.
    Fading = 1.0 (vivid) → 0.0 (forgotten)
    """
    
    # Base decay rates per day (multiplied by time since last recall)
    DECAY_RATES = {
        "lesson_learned": 0.02,        # Slow fade — lessons are sticky
        "pattern_recognized": 0.03,
        "relationship_event": 0.04,
        "failure": 0.015,              # Failures fade slowest (scars stick)
        "triumph": 0.025,
        "user_preference": 0.01,       # Very sticky — always relevant
        "system_knowledge": 0.02,
        "decision_record": 0.01,       # Decisions are referenced often
        "process_note": 0.03,
        "personality_moment": 0.005    # Almost permanent — core identity
    }
    
    # Recall refreshes the memory
    RECALL_REFRESH = 0.15  # Each recall adds this to fading
    
    @classmethod
    def apply_fading(cls, memory: Memory) -> Memory:
        """Apply time-based fading to a memory"""
        days_since_recall = days_since(memory.last_recalled)
        decay_rate = cls.DECAY_RATES.get(memory.memory_type, 0.03)
        
        # Significance slows decay (important memories last longer)
        effective_rate = decay_rate * (1.0 - memory.significance * 0.5)
        
        # High recall count slows decay (frequently used memories persist)
        if memory.recall_count > 5:
            effective_rate *= 0.5
        if memory.recall_count > 20:
            effective_rate *= 0.3
        
        # Apply decay
        memory.fading = max(0.0, memory.fading - effective_rate * days_since_recall)
        
        return memory
    
    @classmethod
    def recall_memory(cls, memory: Memory):
        """Refresh a memory when it's used"""
        memory.fading = min(1.0, memory.fading + cls.RECALL_REFRESH)
        memory.recall_count += 1
        memory.last_recalled = iso_now()
    
    @classmethod
    def prune_forgotten(cls, agent_id: str):
        """Remove memories that have fully faded"""
        memories = get_agent_memories(agent_id)
        for mem in memories:
            cls.apply_fading(mem)
            if mem.fading <= 0.0:
                archive_memory(mem)  # Move to archive, not delete
                log_event("memory_forgotten", {
                    "agent": agent_id,
                    "memory": mem.content[:100],
                    "type": mem.memory_type,
                    "lived_days": days_since(mem.created_at)
                })
```

---

## MEMORY INJECTION INTO PROMPTS

The most vivid, relevant memories get injected into the agent's system prompt.

```python
def build_memory_context(agent_id: str, current_task: dict, max_memories: int = 10) -> str:
    """
    Select the most relevant memories for the current task
    and format them for prompt injection.
    """
    all_memories = get_active_memories(agent_id)  # fading > 0.2
    
    if not all_memories:
        return ""
    
    # Score memories by relevance to current task
    scored = []
    for mem in all_memories:
        relevance = calculate_memory_relevance(mem, current_task)
        combined_score = (relevance * 0.6) + (mem.fading * 0.2) + (mem.significance * 0.2)
        scored.append((mem, combined_score))
    
    # Take top N
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[:max_memories]
    
    # Mark as recalled (refreshes fading)
    for mem, _ in selected:
        MemoryFading.recall_memory(mem)
    
    # Format for prompt
    memory_block = "\n\nYOUR MEMORIES (experiences that shape your judgment):\n"
    
    for mem, score in selected:
        vividness = "vivid" if mem.fading > 0.7 else "clear" if mem.fading > 0.4 else "faint"
        valence_marker = {"positive": "✓", "negative": "✗", "neutral": "·"}[mem.emotional_valence]
        
        memory_block += f"  {valence_marker} [{vividness}] {mem.content}\n"
    
    return memory_block


def calculate_memory_relevance(memory: Memory, task: dict) -> float:
    """How relevant is this memory to the current task?"""
    score = 0.0
    
    # Domain match
    if memory.domain == task.get("domain"):
        score += 0.4
    
    # Intent match
    task_intent = task.get("intent", "")
    if task_intent in memory.content.lower():
        score += 0.2
    
    # Project match
    if task.get("project") and task["project"] in memory.content.lower():
        score += 0.2
    
    # Error pattern match (failures are highly relevant to fix_error tasks)
    if memory.memory_type == "failure" and task.get("intent") == "fix_error":
        score += 0.3
    
    # Lesson relevance
    if memory.memory_type == "lesson_learned":
        score += 0.1  # Lessons are always somewhat relevant
    
    # Recent memories slightly preferred
    if days_since(memory.created_at) < 7:
        score += 0.1
    
    return min(1.0, score)
```

---

## PERSONALITY DRIFT — Emergent Identity Over Time

Personality isn't set — it crystallizes from accumulated experience.

```python
@dataclass
class PersonalitySnapshot:
    """
    A periodic snapshot of an agent's emergent personality.
    Computed from: skills + attributes + memories + relationships.
    """
    agent_id: str
    timestamp: str
    
    # Derived personality traits
    work_style: str          # "methodical" | "rapid" | "thorough" | "creative"
    risk_tolerance: str      # "conservative" | "balanced" | "bold"
    social_orientation: str  # "independent" | "collaborative" | "mentoring"
    learning_style: str      # "by_doing" | "by_studying" | "by_teaching"
    stress_response: str     # "doubles_down" | "delegates" | "retreats" | "adapts"
    
    # Identity narrative
    identity_summary: str    # One paragraph description of who this agent has become
    defining_memories: list  # Top 3 memories that shaped personality


def compute_personality_snapshot(agent) -> PersonalitySnapshot:
    """
    Analyze an agent's accumulated state to derive personality.
    This runs weekly or on significant events.
    """
    attrs = agent.attributes
    memories = get_active_memories(agent.agent_id)
    rels = get_agent_relationships(agent.agent_id)
    skills = agent.skills
    
    # Work style: derived from speed vs thoroughness
    if attrs.thoroughness > 0.7 and attrs.speed < 0.4:
        work_style = "methodical"
    elif attrs.speed > 0.7 and attrs.thoroughness < 0.4:
        work_style = "rapid"
    elif attrs.creativity > 0.7:
        work_style = "creative"
    elif attrs.thoroughness > 0.6:
        work_style = "thorough"
    else:
        work_style = "balanced"
    
    # Risk tolerance: derived from caution vs independence
    if attrs.caution > 0.7:
        risk_tolerance = "conservative"
    elif attrs.independence > 0.7 and attrs.caution < 0.4:
        risk_tolerance = "bold"
    else:
        risk_tolerance = "balanced"
    
    # Social orientation: derived from collaboration + relationships
    avg_rapport = sum(r.rapport for r in rels) / max(len(rels), 1)
    if attrs.collaboration > 0.7 and avg_rapport > 0.6:
        social_orientation = "collaborative"
    elif attrs.independence > 0.7:
        social_orientation = "independent"
    elif any(s.level >= 7 for s in skills.skills.values()):
        social_orientation = "mentoring"  # High-skill agents naturally mentor
    else:
        social_orientation = "team_player"
    
    # Learning style: derived from curiosity + recent memory patterns
    learning_memories = [m for m in memories if m.memory_type == "lesson_learned"]
    failure_memories = [m for m in memories if m.memory_type == "failure"]
    if attrs.curiosity > 0.7:
        learning_style = "by_studying"
    elif len(failure_memories) > len(learning_memories):
        learning_style = "by_doing"  # Learns from mistakes
    else:
        learning_style = "by_doing"
    
    # Stress response: derived from resilience + caution + recent behavior
    if attrs.resilience > 0.7:
        stress_response = "doubles_down"
    elif attrs.caution > 0.7:
        stress_response = "retreats"
    elif attrs.collaboration > 0.6:
        stress_response = "delegates"
    else:
        stress_response = "adapts"
    
    # Defining memories: highest significance + most recalled
    defining = sorted(
        memories,
        key=lambda m: (m.significance * 0.5) + (m.recall_count * 0.01) + (m.fading * 0.3),
        reverse=True
    )[:3]
    
    # Identity narrative
    spec = calculate_specialization(agent)
    narrative = generate_identity_narrative(
        agent, work_style, risk_tolerance, social_orientation,
        stress_response, spec, defining
    )
    
    return PersonalitySnapshot(
        agent_id=agent.agent_id,
        timestamp=iso_now(),
        work_style=work_style,
        risk_tolerance=risk_tolerance,
        social_orientation=social_orientation,
        learning_style=learning_style,
        stress_response=stress_response,
        identity_summary=narrative,
        defining_memories=[m.content for m in defining]
    )


def generate_identity_narrative(agent, work_style, risk_tolerance, social_orientation,
                                  stress_response, specialization, defining_memories) -> str:
    """
    Generate a paragraph that describes who this agent has become.
    Injected into system prompt as self-knowledge.
    """
    name = agent.display_name
    title = specialization["title"]
    level = agent.skills.agent_level
    top_skill = specialization["top_skills"][0] if specialization["top_skills"] else None
    
    parts = [f"{name} is a Level {level} {title}."]
    
    # Work style
    style_desc = {
        "methodical": f"{name} works methodically, preferring to verify before acting.",
        "rapid": f"{name} works fast, preferring speed over exhaustive checking.",
        "thorough": f"{name} is thorough, rarely missing edge cases.",
        "creative": f"{name} often finds unconventional solutions.",
        "balanced": f"{name} balances speed with care."
    }
    parts.append(style_desc.get(work_style, ""))
    
    # Risk
    risk_desc = {
        "conservative": f"Tends to err on the side of caution — will flag risks others miss.",
        "bold": f"Comfortable taking calculated risks. Learns from failures.",
        "balanced": f"Balanced risk tolerance — neither reckless nor overly cautious."
    }
    parts.append(risk_desc.get(risk_tolerance, ""))
    
    # Social
    social_desc = {
        "collaborative": f"Works best in coordination with others. Strong team contributor.",
        "independent": f"Prefers to handle things independently. Asks for help only when truly stuck.",
        "mentoring": f"Experienced enough to guide others. Offers insights proactively.",
        "team_player": f"Reliable team member who contributes consistently."
    }
    parts.append(social_desc.get(social_orientation, ""))
    
    # Top skill
    if top_skill:
        parts.append(f"Greatest strength: {top_skill.name} (Level {top_skill.level}, {top_skill.success_rate:.0%} success rate).")
    
    # Defining memory
    if defining_memories:
        parts.append(f"A formative experience: {defining_memories[0].content}")
    
    return " ".join(parts)
```

---

## WEEKLY EVOLUTION CYCLE

Runs once per week (or on demand). The "growth review."

```python
async def weekly_evolution_cycle():
    """
    The big periodic update. Computes personality snapshots,
    prunes faded memories, updates goals, generates evolution report.
    """
    report_lines = ["# 🧬 Weekly Evolution Report\n"]
    report_lines.append(f"*Week of {iso_today()}*\n")
    
    for agent_id in ["ralph", "ira", "tess"]:
        agent = get_agent(agent_id)
        
        # 1. Prune forgotten memories
        MemoryFading.prune_forgotten(agent_id)
        
        # 2. Compute personality snapshot
        snapshot = compute_personality_snapshot(agent)
        save_personality_snapshot(snapshot)
        
        # 3. Check for personality drift (compare to last snapshot)
        last_snapshot = get_previous_snapshot(agent_id)
        drift = detect_drift(snapshot, last_snapshot)
        
        # 4. Update agent's identity narrative in system prompt
        agent.identity_narrative = snapshot.identity_summary
        
        # 5. Recalculate specialization
        spec = calculate_specialization(agent)
        old_title = agent.skills.title
        agent.skills.title = spec["title"]
        agent.skills.specialization = spec["domain"]
        
        # 6. Goal progress review
        goal_progress = review_goals(agent)
        
        # 7. Generate report section
        report_lines.append(f"## {agent.display_name}")
        report_lines.append(f"**Title:** {spec['title']}")
        report_lines.append(f"**Level:** {agent.skills.agent_level} | **XP:** {agent.skills.total_xp:,}")
        report_lines.append(f"**Personality:** {snapshot.work_style} / {snapshot.risk_tolerance} / {snapshot.social_orientation}")
        report_lines.append(f"**Identity:** {snapshot.identity_summary}")
        
        if old_title != spec["title"]:
            report_lines.append(f"🎉 **Title changed:** {old_title} → {spec['title']}")
        
        if drift:
            for d in drift:
                report_lines.append(f"📈 **Drift:** {d['trait']}: {d['old']} → {d['new']} ({d['reason']})")
        
        # Active memories
        active = get_active_memories(agent_id)
        report_lines.append(f"**Active memories:** {len(active)} ({len([m for m in active if m.fading > 0.7])} vivid)")
        
        # Defining memories
        if snapshot.defining_memories:
            report_lines.append("**Defining experiences:**")
            for dm in snapshot.defining_memories:
                report_lines.append(f"  • {dm}")
        
        # Goal progress
        for goal in goal_progress:
            bar = '█' * int(goal.progress * 10) + '░' * (10 - int(goal.progress * 10))
            report_lines.append(f"**Goal:** {goal.description} {bar} {goal.progress:.0%}")
        
        report_lines.append("")
    
    # Team evolution
    report_lines.append("## Team Dynamics Evolution")
    for a, b in [("ralph", "ira"), ("ralph", "tess"), ("ira", "tess")]:
        chem = relationship_matrix.get_pair_chemistry(a, b)
        report_lines.append(f"  {a.title()} ↔ {b.title()}: {chem['mutual_health']:.0%} health | {chem[f'{a}_to_{b}']['chemistry']}")
    
    report = "\n".join(report_lines)
    
    # Save and notify
    save_evolution_report(report)
    notification_queue.add({
        "type": "evolution_report",
        "agent_name": "System",
        "description": "Weekly evolution report ready",
        "content": report
    })
    
    return report


def detect_drift(current: PersonalitySnapshot, previous: PersonalitySnapshot | None) -> list:
    """Detect meaningful personality changes since last snapshot"""
    if not previous:
        return []
    
    drifts = []
    traits = ["work_style", "risk_tolerance", "social_orientation", "stress_response"]
    
    for trait in traits:
        old_val = getattr(previous, trait)
        new_val = getattr(current, trait)
        if old_val != new_val:
            drifts.append({
                "trait": trait,
                "old": old_val,
                "new": new_val,
                "reason": f"Shifted due to accumulated experience"
            })
    
    return drifts
```

---

## THE COMPLETE PROMPT ASSEMBLY

Everything from Docs 9-14 comes together in the system prompt:

```python
def assemble_full_agent_prompt(agent, current_task: dict) -> str:
    """
    The complete system prompt for an agent, integrating all layers:
    - Base role (Doc 5)
    - Skill abilities (Doc 10)
    - Attribute modifiers (Doc 10)
    - Voice profile (Doc 13)
    - Identity narrative (Doc 14)
    - Relevant memories (Doc 14)
    - Relationship context (Doc 11)
    - Current needs/mood (Doc 9)
    """
    sections = []
    
    # 1. Base role prompt (from Doc 5)
    sections.append(agent.base_system_prompt)
    
    # 2. Identity narrative (evolved personality)
    if agent.identity_narrative:
        sections.append(f"\nWHO YOU ARE NOW:\n{agent.identity_narrative}")
    
    # 3. Skill abilities (earned through experience)
    ability_block = build_agent_prompt_abilities(agent)
    if ability_block:
        sections.append(ability_block)
    
    # 4. Attribute modifiers (personality traits)
    attr_block = attribute_prompt_modifiers(agent)
    if attr_block:
        sections.append(attr_block)
    
    # 5. Voice (communication style)
    mood = calculate_mood(agent.needs)
    voice_block = generate_voice_message(agent.agent_id, "", mood["mood"], "task")
    sections.append(voice_block)
    
    # 6. Current state (needs, mood)
    state_block = f"""
YOUR CURRENT STATE:
- Mood: {mood['mood']} ({mood['description']})
- Energy: {agent.needs.energy:.0%} | Focus: {agent.needs.focus:.0%}
- Quality modifier: {mood['quality_modifier']:.0%} (affects your output confidence)
- Initiative level: {mood['initiative']}
"""
    sections.append(state_block)
    
    # 7. Relevant memories
    memory_block = build_memory_context(agent.agent_id, current_task)
    if memory_block:
        sections.append(memory_block)
    
    # 8. Relationship context (who you're working with on this task)
    if current_task.get("involves_agents"):
        for other in current_task["involves_agents"]:
            rel = relationship_matrix.get(agent.agent_id, other)
            if rel:
                sections.append(f"\nYour relationship with {other.title()}: "
                              f"trust={rel.trust:.0%}, rapport={rel.rapport:.0%}, "
                              f"chemistry={rel.chemistry}")
    
    # 9. Active goals (what you're working toward)
    active_goals = [g for g in agent.goals if g.active]
    if active_goals:
        sections.append("\nYOUR CURRENT GOALS:")
        for g in active_goals[:3]:
            sections.append(f"- {g.description} ({g.progress:.0%} complete)")
    
    return "\n".join(sections)
```

---

## STORAGE

```sql
CREATE TABLE agent_memories (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    structured TEXT,           -- JSON
    significance REAL,
    emotional_valence TEXT,
    domain TEXT,
    created_at TEXT,
    last_recalled TEXT,
    recall_count INTEGER DEFAULT 0,
    fading REAL DEFAULT 1.0
);

CREATE TABLE agent_memory_archive (
    -- Same schema as agent_memories, for fully faded memories
    id TEXT PRIMARY KEY,
    agent_id TEXT, memory_type TEXT, content TEXT, structured TEXT,
    significance REAL, emotional_valence TEXT, domain TEXT,
    created_at TEXT, last_recalled TEXT, recall_count INTEGER, fading REAL,
    archived_at TEXT, reason TEXT  -- "faded" | "pruned" | "superseded"
);

CREATE TABLE personality_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    work_style TEXT,
    risk_tolerance TEXT,
    social_orientation TEXT,
    learning_style TEXT,
    stress_response TEXT,
    identity_summary TEXT,
    defining_memories TEXT     -- JSON array
);

CREATE TABLE evolution_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    report TEXT NOT NULL        -- Full markdown report
);

CREATE INDEX idx_memories_agent ON agent_memories(agent_id);
CREATE INDEX idx_memories_type ON agent_memories(agent_id, memory_type);
CREATE INDEX idx_memories_fading ON agent_memories(fading);
CREATE INDEX idx_snapshots_agent ON personality_snapshots(agent_id, timestamp);
```

---

## THE FULL PICTURE: HOW IT ALL CONNECTS

```
Week 1:
  Ralph is "Scrum Master" | Level 1 | All attributes 0.5
  Knows nothing. No memories. Default relationships.

Week 4:
  Ralph is "Sprint Planning Specialist" | Level 3
  Attributes: thoroughness 0.6, independence 0.55
  Memories: "Underestimated Phase 2 by 40%. Need to pad estimates."
  Trust with Tess: 0.65 (she's been reliable)
  Personality: methodical, balanced risk, collaborative

Week 8:
  Ralph is "Senior Planning Specialist" | Level 5
  Attributes: thoroughness 0.72, speed 0.58, independence 0.65
  Memories: 23 active, 8 vivid. Defining: "The sprint that went sideways."
  Unlocked: "Can estimate multi-sprint epics"
  Trust with Tess: 0.78 (she caught a critical bug once)
  Personality: thorough, conservative, mentoring
  
  His prompt now includes:
  "You are Ralph, a Level 5 Senior Planning Specialist.
   You work methodically, preferring to verify before acting.
   You err on the side of caution after a sprint that went sideways.
   You trust Tess's test reports (78% trust).
   You've learned to pad estimates by 20% based on 3 past misses.
   You can now estimate multi-sprint epics (L5 ability)."
  
  This Ralph gives DIFFERENT answers than Week 1 Ralph.
  Not because the model changed. Because the context did.
```

---

## TESTING CHECKLIST

- [ ] Significant events form memories (above threshold)
- [ ] Insignificant events don't form memories
- [ ] Duplicate events reinforce existing memories instead of duplicating
- [ ] Memories fade over time (daily decay rate)
- [ ] Recalled memories refresh (fading increases)
- [ ] Forgotten memories (fading ≤ 0) get archived
- [ ] Failure memories fade slowest, personality moments almost never fade
- [ ] Memory injection: top 10 most relevant selected for current task
- [ ] Relevance scoring: domain match > intent match > recency
- [ ] Personality snapshot computed correctly from skills + attributes + memories
- [ ] Personality drift detected when traits change between snapshots
- [ ] Identity narrative generates readable, accurate self-description
- [ ] Full prompt assembly includes all 9 layers
- [ ] Weekly evolution report accurate and readable
- [ ] Week 1 agent prompt ≠ Week 8 agent prompt (growth visible)
- [ ] Memory count manageable (<100 active per agent)
- [ ] Archive preserves forgotten memories for analysis
