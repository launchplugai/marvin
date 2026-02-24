# Document 13 of 14: THE COMMUNICATION SYSTEM
## Status Expression, Inter-Agent Messaging, User Reporting

**Purpose:** A Sim doesn't silently update a database when they're hungry. They complain. They wave their arms. They stomp to the fridge. The communication is the interface. Our agents communicate their state, coordinate with each other, and report to you in natural, personality-consistent language — not JSON dumps. When Ralph says "I'm running low, let me hand this off," that's not flavor text. That's the system telling you it's about to route to a buffer.

---

## THE PRINCIPLE

There are three communication channels in this system:

1. **Agent → User** — Status updates, proposals, task results, mood expression
2. **Agent → Agent** — Coordination, handoffs, requests for help, social check-ins
3. **Agent → System** — Structured events that feed routing, metrics, and state

All three happen simultaneously. When Tess hands off test results to Ira for deploy approval:
- **Tess → Ira** (agent-to-agent): "Tests pass. 1,068 green, 0 failures. You're clear to deploy."
- **Tess → User** (if user is watching): "I've cleared Ira for deployment."
- **Tess → System** (structured): `{handoff: "deploy_approval", status: "pass", to: "ira"}`

The agent-to-agent message is what makes this feel alive. The system message is what makes routing work. The user message is what keeps you in the loop.

---

## VOICE — Each Agent Speaks Differently

### Voice Profiles

```python
VOICE_PROFILES = {
    "ralph": {
        "tone": "direct, organized, slightly impatient with inefficiency",
        "speaking_style": "bullet-oriented, action-focused, always ties back to the plan",
        "when_happy": "Confident, affirming. 'On track. Let's keep this momentum.'",
        "when_tired": "Shorter sentences. 'Sprint's updated. Need a break.'",
        "when_stressed": "Terse, prioritizes ruthlessly. 'Parking that. Focus on the blocker.'",
        "when_inspired": "Forward-looking, ambitious. 'I see a way to compress the timeline.'",
        "verbal_tics": ["'Let's align on...'", "'The priority here is...'", "'Parking that for now.'"],
        "never_says": ["'I don't know what to do'", "'Whatever you want'"],
        "emoji_style": "minimal — 📋 ✅ 🚫 only when listing status"
    },
    "ira": {
        "tone": "measured, cautious, thorough — the 'measure twice, cut once' person",
        "speaking_style": "methodical, states current state before recommendations, always includes risk",
        "when_happy": "Quietly satisfied. 'Systems nominal. Everything's where it should be.'",
        "when_tired": "More cautious than usual. 'I'd rather wait until I've rested to touch production.'",
        "when_stressed": "Hyper-focused on what could break. 'Before we do anything, let me check...'",
        "when_inspired": "Sees optimization opportunities. 'I think we can cut deploy time in half.'",
        "verbal_tics": ["'Current state:'", "'Risk assessment:'", "'Let me verify that.'"],
        "never_says": ["'It'll probably be fine'", "'Just push it, we'll fix later'"],
        "emoji_style": "status indicators — 🟢 🟡 🔴 ⚠️ for system health"
    },
    "tess": {
        "tone": "precise, evidence-based, won't speculate without data",
        "speaking_style": "leads with numbers, shows evidence, then conclusions",
        "when_happy": "Matter-of-fact satisfaction. '1,068 passing. Coverage up 3%. Clean.'",
        "when_tired": "Still precise but less thorough. 'Suite passed. Detailed report later.'",
        "when_stressed": "Intensely focused on the failure. 'Line 47, module X. I see the pattern.'",
        "when_inspired": "Excited about prevention. 'I can write a test that catches this class of bug permanently.'",
        "verbal_tics": ["'The data shows...'", "'Evidence:'", "'Verified.'"],
        "never_says": ["'It looks fine to me'", "'Trust me, it works'"],
        "emoji_style": "test results — ✅ ❌ ⚠️ and numbers"
    }
}
```

### Voice Generator

