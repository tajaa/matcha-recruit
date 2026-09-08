"""Per-board AutoPR capability grants.

The hardcoded board allowlist says which boards the harness watches at all;
this map says what each of those boards may do. Sending email and driving a
browser are different blast radii from drafting a PR, so each is granted
separately and every one of them is fail-closed: an absent row, a malformed
payload, an unknown capability name, or a non-UUID key all resolve to "this
board may do nothing extra".
"""
import pytest

from app.core.services import platform_settings as ps

BOARD = "8b924347-d6e4-4000-8e7d-ca8f46f76fba"
OTHER_BOARD = "7f728636-3219-4d83-9df3-a4682e3242de"


@pytest.fixture(autouse=True)
def _clear_cache():
    ps.prime_autopr_board_capabilities_cache({})
    yield
    ps.prime_autopr_board_capabilities_cache({})


def test_known_capabilities_are_the_three_the_lane_implements():
    assert set(ps.AUTOPR_BOARD_CAPABILITIES) == {"research", "outreach", "browse"}


def test_a_well_formed_grant_normalizes_and_dedupes():
    assert ps._normalize_autopr_board_capabilities(
        {BOARD: ["research", "research", "browse"]}
    ) == {BOARD: ["research", "browse"]}


@pytest.mark.parametrize(
    "payload",
    [
        ["research"],                          # not a map
        {BOARD: "research"},                   # capabilities not a list
        {BOARD: ["launch_missiles"]},          # capability we do not implement
        {BOARD: [None]},                       # capability not a string
        {"not-a-uuid": ["research"]},          # key is not a project id
        {BOARD: ["research"], "nope": ["browse"]},  # one bad key poisons the map
    ],
)
def test_malformed_payloads_grant_nothing(payload):
    """None, not a partial map: half a parsed grant is the one outcome that
    could silently hand a board a capability nobody wrote down."""
    assert ps._normalize_autopr_board_capabilities(payload) is None


def test_priming_the_cache_serves_the_new_grant_immediately():
    ps.prime_autopr_board_capabilities_cache({BOARD: ["outreach"]})
    assert ps._autopr_board_capabilities_cache == {BOARD: ["outreach"]}


def test_priming_with_a_malformed_map_grants_nothing():
    ps.prime_autopr_board_capabilities_cache({BOARD: ["outreach"]})
    assert ps.prime_autopr_board_capabilities_cache({BOARD: ["bogus"]}) == {}


@pytest.mark.asyncio
async def test_board_capability_check_is_exact_per_board_and_per_capability():
    ps.prime_autopr_board_capabilities_cache({BOARD: ["research", "browse"]})
    assert await ps.board_has_autopr_capability(BOARD, "research") is True
    assert await ps.board_has_autopr_capability(BOARD, "browse") is True
    # Granted on one board is not granted on another.
    assert await ps.board_has_autopr_capability(OTHER_BOARD, "research") is False
    # A capability this board was not given.
    assert await ps.board_has_autopr_capability(BOARD, "outreach") is False
    # A capability that does not exist is refused before any lookup.
    assert await ps.board_has_autopr_capability(BOARD, "sudo") is False


@pytest.mark.asyncio
async def test_a_board_with_no_entry_has_no_capabilities():
    ps.prime_autopr_board_capabilities_cache({OTHER_BOARD: ["research"]})
    assert await ps.board_has_autopr_capability(BOARD, "research") is False


class _FakeConn:
    """Counts reads and answers with whatever the row would hold."""

    def __init__(self, value):
        self.value = value
        self.reads = 0

    async def fetchval(self, *args, **kwargs):
        self.reads += 1
        return self.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [None, "{not json", '{"nope": ["research"]}'],
    ids=["absent", "unparseable", "malformed"],
)
async def test_every_fallback_is_cached_too(row):
    """No row at all is the documented default, so leaving it uncached made the
    steady state the one that hit Postgres on every capability check — and
    re-logged the malformed-payload warning on every request."""
    ps._autopr_board_capabilities_cache = None
    conn = _FakeConn(row)
    assert await ps.get_autopr_board_capabilities(conn=conn) == {}
    assert conn.reads == 1
    for _ in range(5):
        assert await ps.board_has_autopr_capability(BOARD, "outreach") is False
    assert conn.reads == 1


@pytest.mark.asyncio
async def test_returned_grants_are_copies_a_caller_cannot_mutate():
    """The cache is process-wide and read on every gate; handing out the live
    list would let one caller's edit widen every later check."""
    ps.prime_autopr_board_capabilities_cache({BOARD: ["research"]})
    grants = await ps.get_autopr_board_capabilities()
    grants[BOARD].append("outreach")
    assert await ps.board_has_autopr_capability(BOARD, "outreach") is False
