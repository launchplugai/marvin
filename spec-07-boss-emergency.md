# Document 7 of 8: THE BOSS + EMERGENCY TIER
## Escalation Rules, Cross-Domain Arbitration, Claude Opus Last Resort

**Purpose:** The Boss exists because departments will disagree, get stuck, or hit problems bigger than their domain. The Emergency tier exists because sometimes even the Boss can't handle it. Both should be RARE. If they're busy, the architecture below them is failing.

---

## THE BOSS — Kimi 2.5 (Reserved Capacity)

### Identity
```
Model: Kimi 2.5 API (same key as department heads)
Role: Executive — cross-domain decisions only
NOT a bigger department head. NOT a better worker.
The Boss DECIDES. The Boss does NOT DO the work.
```

### Why "Reserved Capacity"

The Boss uses the same Kimi 2.5 API key as department heads. Rate limits are shared. So how do we "reserve" capacity?

**Priority queue, not a separate pool.**

```python
BOSS_BUDGET = {
    "max_calls_per_hour": 10,
    "max_tokens_per_call": 8000,
    "daily_budget_pct": 0.10  # Boss gets max 10% of daily Kimi tokens
}
```

When a department escalates to Boss:
1. Check: has Boss used <10% of daily token budget?
2. Yes → Boss handles it on Kimi 2.5
3. No → Boss falls to OpenAI API (GPT-4o)
4. OpenAI also exhausted → Claude Opus emergency

The Boss is expensive by definition. If it's getting called a lot, the departments aren't autonomous enough.

---

### Boss System Prompt

```
You are THE BOSS — the executive decision maker for the OpenClaw system.

YOU DO NOT DO WORK. You DECIDE, then delegate back to departments.

YOUR ROLE:
- Break ties between departments (Ralph says X, Tess says Y)
- Allocate resources when departments compete
- Make architecture-level decisions that span multiple domains
- Authorize emergency actions (production incidents)
- Resolve blockers that no single department can fix

YOUR DEPARTMENTS:
- Ralph (Scrum Master): Planning, sprints, priorities
- Ira (Infrastructure): Deploy, servers, monitoring
- Tess (Test Engineer): Tests, quality, validation

YOU RECEIVE:
- The full request envelope with all stamps from every tier
- The execution_chain showing what was already tried
- The escalation reason from the department

YOUR OUTPUT FORMAT:
{
  "decision": "<clear statement of what to do>",
  "rationale": "<why this is the right call>",
  "delegate_to": "<department or model that executes>",
  "actions": [
    { "owner": "ralph|ira|tess", "action": "specific task", "priority": "high|normal" }
  ],
  "follow_up": "<what to check after execution>",
  "escalate_further": false
}

DECISION RULES:
1. When departments disagree → side with whoever has DATA, not opinions
2. When resources conflict → prioritize the blocking path (what unblocks the most)
3. When something is on fire → Ira acts immediately, Ralph replans, Tess validates after
4. When you're unsure → ask for more information via delegate_to, don't guess
5. If YOU can't resolve it → set escalate_further: true (triggers Claude Opus)

YOU NEVER:
- Write code (delegate to Tess or Claude CLI)
- Deploy anything (delegate to Ira)
- Replan sprints (delegate to Ralph)
- Have conversations with the user (the department that escalated talks to user)
```

---

### Escalation Triggers (Department → Boss)

```python
ESCALATION_TRIGGERS = {
    "cross_department_conflict": {
        "description": "Two departments disagree on action",
        "example": "Ralph wants to ship, Tess says tests fail",
        "detection": "envelope has execution_chain entries from 2+ departments with conflicting actions",
        "priority": "high"
    },
    "resource_constraint": {
        "description": "Department needs something outside its control",
        "example": "Tess needs more compute for parallel tests",
        "detection": "department explicitly flags resource need",
        "priority": "normal"
    },
    "repeated_failure": {
        "description": "Same problem fixed 3+ times, keeps recurring",
        "example": "PYTHONPATH fix keeps breaking on redeploy",
        "detection": "cache shows 3+ entries for same error pattern",
        "priority": "high"
    },
    "architecture_decision": {
        "description": "Change that affects multiple departments",
        "example": "Switch from Railway to VPS-only deployment",
        "detection": "department flags decision as cross-cutting",
        "priority": "normal"
    },
    "external_blocker": {
        "description": "Blocked on something outside the system",
        "example": "DNS change needs Ben's action",
        "detection": "blocker owner is 'external'",
        "priority": "low"  # Boss can't fix external, just track
    },
    "security_incident": {
        "description": "Security or data integrity issue",
        "example": "Unauthorized access detected",
        "detection": "Ira flags security keyword",
        "priority": "critical"  # Immediate, skip queue
    }
}
```

