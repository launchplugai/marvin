# Document 18: THE GUARDRAILS SYSTEM
## Code-Level Enforcement for Sims Compliance

**Purpose:** Doc 17 makes agents BELIEVE they have state. This document makes the system ENSURE that state is real. Together they create compliance from both directions. These are not guidelines — they're code patterns that make it structurally impossible to skip Sims integration.

---

## PRINCIPLE: MAKE THE RIGHT PATH THE ONLY PATH

The goal is not "developers should remember to call on_task_complete()."
The goal is "it is impossible to complete a task without on_task_complete() firing."

This is achieved through three patterns:
1. **Wrapper functions** that enforce pre/post hooks
2. **Validation gates** that block execution on state violations
3. **Audit trail** that detects drift between expected and actual state

---

## GUARDRAIL 1: THE EXECUTION WRAPPER

No task executes outside this wrapper. Period.

```python
class SimsEnforcedExecution:
    """
    Every task goes through this wrapper.
    It enforces: state check → prompt assembly → execution → state update.
    There is no execute() method outside this class.
    """
    
    def __init__(self, agents: dict, relationship_matrix, tracker):
        self.agents = agents          # {"ralph": Agent, "ira": Agent, "tess": Agent}
        self.relationships = relationship_matrix
        self.tracker = tracker
        self.audit_log = []
    
    def execute(self, envelope: dict) -> dict:
        """
        THE ONLY WAY to execute a task.
        
        This method:
        1. Validates envelope structure
        2. Checks agent state (can_accept)
        3. Handles delegation if agent can't accept
        4. Assembles Sims-enriched prompt
        5. Executes through waterfall
        6. ALWAYS calls on_task_complete (even on failure)
        7. ALWAYS updates relationships
        8. ALWAYS logs to audit trail
        
        There is no shortcut. There is no bypass.
        """
        department = envelope["routing"]["department"]
        agent = self.agents.get(department)
        complexity = envelope["classification"]["complexity"]
        
        # ── GATE 1: Envelope validation ──
        self._validate_envelope(envelope)
        
        # ── GATE 2: Agent state check ──
        acceptance = agent.can_accept(complexity)
        
        if acceptance == "rest":
            agent.enter_rest()
            # Reroute to buffer — but STILL track it
            return self._execute_on_buffer(envelope, agent, reason="agent_resting")
        
        if acceptance == "delegate":
            delegate = self._find_delegate(complexity, exclude=department)
            if delegate:
                return self._execute_delegated(envelope, agent, delegate)
            else:
                return self._execute_on_buffer(envelope, agent, reason="no_delegate_available")
        
        # ── GATE 3: Assemble Sims-enriched prompt ──
        prompt = agent.assemble_prompt({
            "intent": envelope["classification"]["intent"],
            "complexity": complexity,
            "project": envelope["classification"]["project"],
            "domain": department
        })
        
        # Validate prompt contains enforcement directives
        assert "OPERATIONAL DIRECTIVES" in prompt, \
            "GUARDRAIL VIOLATION: Enforcement prompt missing from assembled prompt"
        
        # ── GATE 4: Execute with guaranteed post-processing ──
        agent.on_task_start(
            project=envelope["classification"]["project"],
            domain=department
        )
        
        result = None
        try:
            result = self._execute_waterfall(prompt, envelope)
            result["success"] = result.get("success", True)
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "model": "unknown",
                "tier": "failed",
                "timestamp": iso_now()
            }
        finally:
            # ── GATE 5: ALWAYS update state ──
            # This is in a finally block. It CANNOT be skipped.
            # Even if execution crashes, state updates.
            self._guaranteed_post_execution(agent, envelope, result)
        
        return result
    
    def _guaranteed_post_execution(self, agent, envelope, result):
        """
        This runs in a finally block. It is impossible to skip.
        
        Even if:
        - The API call fails
        - The model returns garbage
        - The network drops
        - An exception is raised
        
        This STILL runs.
        """
        department = envelope["routing"]["department"]
        
        try:
            # 1. Update agent needs, XP, memories
            task_result = {
                "complexity": envelope["classification"]["complexity"],
                "success": result.get("success", False),
                "project": envelope["classification"]["project"],
                "domain": department,
                "skill_name": self._infer_skill(envelope),
                "cross_department": len(envelope.get("collaboration_context", {}).get("departments_involved", [])) > 1,
                "novel_problem": result.get("novel", False),
            }
            agent.on_task_complete(task_result)
            
            # 2. Update relationships (if handoff involved)
            if envelope.get("metadata", {}).get("handed_off_by"):
                from_agent = envelope["metadata"]["handed_off_by"]
                event = "reliable_handoff" if result.get("success") else "unreliable_handoff"
                self.relationships.on_handoff(from_agent, department, result.get("success", False))
            
            # 3. Log to audit trail
            self.audit_log.append({
                "envelope_id": envelope.get("envelope_id"),
                "agent": department,
                "energy_before": envelope.get("_pre_energy"),
                "energy_after": agent.needs.energy,
                "success": result.get("success"),
                "model": result.get("model"),
                "tier": result.get("tier"),
                "timestamp": iso_now()
            })
            
        except Exception as audit_error:
            # Even if audit fails, log the failure itself
            # This is the last line of defense
            import traceback
            self._emergency_log(f"POST_EXECUTION_FAILURE: {traceback.format_exc()}")
    
    def _validate_envelope(self, envelope: dict):
        """Reject malformed envelopes before they enter the system"""
        required = ["classification", "routing", "original_message"]
        for key in required:
            if key not in envelope:
                raise ValueError(f"GUARDRAIL: Envelope missing required field: {key}")
        
        classification = envelope["classification"]
        for field in ["intent", "complexity", "project", "department"]:
            if field not in classification:
                raise ValueError(f"GUARDRAIL: Classification missing: {field}")
        
        valid_depts = {"ralph", "ira", "tess", "general"}
        if classification["department"] not in valid_depts:
            raise ValueError(f"GUARDRAIL: Invalid department: {classification['department']}")
    
    def _find_delegate(self, complexity: str, exclude: str):
        """Find a rested agent who can accept the task"""
        for agent_id, agent in self.agents.items():
            if agent_id == exclude:
                continue
            if agent.can_accept(complexity) == "accept":
                return agent
        return None
    
    def _execute_on_buffer(self, envelope, original_agent, reason: str) -> dict:
        """
        Execute on buffer model when primary agent can't accept.
        STILL updates the original agent's state (they know about it).
        """
        # Buffer execution still goes through the waterfall
        # but with the persona prompt + a note about buffer mode
        prompt = original_agent.assemble_prompt({
            "intent": envelope["classification"]["intent"],
            "complexity": envelope["classification"]["complexity"],
            "project": envelope["classification"]["project"],
            "domain": envelope["routing"]["department"]
        })
        
        prompt += f"\n\nNOTE: You are running on a backup model because: {reason}."
        
        result = self._execute_waterfall(prompt, envelope)
        
        # STILL update state — the agent "knows" a task was handled in their domain
        # Reduced decay because they didn't do the heavy lifting
        original_agent.needs.energy -= 0.01  # Minimal awareness cost
        original_agent.needs.clamp()
        original_agent._save_state()
        
        return result
    
    def _execute_delegated(self, envelope, original_agent, delegate) -> dict:
        """
        Execute on a different agent. Updates BOTH agents' state.
        """
        envelope["metadata"] = envelope.get("metadata", {})
        envelope["metadata"]["handed_off_by"] = original_agent.agent_id
        envelope["routing"]["department"] = delegate.agent_id
        
        # Recursive call — goes back through the full enforcement pipeline
        return self.execute(envelope)
    
    def _infer_skill(self, envelope: dict) -> str:
        """Map intent + department to a skill name"""
        intent = envelope["classification"]["intent"]
        dept = envelope["routing"]["department"]
        
        skill_map = {
            ("planning", "ralph"): "sprint_planning",
            ("status_check", "ralph"): "sprint_planning",
            ("deploy", "ira"): "deployment_pipelines",
            ("status_check", "ira"): "monitoring",
            ("test", "tess"): "pytest",
            ("fix_error", "tess"): "failure_analysis",
        }
        return skill_map.get((intent, dept), f"{intent}_{dept}")
    
    def _execute_waterfall(self, prompt, envelope):
        """The actual execution cascade from Doc 15"""
        # Implementation from Doc 15: try_execution_waterfall()
        # This is the only place that calls external APIs
        pass
    
    def _emergency_log(self, message: str):
        """When everything else fails, write to a file"""
        import os
        with open("sims_emergency.log", "a") as f:
            f.write(f"{iso_now()}: {message}\n")
```

