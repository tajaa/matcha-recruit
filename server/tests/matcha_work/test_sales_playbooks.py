"""The consulting playbook: its draft checks, Matcha's own offer, and how the
campaign store and the assistant's Sales tools use them. No database."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.sales import CampaignCreate, ProspectPatch
from app.matcha.services.matcha_work import sales_playbooks as playbooks
from app.matcha.services.matcha_work import sales_service as sales
from tests.agent_runtime.helpers import FakeConn, connection

from .test_sales_campaigns import CAMPAIGN, ITEM, PROJECT, USER, access_row, campaign, prospect

CTA = "https://hey-matcha.com/services?book=1"
SIGNAL = "Hiring their first HR Generalist (Greenhouse, posted Oct 2026)"
RESEARCH = "Acme Dental runs 4 clinics in Texas and Oklahoma; Dr. Ana Ruiz is the owner."
GOOD = (
    "Hi Ana,\n\nI saw Acme Dental is hiring its first HR Generalist. Before that hire starts, we help "
    "practices with 4 clinics in Texas and Oklahoma set up handbooks and pay practices that hold up in both states.\n\n"
    f"Worth a 20-minute call? {CTA}\n\nDiego"
)


def problems(subject="Your first HR hire", body=GOOD, signal=SIGNAL, evidence=None):
    return playbooks.draft_problems(
        subject, body, cta_url=CTA, signal=signal,
        evidence=evidence if evidence is not None else "\n".join([RESEARCH, SIGNAL, playbooks.HOUSE["offer"]]),
    )


# ── the checks ───────────────────────────────────────────────────────────────

def test_a_short_signal_led_draft_with_one_ask_passes():
    assert problems() == []


@pytest.mark.parametrize("change, expect", [
    (dict(signal=""), "why-now signal"),
    (dict(subject="Re: your HR"), "Re:"),
    (dict(subject="x" * 71), "subject"),
    (dict(body=GOOD + " word" * 150), "150 words"),
    (dict(body=GOOD.replace(CTA, "")), "booking link"),
    (dict(body=GOOD + "\nSee https://example.test/case-study"), "no link but"),
    (dict(body=GOOD.replace("4 clinics", "12 clinics")), "12"),
    (dict(body=GOOD + "\nClients see 42 gaps closed in 10 days."), "42"),
    (dict(body=GOOD + "\nWe cut turnover in half and tripled retention."), "tripled"),
    (dict(body=GOOD + "\nYour handbook likely violates Texas law."), "violates"),
    (dict(body=GOOD + "\nAvoid OSHA fines and lawsuits."), "fines"),
    (dict(body=GOOD + "\nWe guarantee results."), "guarantee"),
])
def test_what_keeps_a_draft_from_going_out(change, expect):
    found = problems(**change)
    assert found and any(expect in p for p in found), found


def test_a_spelled_out_number_is_its_digits():
    assert problems(body=GOOD.replace("4 clinics", "four clinics")) == []
    assert problems(body=GOOD.replace("4 clinics", "five clinics"))


def test_numbers_come_from_the_research_or_offer_and_links_dont_count():
    # "20" is in the offer ("a 20-minute call"), "4" in the research; the link's "1" isn't a claim.
    assert problems() == []
    assert problems(evidence="") and "4" in " ".join(problems(evidence=""))


def test_flags_only_for_consulting_drafts():
    row = {"subject": "Hello", "body": "Hi", "signal": "", "research": ""}
    assert playbooks.review_flags({"playbook": ""}, row) == []
    assert playbooks.review_flags({"playbook": "consulting", "cta_url": CTA}, {"subject": "", "body": ""}) == []
    assert playbooks.review_flags({"playbook": "consulting", "cta_url": CTA, "offer": ""}, row)


def test_the_house_offer_claims_no_results():
    # The Services page's case numbers ("42 gaps closed", "7 states") aren't in what outreach may cite.
    offer = playbooks.HOUSE["offer"]
    assert "42" not in offer and "7 states" not in offer
    assert playbooks.HOUSE["cta_url"] == CTA


def test_house_is_for_matcha_staff(monkeypatch):
    from app.core import dependencies

    monkeypatch.setattr(dependencies, "_is_master_admin", lambda email: email == "owner@example.com")
    assert playbooks.house_available("admin", "staff@example.com")
    assert playbooks.house_available("individual", "owner@example.com")
    assert not playbooks.house_available("individual", "someone@example.com")


def test_the_guide_lists_every_segment_and_service():
    guide = playbooks.guide()
    assert [s["key"] for s in guide["segments"]] == ["growing", "regulated", "ai", "hourly"]
    assert {s["service"] for s in guide["segments"]} <= {s["key"] for s in guide["services"]}
    assert all(s["signals"] and s["buyer"] for s in guide["segments"])


# ── the campaign store ───────────────────────────────────────────────────────

@pytest.fixture
def wired(monkeypatch):
    conn = FakeConn().on("FROM mw_projects p", access_row())
    monkeypatch.setattr(sales, "connection_or_direct", connection(conn))
    return conn


@pytest.mark.asyncio
async def test_staff_start_from_matchas_offer_and_others_are_refused(wired, monkeypatch):
    monkeypatch.setattr(playbooks, "house_available", lambda role, email: role == "admin")
    wired.on("FROM users WHERE id", {"role": "admin", "email": "staff@example.com"})
    wired.on("INSERT INTO mw_sales_campaigns", campaign(playbook="consulting"))
    await sales.create_campaign(PROJECT, USER, CampaignCreate(
        request_id=uuid4(), title="Clinics", target="Dental clinics in Texas", house=True,
    ))
    args = wired.ran("INSERT INTO mw_sales_campaigns")[0][2]
    # What they wrote wins; the preset fills the rest.
    assert args[4] == "Dental clinics in Texas" and args[5] == playbooks.HOUSE["offer"]
    assert args[7:] == ("consulting", CTA)

    wired.on("FROM users WHERE id", {"role": "individual", "email": "someone@example.com"})
    with pytest.raises(sales.SalesError) as err:
        await sales.create_campaign(PROJECT, USER, CampaignCreate(request_id=uuid4(), title="x", house=True))
    assert err.value.code == 403
    assert (await sales.playbook_options(USER))["house"] is None
    wired.on("FROM users WHERE id", {"role": "admin", "email": "staff@example.com"})
    options = await sales.playbook_options(USER)
    assert options["house"]["cta_url"] == CTA and options["playbooks"][0]["key"] == "consulting"


@pytest.mark.asyncio
async def test_reading_a_consulting_campaign_flags_drafts_and_carries_the_playbook(wired):
    wired.on("SELECT * FROM mw_sales_campaigns", campaign(playbook="consulting", cta_url=CTA))
    wired.on("ORDER BY created_at,id OFFSET", [prospect(signal="", subject="Hi", body="Hello there")])
    wired.on("GROUP BY status", [])
    data = await sales.read_campaign(CAMPAIGN, USER)
    flags = data["prospects"][0]["review_flags"]
    assert any("signal" in f for f in flags) and any("booking link" in f for f in flags)
    assert data["playbook"]["key"] == "consulting"
    wired.on("SELECT * FROM mw_sales_campaigns", campaign())
    data = await sales.read_campaign(CAMPAIGN, USER)
    assert "review_flags" not in data["prospects"][0] and "playbook" not in data


@pytest.mark.asyncio
async def test_signal_and_fit_can_change_on_a_frozen_message_without_reopening_it(wired):
    sent = prospect(status="sent")
    wired.on("SELECT * FROM mw_sales_campaigns", campaign())
    wired.on("FROM mw_sales_prospects WHERE campaign_id = $1 AND id = $2 FOR UPDATE", sent)
    wired.on("UPDATE mw_sales_prospects SET", sent | {"fit": 3})
    await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch(fit=3, signal=SIGNAL, segment="growing"))
    [(_m, query, _a)] = wired.ran("UPDATE mw_sales_prospects SET")
    assert "status" not in query.split("WHERE")[0]
    with pytest.raises(sales.SalesError, match="frozen"):
        await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch(body="new"))


# ── the assistant ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_assistant_must_back_a_signal_and_pass_the_checks(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime.abilities import sales as ability
    from app.matcha.services.matcha_work.agent_runtime.context import RunState
    from tests.agent_runtime.helpers import context

    cid, pid = str(CAMPAIGN), str(ITEM)
    read = AsyncMock(return_value={
        "campaign": {"id": cid, "playbook": "consulting", "offer": playbooks.HOUSE["offer"], "cta_url": CTA},
        "prospects": [{"id": pid, "research": RESEARCH, "signal": "", "subject": "", "body": ""}],
    })
    patch = AsyncMock(side_effect=lambda c, p, u, data: {"id": pid, "research": RESEARCH,
                                                         "signal": data.signal or SIGNAL, "subject": "", "body": ""})
    monkeypatch.setattr(ability.store, "read_campaign", read)
    monkeypatch.setattr(ability.store, "patch_prospect", patch)
    state = RunState(started=0, sessions={"sales": ability.SalesSession()})
    tools = {t.name: t for t in ability.build().tools}

    async def call(name, args):
        return await tools[name].handler(context(), state, args, 60)

    await call("read_sales_campaign", {"campaign_id": cid})
    update = {"campaign_id": cid, "prospect_id": pid}
    out = await call("update_sales_prospect", update | {"changes": {"subject": "Hi", "body": GOOD}})
    assert out.status == "error" and "signal" in out.payload["error"]
    out = await call("update_sales_prospect", update | {"changes": {"signal": SIGNAL}})
    assert out.status == "error" and "source" in out.payload["error"]

    state.provenance.add("https://boards.greenhouse.io/acme/jobs/1")
    out = await call("update_sales_prospect", update | {"changes": {
        "signal": SIGNAL, "segment": "growing", "service": "hr", "fit": 3,
        "sources": ["https://boards.greenhouse.io/acme/jobs/1"]}})
    assert out.status == "ok"
    out = await call("update_sales_prospect", update | {"changes": {
        "subject": "Your first HR hire", "body": GOOD + "\nClients see 42 gaps closed."}})
    assert out.status == "error" and "42" in out.payload["error"]
    out = await call("update_sales_prospect", update | {"changes": {"subject": "Your first HR hire", "body": GOOD}})
    assert out.status == "ok"
    assert patch.await_count == 2


@pytest.mark.asyncio
async def test_the_assistant_starts_matchas_campaign_with_the_house_offer(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime.abilities import sales as ability
    from app.matcha.services.matcha_work.agent_runtime.context import RunState
    from tests.agent_runtime.helpers import context

    create = AsyncMock(return_value={"id": str(CAMPAIGN), "playbook": "consulting", "offer": "o", "cta_url": CTA})
    monkeypatch.setattr(ability.store, "list_projects", AsyncMock(return_value=[{"id": str(PROJECT), "title": "Sales"}]))
    monkeypatch.setattr(ability.store, "create_campaign", create)
    state = RunState(started=0, sessions={"sales": ability.SalesSession()})
    tools = {t.name: t for t in ability.build().tools}
    await tools["list_sales_workspaces"].handler(context(), state, {}, 60)
    out = await tools["create_sales_campaign"].handler(context(), state, {
        "project_id": str(PROJECT), "title": "Matcha consulting", "use_matcha_offer": True}, 60)
    assert out.status == "ok" and out.payload["playbook_guide"]["key"] == "consulting"
    data = create.await_args.args[2]
    assert data.house is True
    assert state.sessions["sales"].campaign_info[str(CAMPAIGN)]["cta_url"] == CTA
    assert "use_matcha_offer" in ability.prompt_block(context())


# ── review fixes (#921) ──────────────────────────────────────────────────────

def test_everyday_words_are_not_legal_threats():
    # "fine-tune" and a contact named Sue pass; real threats still don't.
    assert problems(body=GOOD.replace("Hi Ana", "Hi Sue") + "\nHappy to fine-tune it with you.") == []
    assert problems(body=GOOD + "\nYou could be fined.")
    assert problems(body=GOOD + "\nThis avoids litigation.")


@pytest.mark.parametrize("draft, research", [
    ("two hundred staff", "a team of 200 people"),
    ("a $2.5 million budget", "owns a $2.5M budget"),
    ("twenty-five thousand square feet", "25,000 sq ft"),
    ("40k members", "40,000 members"),
])
def test_spelled_out_and_scaled_numbers_match_their_digits(draft, research):
    body = GOOD.replace("4 clinics", f"4 clinics and {draft}")
    assert problems(body=body, evidence="\n".join([RESEARCH, research, SIGNAL, playbooks.HOUSE["offer"]])) == []
    assert problems(body=body)  # and still refused without that research


def test_a_consulting_campaign_needs_its_booking_link():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="booking link"):
        CampaignCreate(request_id=uuid4(), title="x", playbook="consulting")
    assert CampaignCreate(request_id=uuid4(), title="x", playbook="consulting", house=True).house
    found = playbooks.draft_problems("Hi", GOOD, cta_url="", signal=SIGNAL, evidence=RESEARCH)
    assert any("booking link before drafting" in p for p in found)


@pytest.mark.asyncio
async def test_a_campaign_cant_become_consulting_without_a_booking_link(wired):
    from app.matcha.models.matcha_work.sales import CampaignPatch

    wired.on("SELECT * FROM mw_sales_campaigns", campaign())
    with pytest.raises(sales.SalesError, match="booking link"):
        await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(playbook="consulting"))
    wired.on("UPDATE mw_sales_campaigns SET", campaign(playbook="consulting", cta_url=CTA))
    await sales.update_campaign(CAMPAIGN, USER, CampaignPatch(playbook="consulting", cta_url=CTA))


@pytest.mark.asyncio
async def test_a_signal_with_its_sources_saves_on_a_sent_message(wired):
    sent = prospect(status="sent")
    wired.on("SELECT * FROM mw_sales_campaigns", campaign())
    wired.on("FROM mw_sales_prospects WHERE campaign_id = $1 AND id = $2 FOR UPDATE", sent)
    wired.on("UPDATE mw_sales_prospects SET", sent)
    await sales.patch_prospect(CAMPAIGN, ITEM, USER, ProspectPatch(
        signal=SIGNAL, sources=["https://boards.greenhouse.io/acme/jobs/1"], research=RESEARCH))
    [(_m, query, _a)] = wired.ran("UPDATE mw_sales_prospects SET")
    assert "status" not in query.split("WHERE")[0]


@pytest.mark.asyncio
async def test_template_drafts_in_a_consulting_campaign_are_checked(wired):
    from app.matcha.models.matcha_work.sales import Template

    wired.on("SELECT * FROM mw_sales_campaigns", campaign(playbook="consulting", cta_url=CTA, offer=playbooks.HOUSE["offer"]))
    ready = prospect(id=uuid4(), subject="", body="", signal=SIGNAL, research=RESEARCH)
    bare = prospect(id=uuid4(), name="Bo", subject="", body="", signal="", research="")
    wired.on("status IN ('prospect','draft','failed')", [ready, bare])
    template = Template(subject="Your first HR hire", body=f"Hi {{{{name}}}}, saw {{{{research}}}} Worth a call? {CTA}")
    out = await sales.draft_template(CAMPAIGN, USER, template, overwrite=False, checked=True)
    assert out["drafted"] == 1 and out["skipped_count"] == 1
    assert out["skipped"][0]["prospect"] == "Bo" and any("signal" in p for p in out["skipped"][0]["problems"])
    # The person's own template from the Mac isn't held back: they review every message.
    out = await sales.draft_template(CAMPAIGN, USER, template)
    assert out["drafted"] == 2


@pytest.mark.asyncio
async def test_the_assistant_checks_numbers_against_research_before_it_was_shortened(monkeypatch):
    from app.matcha.services.matcha_work.agent_runtime.abilities import sales as ability
    from app.matcha.services.matcha_work.agent_runtime.context import RunState
    from tests.agent_runtime.helpers import context

    cid, pid = str(CAMPAIGN), str(ITEM)
    long_research = "x " * 600 + "Acme Dental runs 4 clinics."  # the number is past 1,000 characters
    monkeypatch.setattr(ability.store, "read_campaign", AsyncMock(return_value={
        "campaign": {"id": cid, "playbook": "consulting", "offer": playbooks.HOUSE["offer"], "cta_url": CTA},
        "prospects": [{"id": pid, "research": long_research, "signal": SIGNAL, "subject": "", "body": "",
                       "notes": "n" * 3000, "sources": []} for _ in range(1)],
    }))
    monkeypatch.setattr(ability.store, "patch_prospect", AsyncMock(return_value={"id": pid}))
    state = RunState(started=0, sessions={"sales": ability.SalesSession()})
    tools = {t.name: t for t in ability.build().tools}
    from app.matcha.services.matcha_work.agent_runtime.context import RunLimits

    ctx = context(limits=RunLimits(max_tool_output_chars=2000))
    out = await tools["read_sales_campaign"].handler(ctx, state, {"campaign_id": cid}, 60)
    assert out.payload["prospects"][0].get("text_truncated")
    out = await tools["update_sales_prospect"].handler(ctx, state, {
        "campaign_id": cid, "prospect_id": pid, "changes": {"subject": "Your first HR hire", "body": GOOD}}, 60)
    assert out.status == "ok", out.payload


def test_segment_and_service_lists_agree_everywhere():
    import re as _re
    from pathlib import Path
    from typing import get_args

    from app.matcha.models.matcha_work import sales as models

    assert set(get_args(models.Segment)) - {""} == set(playbooks.SEGMENTS)
    assert set(get_args(models.Service)) - {""} == set(playbooks.SERVICES)
    assert set(get_args(models.Playbook)) == set(playbooks.PLAYBOOKS)
    migration = (Path(__file__).parents[2] / "alembic/versions/mwsales03_sales_playbooks.py").read_text()

    def listed(column):
        return set(_re.findall(r"'(\w*)'", _re.search(rf"CHECK \({column} IN \(([^)]*)\)", migration).group(1)))

    assert listed("segment") == set(get_args(models.Segment))
    assert listed("service") == set(get_args(models.Service))
    assert listed("playbook") == set(get_args(models.Playbook))
