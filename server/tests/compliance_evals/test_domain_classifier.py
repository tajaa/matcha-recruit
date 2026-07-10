"""Citation-class classifier. Pure function, no network."""
import pytest

from app.core.services.compliance_evals.authority import (
    AGGREGATOR,
    MISSING,
    PRIMARY,
    SECONDARY_OFFICIAL,
    UNKNOWN,
    classify_domain,
)


@pytest.mark.parametrize("url", [
    "https://www.dol.gov/agencies/whd/minimum-wage",
    "https://dir.ca.gov/dlse/faq_minimumwage.htm",
    "https://www.ecfr.gov/current/title-29/part-541",
    "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml",
    "https://www.federalregister.gov/documents/2024/04/26/2024-08038",
    "https://codelibrary.amlegal.com/codes/san_francisco/latest/overview",
    "https://www.legislation.gov.uk/ukpga/1996/18",
    "https://www.osha.gov/laws-regs",
])
def test_primary_sources(url):
    assert classify_domain(url) == PRIMARY


@pytest.mark.parametrize("url", [
    "https://www.shrm.org/topics-tools/news/minimum-wage-update",
    "https://www.adp.com/spark/articles/minimum-wage.aspx",
    "https://blog.adp.com/some-post",
    "https://www.natlawreview.com/article/whatever",
    "https://www.minimum-wage.org/california",
    "https://en.wikipedia.org/wiki/Minimum_wage",
])
def test_aggregators(url):
    assert classify_domain(url) == AGGREGATOR


def test_secondary_official():
    assert classify_domain("https://www.ncsl.org/labor-and-employment") == SECONDARY_OFFICIAL
    assert classify_domain("https://law.justia.com/codes/california/") == SECONDARY_OFFICIAL


def test_justia_is_not_primary():
    """Justia mirrors statute text; it does not publish it. Demoted deliberately."""
    assert classify_domain("https://law.justia.com/codes/ny/") != PRIMARY


def test_missing_and_blank():
    assert classify_domain(None) == MISSING
    assert classify_domain("") == MISSING
    assert classify_domain("   ") == MISSING


def test_unknown_domain():
    assert classify_domain("https://some-random-consultancy.example/post") == UNKNOWN


def test_www_prefix_stripped():
    assert classify_domain("https://www.dol.gov/x") == classify_domain("https://dol.gov/x")


def test_port_is_ignored():
    assert classify_domain("https://dol.gov:443/x") == PRIMARY


def test_state_us_hosts():
    assert classify_domain("https://labor.state.ny.us/whatever") == PRIMARY


def test_lookalike_domain_is_not_primary():
    """`dol.gov.evil.com` must not classify as primary just because '.gov' appears."""
    assert classify_domain("https://dol.gov.evil.com/phish") != PRIMARY


# ── liveness classification ───────────────────────────────────────────────────

class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.mark.asyncio
async def test_timeout_is_not_reported_as_dead(monkeypatch):
    """A timed-out fetch says nothing about the citation.

    Regression: wagesla.lacity.gov answers HEAD 200 in isolation but times out
    under concurrency. Calling it `dead` sends a curator chasing a live URL.
    """
    import httpx

    from app.core.services.compliance_evals import authority

    async def _always_timeout(self, method, url, **kw):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx.AsyncClient, "request", _always_timeout)
    result = await authority.check_liveness(["https://slow.gov/x"])
    assert result["https://slow.gov/x"] == "timeout"


@pytest.mark.asyncio
async def test_connect_error_is_dead(monkeypatch):
    import httpx

    from app.core.services.compliance_evals import authority

    async def _refuse(self, method, url, **kw):
        raise httpx.ConnectError("no such host")

    monkeypatch.setattr(httpx.AsyncClient, "request", _refuse)
    result = await authority.check_liveness(["https://nope.gov/x"])
    assert result["https://nope.gov/x"] == authority.DEAD


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [
    (200, "alive"),
    (206, "alive"),
    (301, "alive"),
    (403, "alive_unverified"),
    (405, "alive_unverified"),
    (429, "alive_unverified"),
])
async def test_status_classification(monkeypatch, status, expected):
    import httpx

    from app.core.services.compliance_evals import authority

    async def _respond(self, method, url, **kw):
        return _Resp(status)

    monkeypatch.setattr(httpx.AsyncClient, "request", _respond)
    result = await authority.check_liveness(["https://x.gov/y"])
    assert result["https://x.gov/y"] == expected


@pytest.mark.asyncio
async def test_404_falls_through_head_to_get_then_dead(monkeypatch):
    import httpx

    from app.core.services.compliance_evals import authority

    async def _respond(self, method, url, **kw):
        return _Resp(404)

    monkeypatch.setattr(httpx.AsyncClient, "request", _respond)
    result = await authority.check_liveness(["https://x.gov/gone"])
    assert result["https://x.gov/gone"] == authority.DEAD
