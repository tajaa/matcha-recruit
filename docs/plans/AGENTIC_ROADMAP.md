# Agentic Roadmap

Steps to make the compliance pipeline more agentic, ordered from easiest to hardest.

---

## Phase 1: Quick Wins (Days)

### 1.1 Structured Self-Correction Prompts
**Current:** Retry loop appends raw error message as feedback.
**Improvement:** Categorize failures and provide targeted correction hints.

```python
CORRECTION_HINTS = {
    "json_parse": "Return ONLY valid JSON. No markdown, no explanation.",
    "missing_field": "You omitted required field '{field}'. Include it.",
    "invalid_category": "Use only these categories: {valid}. You used '{got}'.",
    "low_confidence": "Your confidence was {conf}. Search for .gov sources specifically.",
}
```

**Why it helps:** More actionable feedback = fewer wasted retries.
**Effort:** ~2 hours

---

### 1.2 Confidence Calibration Logging
**Current:** Confidence scores are used but not tracked.
**Improvement:** Log predictions vs outcomes to measure calibration.

```python
# Log when verification completes
await log_verification_outcome(
    jurisdiction_id=j.id,
    predicted_confidence=result.confidence,
    predicted_is_real=result.is_real_change,
    # Later: admin can mark actual_is_real when reviewing
)
```

**Why it helps:** Data to tune thresholds and identify systematic over/under-confidence.
**Effort:** ~3 hours

---

### 1.3 Jurisdiction-Specific Context Injection
**Current:** Same prompt for all jurisdictions.
**Improvement:** Inject known quirks for jurisdictions we've seen before.

```python
JURISDICTION_CONTEXT = {
    "san_francisco_ca": "SF often has local ordinances stricter than CA state law.",
    "new_york_ny": "NYC has separate rules from NY state for businesses >10 employees.",
    "seattle_wa": "Seattle has tiered minimum wage based on employer size and benefits.",
}
```

**Why it helps:** Reduces hallucinations from generic assumptions.
**Effort:** ~2 hours (start small, grow over time)

---

## Phase 2: Smarter Decisions (1-2 Weeks)

### 2.1 Query Decomposition for Grey-Zone Cases
**Current:** Low confidence → retry with refined prompt.
**Improvement:** Decompose into sub-questions, verify each independently.

```
Original: "Did minimum wage change from $15.50 to $16.00 in CA?"

Decomposed:
1. "What is current CA minimum wage?" → $16.00 (source: dir.ca.gov)
2. "What was CA minimum wage before Jan 2024?" → $15.50
3. "When did CA minimum wage last change?" → Jan 1, 2024

Synthesis: All 3 agree → high confidence
```

**Why it helps:** Triangulation catches hallucinations better than single-shot retries.
**Effort:** ~1 week

---

### 2.2 Dynamic Search Strategy Selection
**Current:** Always uses Gemini with Google Search grounding.
**Improvement:** Agent picks strategy based on query type.

| Query Type | Strategy |
|------------|----------|
| Wage rates | Prefer .gov direct lookup if available |
| Leave policies | Search + verify against state DOL page |
| Pending legislation | News sources + official legislature sites |
| Local ordinances | City .gov sites + news |

```python
def select_search_strategy(requirement_category: str, jurisdiction: Jurisdiction):
    if requirement_category == "minimum_wage" and jurisdiction.state in STATES_WITH_DOL_API:
        return "direct_api_lookup"
    elif requirement_category == "pending_legislation":
        return "news_plus_legislature"
    else:
        return "default_grounded_search"
```

**Why it helps:** Right tool for the job = better accuracy.
**Effort:** ~1 week

---

### 2.3 Verification Batching with Shared Context
**Current:** Each verification is independent.
**Improvement:** Batch related verifications, share research context.

```python
# Instead of 3 separate Gemini calls for same jurisdiction:
changes_to_verify = [wage_change, leave_change, posting_change]

# Single call with shared context:
prompt = f"""
Verify these {len(changes)} changes for {jurisdiction}:
{format_changes(changes_to_verify)}

For EACH change, provide verification with confidence and sources.
"""
```

