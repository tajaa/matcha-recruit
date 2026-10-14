from datetime import datetime, timezone
from uuid import uuid4

USER, COMPANY, SEARCH, LEAD, TOKEN = (uuid4() for _ in range(5))
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def search_row(**over):
    return {
        "id": SEARCH, "request_id": uuid4(), "user_id": USER, "company_id": COMPANY,
        "title": "COO", "ask": "COO roles across the US", "criteria": '{"titles": ["COO"], "currency": "USD"}',
        "plan": "{}", "weights": "{}", "weights_source": "default", "use_resume": False,
        "status": "done", "phase_cursor": "{}", "dispatch_token": TOKEN, "lease_until": None,
        "attempts": 1, "progress": '{"note": "Done"}', "provider_calls": 4, "fetch_calls": 2,
        "model_runs": 0, "tokens": 0, "redrafts": 0, "model": None, "error": None,
        "deleted_at": None, "created_at": NOW, "updated_at": NOW, "started_at": NOW,
        "completed_at": NOW, "lead_count": 2, "posted_pay_count": 1, **over,
    }


def lead_row(**over):
    return {
        "id": LEAD, "search_id": SEARCH, "user_id": USER, "dedupe_key": "acme|coo|austin",
        "title": "COO", "company": "Acme", "location": "Austin, TX", "state_code": "TX", "remote": False,
        "schedule_type": "Full-time", "posted_text": "2 days ago", "source": "greenhouse",
        "provider_job_id": "x", "source_url": "https://boards.greenhouse.io/acme/jobs/1",
        "apply_links": '[{"url": "https://boards.greenhouse.io/acme/jobs/1", "source": "Greenhouse"}]',
        "ats": '{"provider": "greenhouse", "questions": [{"key": "q1", "label": "Why?"}]}',
        "description": "Lead ops.", "highlights": "[]",
        "comp": '{"base": {"status": "posted", "annual_min": 250000, "annual_max": 300000, "currency": "USD"}}',
        "comp_status": "posted", "comp_annual_min": 250000, "comp_annual_max": 300000, "comp_currency": "USD",
        "pay_law_hint": None, "enriched_at": NOW, "screen_status": "pending", "screen_reason": None,
        "fit_score": None, "fit_reasons": "[]", "rank_score": 0.7, "rank": 1, "rank_band": 0,
        "rank_explain": '{"flags": []}', "approach": "{}", "approach_status": "none",
        "user_state": "new", "notes": "", "created_at": NOW, "updated_at": NOW, **over,
    }