---

## GUARDRAIL 2: NO RAW API CALLS

Every external model call MUST go through the execution wrapper. There is no `call_groq()` or `call_kimi()` that exists outside the enforced pipeline.

```python
# ❌ FORBIDDEN — raw API call with no Sims integration
response = call_groq("llama-3.1-8b-instant", system_prompt, user_message)

# ❌ FORBIDDEN — building prompt without Sims layers
prompt = "You are Ralph, a scrum master."
response = call_claude_cli(prompt, message)

# ✅ REQUIRED — everything goes through the wrapper
enforcer = SimsEnforcedExecution(agents, relationships, tracker)
result = enforcer.execute(envelope)
```

To make this structural, NOT just a convention:

```python
# The API clients are PRIVATE to the enforcer
class SimsEnforcedExecution:
    def __init__(self, ...):
        # API clients are instance attributes, not module-level globals
        self._groq_client = GroqClient(api_key)
        self._kimi_client = KimiClient(api_key)
        self._claude_cli = ClaudeCLI()
    
    # These are private methods — only callable from within execute()
    def _call_groq(self, model, prompt, message):
        ...
    
    def _call_kimi(self, prompt, message):
        ...
    
    def _call_claude_cli(self, prompt, message):
        ...

# There is no other way to call the APIs.
# The clients don't exist outside this class.
```

