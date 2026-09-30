"""The assistant's domains ability: what counts as a domain, what a check
keeps, what a registration freezes, and that one yes registers once.
Nothing here calls Porkbun or opens a connection."""
import json
from uuid import uuid4

import httpx
import pytest

from app.core.services import porkbun
from app.matcha.services.matcha_work.agent_runtime import catalog, consent, result, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import domains
from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction, RunState
from app.matcha.services.matcha_work.agent_runtime.policy import Grounding, PolicyContext

from .helpers import FakeClient, FakeConn, call, connection, context, response, wire_store


@pytest.mark.parametrize("raw, expected", [
    ("Matcha.dev", "matcha.dev"),
    ("https://www.matcha.dev/about", "matcha.dev"),
    ("shop.co.uk", "shop.co.uk"),
    ("café.com", "xn--caf-dma.com"),
    ("app.matcha.dev", None),  # a subdomain is not registrable
    ("matcha", None),
    ("co.uk", None),
    ("", None),
])
def test_only_registrable_names_count(raw, expected):
    assert domains.normalize_domain(raw) == expected


class FakePorkbun:
    def __init__(self, prices=None, register_error=None):
        self.prices = prices or {}
        self.register_error = register_error
        self.registered = []

    async def check_domain(self, domain):
        if domain not in self.prices:
            raise porkbun.PorkbunError("Rate limited")
        price = self.prices[domain]
        return {"domain": domain, "available": price is not None, "wholesale_cents": price,
                "retail_cents": None}

    async def register(self, domain, *, cost_cents, idempotency_key):
        self.registered.append((domain, cost_cents, idempotency_key))
        if self.register_error:
            raise self.register_error
        return {"status": "SUCCESS"}


def _state():
    return RunState(started=0.0, sessions={domains.KEY: {"checked": {}}})


async def _checked(monkeypatch, pb, names):
    monkeypatch.setattr(porkbun, "get_porkbun", lambda: pb)
    state = _state()
    out = await domains._check(context(), state, {"domains": names}, 60.0)
    return state, out


@pytest.mark.asyncio
async def test_check_reports_price_and_keeps_what_it_saw(monkeypatch):
    pb = FakePorkbun({"matcha.dev": 1108, "matcha.com": None, "gold.ai": 999999})
    state, out = await _checked(monkeypatch, pb, ["matcha.dev", "matcha.com", "gold.ai", "not a domain", "x.io"])
    by = {r["domain"]: r for r in out.payload["results"]}
    assert by["matcha.dev"] == {"domain": "matcha.dev", "available": True, "first_year_price": "$11.08"}
    assert by["matcha.com"]["available"] is False
    assert "Above the $50.00 limit" in by["gold.ai"]["note"]
    assert out.payload["not_domains"] == ["not a domain"]
    assert "x.io" not in state.sessions[domains.KEY]["checked"]  # the fifth name: only four are checked per call
    assert state.sessions[domains.KEY]["checked"]["matcha.dev"] == {"available": True, "cost_cents": 1108}


@pytest.mark.asyncio
async def test_a_porkbun_error_is_reported_per_name(monkeypatch):
    _, out = await _checked(monkeypatch, FakePorkbun({}), ["matcha.dev"])
    assert out.payload["results"] == [{"domain": "matcha.dev", "error": "Rate limited"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, why", [
    ("other.dev", "check other.dev with check_domains first"),
    ("matcha.com", "is taken"),
    ("gold.ai", r"above the \$50\.00 limit"),
    ("not a domain", "isn't a registrable domain"),
])
async def test_resolve_refuses_what_the_run_did_not_see_free_and_affordable(monkeypatch, name, why):
    state, _ = await _checked(monkeypatch, FakePorkbun({"matcha.dev": 1108, "matcha.com": None, "gold.ai": 999999}),
                              ["matcha.dev", "matcha.com", "gold.ai"])
    with pytest.raises(ValueError, match=why):
        domains.resolve_registration({"domain": name}, state)