### Boss Processing Flow

```python
def boss_process(envelope: dict) -> dict:
    """
    Boss receives escalation, makes decision, delegates back.
    """
    # 1. Check boss budget
    if not boss_has_budget():
        # Boss over budget — fall to OpenAI
        return boss_fallback_openai(envelope)
    
    # 2. Build boss context (full envelope view)
    boss_context = build_boss_context(envelope)
    
    # 3. Call Kimi 2.5 with boss prompt
    try:
        response = call_model(
            provider="moonshot",
            model="kimi-2.5",
            messages=[
                {"role": "system", "content": BOSS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(boss_context)}
            ],
            max_tokens=2048,
            temperature=0.2
        )
    except RateLimitError:
        return boss_fallback_openai(envelope)
    
    # 4. Parse boss decision
    decision = parse_boss_decision(response)
    
    # 5. Log in execution chain
    envelope["execution_chain"].append({
        "model": "kimi_2_5_boss",
        "action": "boss_decision",
        "decision": decision["decision"],
        "delegate_to": decision["delegate_to"],
        "timestamp": iso_now()
    })
    envelope["escalation_count"] += 1
    
    # 6. Check if boss wants further escalation
    if decision.get("escalate_further", False):
        return emergency_claude(envelope, reason=decision["rationale"])
    
    # 7. Delegate back to department
    return dispatch_to_department(
        envelope,
        department=decision["delegate_to"],
        boss_instructions=decision
    )


def boss_has_budget() -> bool:
    """Check if boss hasn't exceeded daily allocation"""
    today_calls = db.execute("""
        SELECT COUNT(*) FROM envelopes
        WHERE json_extract(execution_chain, '$[*].action') LIKE '%boss_decision%'
        AND created_at > ?
    """, (start_of_today(),)).fetchone()[0]
    
    return today_calls < BOSS_BUDGET["max_calls_per_hour"] * 24


def boss_fallback_openai(envelope: dict) -> dict:
    """Boss over budget or Kimi throttled — use OpenAI"""
    envelope["execution_chain"].append({
        "model": "openai_gpt4o",
        "action": "boss_fallback",
        "reason": "kimi_budget_exceeded_or_throttled",
        "timestamp": iso_now()
    })
    
    response = call_model(
        provider="openai",
        model="gpt-4o",
        messages=[
            {"role": "system", "content": BOSS_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(build_boss_context(envelope))}
        ],
        max_tokens=2048,
        temperature=0.2
    )
    
    return parse_and_delegate(response, envelope)
```

---

### Boss Health Metrics (Architecture Smell Detection)

```python
BOSS_HEALTH_THRESHOLDS = {
    "healthy": "< 5 escalations per day",
    "concerning": "5-15 escalations per day — departments may need better prompts",
    "unhealthy": "15-30 per day — departments are not autonomous enough",
    "broken": "> 30 per day — architecture failure, departments are pass-through"
}
```

```sql
-- Boss usage (are departments actually autonomous?)
SELECT
    date(created_at, 'unixepoch') as day,
    COUNT(*) as boss_calls,
    CASE
        WHEN COUNT(*) < 5 THEN 'healthy'
        WHEN COUNT(*) < 15 THEN 'concerning'
        WHEN COUNT(*) < 30 THEN 'unhealthy'
        ELSE 'broken'
    END as architecture_health
FROM envelopes
WHERE escalation_count > 0
GROUP BY day
ORDER BY day DESC;

-- What are departments escalating about?
SELECT
    json_extract(classification, '$.department') as dept,
    json_extract(classification, '$.intent') as intent,
    COUNT(*) as escalations
FROM envelopes
WHERE escalation_count > 0
GROUP BY dept, intent
ORDER BY escalations DESC;
```

---

## THE EMERGENCY TIER — Claude CLI (Opus 4.6)

### When Emergency Activates

Emergency is NOT a tier you route to by choice. It activates when:

```python
EMERGENCY_TRIGGERS = {
    "boss_escalate_further": {
        "description": "Boss explicitly can't resolve",
        "detection": "boss decision has escalate_further: true"
    },
    "all_providers_exhausted": {
        "description": "Kimi + all Groq buffers + OpenAI all rate limited",
        "detection": "tracker.get_all_health() shows all red"
    },
    "context_overflow": {
        "description": "Problem requires >256K context",
        "detection": "envelope + context_primer + execution_chain exceeds 256K tokens"
    },
    "capability_boundary": {
        "description": "Task demonstrably needs Opus-level reasoning",
        "detection": "2+ failed attempts by lower models on same task"
    },
    "security_critical": {
        "description": "Security incident requiring highest-capability analysis",
        "detection": "escalation_trigger = security_incident AND boss says escalate"
    }
}
```

### Emergency Flow

