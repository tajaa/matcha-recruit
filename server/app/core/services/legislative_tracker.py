"""Legislative tracker service — Gemini grounding + Polymarket, no DB."""

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Optional

import httpx

from ...config import get_settings

POLYMARKET_SEARCH = "https://gamma-api.polymarket.com/public-search"

# Gemini string status → int (for frontend sorting/coloring)
GEMINI_STATUS_MAP = {
    "Introduced": 1,
    "In Committee": 1,
    "Passed Committee": 2,
    "Passed One Chamber": 2,
    "Passed Both Chambers": 3,
    "Enrolled": 3,
    "Signed": 4,
    "Passed": 4,
    "Vetoed": 5,
    "Failed": 6,
}

STATUS_LABELS = {
    0: "N/A",
    1: "Introduced",
    2: "Engrossed",
    3: "Enrolled",
    4: "Passed",
    5: "Vetoed",
    6: "Failed",
}

# Stage heuristic by status string
STATUS_HEURISTIC = {
    "Introduced": 0.07,
    "In Committee": 0.15,
    "Passed Committee": 0.25,
    "Passed One Chamber": 0.45,
    "Passed Both Chambers": 0.82,
    "Enrolled": 0.75,
    "Signed": 0.97,
    "Passed": 0.88,
    "Vetoed": 0.02,
    "Failed": 0.02,
}

HR_KEYWORDS = [
    "minimum wage",
    "paid leave",
    "paid sick leave",
    "overtime",
    "employee classification",
    "workplace safety",
    "pay transparency",
    "predictive scheduling",
    "non-compete",
    "equal pay",
]

ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "US",
]

CATEGORY_MAP = [
    (["minimum wage", "min wage", "tipped wage"], "Minimum Wage"),
    (["overtime", "over time", "ot pay"], "Overtime"),
    (["sick leave", "sick day", "illness leave"], "Paid Sick Leave"),
    (["paid leave", "parental leave", "family leave", "maternity", "paternity", "fmla"], "Paid Leave"),
    (["employee classification", "independent contractor", "gig worker", "misclassif"], "Employee Classification"),
    (["workplace safety", "osha", "hazard", "injury"], "Workplace Safety"),
    (["pay transparency", "pay equity", "salary disclosure", "wage disclosure"], "Pay Transparency"),
    (["scheduling", "predictive schedule", "fair workweek"], "Predictive Scheduling"),
    (["non-compete", "noncompete", "covenant not to compete"], "Non-Compete"),
    (["equal pay", "pay discrimination", "gender pay gap"], "Equal Pay"),
]

REQUEST_TIMEOUT = 15.0


def _categorize_bill(title: str, category_hint: str = "") -> str:
    text = (title + " " + category_hint).lower()
    for keywords, category in CATEGORY_MAP:
        for kw in keywords:
            if kw in text:
                return category
    return "Other"


def _bill_id_from_key(state: str, bill_number: str) -> int:
    """Generate a stable integer ID from state + bill number."""
    key = f"{state}-{bill_number}".encode()
    return int(hashlib.md5(key).hexdigest()[:8], 16)


def _stage_heuristic(status_label: str) -> float:
    return STATUS_HEURISTIC.get(status_label, 0.07)


def _parse_gemini_json(text: str) -> list:
    """Extract a JSON array from Gemini response text."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("`").strip()
    # Find outermost array
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return []


async def search_bills_via_gemini_grounding(
    keywords: list[str],
    states: list[str],
) -> list[dict]:
    """
    Use Gemini with Google Search grounding to find pending HR/employment bills.
    Batches keywords to minimize API calls (3 keywords per call).
    """
    from google.genai import types
    from .gemini_compliance import get_gemini_compliance_service

    gemini = get_gemini_compliance_service()
    if not gemini._has_api_key():
        print("[LegTracker] No Gemini API key — cannot search bills")
        return []

    is_all_states = len(states) >= 40
    state_context = (
        "across all 50 US states and the US Congress"
        if is_all_states
        else f"in {', '.join(states)}"
    )
    state_set = set(states)

    # Batch keywords: 3 per Gemini call
    batches = [keywords[i:i+3] for i in range(0, len(keywords), 3)]

    async def _search_batch(kw_batch: list[str]) -> list[dict]:
        prompt = f"""Use Google Search to find currently PENDING or recently introduced legislative bills related to: {', '.join(kw_batch)}.