@pytest.mark.asyncio
async def test_the_price_is_the_checked_one_and_the_cap_is_configurable(monkeypatch):
    monkeypatch.setenv(domains.MAX_CENTS_ENV, "2000")
    state, _ = await _checked(monkeypatch, FakePorkbun({"matcha.dev": 1108}), ["MATCHA.dev"])
    frozen = domains.resolve_registration({"domain": "matcha.dev", "cost_cents": 1}, state)
    assert frozen == {"domain": "matcha.dev", "cost_cents": 1108}
    preview = domains._preview(frozen, state)
    assert preview["title"] == "Register matcha.dev for $11.08"
    assert any("Real money" in line["value"] for line in preview["lines"])
    assert "$20.00" in domains._prompt(context())


def _abilities():
    return [domains.build()]


async def _run(ctx, client):
    abilities = _abilities()
    return await runner.run_agent(
        ctx, client=client, abilities=abilities,
        contract=runner.ResultContract(finish=result.finish_tool(abilities),
                                       normalize=lambda a, s: result.normalize(a, s, abilities)),
        instructions="sys", first_input=[],
    )


def _policy():
    return PolicyContext(surface="assistant", private_conversation=True,
                         grounding=Grounding(user_texts=("register matcha.dev on porkbun.com",)))


@pytest.mark.asyncio
async def test_a_registration_is_always_held_for_a_yes(monkeypatch):
    wire_store(monkeypatch)
    pb = FakePorkbun({"matcha.dev": 1108})
    monkeypatch.setattr(porkbun, "get_porkbun", lambda: pb)
    client = FakeClient([
        response(call("check_domains", {"domains": ["matcha.dev"]})),
        response(call("register_domain", {"domain": "matcha.dev"})),
    ])
    out = await _run(context(policy=_policy(), commit_mode="live"), client)
    assert out.kind == "confirmation" and out.decision.reason == "always_confirm"
    assert out.pending.args == {"domain": "matcha.dev", "cost_cents": 1108}
    assert pb.registered == []
    assert FrozenAction.from_payload(json.loads(json.dumps(out.pending.to_payload()))) == out.pending


PROMPT_ID = uuid4()


def _frozen():
    args = {"domain": "matcha.dev", "cost_cents": 1108}
    return FrozenAction(tool="register_domain", args=args, targets=domains._targets(args, _state()),
                        preview=domains._preview(args, _state()))


async def _approve(monkeypatch, conn, pb, commit_mode="live"):
    wire_store(monkeypatch)
    monkeypatch.setattr(domains, "connection_or_direct", connection(conn))
    monkeypatch.setattr(porkbun, "get_porkbun", lambda: pb)
    receipts = []

    async def on_receipt(receipt):
        receipts.append(receipt)

    client = FakeClient([response(call("finish", {"headline": "Registered", "summary": "Done."}))])
    await _run(context(policy=_policy(), commit_mode=commit_mode, resume=_frozen(),
                       resume_prompt_id=PROMPT_ID, channel_id=uuid4(), on_receipt=on_receipt), client)
    return receipts


def _conn(row_id, *, status="registering", inserted=True, error=None):
    return FakeConn().on("INSERT INTO mw_agent_domain_registrations",
                         {"id": row_id, "status": status, "error": error, "inserted": inserted})


@pytest.mark.asyncio
async def test_a_yes_registers_once_under_the_row_id(monkeypatch):
    row_id = uuid4()
    conn, pb = _conn(row_id), FakePorkbun()
    receipts = await _approve(monkeypatch, conn, pb)
    query, args = conn.ran("INSERT INTO mw_agent_domain_registrations")[0][1:]
    assert "ON CONFLICT (prompt_id)" in query and args[3] == PROMPT_ID and args[5:] == ("matcha.dev", 1108)
    assert pb.registered == [("matcha.dev", 1108, f"espresso-domain-{row_id}")]
    assert "status = 'registered'" in conn.ran("UPDATE mw_agent_domain_registrations")[0][1]
    assert receipts[0]["status"] == "done" and receipts[0]["title"] == "Registered matcha.dev"


@pytest.mark.asyncio
async def test_a_second_run_of_a_registered_yes_buys_nothing(monkeypatch):
    pb = FakePorkbun()
    receipts = await _approve(monkeypatch, _conn(uuid4(), status="registered", inserted=False), pb)
    assert pb.registered == []
    assert receipts[0]["status"] == "done" and "nothing was bought again" in receipts[0]["note"]


