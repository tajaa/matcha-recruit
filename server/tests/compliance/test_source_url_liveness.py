"""_validate_source_urls must FLAG dead source URLs, never erase them.

A dead source_url is the pointer back to the authority — it's how a stale policy
gets re-verified. The old behavior blanked it (and source_name) on a 404; this
guards the fix that retains the URL and records liveness instead.
"""
import asyncio

from app.core.services import compliance_service as cs


class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeClient:
    """Stands in for httpx.AsyncClient: URLs containing 'dead' 404, else 200,
    and 'boom' raises (connection error)."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def head(self, url):
        if "boom" in url:
            raise RuntimeError("connection refused")
        return _FakeResp(404 if "dead" in url else 200)


def test_dead_url_is_flagged_not_erased(monkeypatch):
    reqs = [
        {"source_url": "https://labor.example.gov/dead-page", "source_name": "State DOL"},
        {"source_url": "https://labor.example.gov/live-page", "source_name": "State DOL"},
        {"source_url": "https://labor.example.gov/boom", "source_name": "State DOL"},
    ]
    monkeypatch.setattr(cs.httpx, "AsyncClient", _FakeClient)
    asyncio.get_event_loop().run_until_complete(cs._validate_source_urls(reqs))

    dead, live, err = reqs
    # URL + name RETAINED in every case (the whole point of the fix)
    assert dead["source_url"] == "https://labor.example.gov/dead-page"
    assert dead["source_name"] == "State DOL"
    assert dead["source_url_status"] == "dead"

    assert live["source_url_status"] == "ok"
    assert live["source_url"] == "https://labor.example.gov/live-page"

    # a connection error is also 'dead' (not alive), URL retained
    assert err["source_url_status"] == "dead"
    assert err["source_url"] == "https://labor.example.gov/boom"


def test_missing_url_is_left_untouched(monkeypatch):
    reqs = [{"source_name": "Whatever"}]  # no source_url
    monkeypatch.setattr(cs.httpx, "AsyncClient", _FakeClient)
    asyncio.get_event_loop().run_until_complete(cs._validate_source_urls(reqs))
    # no url ⇒ not checked ⇒ no status stamped (column default 'unchecked' applies)
    assert "source_url_status" not in reqs[0]
