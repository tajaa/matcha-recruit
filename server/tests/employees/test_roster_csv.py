"""The field rules and line accounting every roster CSV importer shares."""

import pytest

from app.matcha.routes.employees import _shared
from app.matcha.services.employees import roster_csv

COLUMNS = ("name", "address", "city", "state", "zipcode")


def test_bulk_upload_and_the_wizard_normalize_a_work_state_identically():
    # _shared keeps the name its five callers import; the implementation is the
    # service's, so the two importers cannot answer this differently.
    assert _shared._normalize_work_state is roster_csv.normalize_work_state
    assert roster_csv.normalize_work_state("California") == ("CA", True)
    assert roster_csv.normalize_work_state(" ca ") == ("CA", True)
    assert roster_csv.normalize_work_state("") == (None, True)
    assert roster_csv.normalize_work_state("Westeros") == (None, False)


def test_email_rule_is_the_one_bulk_upload_applies():
    assert roster_csv.is_valid_email("jane.doe+tag@example.com")
    assert not roster_csv.is_valid_email("not-an-email")
    assert not roster_csv.is_valid_email("")
    assert not roster_csv.is_valid_email(None)


def test_rows_carry_their_source_line_past_skipped_blanks():
    rows = roster_csv.read_rows("a,b\n\n\nc,d\n")
    assert [(row.values, row.line) for row in rows] == [(["a", "b"], 1), (["c", "d"], 4)]


def test_a_quoted_newline_does_not_shift_later_rows():
    text = 'name,address,city,state,zipcode\nHQ,"1 Main\nSuite 2",Austin,TX,78701\nWest,9 Oak,Austin,TX,78702'
    rows = roster_csv.read_rows(text)
    assert rows[1].values[1] == "1 Main\nSuite 2"
    assert rows[2].line == 4


def test_parse_table_reports_the_real_line_of_an_incomplete_row():
    with pytest.raises(roster_csv.RosterCsvError, match="Row 4 must contain all 5 values"):
        roster_csv.parse_table(
            "name,address,city,state,zipcode\n\n\nHQ,1 Main,,TX,78701", COLUMNS, max_rows=500
        )


def test_parse_table_rejects_a_wrong_header_and_a_header_only_file():
    with pytest.raises(roster_csv.RosterCsvError, match="Expected header: name,address"):
        roster_csv.parse_table("name,address\nHQ,1 Main", COLUMNS, max_rows=500)
    with pytest.raises(roster_csv.RosterCsvError, match="at least one data row"):
        roster_csv.parse_table("name,address,city,state,zipcode\n", COLUMNS, max_rows=500)
    with pytest.raises(roster_csv.RosterCsvError, match="CSV is empty"):
        roster_csv.parse_table("", COLUMNS, max_rows=500)


def test_parse_table_caps_rows():
    body = "\n".join(f"S{i},{i} Main,Austin,TX,78701" for i in range(3))
    with pytest.raises(roster_csv.RosterCsvError, match="more than 2 data rows"):
        roster_csv.parse_table(
            "name,address,city,state,zipcode\n" + body, COLUMNS, max_rows=2
        )


def test_a_byte_order_mark_does_not_break_the_header():
    parsed = roster_csv.parse_table(
        "﻿name,address,city,state,zipcode\nHQ,1 Main,Austin,TX,78701",
        COLUMNS,
        max_rows=500,
    )
    assert parsed[0][0]["name"] == "HQ"


def test_require_unique_names_the_repeating_line():
    with pytest.raises(roster_csv.RosterCsvError, match="Row 7 duplicates"):
        roster_csv.require_unique([("a", 5), ("b", 6), ("a", 7)], "duplicates an earlier row")


# ── Optional trailing columns ────────────────────────────────────────────

ROSTER = ("email", "name")


def test_optional_columns_may_be_absent_blank_or_filled():
    parse = lambda text: roster_csv.parse_table(  # noqa: E731
        text, ROSTER, max_rows=10, optional_columns=("location",)
    )
    assert parse("email,name\na@example.com,A")[0][0] == {
        "email": "a@example.com", "name": "A", "location": "",
    }
    filled = parse("email,name,location\na@example.com,A,Downtown\nb@example.com,B,\nc@example.com,C")
    assert [row["location"] for row, _ in filled] == ["Downtown", "", ""]


