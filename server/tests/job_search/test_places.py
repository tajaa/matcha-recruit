"""Whether a job is in a place the person named: the Census gazetteer, read offline."""
import pytest

from app.matcha.services.matcha_work.job_search import places

SOCAL_NY = {"locations": ["San Diego, CA", "Orange County, CA", "Los Angeles, CA", "San Francisco, CA",
                          "New York, NY"], "remote": "any"}


def keep(location, criteria, remote=None):
    return places.judge(location, remote, criteria)


@pytest.mark.parametrize("location", [
    "Irvine, CA", "Costa Mesa, California", "El Segundo, CA and/or Burbank", "NYC HQ", "Jersey City, NJ",
    "Oakland, CA", "San Jose, CA", "Palo Alto, CA", "Stamford, CT", "Brooklyn, NY", "Hybrid (San Diego, CA)",
    "US-CA-Irvine", "Greater Los Angeles Area", "Seattle, WA; Los Angeles, CA", "Carlsbad, CA 92008",
    "San Francisco Bay Area",
])
def test_kept_near_a_place_they_named(location):
    assert keep(location, SOCAL_NY).keep, location


@pytest.mark.parametrize(("location", "why"), [
    ("Seattle, WA", "mi from"), ("Austin, TX", "mi from"), ("Sacramento, CA", "mi from"),
    ("Toronto, Ontario, Canada", "outside the US"), ("London, United Kingdom", "outside the US"),
    ("", "no location"), ("Somewhere Made Up, ZZ", "location not placed"),
])
def test_dropped_elsewhere(location, why):
    verdict = keep(location, SOCAL_NY)
    assert not verdict.keep and why in verdict.why, (location, verdict)


def test_distance_is_measured_from_the_nearest_place_named():
    assert keep("Costa Mesa, CA", SOCAL_NY).why == "8 mi from Orange County, CA"
    assert not keep("Sacramento, CA", SOCAL_NY).keep  # 75 miles from San Francisco
    assert 45 < places.miles(places.target("San Jose, CA").points[0], places.target("San Francisco, CA").points[0]) < 50


def test_remote_jobs():
    assert keep("Remote", SOCAL_NY).keep
    assert keep("United States", SOCAL_NY, remote=True).keep
    assert not keep("Remote - Canada", SOCAL_NY).keep
    assert not keep("Remote", {**SOCAL_NY, "remote": "onsite_only"}).keep
    # A remote job abroad, for someone who named a place abroad.
    assert keep("Remote - United Kingdom", {"locations": ["London, UK"]}).keep


def test_a_remote_job_open_only_abroad_is_not_kept_for_a_us_search():
    remote_only = {"remote": "remote_only"}
    # Named no place: the search is across the US.
    assert not keep("Remote - Canada", remote_only).keep
    assert not keep("EMEA", remote_only, remote=True).keep
    assert keep("Remote - US or Canada", remote_only).keep
    assert keep("Anywhere", remote_only).keep and keep("Remote (USA)", remote_only).keep
    assert keep("Remote - US or Canada", SOCAL_NY).keep
    # An explicit not-remote (the employer's own field) isn't overruled by the location's words.
    assert not places.is_remote("Remote - US", False) and places.is_remote("Remote - US", None)
    assert not keep("Remote - US", SOCAL_NY, remote=False).keep


def test_no_places_or_only_nationwide_keeps_anything():
    for criteria in ({}, {"locations": []}, {"locations": ["United States", "Remote"]}, {"locations": ["nationwide"]}):
        assert keep("Austin, TX", criteria).keep
    assert places.targets({"locations": ["Remote", "USA", 7, None]}) == []


def test_a_named_state_or_region():
    texas = {"locations": ["Texas"]}
    assert keep("Dallas, TX", texas).keep and keep("Houston", texas).keep
    assert not keep("Denver, CO", texas).keep
    assert keep("Palo Alto, CA", {"locations": ["Bay Area"]}).keep
    assert keep("Boston, MA", {"locations": ["New England"]}).keep
    # New York and Washington alone are the cities, not the states.
    assert not keep("Buffalo, NY", {"locations": ["New York"]}).keep
    assert keep("Arlington, VA", {"locations": ["Washington"]}).keep


def test_a_place_abroad_is_matched_by_name():
    london = {"locations": ["London"]}
    assert keep("London, England", london).keep
    assert not keep("Manchester, UK", london).keep
    assert not keep("London, KY", SOCAL_NY).keep


def test_how_location_text_is_read():
    assert places.named("Hybrid (San Diego, CA)") == [places.Named("san diego", "CA")]
    assert places.named("Remote - United States") == []
    assert places.named("London, United Kingdom") == [places.Named("london", None, abroad=True)]
    assert places.named("Texas") == [places.Named("", "TX")]
    assert places.named("Peru, IN") == [places.Named("peru", "IN")]  # Indiana's, not the country
    assert places.named("US-CA-Irvine") == [places.Named("irvine", "CA")]
    assert [p.name for p in places.named("El Segundo, CA and/or Burbank")] == ["el segundo", "burbank"]
    assert places.place_key("St. Louis") == places.place_key("Saint Louis") == "st louis"
    assert places.place_key("Ft. Worth") == "fort worth"


def test_a_name_without_a_state_is_the_namesake_nearest_their_places():
    la = {"locations": ["Los Angeles, CA"]}
    assert keep("Burbank", la).keep  # Burbank, CA, not Burbank, IL
    assert keep("Burbank", {"locations": ["Chicago, IL"]}).keep
    assert places.target("Springfield").points  # the largest Springfield when nothing anchors it


def test_the_gazetteer_carries_the_names_people_use():
    for name in ("jersey city", "nashville", "honolulu", "boise", "ventura", "orange county"):
        assert places._index().get(name), name
