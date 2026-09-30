import pytest

from app.matcha.services.matcha_work.browser import booking, computer_use, forms

from .fakes import FakePage, session_factory

JOB = {"url": "https://www.tables.example/r/nopa", "host": "www.tables.example", "venue": "Nopa",
       "party_size": 4, "date": "2026-10-02", "time": "19:00", "special_requests": "Window table",
       "contact": {"name": "Ana Lee", "phone": "+1 555 010 0100", "email": "ana@example.com"}}
REQUEST = forms.ReservationRequest(name="Ana Lee", phone="+1 555 010 0100", email="ana@example.com",
                                   party_size=4, date="2026-10-02", time="19:00")
TYPE = {"x": 500, "y": 500}


def test_the_instructions_carry_the_booking_and_never_the_contact_details():
    text = booking.instructions_for(JOB)
    assert "Nopa" in text and "2026-10-02" in text and "19:00" in text and "Window table" in text
    assert "{{first_name}}" in text and "{{email}}" in text
    for secret in ("Ana", "555", "ana@example.com"):
        assert secret not in text
    assert "Special requests" not in booking.instructions_for({**JOB, "special_requests": ""})


@pytest.mark.asyncio
async def test_a_card_number_is_never_typed():
    guard = booking.guard_for(REQUEST)
    page = FakePage(element={"name": "notes"})
    for text in ("4242 4242 4242 4242", "card 4242424242424242 exp 12/29"):
        verdict = await guard(page, "type_text_at", {**TYPE, "text": text})
        assert verdict.stop == "handoff"


@pytest.mark.asyncio
async def test_a_payment_field_stops_the_booking_before_anything_is_typed_or_clicked():
    guard = booking.guard_for(REQUEST)
    for element in ({"autocomplete": "cc-number"}, {"label": "Security code"},
                    {"src": "https://js.stripe.com/v3/elements-inner-card.html", "tag": "IFRAME"}):
        for name in ("type_text_at", "click_at", "double_click_at"):
            verdict = await guard(FakePage(element=element), name, {**TYPE, "text": "{{name}}"})
            assert verdict.stop == "handoff", (element, name)


@pytest.mark.asyncio
async def test_a_login_wall_or_a_captcha_stops_it():
    guard = booking.guard_for(REQUEST)
    login = await guard(FakePage(element={"type": "password"}), "click_at", TYPE)
    assert login.stop == "blocked"
    captcha = await guard(FakePage(text="Please verify you are human"), "scroll_document", {})
    assert captcha.stop == "blocked"
    framed = await guard(FakePage(frames=["https://newassets.hcaptcha.com/captcha"]), "click_at", TYPE)
    assert framed.stop == "blocked"


@pytest.mark.asyncio
async def test_placeholders_are_filled_and_other_actions_pass():
    guard = booking.guard_for(REQUEST)
    page = FakePage(element={"name": "first_name"})
    typed = await guard(page, "type_text_at", {**TYPE, "text": "{{first_name}} {{last_name}}"})
    assert typed.args["text"] == "Ana Lee" and typed.stop is None and typed.allow
    assert await guard(page, "click_at", TYPE) is None
    assert await guard(page, "scroll_document", {"direction": "down"}) is None
    assert await guard(page, "navigate", {"url": "https://evil.example"}) is None  # the allowlist decides
    # A page whose scripts cannot be read is treated as having nothing under the pointer.
    broken = FakePage()

    async def boom(*_a, **_k):
        raise RuntimeError("navigating")

    broken.evaluate = boom
    assert (await guard(broken, "type_text_at", {**TYPE, "text": "{{email}}"})).args["text"] == "ana@example.com"


def _result(**over):
    base = dict(text="", turns=5, stopped=None, error=None)
    base.update(over)
    return computer_use.Outcome(**base)


def test_the_status_comes_from_what_the_page_shows():
    url = "https://www.tables.example/done"
    confirmed = "Your reservation is confirmed. Confirmation number: AB-1234"
    assert booking.outcome_of(_result(text="CONFIRMED"), confirmed, url) == {
        "url": url, "turns": 5, "status": "booked", "confirmation": "AB-1234"}
    # The model says so, the page does not: not a booking to rely on.
    assert booking.outcome_of(_result(text="CONFIRMED AB-1234"), "Pick a time", url)["status"] == "unverified"
    assert booking.outcome_of(_result(text="unavailable, nearest 18:30"), "No tables", url)["status"] == "unavailable"
    assert booking.outcome_of(_result(stopped="handoff"), confirmed, url)["status"] == "handoff"
    assert booking.outcome_of(_result(stopped="blocked"), "", url)["status"] == "blocked"
    for stuck in (_result(stopped="turns"), _result(stopped="time"), _result(error="model_timeout")):
        assert booking.outcome_of(stuck, "Pick a time", url)["status"] == "failed"
        # Cut off on a page that reads as confirmed: something to check, never "booked".
        assert booking.outcome_of(stuck, confirmed, url)["status"] == "unverified"
    # A verification-code step that timed out is not a booking.
    code_step = "Enter the confirmation code we sent to your phone"
    assert booking.outcome_of(_result(stopped="time"), code_step, url)["status"] == "failed"


@pytest.mark.asyncio
async def test_a_booking_stays_on_the_one_site_and_is_guarded():
    page = FakePage(text="You're all set. Confirmation code: ZX99")
    policies, driven = [], {}

    async def drive(page, *, instructions, model, policy, before_action, on_status):
        driven.update(instructions=instructions, model=model, policy=policy)
        verdict = await before_action(page, "type_text_at", {"x": 1, "y": 1, "text": "{{phone}}"})
        driven["typed"] = verdict.args["text"]
        return _result(text="CONFIRMED", turns=7)

    out = await booking.book(JOB, open_session=session_factory(page, policies), drive=drive, model="gemini-x")
    assert out == {"url": JOB["url"], "turns": 7, "status": "booked", "confirmation": "ZX99"}
    assert policies[0].allowed_hosts == frozenset({"tables.example"})
    assert policies[0].max_turns == booking.MAX_TURNS
    assert page.log[0] == ("goto", (JOB["url"],))
    assert driven["typed"] == "+1 555 010 0100" and driven["model"] == "gemini-x"
    assert "Ana" not in driven["instructions"]


@pytest.mark.asyncio
async def test_a_page_that_never_finishes_loading_is_still_driven():
    page = FakePage(text="Pick a time")

    async def slow(url, **_kw):
        raise TimeoutError()

    page.goto = slow

    async def drive(page, **_kw):
        return _result(stopped="blocked")

    out = await booking.book({**JOB, "contact": {"name": "Ana Lee", "email": "ana@example.com"}},
                             open_session=session_factory(page), drive=drive, model="m")
    assert out["status"] == "blocked"