**Why it helps:** Fewer API calls, shared context improves coherence.
**Effort:** ~3 days

---

## Phase 3: Learning & Memory (2-4 Weeks)

### 3.1 Feedback Loop from Admin Corrections
**Current:** Admin dismisses false alerts, but system doesn't learn.
**Improvement:** Track corrections, inject as negative examples.

```python
# When admin dismisses alert:
await store_correction(
    jurisdiction_id=j.id,
    requirement_key=req.key,
    predicted="changed",
    actual="unchanged",
    reason=admin_reason,  # "Gemini misread effective date"
)

# On future research for same jurisdiction:
recent_corrections = await get_recent_corrections(jurisdiction_id)
if recent_corrections:
    prompt += f"\n\nPREVIOUS ERRORS TO AVOID:\n{format_corrections(recent_corrections)}"
```

**Why it helps:** System improves from mistakes without code changes.
**Effort:** ~1 week (schema + UI + injection logic)

---

### 3.2 Source Reputation Tracking
**Current:** Source confidence is rule-based (.gov = high, blog = low).
**Improvement:** Track which sources have been accurate over time.

```python
# After verification is confirmed/rejected:
await update_source_reputation(
    domain="dir.ca.gov",
    was_accurate=True,
    category="minimum_wage"
)

# Use in future scoring:
def score_source(domain: str, category: str) -> float:
    base = SOURCE_TYPE_WEIGHTS.get(get_source_type(domain), 0.5)
    historical = await get_source_accuracy(domain, category)
    return base * 0.7 + historical * 0.3
```

**Why it helps:** Learns which sources to trust for which topics.
**Effort:** ~1 week

---

### 3.3 Pattern Recognition Across Jurisdictions
**Current:** Each jurisdiction is checked independently.
**Improvement:** Detect patterns that suggest coordinated changes.

```
Observation: 5 states updated minimum wage on Jan 1
Pattern: "Annual minimum wage updates common on Jan 1"
Action: Pre-check all tracked jurisdictions in late December
```

**Why it helps:** Proactive rather than reactive.
**Effort:** ~2 weeks

---

## Phase 4: Autonomous Agents (1-2 Months)

### 4.1 Legislation Watch Agent
**Current:** Legislation scan is reactive (runs during compliance check).
**Improvement:** Background agent monitors for changes proactively.

```python
class LegislationWatchAgent:
    async def run(self):
        while True:
            for jurisdiction in await get_watched_jurisdictions():
                changes = await scan_for_changes(jurisdiction)
                if changes:
                    await create_proactive_alert(jurisdiction, changes)
            await asyncio.sleep(SCAN_INTERVAL)  # e.g., daily
```

**Watches:**
- State legislature RSS feeds
- DOL news pages
- Google Alerts for "[state] employment law"

**Why it helps:** Alerts before effective date, not after.
**Effort:** ~2-3 weeks

---

### 4.2 Multi-Agent Verification Pipeline
**Current:** Single agent does research + verification.
**Improvement:** Specialized agents with different perspectives.

```
┌─────────────────┐
│  Researcher     │ → Finds information
└────────┬────────┘
         ↓
┌─────────────────┐
│  Skeptic        │ → Challenges findings, looks for contradictions
└────────┬────────┘
         ↓
┌─────────────────┐
│  Synthesizer    │ → Resolves conflicts, produces final answer
└─────────────────┘
```

**Why it helps:** Adversarial setup catches errors single agent misses.
**Effort:** ~3-4 weeks

---

### 4.3 Autonomous Research Planner
**Current:** Fixed pipeline (research → verify → scan).
**Improvement:** Agent decides what to research based on goals.