Scope: {state_context}, 2024-2025 legislative sessions.

Return ONLY a valid JSON array (no markdown, no explanation). Each element:
{{
  "state": "2-letter state code or US for federal",
  "bill_number": "e.g. SB 123 or H.R. 456",
  "title": "full official bill title",
  "description": "1-2 sentence plain-english summary",
  "status": "exactly one of: Introduced, In Committee, Passed Committee, Passed One Chamber, Passed Both Chambers, Signed, Vetoed, Failed",
  "last_action": "most recent action taken",
  "last_action_date": "YYYY-MM-DD or best approximation",
  "url": "direct link to bill text or state legislature page",
  "category": "best matching topic from: {', '.join(kw_batch)}"
}}

Include up to 6 real bills per keyword. Only include bills you can verify exist via search."""

        try:
            response = await gemini.client.aio.models.generate_content(
                model=get_settings().analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )
            return _parse_gemini_json(response.text or "")
        except Exception as e:
            print(f"[LegTracker] Gemini grounding batch {kw_batch}: {e}")
            return []

    results = await asyncio.gather(*[_search_batch(b) for b in batches])

    seen: set[str] = set()
    bills: list[dict] = []
    for batch_result in results:
        for bill in batch_result:
            if not isinstance(bill, dict):
                continue
            state = (bill.get("state") or "").upper().strip()
            bill_number = (bill.get("bill_number") or "").strip()
            if not state or not bill_number:
                continue
            # Filter to requested states (skip when searching all)
            if not is_all_states and state not in state_set and state != "US":
                continue
            key = f"{state}-{bill_number}"
            if key not in seen:
                seen.add(key)
                bills.append(bill)

    return bills


def _build_bill_from_gemini(raw: dict) -> dict:
    state = (raw.get("state") or "").upper().strip()
    bill_number = (raw.get("bill_number") or "").strip()
    title = raw.get("title") or ""
    status_str = raw.get("status") or "Introduced"
    category_hint = raw.get("category") or ""

    return {
        "bill_id": _bill_id_from_key(state, bill_number),
        "state": state,
        "bill_number": bill_number,
        "title": title,
        "description": raw.get("description") or "",
        "status": GEMINI_STATUS_MAP.get(status_str, 1),
        "status_label": status_str,
        "last_action": raw.get("last_action") or "",
        "last_action_date": raw.get("last_action_date") or "",
        "url": raw.get("url") or "",
        "category": _categorize_bill(title, category_hint) if not category_hint else category_hint,
        "sponsors": [],
    }


async def search_polymarket_match(bill_title: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Search Polymarket for a prediction market matching this bill."""
    words = [w for w in bill_title.lower().split() if len(w) > 3][:5]
    query = " ".join(words[:4])
    if not query:
        return None
    try:
        resp = await client.get(
            POLYMARKET_SEARCH,
            params={"q": query},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        for event in data.get("events", []):
            for market in event.get("markets", []):
                outcomes = market.get("outcomes", [])
                prices = market.get("outcomePrices", [])
                if outcomes and prices and "Yes" in outcomes:
                    yes_idx = outcomes.index("Yes")
                    try:
                        prob = float(prices[yes_idx])
                    except (ValueError, IndexError):
                        continue
                    return {
                        "probability": prob,
                        "volume": market.get("volume", 0),
                        "question": market.get("question", ""),
                        "url": f"https://polymarket.com/event/{event.get('slug', '')}",
                    }
    except Exception as e:
        print(f"[LegTracker] Polymarket search '{query}': {e}")
    return None


async def estimate_probability_gemini(bill: dict) -> Optional[dict]:
    """Use Gemini to estimate passage probability for a bill without a Polymarket match."""
    try:
        from google.genai import types
        from .gemini_compliance import get_gemini_compliance_service
        gemini = get_gemini_compliance_service()
        if not gemini._has_api_key():
            return None

        prompt = f"""You are a legislative analyst estimating passage probability.

Bill: {bill.get('title', '')}
State: {bill.get('state', '')}
Description: {bill.get('description', '')[:400]}
Current status: {bill.get('status_label', 'Introduced')}

Estimate the probability (0.0 to 1.0) this bill passes into law this session.
Consider: legislative stage, political context, typical passage rates for this bill type.

Respond in JSON only: {{"probability": 0.XX, "reasoning": "1-2 sentence explanation"}}"""

        response = await gemini.client.aio.models.generate_content(
            model=get_settings().analysis_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_modalities=["TEXT"],
            ),
        )
        text = (response.text or "").strip()
        text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("`")
        result = json.loads(text)
        prob = max(0.0, min(1.0, float(result.get("probability", 0.1))))
        return {"probability": prob, "reasoning": result.get("reasoning", "")}
    except Exception as e:
        print(f"[LegTracker] Gemini probability estimate: {e}")
        return None


