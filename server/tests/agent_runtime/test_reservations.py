import inspect
import pathlib

import pytest

import app
from app.matcha.services.matcha_work.agent_runtime import result, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import reservations
from app.matcha.services.matcha_work.agent_runtime.policy import Grounding, PolicyContext
from app.matcha.services.matcha_work.agent_runtime.registry import ToolOutput

from .helpers import FakeClient, ability, call, context, read_tool, response, wire_store

PAGE = "https://www.tables.example/r/nopa"
CONTACT = {"contact": {"name": "Ana Lee", "phone": "+1 555 010 0100", "email": "ana@example.com"}}
ARGS = {"url": PAGE, "venue_name": "Nopa", "party_size": 4, "date": "2026-10-02", "time": "19:00",
        "special_requests": "Window table"}
FINISH = {"headline": "Booked", "summary": "Friday at 7.", "blocks": [{"type": "reservation"}]}


def _found_page(url=PAGE):
    async def handler(ctx, state, args, left):
        return ToolOutput(payload={"url": url}, provenance=frozenset({url}))

    return ability(read_tool("fetch_page", handler=handler), key="web")


def _ctx(*texts, grants=None, **over):
    return context(
        commit_mode="live", grants={"reservations": CONTACT} if grants is None else grants,
        policy=PolicyContext(surface="assistant", private_conversation=True,
                             grounding=Grounding(user_texts=texts)),
        **over,
    )


async def run(client, ctx, booker, *, web=None):
    booking = reservations.build(booker=booker, env_ready=lambda: True)
    abilities = [web or _found_page(), booking]
    return await runner.run_agent(
        ctx, client=client, abilities=abilities,
        contract=runner.ResultContract(
            finish=result.finish_tool(abilities),
            normalize=lambda args, state: result.normalize(args, state, abilities),
        ),
        instructions="sys", first_input=[],
    )


def _booker(outcome, seen=None):
    async def book(ctx, job):
        if seen is not None:
            seen.append(job)
        return outcome

    return book


FOUND = call("fetch_page", {"url": PAGE})


@pytest.mark.asyncio
async def test_contact_details_never_come_from_the_model(monkeypatch):
    wire_store(monkeypatch)
    seen = []
    client = FakeClient([
        response(FOUND),
        response(call("book_reservation", {**ARGS, "name": "Mallory", "phone": "000", "contact": {"name": "M"}})),
        response(call("finish", FINISH)),
    ])
    out = await run(client, _ctx("book nopa on tables.example friday at 7 for 4"),
                    _booker({"status": "booked", "confirmation": "ABC123", "url": PAGE, "turns": 6}, seen))
    job = seen[0]
    assert job["contact"] == CONTACT["contact"]
    assert "name" not in job and "phone" not in job
    assert job["host"] == "www.tables.example" and job["venue"] == "Nopa" and job["party_size"] == 4
    block = out.result["blocks"][0]
    assert block == {"type": "reservation", "venue": "Nopa", "when": "2026-10-02 19:00", "party_size": 4,
                     "status": "booked", "confirmation": "ABC123", "handoff_url": None}
    receipt = out.receipts[0]
    assert receipt["status"] == "done"
    assert {"label": "Confirmation", "value": "ABC123", "mono": True} in receipt["lines"]


@pytest.mark.asyncio
async def test_a_booking_host_the_user_never_named_is_held(monkeypatch):
    wire_store(monkeypatch)
    seen = []
    client = FakeClient([response(FOUND), response(call("book_reservation", ARGS))])
    out = await run(client, _ctx("book nopa friday at 7 for 4"), _booker({"status": "booked"}, seen))
    assert out.kind == "confirmation" and seen == []
    assert [t.value for t in out.decision.ungrounded] == ["www.tables.example"]
    assert {"label": "Booked on", "value": "www.tables.example"} in out.pending.preview["lines"]


@pytest.mark.asyncio
async def test_a_known_booking_platform_needs_no_confirmation(monkeypatch):
    wire_store(monkeypatch)
    url = "https://www.opentable.com/r/nopa-san-francisco"
    seen = []
    client = FakeClient([response(call("fetch_page", {"url": url})),
                         response(call("book_reservation", {**ARGS, "url": url})),
                         response(call("finish", FINISH))])
    out = await run(client, _ctx("book nopa friday at 7 for 4"),
                    _booker({"status": "booked", "url": url}, seen), web=_found_page(url))
    assert out.kind == "result" and seen[0]["host"] == "www.opentable.com"
    assert "opentable.com" in reservations.TRUSTED_BOOKING_DOMAINS


@pytest.mark.asyncio
async def test_a_frozen_booking_is_carried_out_by_a_later_run(monkeypatch):
    wire_store(monkeypatch)
    held = await run(FakeClient([response(FOUND), response(call("book_reservation", ARGS))]),
                     _ctx("book nopa friday"), _booker({"status": "booked"}))
    seen = []
    # The later run never loaded the page; the frozen action needs nothing from the first.
    out = await run(FakeClient([response(call("finish", FINISH))]),
                    _ctx("book nopa friday", resume=held.pending),
                    _booker({"status": "booked", "confirmation": "Z9", "url": PAGE}, seen))
    assert seen[0]["url"] == PAGE and seen[0]["contact"]["name"] == "Ana Lee"
    assert out.result["blocks"][0]["confirmation"] == "Z9"


