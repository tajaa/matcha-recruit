"""stripe-python 16 objects are not dicts; Cappe code reads Stripe data with `.get`.

Every call in `stripe_connect` hands back `StripeData` (plain dicts, also readable
by attribute), and the webhooks verify the signature, then read the signed JSON."""
import asyncio
import json
import time

import pytest
import stripe

from app.cappe.services import stripe_connect
from app.cappe.services.stripe_connect import StripeData, _call, _plain, _verified_event


def test_sdk_objects_become_plain_dicts_all_the_way_down():
    obj = stripe.StripeObject.construct_from(
        {"id": "sub_1", "metadata": {"k": "v"}, "items": {"data": [{"price": {"id": "price_1"}}]}}, "sk_test_x")
    with pytest.raises(AttributeError):
        obj.get("metadata")  # the SDK behaviour this guards against
    out = _plain(obj)
    assert isinstance(out, dict) and out.get("metadata").get("k") == "v"
    assert out["items"]["data"][0].get("price").get("id") == "price_1"
    assert out.id == "sub_1"
    with pytest.raises(AttributeError):
        out.missing
    assert json.loads(json.dumps(out)) == {"id": "sub_1", "metadata": {"k": "v"},
                                           "items": {"data": [{"price": {"id": "price_1"}}]}}


def test_tuples_and_lists_keep_their_shape():
    a = stripe.StripeObject.construct_from({"amount": 1}, "sk_test_x")
    pair = _plain((a, [a]))
    assert isinstance(pair, tuple) and pair[0].get("amount") == 1 and pair[1][0].get("amount") == 1


def test_call_runs_the_function_and_returns_plain_data():
    def fn(x, *, y):
        return stripe.StripeObject.construct_from({"x": x, "y": y}, "sk_test_x")
    out = asyncio.run(_call(fn, 1, y=2))
    assert isinstance(out, StripeData) and out.get("x") == 1 and out.y == 2


def _signed(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload.decode()}", secret)
    return f"t={ts},v1={sig}"


def test_a_verified_event_is_the_signed_json():
    secret = "whsec_test"
    payload = json.dumps({"id": "evt_1", "type": "invoice.paid", "account": "acct_1",
                          "data": {"object": {"id": "in_1", "parent": {"subscription_details": {"subscription": "sub_1"}}}}}).encode()
    event = _verified_event(payload, _signed(payload, secret), secret)
    assert event.get("data").get("object").get("parent").get("subscription_details").get("subscription") == "sub_1"


def test_a_bad_signature_is_refused():
    payload = b'{"id": "evt_1"}'
    with pytest.raises(stripe.SignatureVerificationError):
        _verified_event(payload, _signed(payload, "whsec_other"), "whsec_test")


def test_no_stripe_call_in_the_module_skips_the_conversion():
    import inspect
    src = inspect.getsource(stripe_connect)
    assert src.count("await asyncio.to_thread(") == 1  # only inside _call