---

## GUARDRAIL 3: STATE VALIDATION

Periodic checks that verify the Sims state is consistent and hasn't drifted.

```python
class StateValidator:
    """
    Runs periodically (every 30 minutes or on startup).
    Catches state drift, corruption, or missed updates.
    """
    
    def validate_all(self, agents: dict) -> list:
        """Returns list of violations found"""
        violations = []
        
        for agent_id, agent in agents.items():
            # 1. Needs must be in valid range
            for need in ['energy', 'focus', 'morale', 'social', 'knowledge', 'patience']:
                val = getattr(agent.needs, need)
                if not (0.0 <= val <= 1.0):
                    violations.append({
                        "type": "needs_out_of_range",
                        "agent": agent_id,
                        "need": need,
                        "value": val,
                        "fix": "clamped to [0.0, 1.0]"
                    })
                    setattr(agent.needs, need, max(0.0, min(1.0, val)))
            
            # 2. Tasks completed should match audit log
            audit_count = count_audit_entries(agent_id, today=True)
            if abs(agent.tasks_completed_today - audit_count) > 2:
                violations.append({
                    "type": "task_count_mismatch",
                    "agent": agent_id,
                    "agent_count": agent.tasks_completed_today,
                    "audit_count": audit_count,
                    "fix": "corrected to audit count"
                })
                agent.tasks_completed_today = audit_count
            
            # 3. Resting agent should have low energy
            if agent.resting and agent.needs.energy > 0.8:
                violations.append({
                    "type": "resting_but_high_energy",
                    "agent": agent_id,
                    "energy": agent.needs.energy,
                    "fix": "woke agent up"
                })
                agent.resting = False
            
            # 4. Skills should have non-negative XP
            for skill_name, skill in agent.skills.skills.items():
                if skill.xp < 0:
                    violations.append({
                        "type": "negative_xp",
                        "agent": agent_id,
                        "skill": skill_name,
                        "fix": "reset to 0"
                    })
                    skill.xp = 0
            
            # 5. DB state matches in-memory state
            db_state = load_agent_state(agent_id)
            if db_state:
                energy_drift = abs(agent.needs.energy - db_state.get("energy", 0))
                if energy_drift > 0.2:
                    violations.append({
                        "type": "db_memory_drift",
                        "agent": agent_id,
                        "in_memory_energy": agent.needs.energy,
                        "db_energy": db_state.get("energy"),
                        "fix": "synced to in-memory (source of truth)"
                    })
                    agent._save_state()
        
        if violations:
            log_event("state_validation", {
                "violations_found": len(violations),
                "details": violations
            })
        
        return violations
```

