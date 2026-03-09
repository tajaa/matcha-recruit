"""Legislative tracker service — LegiScan + Polymarket + Gemini, no DB."""

import asyncio
import json
import time
from typing import Any, Optional

import httpx

from ...config import get_settings

LEGISCAN_BASE = "https://api.legiscan.com/"
POLYMARKET_SEARCH = "https://gamma-api.polymarket.com/public-search"

# LegiScan status integer → label
STATUS_LABELS = {
    0: "N/A",
    1: "Introduced",
    2: "Engrossed",
    3: "Enrolled",
    4: "Passed",
    5: "Vetoed",
    6: "Failed",
}

# Default keywords to search when none provided
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

# All 50 states + Congress
ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "US",
]

# HR category mapping: title keyword fragments → category name
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


def _categorize_bill(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for keywords, category in CATEGORY_MAP:
        for kw in keywords:
            if kw in text:
                return category
    return "Other"


def _stage_heuristic(status: int) -> float:
    """Return a rough passage probability based on LegiScan status code."""
    if status == 4:
        return 0.88
    if status == 5:
        return 0.02
    if status == 6:
        return 0.02
    if status == 3:
        return 0.75
    if status == 2:
        return 0.45
    if status == 1:
        return 0.07
    return 0.05


async def _legiscan_request(op: str, params: dict, client: httpx.AsyncClient) -> dict:
    settings = get_settings()
    api_key = settings.legiscan_api_key
    if not api_key:
        raise ValueError("LEGISCAN_API_KEY not configured")

    query = {"key": api_key, "op": op, **params}
    response = await client.get(LEGISCAN_BASE, params=query, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if data.get("status") == "ERROR":
        raise ValueError(f"LegiScan error: {data.get('alert', {}).get('message', 'unknown')}")
    return data


async def search_legiscan_bills(
    keywords: list[str],
    states: list[str],
    client: httpx.AsyncClient,
) -> list[dict]:
    """Search LegiScan for bills matching each keyword in each state."""
    seen: set[int] = set()
    bills: list[dict] = []

    async def _search(keyword: str, state: str) -> list[dict]:
        try:
            data = await _legiscan_request(
                "getSearch",
                {"state": state, "query": keyword, "year": "2"},
                client,
            )
            results = data.get("searchresult", {})
            found = []
            for key, val in results.items():
                if key == "summary":
                    continue
                if isinstance(val, dict) and "bill_id" in val:
                    found.append(val)
            return found
        except Exception as e:
            print(f"[LegTracker] getSearch {state}/{keyword}: {e}")
            return []

    tasks = [
        _search(kw, state)
        for kw in keywords
        for state in states
    ]
    results = await asyncio.gather(*tasks)

    for batch in results:
        for bill in batch:
            bid = bill.get("bill_id")
            if bid and bid not in seen:
                seen.add(bid)
                bills.append(bill)

    return bills


async def get_legiscan_bill_detail(bill_id: int, client: httpx.AsyncClient) -> Optional[dict]:
    """Fetch full bill detail from LegiScan."""
    try:
        data = await _legiscan_request("getBill", {"id": bill_id}, client)
        return data.get("bill")
    except Exception as e:
        print(f"[LegTracker] getBill {bill_id}: {e}")
        return None


async def search_polymarket_match(bill_title: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Search Polymarket for a market matching this bill."""
    # Use 3-5 key words from the title
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
        events = data.get("events", [])
        for event in events:
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
    """Use Gemini to estimate passage probability for a bill."""
    try:
        from google.genai import types
        from .gemini_compliance import get_gemini_compliance_service
        gemini = get_gemini_compliance_service()
        if not gemini._has_api_key():
            return None

        status = bill.get("status", 0)
        state = bill.get("state", "Unknown")
        title = bill.get("title", "")
        description = bill.get("description", "")
        sponsors = bill.get("sponsors", [])
        sponsor_count = len(sponsors)
        parties = {s.get("party", "") for s in sponsors if s.get("party")}

        prompt = f"""You are a legislative analyst estimating the probability that a bill will pass.

Bill: {title}
State: {state}
Description: {description[:500] if description else 'N/A'}
Legislative stage: {STATUS_LABELS.get(status, 'Unknown')} (status code {status})
Sponsor count: {sponsor_count}
Sponsor parties: {', '.join(parties) if parties else 'Unknown'}

Based on the legislative stage, bipartisan support, sponsor count, and general political context for {state}, estimate the probability (0.0 to 1.0) that this bill will be passed into law this session.

Respond in JSON: {{"probability": 0.XX, "reasoning": "brief 1-2 sentence explanation"}}"""

        response = await gemini.client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_modalities=["TEXT"],
            ),
        )
        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        prob = float(result.get("probability", 0.1))
        prob = max(0.0, min(1.0, prob))
        return {
            "probability": prob,
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        print(f"[LegTracker] Gemini estimate failed: {e}")
        return None


def _build_bill_summary(search_result: dict, detail: Optional[dict]) -> dict:
    """Merge search result + detail into a unified bill dict."""
    bill_id = search_result.get("bill_id", 0)
    status = search_result.get("status", 0)
    title = search_result.get("title", "")

    sponsors = []
    history = []
    votes = []

    if detail:
        for s in detail.get("sponsors", []):
            sponsors.append({
                "name": s.get("name", ""),
                "party": s.get("party", ""),
                "role": s.get("role", ""),
            })
        history = detail.get("history", [])
        votes = detail.get("votes", [])
        # Use detail title if available
        if detail.get("title"):
            title = detail["title"]

    return {
        "bill_id": bill_id,
        "state": search_result.get("state", ""),
        "bill_number": search_result.get("bill_number", ""),
        "title": title,
        "description": search_result.get("description", ""),
        "status": status,
        "status_label": STATUS_LABELS.get(status, "Unknown"),
        "last_action": search_result.get("last_action", ""),
        "last_action_date": search_result.get("last_action_date", ""),
        "url": search_result.get("url", ""),
        "category": _categorize_bill(title, search_result.get("description", "")),
        "sponsors": sponsors,
        "history": history,
        "votes": votes,
    }


async def scan_bills(
    keywords: Optional[list[str]] = None,
    states: Optional[list[str]] = None,
) -> dict:
    """
    Main orchestrator: search LegiScan → detail → Polymarket → Gemini.
    Returns unified bill list with probabilities.
    """
    start = time.monotonic()
    kw_list = keywords or HR_KEYWORDS
    state_list = states or ALL_STATES

    async with httpx.AsyncClient() as client:
        # Step 1: Search for bills
        search_results = await search_legiscan_bills(kw_list, state_list, client)

        if not search_results:
            return {
                "bills": [],
                "total": 0,
                "keywords_searched": kw_list,
                "states_searched": state_list,
                "scan_duration_seconds": round(time.monotonic() - start, 1),
                "polymarket_matches": 0,
                "gemini_estimates": 0,
            }

        # Step 2: Fetch details in batches (limit to top 50 to avoid rate limits)
        top_results = search_results[:50]
        detail_tasks = [
            get_legiscan_bill_detail(r["bill_id"], client)
            for r in top_results
        ]
        details = await asyncio.gather(*detail_tasks)

        # Step 3: Polymarket match (parallel)
        poly_tasks = [
            search_polymarket_match(r.get("title", ""), client)
            for r in top_results
        ]
        poly_results = await asyncio.gather(*poly_tasks)

        # Step 4: Build summaries + assign probabilities
        bills = []
        polymarket_matches = 0
        gemini_estimates = 0
        gemini_tasks = []
        gemini_indices = []

        for i, (search_r, detail, poly) in enumerate(zip(top_results, details, poly_results)):
            bill = _build_bill_summary(search_r, detail)

            if poly:
                bill["probability"] = poly["probability"]
                bill["probability_source"] = "polymarket"
                bill["polymarket_url"] = poly["url"]
                bill["polymarket_volume"] = poly["volume"]
                polymarket_matches += 1
                bills.append(bill)
            else:
                bill["probability"] = _stage_heuristic(bill["status"])
                bill["probability_source"] = "heuristic"
                bills.append(bill)
                # Queue for Gemini estimate
                gemini_tasks.append(estimate_probability_gemini(bill))
                gemini_indices.append(i)

        # Step 5: Gemini estimates for bills without Polymarket (batch, capped at 20)
        if gemini_tasks:
            capped = gemini_tasks[:20]
            capped_indices = gemini_indices[:20]
            gemini_results = await asyncio.gather(*capped)
            for task_i, gemini_res in zip(capped_indices, gemini_results):
                if gemini_res:
                    bill = bills[task_i]
                    bill["probability"] = gemini_res["probability"]
                    bill["probability_source"] = "gemini"
                    bill["probability_reasoning"] = gemini_res["reasoning"]
                    gemini_estimates += 1

    duration = round(time.monotonic() - start, 1)

    return {
        "bills": bills,
        "total": len(bills),
        "keywords_searched": kw_list,
        "states_searched": state_list,
        "scan_duration_seconds": duration,
        "polymarket_matches": polymarket_matches,
        "gemini_estimates": gemini_estimates,
    }
