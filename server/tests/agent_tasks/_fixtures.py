import json
from datetime import date, datetime, timezone
from uuid import uuid4

USER, COMPANY, TASK, ITEM, TOKEN = (uuid4() for _ in range(5))
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 14)

PLAN = {
    "title": "1bd in SF", "item_kind": "listing", "source": "web", "queries": ["1 bedroom apartment SF dogs"],
    "fields": ["price", "beds", "pets"],
    "constraints": [
        {"field": "price", "op": "lte", "value": 3500.0, "unit": "month", "currency": "USD", "source": "brief"},
        {"field": "pets", "op": "includes", "value": ["dogs"]},
    ],
    "preferences": [{"field": "price", "weight": 0.6}], "fit_weight": 0.4, "summary": "A 1bd that takes dogs",
    "location": "San Francisco",
}


def task_row(**over):
    return {
        "id": TASK, "request_id": uuid4(), "user_id": USER, "company_id": COMPANY, "source": "espresso",
        "playbook": "research", "engine": "chain", "title": "1bd in SF",
        "directive": "find me a 1bd in SF under 3500 that allows dogs",
        "brief": json.dumps({"location": "San Francisco", "budget_max": 3500}), "plan": json.dumps(PLAN),
        "input_ids": [], "status": "done", "phase": "research.summarize", "phase_cursor": "{}",
        "dispatch_token": TOKEN, "lease_until": None, "attempts": 1, "progress": '{"note": "Found 3"}',
        "needs": None, "waiting_since": None, "provider_calls": 0, "fetch_calls": 0, "browser_views": 0,
        "model_runs": 0, "tokens": 0, "current_round": 1, "origin_channel_id": None, "origin_message_id": None,
        "project_id": None, "card_task_id": None, "job_search_id": None, "model": None, "error": None,
        "seen_at": None, "deleted_at": None, "created_at": NOW, "updated_at": NOW, "started_at": NOW,
        "completed_at": NOW, "item_count": 2, "shown_count": 1, **over,
    }


def price(value, status="verified", unit="month", origin="page_text", url="https://apts.test/1"):
    return {"value": value, "status": status, "currency": "USD", "unit": unit,
            "display": f"${value:,.0f}/mo", "evidence": {"quote": f"${value:,.0f}/mo", "url": url, "origin": origin}}


def item_row(**over):
    return {
        "id": ITEM, "task_id": TASK, "round_n": 1, "dedupe_key": "u:https://apts.test/1", "kind": "listing",
        "title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1", "origin": "web",
        "provider": None, "fields": json.dumps({"price": price(3200)}), "images": "[]",
        "image_candidates": "[]", "status": "verified", "violations": "[]", "enriched_at": NOW,
        "screened_at": NOW, "fit_score": 4, "fit_reasons": '["Close to transit"]', "rank": 1, "rank_band": 0,
        "rank_score": 0.8, "rank_explain": '{"flags": []}', "user_state": "new", "notes": "",
        "created_at": NOW, "updated_at": NOW, **over,
    }


def round_row(**over):
    return {
        "id": uuid4(), "task_id": TASK, "user_id": USER, "n": 1, "kind": "initial", "request_id": None,
        "directive": "find me a 1bd", "scope": "{}", "status": "done", "units": 3, "items_added": 2,
        "run_id": None, "summary": '{"headline": "Found 2"}', "document": None, "error": None,
        "created_at": NOW, "completed_at": NOW, **over,
    }