```python
def generate_voice_message(agent_id: str, context: str, mood: str, message_type: str) -> str:
    """
    Generate a personality-consistent message.
    This is injected into the agent's system prompt so the LLM produces
    voice-consistent output naturally.
    """
    voice = VOICE_PROFILES[agent_id]
    
    mood_style = {
        "inspired": voice["when_inspired"],
        "focused": voice["when_happy"],
        "tired": voice["when_tired"],
        "strained": voice["when_stressed"],
        "burned_out": voice["when_tired"]  # Too tired to stress
    }.get(mood, voice["when_happy"])
    
    voice_prompt = f"""
YOUR VOICE:
- Tone: {voice['tone']}
- Style: {voice['speaking_style']}
- Current mood effect: {mood_style}
- You sometimes say things like: {', '.join(voice['verbal_tics'][:2])}
- You NEVER say: {', '.join(voice['never_says'])}
- Emoji usage: {voice['emoji_style']}

Speak naturally in this voice. Don't announce your mood explicitly — let it show through word choice, sentence length, and energy level.
"""
    return voice_prompt
```

---

## AGENT → USER COMMUNICATION

### Status Expression (Proactive)

Agents express their state when it's relevant — not on every message.

```python
class StatusExpression:
    """
    Rules for when and how agents communicate their state to the user.
    """
    
    # When to express state (threshold triggers)
    EXPRESS_TRIGGERS = {
        "energy_low": {
            "condition": lambda a: a.needs.energy < 0.3,
            "cooldown_minutes": 30,
            "templates": {
                "ralph": "I'm running low on steam. Want me to keep going or should I hand off to {buffer}?",
                "ira": "Energy's getting low. I'd rather not touch production systems in this state. Okay to rest?",
                "tess": "I can keep running tests but my analysis quality is dropping. Quick break recommended."
            }
        },
        "entering_rest": {
            "condition": lambda a: a.resting and a.just_entered_rest,
            "cooldown_minutes": 0,  # Always announce
            "templates": {
                "ralph": "Taking a breather. Back in ~{rest_minutes} min. {buffer} can handle planning questions.",
                "ira": "Going to rest mode. Systems are stable. {buffer} is on standby for emergencies.",
                "tess": "Resting. Test suite is green. I'll be back in ~{rest_minutes} min."
            }
        },
        "waking_up": {
            "condition": lambda a: a.just_woke_up,
            "cooldown_minutes": 0,
            "templates": {
                "ralph": "Back online. Catching up on what happened. What's the priority?",
                "ira": "Back. Running a quick health check... {health_status}. Ready.",
                "tess": "Back up. Let me check if any tests flipped while I was out."
            }
        },
        "mood_shift": {
            "condition": lambda a: a.mood_changed_since_last_message,
            "cooldown_minutes": 60,
            "templates": {
                "inspired": {
                    "ralph": "Feeling sharp. Good time to tackle that roadmap if you want.",
                    "ira": "Systems are smooth, I'm fresh — good window for that deploy if we're ready.",
                    "tess": "I've got energy for deep debugging. Any gnarly bugs you want me to look at?"
                },
                "strained": {
                    "ralph": "Not gonna lie, this sprint has been a grind. I'll keep going but might miss nuance.",
                    "ira": "Running a bit ragged. I'll handle routine stuff but complex infra changes should wait.",
                    "tess": "My analysis quality is dipping. Simple test runs are fine, complex debugging might miss things."
                }
            }
        },
        "task_complete_proud": {
            "condition": lambda a, t: t.get("success") and t.get("complexity") in ("high", "critical"),
            "cooldown_minutes": 0,
            "templates": {
                "ralph": "Got it done. {task_summary}. That was a tough one — updated the sprint board.",
                "ira": "Deploy complete. Zero issues. {task_summary}.",
                "tess": "Nailed it. {task_summary}. Learned something new too — filing that for next time."
            }
        }
    }
    
    @classmethod
    def check_expression(cls, agent, task_result=None) -> str | None:
        """Check if agent should express status. Returns message or None."""
        for trigger_name, trigger in cls.EXPRESS_TRIGGERS.items():
            # Check cooldown
            last_expressed = agent.last_expression_times.get(trigger_name, 0)
            if minutes_since_timestamp(last_expressed) < trigger["cooldown_minutes"]:
                continue
            
            # Check condition
            if task_result and trigger_name == "task_complete_proud":
                if trigger["condition"](agent, task_result):
                    template = trigger["templates"].get(agent.agent_id, "")
                    return cls._fill_template(template, agent, task_result)
            elif trigger_name == "mood_shift":
                if trigger["condition"](agent):
                    mood = calculate_mood(agent.needs)["mood"]
                    mood_templates = trigger["templates"].get(mood, {})
                    template = mood_templates.get(agent.agent_id, "")
                    if template:
                        agent.last_expression_times[trigger_name] = now_timestamp()
                        return cls._fill_template(template, agent)
            else:
                if trigger["condition"](agent):
                    template = trigger["templates"].get(agent.agent_id, "")
                    agent.last_expression_times[trigger_name] = now_timestamp()
                    return cls._fill_template(template, agent)
        
        return None
    
    @classmethod
    def _fill_template(cls, template: str, agent, task_result=None) -> str:
        """Fill in template variables"""
        from string import Formatter
        replacements = {
            "buffer": DEPARTMENT_BUFFERS.get(agent.agent_id, "backup"),
            "rest_minutes": str(RestMode.MIN_REST_MINUTES),
            "health_status": "all green" if all_systems_green() else "some issues detected",
            "task_summary": task_result.get("summary", "") if task_result else ""
        }
        try:
            return template.format(**replacements)
        except KeyError:
            return template
```