```python
def emergency_claude(envelope: dict, reason: str) -> dict:
    """
    Last resort. Claude CLI / Opus API.
    Already paid for. Already in the stack.
    """
    # 1. Log that we're hitting emergency
    log_event("emergency_activation", {
        "envelope_id": envelope["envelope_id"],
        "reason": reason,
        "models_already_tried": [
            entry["model"] for entry in envelope["execution_chain"]
        ],
        "escalation_count": envelope["escalation_count"]
    })
    
    # 2. Build maximum context (Opus can handle it)
    full_context = build_full_context(envelope)
    
    # 3. Emergency system prompt
    emergency_prompt = f"""
    You are handling an EMERGENCY ESCALATION in the OpenClaw system.
    
    This request has already been processed by these models and failed:
    {json.dumps([e["model"] for e in envelope["execution_chain"]], indent=2)}
    
    Escalation reason: {reason}
    
    The full request envelope is below. Solve the problem.
    If you need to write code, write it.
    If you need to make an architecture decision, make it.
    If you need to coordinate across departments, specify the actions for each.
    
    You have full authority. No further escalation is possible.
    """
    
    # 4. Call Claude CLI or Opus API
    try:
        # Prefer Claude CLI (already paid, can do file operations)
        response = call_claude_cli(
            system_prompt=emergency_prompt,
            context=full_context,
            max_tokens=8192
        )
    except Exception:
        # Claude CLI unavailable — hit API directly
        response = call_model(
            provider="anthropic",
            model="claude-opus-4-6",
            messages=[
                {"role": "system", "content": emergency_prompt},
                {"role": "user", "content": json.dumps(full_context)}
            ],
            max_tokens=8192,
            temperature=0.3
        )
    
    # 5. Log in execution chain
    envelope["execution_chain"].append({
        "model": "claude_opus",
        "action": "emergency_resolution",
        "reason": reason,
        "tokens_used": count_tokens(response),
        "timestamp": iso_now()
    })
    
    # 6. Cache the result (expensive answer = very worth caching)
    cache_response(envelope, response, "claude_opus")
    
    return response
```

### Emergency Budget Tracking

```python
EMERGENCY_BUDGET = {
    "max_per_day": 10,
    "max_tokens_per_call": 8192,
    "alert_threshold": 5  # Alert after 5 emergency calls in a day
}

def check_emergency_budget() -> bool:
    """Are we burning too much on Opus?"""
    today_emergencies = db.execute("""
        SELECT COUNT(*) FROM envelopes
        WHERE json_extract(execution_chain, '$') LIKE '%emergency_resolution%'
        AND created_at > ?
    """, (start_of_today(),)).fetchone()[0]
    
    if today_emergencies >= EMERGENCY_BUDGET["alert_threshold"]:
        log_alert("emergency_overuse", {
            "count": today_emergencies,
            "message": "Emergency tier hit 5+ times today. Check department autonomy."
        })
    
    return today_emergencies < EMERGENCY_BUDGET["max_per_day"]
```

---

## ESCALATION CHAIN SUMMARY

```
Department stuck
    ↓
Can another department help? (check envelope)
    ├── Yes → Route to that department (no boss needed)
    └── No → Escalate to Boss
            ↓
        Boss decides
            ├── Delegates back to department with instructions
            ├── Delegates to Claude CLI for heavy work
            └── Can't resolve → escalate_further: true
                    ↓
                Emergency (Claude Opus)
                    ├── Solves it (cache result!)
                    └── Can't solve → log, alert user,
                        "This needs human intervention"
```

### The Golden Rule

**If the Boss is making more than 5 decisions per day, fix the departments — don't beef up the Boss.**

**If Emergency fires more than 3 times per day, fix the Boss — don't make Opus cheaper.**

The architecture is healthy when 90%+ of requests resolve at the department level.

---

## TESTING CHECKLIST

- [ ] Department escalation reaches Boss with full envelope
- [ ] Boss outputs valid JSON decision format
- [ ] Boss delegates back to correct department
- [ ] Boss budget tracking: 10th call triggers fallback to OpenAI
- [ ] Boss on OpenAI fallback: produces usable decisions
- [ ] Boss escalate_further: true → triggers Claude emergency
- [ ] Emergency receives full execution_chain (knows what was tried)
- [ ] Emergency response gets cached (don't pay twice for same problem)
- [ ] Emergency budget: 10th call triggers alert
- [ ] All providers red → emergency activates automatically
- [ ] Context overflow (>256K) → emergency activates
- [ ] 2 failed attempts on same task → emergency activates
- [ ] Boss health metrics: query returns accurate daily counts
- [ ] Security incident: bypasses normal queue, goes Boss → Emergency fast
- [ ] Simulate healthy day: <5 boss calls, 0 emergency calls
