from app.matcha.services.matcha_work.browser import forms
from app.matcha.services.matcha_work.browser.session import BrowsePolicy, host_allowed

REQUEST = forms.ReservationRequest(
    name="Ana Maria Lee", phone="+1 555 010 0100", email="ana@example.com",
    party_size=4, date="2026-10-02", time="19:00",
)


def test_placeholders_are_filled_at_the_moment_of_typing():
    assert forms.substitute("{{first_name}}", REQUEST) == "Ana"
    assert forms.substitute("{{ last_name }}", REQUEST) == "Maria Lee"
    assert forms.substitute("{{name}} / {{phone}} / {{email}}", REQUEST) == (
        "Ana Maria Lee / +1 555 010 0100 / ana@example.com")
    # An unknown placeholder stays visible instead of vanishing.
    assert forms.substitute("{{card_number}} {{name}}", REQUEST) == "{{card_number}} Ana Maria Lee"
    assert forms.substitute("", REQUEST) == "" and forms.substitute(None, REQUEST) == ""
    single = forms.ReservationRequest(name="Ana", phone="", email="", party_size=1, date="d", time="t")
    assert forms.substitute("{{last_name}}", single) == "Ana"
    assert forms.has_placeholder("hi {{email}}") and not forms.has_placeholder("hi {{card}}")


def test_a_card_field_is_recognised_however_it_is_described():
    payment = [
        {"autocomplete": "cc-number"}, {"autocomplete": "section-pay cc-csc"}, {"autocomplete": "cc-exp"},
        {"name": "cardnumber"}, {"id": "card_number"}, {"placeholder": "Card number"},
        {"aria_label": "Security code"}, {"label": "CVV"}, {"name": "cvc"},
        {"placeholder": "Expiry date"}, {"label": "Name on card"}, {"name": "cc-exp"},
        {"frame_host": "js.stripe.com"}, {"frame_host": "assets.braintreegateway.com"},
    ]
    for attrs in payment:
        assert forms.is_payment_field(attrs), attrs
    harmless = [
        {}, {"name": "first_name"}, {"autocomplete": "email"}, {"placeholder": "Phone number"},
        {"label": "Party size"}, {"name": "special_requests"}, {"frame_host": "www.tables.example"},
        {"label": "Expected arrival"}, {"name": "discount_code"},
    ]
    for attrs in harmless:
        assert not forms.is_payment_field(attrs), attrs
    assert not forms.is_payment_field(None) and not forms.is_payment_field("cc-number")


def test_login_walls_and_captchas_are_recognised():
    assert forms.is_login_field({"type": "password"})
    assert forms.is_login_field({"autocomplete": "current-password"})
    assert not forms.is_login_field({"type": "text", "autocomplete": "email"})
    assert not forms.is_login_field(None)
    assert forms.looks_like_captcha("Please verify you are human to continue")
    assert forms.looks_like_captcha("", ["https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html"])
    assert forms.looks_like_captcha("", ["https://www.google.com/recaptcha/api2/anchor?ar=1&k=x&size=normal"])
    assert forms.looks_like_captcha("", ["https://www.google.com/recaptcha/api2/bframe?k=x"])
    assert not forms.looks_like_captcha("Pick a time for your table", ["https://www.tables.example/book"])


def test_a_recaptcha_notice_is_not_a_challenge():
    # Invisible reCAPTCHA v3: the mandated footer line and its hidden anchor
    # frame are on the page, and nobody is being asked anything.
    footer = "Book a table. This site is protected by reCAPTCHA and the Google Privacy Policy applies."
    invisible = ["https://www.google.com/recaptcha/api2/anchor?ar=1&k=x&size=invisible&cb=y"]
    assert not forms.looks_like_captcha(footer, invisible)
    assert not forms.looks_like_captcha("Powered by hCaptcha and Turnstile", [])


def test_booked_means_the_page_said_so():
    assert forms.confirmation_in("Your reservation is confirmed! Confirmation number: AB-12345") == (True, "AB-12345")
    assert forms.confirmation_in("You're all set. See you on Friday.") == (True, None)
    assert forms.confirmation_in("Booking confirmed") == (True, None)
    assert forms.confirmation_in("Select a time to continue") == (False, None)
    # A site asking for a verification code, or a footer, confirms nothing.
    assert forms.confirmation_in("Enter the confirmation code we sent to your phone") == (False, None)
    assert forms.confirmation_in("Thanks for visiting. See you soon!") == (False, None)
    # A code needs a digit, so a word after "confirmation code" is never one.
    assert forms.confirmation_in("Your booking is confirmed. Confirmation code sent by text") == (True, None)
    assert forms.confirmation_in("Reservation has been confirmed. Confirmation #: 7QX2") == (True, "7QX2")
    assert forms.confirmation_in("") == (False, None) and forms.confirmation_in(None) == (False, None)


def test_the_main_frame_stays_on_the_allowed_site():
    allowed = frozenset({"tables.example"})
    for url in ("https://tables.example/r/nopa", "https://www.tables.example/x", "http://tables.example",
                "https://book.tables.example./y", "about:blank"):
        assert host_allowed(url, allowed), url
    for url in ("https://evil.example/", "https://tables.example.evil.test/", "https://nottables.example/",
                "javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi", "https://", "",
                "ftp://tables.example/", "http://[::1", "chrome://settings"):
        assert not host_allowed(url, allowed), url


def test_without_an_allowlist_any_public_web_page_may_be_opened():
    for url in ("https://anything.example/", "http://other.test/x", "about:blank"):
        assert host_allowed(url, None)
    for url in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi"):
        assert not host_allowed(url, None)
    policy = BrowsePolicy()
    assert policy.allowed_hosts is None and policy.max_turns == 15