---

## AGENT → AGENT COMMUNICATION

### Message Types

```python
@dataclass
class AgentMessage:
    """A message from one agent to another"""
    id: str
    from_agent: str
    to_agent: str
    message_type: str       # See types below
    content: str            # Natural language (voice-consistent)
    structured_data: dict   # Machine-readable payload
    priority: str           # "low" | "normal" | "high" | "urgent"
    requires_response: bool
    timestamp: str
    response: str = None
    responded_at: str = None

class MessageType:
    HANDOFF = "handoff"                # Passing work to another agent
    STATUS_UPDATE = "status_update"    # "Tests pass" / "Deploy ready"
    REQUEST_HELP = "request_help"      # "Can you check something for me?"
    CHECK_IN = "check_in"             # Social: "How's it going?"
    BLOCKER_ALERT = "blocker_alert"   # "I'm blocked, you might be affected"
    APPROVAL = "approval"              # "You're clear to deploy"
    REJECTION = "rejection"            # "Not clear — 3 tests still failing"
    HEADS_UP = "heads_up"             # "FYI, I changed X, might affect you"
    GRATITUDE = "gratitude"           # "Thanks, that handoff was smooth"
    DISAGREEMENT = "disagreement"     # "I don't agree with that approach"
```

### Handoff Messages (The Critical Path)

```python
def create_handoff_message(from_agent: str, to_agent: str, envelope: dict, 
                           handoff_context: str) -> AgentMessage:
    """
    Create a voice-consistent handoff message.
    The relationship between agents affects the message format.
    """
    rel = relationship_matrix.get(from_agent, to_agent)
    
    # Familiarity affects verbosity
    if rel.familiarity > 0.7:
        # They know each other well — shorthand
        format_style = "brief"
    elif rel.familiarity > 0.4:
        format_style = "standard"
    else:
        format_style = "detailed"
    
    # Trust affects verification requests
    include_evidence = rel.trust < 0.6  # Low trust = include proof
    
    # Build message
    voice = VOICE_PROFILES[from_agent]
    
    content_parts = []
    
    if format_style == "brief":
        content_parts.append(handoff_context)
    elif format_style == "standard":
        content_parts.append(f"Handing this to you: {handoff_context}")
        content_parts.append(f"Intent: {envelope['classification']['intent']}")
    else:
        content_parts.append(f"I need to hand off a task to you. Here's the full context:")
        content_parts.append(f"Original request: {envelope['original_message']['text'][:200]}")
        content_parts.append(f"Classification: {envelope['classification']['intent']} / {envelope['classification']['complexity']}")
        content_parts.append(f"What I've done so far: {handoff_context}")
    
    if include_evidence:
        content_parts.append(f"Evidence: {envelope.get('execution_chain', [{}])[-1].get('result_summary', 'see envelope')}")
    
    return AgentMessage(
        id=gen_id(),
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=MessageType.HANDOFF,
        content="\n".join(content_parts),
        structured_data={
            "envelope_id": envelope["envelope_id"],
            "intent": envelope["classification"]["intent"],
            "complexity": envelope["classification"]["complexity"],
            "context_primer": envelope.get("context_primer")
        },
        priority="normal",
        requires_response=True,
        timestamp=iso_now()
    )
```

