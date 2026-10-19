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


class MemoryStore:
    """`postings.Store` in memory: what was saved is fresh, and live rows match."""

    def __init__(self):
        from app.matcha.services.matcha_work.job_search import postings

        self._p = postings
        self.rows: dict = {}
        self.sent_pages: dict[str, tuple[int, bool]] = {}
        self.searched_pages: list[tuple[str, int, bool]] = []
        self.looked_up: list = []

    def put(self, record, *, fresh=True):
        key = self._p.key_of_record(record)
        self.rows[key] = self._p.Stored(key, record["source_url"], True, fresh, record)

    async def known(self, keys):
        self.looked_up += list(keys)
        return {k: self.rows[k] for k in keys if k in self.rows}

    async def matching(self, titles, criteria, *, limit=0):
        return self._p.keep([r for r in self.rows.values() if r.live], titles, criteria)

    async def save(self, records, closed=()):
        for record in records:
            if self._p.key_of_record(record) is not None:
                self.put(record)
        for key in closed:
            self.rows[key] = self._p.Stored(key, "", False, True, None)

    async def sent(self, queries):
        keys = [self._p.query_key(q) for q in queries]
        return {k: self.sent_pages[k] for k in keys if k in self.sent_pages}

    async def searched(self, pages):
        for page, last in pages:
            self.sent_pages[self._p.query_key(page.query)] = (page.offset + 1, last)
            self.searched_pages.append((page.query, page.offset, last))

    def opener(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def opened():
            yield self

        return opened