@pytest.mark.asyncio
async def test_a_second_run_of_a_failed_yes_does_not_retry(monkeypatch):
    pb = FakePorkbun()
    receipts = await _approve(monkeypatch, _conn(uuid4(), status="failed", inserted=False, error="Insufficient funds"), pb)
    assert pb.registered == [] and receipts[0]["status"] == "failed"
    assert "Insufficient funds" in receipts[0]["note"]


@pytest.mark.asyncio
async def test_an_unsettled_registration_is_resent_under_the_same_key(monkeypatch):
    row_id = uuid4()
    pb = FakePorkbun()
    receipts = await _approve(monkeypatch, _conn(row_id, inserted=False), pb)
    assert pb.registered == [("matcha.dev", 1108, f"espresso-domain-{row_id}")]
    assert receipts[0]["status"] == "done"


@pytest.mark.asyncio
async def test_porkbun_refusing_is_a_failure_on_the_row(monkeypatch):
    conn = _conn(uuid4())
    receipts = await _approve(monkeypatch, conn, FakePorkbun(register_error=porkbun.PorkbunError("Insufficient funds")))
    update = conn.ran("UPDATE mw_agent_domain_registrations")[0]
    assert "status = 'failed'" in update[1] and update[2][1] == "Insufficient funds"
    assert receipts[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_a_request_that_may_have_reached_porkbun_is_unknown_and_stays_registering(monkeypatch):
    error = porkbun.PorkbunError("Porkbun request failed: timeout")
    error.__cause__ = httpx.ReadTimeout("timeout")
    conn = _conn(uuid4())
    receipts = await _approve(monkeypatch, conn, FakePorkbun(register_error=error))
    assert conn.ran("UPDATE mw_agent_domain_registrations") == []
    assert receipts[0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_registered_but_not_recorded_is_unknown_not_failed(monkeypatch):
    conn = _conn(uuid4()).on("UPDATE mw_agent_domain_registrations", RuntimeError("db gone"))
    receipts = await _approve(monkeypatch, conn, FakePorkbun())
    assert receipts[0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_a_dry_run_registers_nothing(monkeypatch):
    pb = FakePorkbun()
    conn = _conn(uuid4())
    receipts = await _approve(monkeypatch, conn, pb, commit_mode="dry_run")
    assert pb.registered == [] and conn.calls == [] and receipts[0]["status"] == "dry_run"


# ── who gets it ───────────────────────────────────────────────────────────────

async def _no_fetch(_url):
    return {}, set()


def test_domains_need_porkbun_keys_the_allowance_the_switch_and_the_private_conversation(monkeypatch):
    allowed = frozenset({domains.ALLOWANCE})
    granted = {domains.KEY: {}}
    monkeypatch.setattr(domains, "porkbun_configured", lambda: True)
    ability = next(a for a in catalog.build_catalog(fetch_page=_no_fetch) if a.key == domains.KEY)
    assert catalog.availability(ability, catalog.Situation(private=True, grants=granted, allowed=allowed)).available
    assert catalog.availability(ability, catalog.Situation(private=True, allowed=allowed)).needs_consent
    assert not catalog.offered(ability, catalog.Situation(private=True, grants=granted))
    assert not catalog.availability(ability, catalog.Situation(private=False, grants=granted, allowed=allowed)).available
    assert ability.consent_version == consent.current_version(domains.KEY)
    monkeypatch.setattr(domains, "porkbun_configured", lambda: False)
    ability = next(a for a in catalog.build_catalog(fetch_page=_no_fetch) if a.key == domains.KEY)
    assert catalog.availability(ability, catalog.Situation(private=True, grants=granted, allowed=allowed)).reason \
        == "Not set up on this server yet."


def test_porkbun_readiness_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: (_ for _ in ()).throw(RuntimeError("not loaded")))
    monkeypatch.setenv("PORKBUN_API_KEY", "pk1")
    monkeypatch.delenv("PORKBUN_SECRET_KEY", raising=False)
    assert domains.porkbun_configured() is False
    monkeypatch.setenv("PORKBUN_SECRET_KEY", "sk1")
    assert domains.porkbun_configured() is True