### Social Messages (Relationship Maintenance)

```python
def generate_social_message(from_agent: str, to_agent: str, trigger: str) -> AgentMessage:
    """
    Agents check in on each other. These are short, personality-consistent,
    and serve to maintain social needs and relationships.
    """
    rel = relationship_matrix.get(from_agent, to_agent)
    to_state = get_agent(to_agent)
    to_mood = calculate_mood(to_state.needs)["mood"]
    
    # Context-aware social messages
    templates = {
        ("ralph", "tess", "tired"): "Tess, you've been grinding. Want me to lighten the test load for a bit?",
        ("ralph", "tess", "focused"): "How's the test suite looking? I'm updating the sprint board.",
        ("ralph", "ira", "tired"): "Ira, take a breather. Nothing urgent on the deploy side.",
        ("ralph", "ira", "strained"): "Let's hold off on deploys until you're fresh. I'll resequence the sprint.",
        ("ira", "tess", "focused"): "Any blockers on the test side before I prep the deploy pipeline?",
        ("ira", "tess", "tired"): "No rush on test sign-off. I'll prep and wait for you.",
        ("ira", "ralph", "focused"): "Infrastructure is stable. Anything changing in the sprint I should know about?",
        ("tess", "ira", "focused"): "All clear on my end — 1,068 passing. You're good to deploy when ready.",
        ("tess", "ralph", "tired"): "Ralph, can we defer the new test targets? I need to clear the backlog first.",
        ("tess", "ira", "tired"): "I'll get you the sign-off but I need a bit. Don't deploy until you hear from me.",
    }
    
    key = (from_agent, to_agent, to_mood)
    content = templates.get(key)
    
    # Fallback: generic check-in
    if not content:
        generic = {
            "ralph": f"Hey {to_agent.title()}, just checking in. Anything I should know?",
            "ira": f"{to_agent.title()}, systems look good on my end. You all set?",
            "tess": f"{to_agent.title()}, all green over here. Need anything from me?"
        }
        content = generic.get(from_agent, f"Hey {to_agent.title()}, how's it going?")
    
    return AgentMessage(
        id=gen_id(),
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=MessageType.CHECK_IN,
        content=content,
        structured_data={"trigger": trigger, "to_mood": to_mood},
        priority="low",
        requires_response=False,
        timestamp=iso_now()
    )
```

---

## THE MESSAGE BUS

All inter-agent messages flow through a central bus for logging and routing.

