from datetime import datetime, timezone

from app.matcha.services.symlink import passcode


def test_generate_code_uses_unambiguous_alphabet():
    for _ in range(50):
        code = passcode.generate_code()
        assert len(code) == passcode.CODE_LENGTH
        assert all(ch in passcode.ALPHABET for ch in code)
        assert not any(ch in code for ch in "0O1I")


def test_normalize_is_case_space_dash_insensitive():
    assert passcode.normalize(" abc-234 ") == "ABC234"
    assert passcode.normalize("a b c 2 3 4") == "ABC234"
    assert passcode.normalize(None) == ""


def test_verify_accepts_normalized_entry_and_rejects_wrong():
    assert passcode.verify("abc-234", "ABC234")
    assert passcode.verify("ABC234", "abc234")
    assert not passcode.verify("ABC235", "ABC234")
    assert not passcode.verify("", "ABC234")
    assert not passcode.verify("ABC234", None)
    assert not passcode.verify(None, "ABC234")


def test_format_code_groups_three_and_three():
    assert passcode.format_code("abc234") == "ABC-234"
    assert passcode.format_code("ABCD") == "ABCD"


def test_next_rotation_lands_on_requested_weekday_strictly_after_now():
    # Wednesday 2026-09-09 12:00 UTC
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    assert now.weekday() == 2
    nxt = passcode.next_rotation(now, weekday=0)  # Monday
    assert nxt.weekday() == 0
    assert nxt > now
    assert (nxt - now).days == 4
    assert nxt.hour == passcode.ROTATION_HOUR_UTC

    # Same weekday, but the rotation hour already passed → a week out.
    same_day = passcode.next_rotation(now, weekday=2)
    assert same_day.weekday() == 2
    assert (same_day - now).days == 6  # 6 days + 18 hours

    # Same weekday, before the rotation hour → today.
    early = datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)
    assert passcode.next_rotation(early, weekday=2).date() == early.date()


def test_next_rotation_treats_naive_as_utc():
    naive = datetime(2026, 9, 9, 12, 0)
    aware = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    assert passcode.next_rotation(naive) == passcode.next_rotation(aware)


def test_due_for_rotation():
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    assert passcode.due_for_rotation(None, now)
    assert passcode.due_for_rotation(datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc), now)
    assert passcode.due_for_rotation(datetime(2026, 9, 9, 6, 0), now)  # naive → UTC
    assert not passcode.due_for_rotation(datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc), now)