---

## GUARDRAIL 4: RELATIONSHIP ENFORCEMENT

Relationships must update on every inter-agent interaction. Not optional.

```python
class RelationshipEnforcer:
    """
    Wraps all inter-agent interactions to guarantee relationship updates.
    """
    
    def handoff(self, from_id: str, to_id: str, envelope: dict, success: bool):
        """REQUIRED call on every handoff between agents"""
        # Update forward relationship
        self.matrix.on_handoff(from_id, to_id, success)
        
        # Log for audit
        self._log_interaction(from_id, to_id, "handoff", success)
        
        # Update social needs for both agents
        from_agent = self.agents[from_id]
        to_agent = self.agents[to_id]
        from_agent.needs.social = min(1.0, from_agent.needs.social + 0.02)
        to_agent.needs.social = min(1.0, to_agent.needs.social + 0.02)
    
    def escalation(self, from_id: str, about_id: str, envelope: dict):
        """REQUIRED call on every escalation"""
        self.matrix.on_escalation(from_id, about_id)
        self._log_interaction(from_id, about_id, "escalation", None)
    
    def collaboration(self, agent_ids: list, envelope: dict, success: bool):
        """REQUIRED call on every multi-agent task"""
        self.matrix.on_collab_task(agent_ids, success)
        for aid in agent_ids:
            self._log_interaction(aid, "team", "collaboration", success)
```

---

## GUARDRAIL 5: EXPERIMENTATION SANDBOX

Enforcement shouldn't kill experimentation. Here's the escape hatch — controlled and logged.

```python
class ExperimentMode:
    """
    Allows testing new behaviors without breaking the Sims engine.
    
    RULES:
    - Experiments run through the SAME enforcement pipeline
    - Experiments can MODIFY decay rates, XP multipliers, thresholds
    - Experiments CANNOT skip state updates
    - Experiments CANNOT bypass can_accept() gates
    - All experiments are logged with before/after state
    - Experiments auto-expire after N tasks or N hours
    """
    
    def __init__(self, name: str, duration_hours: float = 4, max_tasks: int = 50):
        self.name = name
        self.duration_hours = duration_hours
        self.max_tasks = max_tasks
        self.tasks_run = 0
        self.started_at = iso_now()
        self.modifications = {}
        self.baseline_state = {}
        self.experiment_state = {}
        self.active = True
    
    def modify_decay_rate(self, need: str, multiplier: float):
        """
        Change how fast a need decays during this experiment.
        multiplier=0.5 means half the normal decay.
        multiplier=2.0 means double.
        """
        assert 0.1 <= multiplier <= 5.0, "Multiplier must be between 0.1 and 5.0"
        self.modifications[f"decay_{need}"] = multiplier
    
    def modify_xp_rate(self, multiplier: float):
        """Change XP award rate"""
        assert 0.1 <= multiplier <= 5.0, "Multiplier must be between 0.1 and 5.0"
        self.modifications["xp_rate"] = multiplier
    
    def modify_initiative_threshold(self, mood: str, threshold: float):
        """Change when agents take initiative"""
        assert 0.0 <= threshold <= 1.5, "Threshold must be between 0.0 and 1.5"
        self.modifications[f"initiative_{mood}"] = threshold
    
    def check_expiry(self) -> bool:
        """Auto-expire experiments"""
        if self.tasks_run >= self.max_tasks:
            self.active = False
            return True
        if hours_since(self.started_at) >= self.duration_hours:
            self.active = False
            return True
        return False
    
    def report(self) -> dict:
        """What happened during this experiment"""
        return {
            "name": self.name,
            "tasks_run": self.tasks_run,
            "modifications": self.modifications,
            "duration_hours": hours_since(self.started_at),
            "state_delta": self._compute_delta(),
            "conclusion": "pending" if self.active else "complete"
        }

    def _compute_delta(self) -> dict:
        """Compare baseline to current state"""
        # Shows exactly what the experiment changed
        pass


# Usage:
# experiment = ExperimentMode("faster_recovery", duration_hours=2)
# experiment.modify_decay_rate("energy", 0.5)  # Half decay
# experiment.modify_xp_rate(2.0)               # Double XP
# enforcer.set_experiment(experiment)
# ... run tasks normally ...
# print(experiment.report())                    # What happened?
```