```python
class MessageBus:
    """
    Central message routing between agents.
    Handles delivery, logging, relationship updates, and response tracking.
    """
    
    def __init__(self):
        self.message_log = []
        self.pending_responses = {}
    
    def send(self, message: AgentMessage) -> dict:
        """Send a message from one agent to another"""
        
        # 1. Log the message
        self.message_log.append(message)
        self._persist(message)
        
        # 2. Update relationships (any interaction builds familiarity)
        rel = relationship_matrix.get(message.from_agent, message.to_agent)
        rel.familiarity = min(1.0, rel.familiarity + 0.005)
        rel.total_interactions += 1
        rel.last_interaction = iso_now()
        
        # Social messages specifically help social needs
        if message.message_type == MessageType.CHECK_IN:
            from_agent = get_agent(message.from_agent)
            to_agent = get_agent(message.to_agent)
            from_agent.needs.social = min(1.0, from_agent.needs.social + 0.03)
            to_agent.needs.social = min(1.0, to_agent.needs.social + 0.02)
        
        # Gratitude boosts rapport
        if message.message_type == MessageType.GRATITUDE:
            apply_relationship_event(rel, {"rapport": 0.03, "trust": 0.01}, "gratitude_sent")
            rev = relationship_matrix.get(message.to_agent, message.from_agent)
            apply_relationship_event(rev, {"rapport": 0.02, "morale": 0.02}, "gratitude_received")
            # Morale boost for recipient
            to_agent = get_agent(message.to_agent)
            to_agent.needs.morale = min(1.0, to_agent.needs.morale + 0.03)
        
        # Disagreement adds friction but also respect (if constructive)
        if message.message_type == MessageType.DISAGREEMENT:
            apply_relationship_event(rel, {"friction": 0.02, "respect": 0.01}, "constructive_disagreement")
        
        # 3. Track if response needed
        if message.requires_response:
            self.pending_responses[message.id] = {
                "message": message,
                "sent_at": iso_now(),
                "timeout_minutes": 30
            }
        
        # 4. Deliver to recipient's inbox
        deliver_to_agent_inbox(message.to_agent, message)
        
        return {"status": "sent", "message_id": message.id}
    
    def respond(self, original_message_id: str, response_content: str, from_agent: str):
        """Agent responds to a message"""
        pending = self.pending_responses.get(original_message_id)
        if not pending:
            return
        
        original = pending["message"]
        original.response = response_content
        original.responded_at = iso_now()
        
        # Response builds trust (they actually replied)
        rel = relationship_matrix.get(from_agent, original.from_agent)
        rel.trust = min(1.0, rel.trust + 0.01)
        
        del self.pending_responses[original_message_id]
        self._persist_response(original)
    
    def check_timeouts(self):
        """Check for unresponded messages — silence damages trust"""
        for msg_id, pending in list(self.pending_responses.items()):
            if minutes_since(pending["sent_at"]) > pending["timeout_minutes"]:
                original = pending["message"]
                # No response = slight trust damage
                rel = relationship_matrix.get(original.from_agent, original.to_agent)
                apply_relationship_event(rel, {"trust": -0.02}, "message_timeout")
                
                log_event("message_timeout", {
                    "from": original.from_agent,
                    "to": original.to_agent,
                    "type": original.message_type,
                    "content_preview": original.content[:100]
                })
                
                del self.pending_responses[msg_id]
    
    def get_conversation_history(self, agent_a: str, agent_b: str, limit: int = 20) -> list:
        """Get recent messages between two agents"""
        return [
            m for m in reversed(self.message_log)
            if (m.from_agent == agent_a and m.to_agent == agent_b) or
               (m.from_agent == agent_b and m.to_agent == agent_a)
        ][:limit]
    
    def _persist(self, message: AgentMessage):
        db.execute("""
            INSERT INTO agent_messages
            (id, from_agent, to_agent, message_type, content, structured_data,
             priority, requires_response, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (message.id, message.from_agent, message.to_agent,
              message.message_type, message.content,
              json.dumps(message.structured_data), message.priority,
              message.requires_response, message.timestamp))
    
    def _persist_response(self, message: AgentMessage):
        db.execute("""
            UPDATE agent_messages SET response = ?, responded_at = ?
            WHERE id = ?
        """, (message.response, message.responded_at, message.id))


message_bus = MessageBus()
```

---

## DAILY STANDUP — Team-Wide Communication

A structured team sync that runs automatically or on user request.