```python
class ResearchPlanner:
    async def plan(self, goal: str, context: dict) -> List[Step]:
        """
        Given a goal like "ensure compliance for new SF location",
        dynamically plan research steps based on what's known/unknown.
        """
        prompt = f"""
        Goal: {goal}
        Known: {context.get('known_requirements', [])}
        Unknown: {context.get('gaps', [])}

        What research steps are needed? Consider:
        - What jurisdictions apply (city, county, state, federal)?
        - What categories are most critical (wage, leave, safety)?
        - What's the priority order?

        Return a plan as JSON.
        """
        return await self.llm.generate_plan(prompt)
```

**Why it helps:** Handles novel situations without hardcoded logic.
**Effort:** ~1 month

---

## Summary (Cost-Optimized Order)

| Priority | Item | Effort | Impact | API Cost |
|----------|------|--------|--------|----------|
| 🟢 1 | Structured self-correction | 2h | Medium | Neutral |
| 🟢 2 | Jurisdiction context | 2h | Medium | Neutral |
| 🟢 3 | Verification batching | 3d | Medium | **Saves** |
| 🟢 4 | Admin feedback loop | 1w | High | Neutral |
| 🟡 5 | Confidence calibration | 3h | Low | Neutral |
| 🟡 6 | Dynamic search strategy | 1w | High | Neutral |
| 🟡 7 | Source reputation | 1w | Medium | Neutral |
| 🟡 8 | Legislation watch (RSS-based) | 1w | High | Low |
| 🔴 9 | Query decomposition | 1w | High | **Increases** |
| 🔴 10 | Cross-jurisdiction patterns | 2w | Medium | Neutral |
| 🔴 11 | Multi-agent verification | 3-4w | Medium | **Increases** |
| 🔴 12 | Autonomous planner | 1m | High | **Increases** |

🟢 = Do first (high ROI, low/neutral cost)
🟡 = Do when ready (good value)
🔴 = Consider alternatives or defer

---

## Design Constraints

**Goals:** Reduce false positives + Proactive monitoring + Less manual oversight
**Cost constraint:** Keep API calls lean—prefer smarter single calls over multiple calls

---

## Reprioritized Recommendations

Given "all goals + lean costs", here's the adjusted priority:

### High Priority (Best ROI)
| Item | Why | API Impact |
|------|-----|------------|
| Structured self-correction | Better retries = fewer total calls | Neutral |
| Jurisdiction context injection | More accurate first attempt | Neutral |
| Admin feedback loop | Learn from mistakes, reduce future errors | Neutral |
| Verification batching | Same accuracy, fewer calls | **Reduces calls** |
| Legislation watch (lightweight) | RSS/news scraping, Gemini only for alerts | Low |

### Medium Priority (Good Value)
| Item | Why | API Impact |
|------|-----|------------|
| Confidence calibration | Enables smart retry decisions | Neutral |
| Source reputation | Better weighting without extra calls | Neutral |
| Dynamic search strategy | Right tool = fewer retries | Neutral to reduced |

### Lower Priority (Cost Concerns)
| Item | Why | API Impact |
|------|-----|------------|
| Query decomposition | 3x calls per verification | **Increases calls** |
| Multi-agent verification | 2-3x calls per check | **Increases calls** |
| Autonomous planner | Many planning calls | **Increases calls** |

### Cost-Effective Alternatives

**Instead of query decomposition:**
→ Single call with explicit sub-questions in prompt
```
"Answer these 3 questions about CA minimum wage:
1. Current rate? 2. Previous rate? 3. Effective date?
Provide sources for each."
```

**Instead of multi-agent verification:**
→ Single call with adversarial self-check prompt
```
"Verify this change. Then play devil's advocate—what evidence
would contradict this? Finally, give your confidence considering both."
```

**Instead of autonomous planner:**
→ Expand jurisdiction context with decision trees
```python
JURISDICTION_RESEARCH_HINTS = {
    "california": {
        "check_local": True,  # Cities often have stricter rules
        "priority_categories": ["minimum_wage", "paid_leave"],
        "known_sources": ["dir.ca.gov", "labor.ca.gov"],
    }
}
```