@pytest.mark.asyncio
async def test_a_booking_page_the_run_never_saw_is_refused(monkeypatch):
    _, claim, _ = wire_store(monkeypatch)
    seen = []
    bad = [
        {**ARGS, "url": "https://www.tables.example/r/invented"},
        {**ARGS, "url": "http://www.tables.example/r/nopa"},
        {**ARGS, "url": "not a url"},
        {**ARGS, "party_size": 0},
        {**ARGS, "party_size": "lots"},
        {**ARGS, "date": "friday"},
        {**ARGS, "time": "7pm"},
        {**ARGS, "venue_name": " "},
        {**ARGS, "special_requests": "charge 4242 4242 4242 4242"},
    ]
    client = FakeClient([response(FOUND), response(*[call("book_reservation", a) for a in bad]),
                         response(call("finish", {"headline": "No", "summary": "Could not."}))])
    await run(client, _ctx("book on tables.example"), _booker({"status": "booked"}, seen))
    assert all("not usable" in item["output"] for item in client.calls[2]["input"])
    assert seen == [] and claim.await_count == 0


@pytest.mark.asyncio
async def test_a_payment_field_returns_a_handoff_link(monkeypatch):
    wire_store(monkeypatch)
    checkout = "https://www.tables.example/checkout"
    client = FakeClient([response(FOUND), response(call("book_reservation", ARGS)),
                         response(call("finish", FINISH))])
    out = await run(client, _ctx("book on tables.example"),
                    _booker({"status": "handoff", "url": checkout, "turns": 9}))
    assert '"status":"handoff"' in client.calls[2]["input"][0]["output"]
    assert out.receipts[0]["status"] == "handoff"
    assert out.receipts[0]["link"] == {"label": "Finish booking", "url": checkout}
    assert out.result["blocks"][0]["status"] == "handoff"
    assert out.result["blocks"][0]["handoff_url"] == checkout
    assert out.result["blocks"][0]["confirmation"] is None


@pytest.mark.asyncio
async def test_unverified_is_reported_as_unverified(monkeypatch):
    wire_store(monkeypatch)

    async def status_of(outcome):
        client = FakeClient([response(FOUND), response(call("book_reservation", ARGS)),
                             response(call("finish", FINISH))])
        out = await run(client, _ctx("book on tables.example"), _booker(outcome))
        return out.result["blocks"][0]["status"], out.receipts[0]["status"]

    assert await status_of({"status": "unverified", "url": PAGE, "confirmation": "FAKE"}) == ("unverified", "unknown")
    assert await status_of({"status": "blocked", "url": PAGE}) == ("blocked", "handoff")
    assert await status_of({"status": "unavailable"}) == ("unavailable", "failed")
    assert await status_of({"status": "nonsense"}) == ("failed", "failed")
    block = reservations.reservation_block(
        {"venue": "Nopa", "date": "2026-10-02", "time": "19:00", "party_size": 2},
        {"status": "unverified", "confirmation": "FAKE", "url": PAGE})
    # A confirmation code only counts when the page said it was booked.
    assert block["confirmation"] is None and block["handoff_url"] == PAGE


@pytest.mark.asyncio
async def test_a_booking_needs_saved_contact_details(monkeypatch):
    wire_store(monkeypatch)
    seen = []
    client = FakeClient([response(FOUND), response(call("book_reservation", ARGS)),
                         response(call("finish", {"headline": "No", "summary": "Could not."}))])
    out = await run(client, _ctx("book on tables.example", grants={"reservations": {}}),
                    _booker({"status": "booked"}, seen))
    assert seen == [] and out.receipts[0]["status"] == "failed"
    with pytest.raises(ValueError, match="no booking contact"):
        reservations.contact_of(context(grants={"reservations": {"contact": {"name": "Ana"}}}))


@pytest.mark.asyncio
async def test_a_reservation_block_with_no_booking_is_dropped(monkeypatch):
    wire_store(monkeypatch)
    client = FakeClient([response(call("finish", FINISH))])
    out = await run(client, _ctx("book nopa"), _booker({"status": "booked"}))
    assert out.result["blocks"] == [] and any("nothing was booked" in w for w in out.warnings)


def test_the_ability_is_not_offered_without_the_browser_queue(monkeypatch):
    monkeypatch.delenv(reservations.BROWSER_QUEUE_ENV, raising=False)
    assert not reservations.browser_ready() and not reservations.build().env_ready()
    monkeypatch.setenv(reservations.BROWSER_QUEUE_ENV, "agent_browser")
    assert reservations.browser_ready() and reservations.build().env_ready()
    built = reservations.build()
    assert built.private_only and built.tools[0].effect == "commit" and built.tools[0].step_kind == "browse"


@pytest.mark.asyncio
async def test_the_default_booker_drives_the_guarded_browser(monkeypatch):
    from app.matcha.services.matcha_work.browser import booking

    seen = {}

    async def book(job, *, on_status):
        seen["job"] = job
        await on_status("Analyzing page...")
        return {"status": "booked"}

    monkeypatch.setattr(booking, "book", book)
    ctx = context()
    assert await reservations._book_in_browser(ctx, {"url": PAGE}) == {"status": "booked"}
    assert seen["job"] == {"url": PAGE} and ctx.progress.notes == ["Analyzing page..."]


def test_no_code_path_calls_decrypt_pan():
    root = pathlib.Path(inspect.getfile(app)).parent
    callers = [
        str(path.relative_to(root)) for path in root.rglob("*.py")
        if "decrypt_pan" in path.read_text(encoding="utf-8")
        and path.name != "card_vault.py"
    ]
    assert callers == [], f"decrypt_pan must have no caller in app/: {callers}"