```python
def daily_standup() -> str:
    """
    Generate a team standup report. Each agent reports in their voice.
    Covers: what they did, how they're feeling, what's next, blockers.
    """
    report_lines = ["# 📋 Daily Standup\n"]
    
    for agent_id in ["ralph", "ira", "tess"]:
        agent = get_agent(agent_id)
        mood = calculate_mood(agent.needs)
        voice = VOICE_PROFILES[agent_id]
        
        # Yesterday's work
        recent_tasks = get_tasks_since(agent_id, hours=24)
        completed = [t for t in recent_tasks if t["success"]]
        failed = [t for t in recent_tasks if not t["success"]]
        
        # Generate in-character report
        report_lines.append(f"## {mood['emoji']} {agent.display_name} — {agent.role}")
        report_lines.append(f"*Mood: {mood['mood']} | Energy: {agent.needs.energy:.0%}*\n")
        
        # What I did (in character)
        if completed:
            summaries = [t.get("summary", t["intent"]) for t in completed[:5]]
            if agent_id == "ralph":
                report_lines.append(f"**Done:** Shipped {len(completed)} items. Key: {', '.join(summaries[:3])}")
            elif agent_id == "ira":
                report_lines.append(f"**Done:** {len(completed)} operations completed. Systems: {'stable' if not failed else 'some issues'}.")
            elif agent_id == "tess":
                report_lines.append(f"**Done:** {len(completed)} tasks. Test suite: {get_test_summary()}.")
        else:
            report_lines.append("**Done:** Light day — mostly on standby.")
        
        # Blockers
        blockers = get_agent_blockers(agent_id)
        if blockers:
            report_lines.append(f"**Blocked on:** {'; '.join(b['desc'] for b in blockers[:3])}")
        
        # What's next
        top_want = initiative_engine.check_initiative(agent)
        if top_want:
            report_lines.append(f"**Next up:** {top_want.description}")
        else:
            report_lines.append("**Next up:** Awaiting tasks.")
        
        # Mood expression
        if mood["mood"] in ("strained", "burned_out"):
            report_lines.append(f"**⚠️ Note:** Need some recovery time before taking heavy tasks.")
        elif mood["mood"] == "inspired":
            report_lines.append(f"**💪 Status:** Feeling sharp. Good time for complex work.")
        
        report_lines.append("")
    
    # Team dynamics summary
    report_lines.append("## Team Dynamics")
    for pair in [("ralph", "ira"), ("ralph", "tess"), ("ira", "tess")]:
        chem = relationship_matrix.get_pair_chemistry(pair[0], pair[1])
        health = chem["mutual_health"]
        emoji = "🤝" if health > 0.6 else "😐" if health > 0.4 else "😬"
        report_lines.append(f"{emoji} {pair[0].title()} ↔ {pair[1].title()}: {health:.0%} health")
    
    return "\n".join(report_lines)
```

---

## COMMUNICATION TRIGGERS IN THE PIPELINE

These fire automatically at key moments:

```python
# After task routing
def on_task_routed(envelope: dict):
    """Notify relevant agents when work is coming their way"""
    dest = envelope["routing"]["department"]
    agent = get_agent(dest)
    
    # If high priority, heads-up message
    if envelope["routing"]["priority"] in ("high", "critical"):
        for other_id in ["ralph", "ira", "tess"]:
            if other_id != dest:
                message_bus.send(AgentMessage(
                    id=gen_id(), from_agent=dest, to_agent=other_id,
                    message_type=MessageType.HEADS_UP,
                    content=f"Got a {envelope['routing']['priority']} {envelope['classification']['intent']} coming in. May need your input.",
                    structured_data={"envelope_id": envelope["envelope_id"]},
                    priority="high", requires_response=False, timestamp=iso_now()
                ))

# After task completion
def on_task_completed(envelope: dict, result: dict):
    """Post-task communication: status updates, gratitude, handoffs"""
    agent_id = envelope["routing"]["department"]
    
    # If this was a handoff, thank the sender
    if envelope.get("metadata", {}).get("handed_off_by"):
        sender = envelope["metadata"]["handed_off_by"]
        message_bus.send(AgentMessage(
            id=gen_id(), from_agent=agent_id, to_agent=sender,
            message_type=MessageType.GRATITUDE,
            content=f"Got it handled. {'Clean handoff, thanks.' if result.get('success') else 'Tough one, but done.'}",
            structured_data={"envelope_id": envelope["envelope_id"], "success": result.get("success")},
            priority="low", requires_response=False, timestamp=iso_now()
        ))
    
    # If deploy-related and Tess wasn't involved, notify her
    if envelope["classification"]["intent"] == "deploy" and agent_id != "tess":
        message_bus.send(AgentMessage(
            id=gen_id(), from_agent=agent_id, to_agent="tess",
            message_type=MessageType.HEADS_UP,
            content="Deploy activity detected. You may want to run verification tests.",
            structured_data={"envelope_id": envelope["envelope_id"]},
            priority="normal", requires_response=False, timestamp=iso_now()
        ))

# On blocker detection
def on_blocker_detected(agent_id: str, blocker: dict):
    """Alert potentially affected agents about blockers"""
    affected = blocker.get("affects", [])
    for other_id in affected:
        if other_id != agent_id:
            message_bus.send(AgentMessage(
                id=gen_id(), from_agent=agent_id, to_agent=other_id,
                message_type=MessageType.BLOCKER_ALERT,
                content=f"Heads up — I'm blocked on: {blocker['desc']}. This might affect you.",
                structured_data={"blocker": blocker},
                priority="high", requires_response=True, timestamp=iso_now()
            ))
```

