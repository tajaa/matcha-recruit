# IR Pattern Detection Analytics

## Context
The IR system has solid per-incident analysis (similar incidents, AI root cause, consistency guidance) and basic dashboard stats (counts by status/severity/type, weekly trend bars, top locations by count). But it lacks **cross-location pattern detection** — connecting dots across the org to surface systemic issues. The goal is to detect patterns across locations covering safety, behavioral, and compliance incidents.

## What Already Exists (reuse, don't rebuild)
- `GET /ir/incidents/analytics/locations` — location hotspot counts with severity breakdown
- `GET /ir/incidents/analytics/trends` — weekly incident counts over time
- `GET /ir/incidents/analytics/consistency` — action distribution by type & severity
- `ir_precedent.py` — 7-dimension similarity scoring (type, severity, category, location, temporal, text, root cause)
- `IRDashboardTab.tsx` — current dashboard with trends, top locations, recent incidents
- `IRConsistencyAnalyticsPanel.tsx` — current Analytics tab content

## Plan: Add Pattern Detection Endpoint + UI Panel

### Backend: New endpoint `GET /ir/incidents/analytics/patterns`

Add to `server/app/matcha/routes/ir_incidents.py`. Pure SQL + Python, no Gemini needed.

**Cross-location patterns** (same incident type appearing at 2+ locations):
```sql
SELECT incident_type, COUNT(DISTINCT location_id), COUNT(*),
       array_agg(DISTINCT location)
FROM ir_incidents
WHERE company_id = $1 AND occurred_at > now() - interval '6 months'
GROUP BY incident_type
HAVING COUNT(DISTINCT location_id) > 1
```

**Temporal clusters** (day-of-week and time-of-day concentration):
```sql
SELECT incident_type,
       EXTRACT(dow FROM occurred_at) as day_of_week,
       CASE WHEN EXTRACT(hour FROM occurred_at) < 6 THEN 'overnight'
            WHEN EXTRACT(hour FROM occurred_at) < 12 THEN 'morning'
            WHEN EXTRACT(hour FROM occurred_at) < 18 THEN 'afternoon'
            ELSE 'evening' END as time_block,
       COUNT(*)
FROM ir_incidents
WHERE company_id = $1 AND occurred_at > now() - interval '6 months'
GROUP BY incident_type, day_of_week, time_block
```

**Recurring root causes** (group by type + location):
- Group incidents by incident_type + location_id where root_cause is not null
- Flag locations with 3+ incidents sharing the same type in 6 months

**Velocity detection** (acceleration/deceleration per location):
- Compare last 30d count vs previous 30d count per location
- Flag locations where rate increased by >50%

**Response shape:**
```json
{
  "cross_location": [
    { "incident_type": "safety", "location_count": 4, "incident_count": 12,
      "locations": ["LA Office", "SF HQ", "Denver", "Austin"],
      "insight": "Safety incidents appear across 4 of 6 locations" }
  ],
  "temporal": [
    { "incident_type": "behavioral", "peak_day": "Friday", "peak_time": "evening",
      "concentration_pct": 0.42, "total": 15,
      "insight": "42% of behavioral incidents occur on Friday evenings" }
  ],
  "velocity": [
    { "location": "SF HQ", "location_id": "...", "current_30d": 8, "previous_30d": 3,
      "change_pct": 1.67, "insight": "SF HQ incidents up 167% vs prior month" }
  ],
  "recurring": [
    { "location": "Denver", "incident_type": "safety", "count": 5,
      "common_root_cause": "wet floors", "insight": "5 safety incidents at Denver, recurring root cause: wet floors" }
  ]
}
```

### Frontend: New `IRPatternDetectionPanel.tsx`

Add to `client/src/components/ir/`. Display in the Analytics tab of `IRList.tsx` above the existing consistency analytics.

**Layout:**
- 4 sections: Cross-Location Patterns, Temporal Clusters, Velocity Alerts, Recurring Issues
- Each pattern as a card with icon, insight text, and supporting data
- Color-coded severity: red for critical patterns (high velocity, many locations), amber for moderate
- Expandable detail rows showing affected locations/times

### Files to modify:
- `server/app/matcha/routes/ir_incidents.py` — add `/analytics/patterns` endpoint (~100 lines)
- New: `client/src/components/ir/IRPatternDetectionPanel.tsx` (~150 lines)
- `client/src/pages/app/IRList.tsx` — import and render pattern panel in Analytics tab
- `client/src/types/ir.ts` — add pattern detection types

### Files to NOT modify:
- `ir_precedent.py` — per-incident similarity, separate concern
- `ir_analysis.py` — per-incident AI analysis, separate concern
- `ir_consistency.py` — action distribution, separate concern

## Verification
- TypeScript: `cd client && npx tsc --noEmit`
- Manual: Navigate to IR > Analytics tab, verify pattern cards render
- Test with company that has incidents across multiple locations
- Check that empty states render cleanly (no incidents = "No patterns detected")