async def scan_bills(
    keywords: Optional[list[str]] = None,
    states: Optional[list[str]] = None,
) -> dict:
    """
    Main orchestrator: Gemini grounding search → Polymarket match → Gemini probability estimate.
    Returns unified bill list with probabilities. No database, all live.
    """
    start = time.monotonic()
    kw_list = keywords or HR_KEYWORDS
    state_list = states or ALL_STATES

    # Step 1: Find bills via Gemini grounding
    raw_bills = await search_bills_via_gemini_grounding(kw_list, state_list)

    if not raw_bills:
        return {
            "bills": [],
            "total": 0,
            "keywords_searched": kw_list,
            "states_searched": state_list,
            "scan_duration_seconds": round(time.monotonic() - start, 1),
            "polymarket_matches": 0,
            "gemini_estimates": 0,
        }

    async with httpx.AsyncClient() as client:
        # Step 2: Polymarket matching (parallel)
        poly_tasks = [search_polymarket_match(r.get("title", ""), client) for r in raw_bills]
        poly_results = await asyncio.gather(*poly_tasks)

    # Step 3: Build bills + assign heuristic probabilities
    bills = []
    needs_gemini: list[int] = []

    for i, (raw, poly) in enumerate(zip(raw_bills, poly_results)):
        bill = _build_bill_from_gemini(raw)
        if poly:
            bill["probability"] = poly["probability"]
            bill["probability_source"] = "polymarket"
            bill["polymarket_url"] = poly["url"]
            bill["polymarket_volume"] = poly["volume"]
        else:
            bill["probability"] = _stage_heuristic(bill["status_label"])
            bill["probability_source"] = "heuristic"
            needs_gemini.append(i)
        bills.append(bill)

    # Step 4: Gemini probability estimates for up to 15 bills (parallel)
    gemini_estimates = 0
    if needs_gemini:
        capped = needs_gemini[:15]
        gemini_results = await asyncio.gather(*[estimate_probability_gemini(bills[i]) for i in capped])
        for idx, g in zip(capped, gemini_results):
            if g:
                bills[idx]["probability"] = g["probability"]
                bills[idx]["probability_source"] = "gemini"
                bills[idx]["probability_reasoning"] = g["reasoning"]
                gemini_estimates += 1

    polymarket_matches = sum(1 for b in bills if b.get("probability_source") == "polymarket")

    return {
        "bills": bills,
        "total": len(bills),
        "keywords_searched": kw_list,
        "states_searched": state_list,
        "scan_duration_seconds": round(time.monotonic() - start, 1),
        "polymarket_matches": polymarket_matches,
        "gemini_estimates": gemini_estimates,
    }