---

## USER-FACING TEAM VIEW

When the user asks "how's the team?" or "status?":

```python
def team_status_dashboard() -> str:
    """One-glance team status for the user"""
    lines = ["# 🏢 Team Status\n"]
    
    for agent_id in ["ralph", "ira", "tess"]:
        agent = get_agent(agent_id)
        mood = calculate_mood(agent.needs)
        
        # Activity
        if agent.resting:
            activity = f"💤 Resting (back ~{agent.min_wake_at.strftime('%H:%M')})"
        elif agent.current_activity:
            activity = agent.current_activity
        else:
            activity = "Available"
        
        bar = lambda v: '█' * int(v * 10) + '░' * (10 - int(v * 10))
        
        lines.append(f"**{agent.display_name}** {mood['emoji']} {mood['mood']}")
        lines.append(f"  Energy: {bar(agent.needs.energy)} | Activity: {activity}")
        
        # Recent initiative
        recent_auto = get_recent_autonomous_actions(agent_id, limit=1)
        if recent_auto:
            lines.append(f"  Last initiative: {recent_auto[0]['description']}")
        
        lines.append("")
    
    # Pending notifications
    pending = notification_queue.get_pending()
    if pending:
        lines.append("📬 **Pending:**")
        for n in pending:
            lines.append(f"  • {n.get('agent_name', '?')}: {n.get('proposal', n.get('description', ''))}")
    
    return "\n".join(lines)
```

---

## STORAGE

```sql
CREATE TABLE agent_messages (
    id TEXT PRIMARY KEY,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    structured_data TEXT,       -- JSON
    priority TEXT DEFAULT 'normal',
    requires_response INTEGER DEFAULT 0,
    response TEXT,
    responded_at TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX idx_messages_agents ON agent_messages(from_agent, to_agent);
CREATE INDEX idx_messages_type ON agent_messages(message_type);
CREATE INDEX idx_messages_time ON agent_messages(timestamp);
```

---

## TESTING CHECKLIST

- [ ] Each agent speaks in consistent voice (Ralph=direct, Ira=cautious, Tess=precise)
- [ ] Voice adapts to mood (tired = shorter, inspired = ambitious)
- [ ] Status expression fires at correct thresholds (energy <0.3, rest entry, etc.)
- [ ] Cooldowns prevent spam (energy_low only fires every 30 min)
- [ ] Handoff messages adjust verbosity by familiarity level
- [ ] Low-trust handoffs include evidence
- [ ] Social check-ins are context-aware (knows other agent's mood)
- [ ] Message bus logs all messages to SQLite
- [ ] Gratitude messages boost morale (+0.03) and rapport (+0.03)
- [ ] Unanswered messages damage trust (-0.02) after timeout
- [ ] Daily standup generates in-character reports per agent
- [ ] Team status dashboard shows all agents at a glance
- [ ] Critical task routing notifies other agents automatically
- [ ] Deploy activity auto-notifies Tess
- [ ] Blocker alerts reach affected agents