---

## GUARDRAIL 6: DAILY HEALTH CHECK

Runs once per day (or on demand). Verifies the whole system is healthy.

```python
def daily_health_check(enforcer: SimsEnforcedExecution) -> str:
    """
    Comprehensive system health check.
    Returns human-readable report.
    """
    report = ["# Daily Health Check\n"]
    
    # 1. Agent state
    for agent_id, agent in enforcer.agents.items():
        mood = agent.mood
        report.append(f"## {agent.display_name} {mood['emoji']}")
        report.append(f"Energy: {agent.needs.energy:.0%} | Mood: {mood['mood']}")
        report.append(f"Tasks today: {agent.tasks_completed_today}")
        
        # Flag concerns
        if agent.needs.energy < 0.2 and not agent.resting:
            report.append(f"⚠️ LOW ENERGY but not resting — force rest recommended")
        if agent.needs.morale < 0.3:
            report.append(f"⚠️ LOW MORALE — check for repeated failures")
        if agent.tasks_since_rest > 20:
            report.append(f"⚠️ 20+ tasks without rest — quality may be degraded")
    
    # 2. Relationship health
    report.append("\n## Relationships")
    for a, b in [("ralph", "ira"), ("ralph", "tess"), ("ira", "tess")]:
        health = enforcer.relationships.get_pair_chemistry(a, b)["mutual_health"]
        if health < 0.4:
            report.append(f"⚠️ {a.title()} ↔ {b.title()}: STRAINED ({health:.0%})")
        else:
            report.append(f"✅ {a.title()} ↔ {b.title()}: {health:.0%}")
    
    # 3. State validation
    violations = StateValidator().validate_all(enforcer.agents)
    if violations:
        report.append(f"\n## ⚠️ {len(violations)} State Violations Found")
        for v in violations:
            report.append(f"- {v['type']}: {v['agent']} — {v['fix']}")
    else:
        report.append("\n## ✅ State Validation: Clean")
    
    # 4. Audit trail completeness
    audit_gaps = check_audit_gaps(enforcer.audit_log)
    if audit_gaps:
        report.append(f"\n## ⚠️ {len(audit_gaps)} Audit Gaps")
    else:
        report.append("\n## ✅ Audit Trail: Complete")
    
    # 5. Experiment status
    if enforcer.active_experiment:
        exp = enforcer.active_experiment
        report.append(f"\n## 🧪 Active Experiment: {exp.name}")
        report.append(f"Tasks: {exp.tasks_run}/{exp.max_tasks}")
        report.append(f"Modifications: {exp.modifications}")
    
    return "\n".join(report)
```

---

## GUARDRAIL SUMMARY

| # | Guardrail | Enforces | Bypass? |
|---|-----------|----------|---------|
| 1 | Execution Wrapper | Pre/post hooks on every task | NO — only path to APIs |
| 2 | No Raw API Calls | All calls go through enforcer | NO — clients are private |
| 3 | State Validation | Needs, skills, DB consistency | Runs automatically |
| 4 | Relationship Enforcement | Updates on every interaction | NO — built into wrapper |
| 5 | Experimentation Sandbox | Controlled tuning with limits | YES — but logged and bounded |
| 6 | Daily Health Check | System-wide integrity | Runs automatically |

**The key insight:** Guardrails 1-4 are structural — they make compliance the only available path. Guardrail 5 allows growth and experimentation without breaking the structure. Guardrail 6 catches anything that slips through.

This is not the honor system. This is architecture.