def test_optional_columns_do_not_loosen_the_required_ones():
    parse = lambda text: roster_csv.parse_table(  # noqa: E731
        text, ROSTER, max_rows=10, optional_columns=("location",)
    )
    with pytest.raises(roster_csv.RosterCsvError, match="Row 2 must contain all 2 values"):
        parse("email,name,location\na@example.com,,Downtown")
    with pytest.raises(roster_csv.RosterCsvError, match="Row 2 must contain all 2 values"):
        parse("email,name,location\na@example.com,A,Downtown,extra")
    with pytest.raises(roster_csv.RosterCsvError, match=r"Expected header: email,name \(optional: location\)"):
        parse("email,name,store\na@example.com,A,Downtown")
    # A caller that declares none keeps the strict header it always had.
    with pytest.raises(roster_csv.RosterCsvError, match="Expected header: email,name$"):
        roster_csv.parse_table("email,name,location\na@example.com,A,X", ROSTER, max_rows=10)


# ── Upload decoding ──────────────────────────────────────────────────────

def test_an_excel_byte_order_mark_is_dropped_on_decode():
    assert roster_csv.decode_csv_bytes("email,name\n".encode("utf-8-sig")) == "email,name\n"
    assert roster_csv.decode_csv_bytes(b"email,name\n") == "email,name\n"


def test_headers_compare_trimmed_and_lower_case():
    assert roster_csv.normalize_header([" Email ", "First_Name", None]) == ["email", "first_name", ""]
    assert roster_csv.normalize_header(None) == []


# ── Which store does this row work at ────────────────────────────────────

DOWNTOWN = {"id": "downtown-id", "name": "Downtown", "address": "1 Main", "city": "Oakland", "state": "CA"}
MISSION = {"id": "mission-id", "name": "Mission", "address": "9 Oak", "city": "San Francisco", "state": "CA"}
# What a work-state-only employee import leaves behind: a jurisdiction stub.
CA_STUB = {"id": "stub-id", "name": "CA", "address": "", "city": "", "state": "CA"}


def _resolve(stores, name=None, state=None, city=None):
    return roster_csv.StoreDirectory(stores).resolve(
        location_name=name, work_state=state, work_city=city,
    )


def test_a_named_store_matches_regardless_of_case_and_spacing():
    assert _resolve([DOWNTOWN, MISSION], "  mission ") == ("mission-id", True, None)


def test_an_unknown_store_name_says_which_names_exist():
    store_id, covers, error = _resolve([DOWNTOWN, MISSION], "Uptown")
    assert (store_id, covers) == (None, False)
    assert error == "Location 'Uptown' doesn't match any store. Use one of: Downtown, Mission."
    assert _resolve([], "Uptown")[2] == (
        "Location 'Uptown' doesn't match any store. Add the store first, then upload again."
    )


def test_two_stores_sharing_a_name_cannot_be_picked_between():
    twin = {**MISSION, "name": "downtown"}
    assert "More than one store is named 'Downtown'" in _resolve([DOWNTOWN, twin], "Downtown")[2]


def test_no_name_defaults_to_the_only_real_store():
    # The stub is not somewhere a shift can happen, so it does not make the
    # company "multi-store".
    assert _resolve([DOWNTOWN, CA_STUB]) == ("downtown-id", True, None)
    assert _resolve([DOWNTOWN, CA_STUB], state="CA", city="oakland") == ("downtown-id", True, None)
    # Two real stores, or none: no honest default.
    assert _resolve([DOWNTOWN, MISSION]) == (None, False, None)
    assert _resolve([CA_STUB]) == (None, False, None)


def test_a_row_that_works_elsewhere_is_not_defaulted_to_the_store():
    assert _resolve([DOWNTOWN], state="NV") == (None, False, None)
    assert _resolve([DOWNTOWN], state="CA", city="Fresno") == (None, False, None)


def test_a_named_store_elsewhere_still_derives_its_own_compliance_location():
    # The manager said this person is on Downtown's roster but works in Nevada:
    # keep the assignment, and report that the store does not cover the place.
    assert _resolve([DOWNTOWN], "Downtown", state="NV") == ("downtown-id", False, None)
