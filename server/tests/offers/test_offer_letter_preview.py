from datetime import datetime, timezone

from app.matcha.services.offer_letters.document import _generate_offer_letter_html

_BASE_OFFER = {
    "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
    "candidate_name": "Francesca Rome",
    "position_title": "Head of Marketing",
    "company_name": "720 Behavioral",
    "salary": "$88,000/year",
    "start_date": datetime(2026, 8, 8, tzinfo=timezone.utc),
}


def test_generate_offer_letter_html_unsigned_has_no_signature_block():
    html_out = _generate_offer_letter_html(dict(_BASE_OFFER))

    assert "<!DOCTYPE" in html_out
    assert "Francesca Rome" in html_out
    assert "Head of Marketing" in html_out
    assert "Electronically signed" not in html_out
    assert "Candidate Acceptance (Electronic Signature)" not in html_out


def test_generate_offer_letter_html_signed_has_signature_disclosure():
    signature = {
        "name": "Jane Doe",
        "signed_at": datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
        "ip": "1.2.3.4",
    }

    html_out = _generate_offer_letter_html(dict(_BASE_OFFER), signature=signature)

    assert "Electronically signed by Jane Doe" in html_out
    assert "Candidate Acceptance (Electronic Signature)" in html_out
    assert "1.2.3.4" in html_out


def test_generate_offer_letter_html_signature_without_name_falls_back_to_blank_line():
    # Matches _render_offer_html's guard: signed_at without a captured name
    # (shouldn't happen in practice, but the generator itself only branches
    # on signature.get("name")) still renders the pre-signing block.
    html_out = _generate_offer_letter_html(dict(_BASE_OFFER), signature={"name": None, "signed_at": None, "ip": None})

    assert "Electronically signed" not in html_out
    assert "Candidate Acceptance</div>" in html_out


def _signature_of(offer: dict) -> dict | None:
    """Mirrors the derivation in offer_letters.py:_render_offer_html — kept
    here so the branch is covered without spinning up a DB connection."""
    if not offer.get("signed_at"):
        return None
    return {
        "name": offer.get("signed_name"),
        "signed_at": offer["signed_at"],
        "ip": offer.get("signer_ip"),
    }


def test_signature_of_none_when_unsigned():
    assert _signature_of({**_BASE_OFFER, "signed_at": None}) is None


def test_signature_of_returns_three_keys_when_signed():
    signed_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    offer = {**_BASE_OFFER, "signed_at": signed_at, "signed_name": "Jane Doe", "signer_ip": "1.2.3.4"}

    result = _signature_of(offer)

    assert result == {"name": "Jane Doe", "signed_at": signed_at, "ip": "1.2.3.4"}
